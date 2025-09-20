from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


Z_SCORE_CLIP = 2.0


@dataclass(frozen=True)
class BaselineParams:
    # 位置基线（大致贴合常见每轮均分区间），可按需调
    base_by_pos: dict[str, float] | None = None
    spread_by_pos: dict[str, float] | None = None
    min_points: float = 0.0
    max_points: float = 12.0
    min_availability: float = 0.0  # < 该值则硬降为 0（极端不出场）
    availability_power: float = 1.0  # 可调软权重（<1 放大，>1 收缩）
    minutes_for_full_weight: float = 180.0
    minutes_weight_exponent: float = 0.5
    price_tie_weight: float = 0.0

    def __post_init__(self) -> None:
        if self.base_by_pos is None:
            object.__setattr__(self, "base_by_pos", {"GK": 3.4, "DEF": 3.7, "MID": 4.5, "FWD": 4.8})
        if self.spread_by_pos is None:
            # spread 越大，z 分数影响越大
            object.__setattr__(
                self, "spread_by_pos", {"GK": 1.1, "DEF": 1.2, "MID": 1.4, "FWD": 1.4}
            )


def _safe(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _position_scale(df_pos: pd.DataFrame, pos: str, params: BaselineParams) -> pd.Series:
    """
    同位置内将 fdr_adjusted_recent_score 标准化为 z 分数，
    再映射到 expected_points = base + spread * z，最后裁剪到 [min,max]。
    """
    assert params.base_by_pos is not None
    assert params.spread_by_pos is not None
    base = params.base_by_pos.get(pos, 4.0)
    spread = params.spread_by_pos.get(pos, 1.2)

    x = _safe(df_pos["fdr_adjusted_recent_score"]).fillna(0.0)
    # 若全部相同，避免除 0：给一个很小的 std
    mean = float(x.mean())
    std = float(x.std(ddof=0)) or 1e-6
    z = (x - mean) / std
    z = np.clip(z, -Z_SCORE_CLIP, Z_SCORE_CLIP)

    exp_points = base + spread * z
    exp_points = exp_points.clip(params.min_points, params.max_points)

    # 可选：按可用性做软/硬门槛
    avail = _safe(
        df_pos.get("availability_score", pd.Series(index=df_pos.index, dtype=float))
    ).fillna(0.5)
    exp_points = np.where(
        avail < params.min_availability, 0.0, exp_points * (avail**params.availability_power)
    )

    # 低分钟球员做软折扣，避免单轮爆点占据榜首
    minutes = _safe(df_pos.get("minutes", pd.Series(index=df_pos.index, dtype=float))).fillna(0.0)
    minutes_for_full = max(params.minutes_for_full_weight, 1e-6)
    minutes_factor = np.power(
        np.clip(minutes / minutes_for_full, 0.0, 1.0), params.minutes_weight_exponent
    )
    exp_points = exp_points * minutes_factor

    if params.price_tie_weight != 0.0:
        price = _safe(df_pos.get("price_now", pd.Series(index=df_pos.index, dtype=float)))
        price_mean = float(price.mean()) if not price.isna().all() else 0.0
        price_std = float(price.std(ddof=0)) or 1.0
        price_scaled = (price.fillna(price_mean) - price_mean) / price_std
        exp_points = exp_points + params.price_tie_weight * price_scaled

    return pd.Series(exp_points, index=df_pos.index)


def predict_from_features(
    features_path: Path,
    out_path: Path | None = None,
    params: BaselineParams | None = None,
) -> pd.DataFrame:
    """
    将 M2 特征转为 M3 期望分。返回排序后的 DataFrame；如给出 out_path 则同时落盘（parquet）。
    """
    params = params or BaselineParams()
    feats = pd.read_parquet(features_path)

    # 只保留必要列（缺失则补 NA）
    need = [
        "player_id",
        "web_name",
        "team_id",
        "team_short",
        "position",
        "price_now",
        "selected_by_pct",
        "fdr_adjusted_recent_score",
        "availability_score",
        "minutes",
    ]
    for c in need:
        if c not in feats.columns:
            feats[c] = np.nan
    df = feats[need].copy()

    # 分位置拟合
    parts = []
    for pos in ["GK", "DEF", "MID", "FWD"]:
        sub = df[df["position"] == pos].copy()
        if len(sub) == 0:
            continue
        sub["expected_points"] = _position_scale(sub, pos, params)
        parts.append(sub)
    out = pd.concat(parts, axis=0, ignore_index=True)

    # 排名（同位置+全局）
    out["rank_pos"] = (
        out.groupby("position")["expected_points"].rank(ascending=False, method="min").astype(int)
    )
    out["rank_overall"] = out["expected_points"].rank(ascending=False, method="min").astype(int)

    # 便于优化器使用的几个排序键
    out = out.sort_values(["expected_points"], ascending=False).reset_index(drop=True)

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(out_path, index=False)

    return out
