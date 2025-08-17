from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
import typer

from fpl_data.loaders import build_all
from fpl_data.transforms import run_clean

app = typer.Typer(add_completion=False)


# ---- 可调系数（也可后续移到 configs/base.yaml） ----
ALPHA_BY_POS: dict[str, float] = {"GK": 0.10, "DEF": 0.10, "MID": 0.08, "FWD": 0.06}  # FDR 惩罚强度
BETA_HOME_BY_POS: dict[str, float] = {"GK": 0.02, "DEF": 0.03, "MID": 0.03, "FWD": 0.04}  # 主场奖励
STATUS_WEIGHT = {"a": 1.0, "d": 0.6, "i": 0.2, "s": 0.0}  # available/doubtful/injured/suspended


def _ensure_dir(p: Path) -> None:
    Path(p).mkdir(parents=True, exist_ok=True)


def _team_upcoming_features(
    fixtures_clean: pd.DataFrame,
    *,
    team_id: int,
    k: int,
    gw: int | None,
    now_ts: pd.Timestamp,
) -> tuple[float, float, float]:
    """
    计算球队未来 K 场赛程特征：
      - upcoming_mean_fdr: 均值（己方视角）
      - upcoming_home_ratio: 主场占比
      - days_to_next: 距离最近一场的天数（<0 表示已开赛；通常过滤后应 >=0）
    """
    df = fixtures_clean.copy()

    # 过滤未来赛程：优先使用 gw；否则用时间
    if gw is not None and "event" in df.columns:
        df = df[(df["event"].notna()) & (df["event"] >= gw) & (~df["finished"].fillna(False))]
    else:
        df = df[(df["kickoff_time"].notna()) & (df["kickoff_time"] >= now_ts)]

    # 与 team 关联
    m_team = (df["team_h"] == team_id) | (df["team_a"] == team_id)
    df = df[m_team].copy()
    if df.empty:
        return (np.nan, np.nan, np.nan)

    # 己方视角的 FDR & 主客
    is_home = (df["team_h"] == team_id).astype(float)
    own_fdr = np.where(is_home == 1.0, df["home_fdr"], df["away_fdr"]).astype(float)

    # 排序并截取前 K 场
    # 优先按 event，其次 kickoff_time
    sort_keys = []
    if "event" in df.columns:
        sort_keys.append("event")
    if "kickoff_time" in df.columns:
        sort_keys.append("kickoff_time")
    df = df.sort_values(sort_keys).head(k)

    # 统计
    mean_fdr = float(np.nanmean(own_fdr)) if len(own_fdr) else np.nan
    home_ratio = float(np.nanmean(is_home)) if len(is_home) else np.nan
    if "kickoff_time" in df.columns and not df["kickoff_time"].isna().all():
        days_to_next = float((df["kickoff_time"].iloc[0] - now_ts).total_seconds() / 86400.0)
    else:
        days_to_next = np.nan

    return (mean_fdr, home_ratio, days_to_next)


def _availability_score(row: pd.Series) -> tuple[float, bool]:
    """
    0-1 的出场稳定性分数 + likely_starter bool
    组合：status 权重 与 chance_of_playing_next_round（0-100），各占 50%
    """
    status = (row.get("status") or "").strip().lower()
    sw = STATUS_WEIGHT.get(status, 0.5)
    chance = row.get("chance_of_playing_next_round")
    try:
        cp = float(chance) / 100.0 if pd.notna(chance) else 0.5
    except Exception:
        cp = 0.5

    score = max(0.0, min(1.0, 0.5 * sw + 0.5 * cp))
    likely = bool(score >= 0.70)
    return score, likely


def _base_recent_score(row: pd.Series) -> float:
    """
    最近表现的一个可解释代理：
      base = 0.7 * form + 0.3 * points_per90
    说明：
      - form：FPL 提供的近况指标（字符串数字），我们已在清洗时转 float
      - points_per90：total_points / max(1, minutes/90)
    """
    form = row.get("form")
    try:
        form_val = float(form) if pd.notna(form) else 0.0
    except Exception:
        form_val = 0.0

    minutes = float(row.get("minutes") or 0.0)
    tp = float(row.get("total_points") or 0.0)
    denom_matches = max(1.0, minutes / 90.0)
    pp90 = tp / denom_matches

    return 0.7 * form_val + 0.3 * pp90


def _apply_fdr_home_adjustment(base: float, pos: str, mean_fdr: float, home_ratio: float) -> float:
    """
    FDR 惩罚 + 主场奖励：
      adj = base * (1 - α_pos * (mean_fdr - 3)/2) * (1 + β_pos * home_ratio)
      - FDR 以 1..5 计，3 为中性；>3 惩罚，<3 奖励
      - home_ratio ∈ [0,1]，根据位置给予主场奖励
    """
    if not pd.notna(base):
        return np.nan
    alpha = ALPHA_BY_POS.get(pos, 0.08)
    beta = BETA_HOME_BY_POS.get(pos, 0.03)

    fdr_term = 1.0
    if pd.notna(mean_fdr):
        fdr_term = 1.0 - alpha * ((float(mean_fdr) - 3.0) / 2.0)
    home_term = 1.0 + beta * float(home_ratio) if pd.notna(home_ratio) else 1.0

    return max(0.0, base * fdr_term * home_term)


@app.command()
def main(
    raw_dir: Annotated[Path, typer.Option(help="原始 JSON 目录")] = Path("data/raw/fpl"),
    interim_dir: Annotated[Path, typer.Option(help="中间 parquet 目录")] = Path("data/interim"),
    out_dir: Annotated[Path, typer.Option(help="特征输出目录")] = Path("data/processed"),
    gw: Annotated[
        int | None, typer.Option(help="当前 Gameweek（用于选择未来赛程）；不填则按时间")
    ] = None,
    k: Annotated[int, typer.Option(help="未来 K 场用于 FDR/主客统计")] = 3,
):
    """
    M2：基于 players_clean / fixtures_clean 生成可用于 M3 的统一特征表：
      - recent_score_wma（代理）
      - upcoming_mean_fdr / upcoming_home_ratio / days_to_next
      - availability_score / likely_starter
      - fdr_adjusted_recent_score
      - 基础画像：price_now / selected_by_pct / position / team_short ...
    """
    from datetime import datetime

    _ensure_dir(out_dir)
    build_all(raw_dir, interim_dir)
    run_clean(interim_dir, interim_dir)

    players = pd.read_parquet(interim_dir / "players_clean.parquet")
    fixtures = pd.read_parquet(interim_dir / "fixtures_clean.parquet")
    now_ts = pd.Timestamp(datetime.now(UTC))

    # 2) 计算球队层面的未来赛程特征，并 merge 回球员
    uniq_team_ids = players["team_id"].dropna().unique().tolist()
    recs = []
    for tid in uniq_team_ids:
        mean_fdr, home_ratio, days_to_next = _team_upcoming_features(
            fixtures, team_id=int(tid), k=k, gw=gw, now_ts=now_ts
        )
        recs.append(
            {
                "team_id": int(tid),
                "upcoming_mean_fdr": mean_fdr,
                "upcoming_home_ratio": home_ratio,
                "days_to_next": days_to_next,
            }
        )
    team_upcoming = pd.DataFrame.from_records(recs)

    df = players.merge(team_upcoming, on="team_id", how="left")

    # 3) 出场稳定性分数
    avail = df.apply(_availability_score, axis=1, result_type="expand")
    df["availability_score"] = avail[0]
    df["likely_starter"] = avail[1].astype(bool)

    # 4) 最近表现代理分（form + points/90）
    df["recent_score_wma"] = df.apply(_base_recent_score, axis=1)

    # 5) FDR/主场 修正
    df["fdr_adjusted_recent_score"] = df.apply(
        lambda r: _apply_fdr_home_adjustment(
            r["recent_score_wma"], r["position"], r["upcoming_mean_fdr"], r["upcoming_home_ratio"]
        ),
        axis=1,
    )

    # 6) 基础画像保留 & 重命名
    keep_cols = [
        # keys
        "id",
        "web_name",
        "team_id",
        "team_name",
        "team_short",
        "position",
        # price & popularity
        "price_now",
        "selected_by_pct",
        # availability
        "status",
        "availability_score",
        "likely_starter",
        # recent & adjusted
        "form",
        "minutes",
        "total_points",
        "recent_score_wma",
        "upcoming_mean_fdr",
        "upcoming_home_ratio",
        "days_to_next",
        "fdr_adjusted_recent_score",
    ]
    for c in keep_cols:
        if c not in df.columns:
            df[c] = np.nan
    features = df[keep_cols].copy()
    features = features.rename(columns={"id": "player_id"})

    # 7) 输出
    _ensure_dir(out_dir)
    out_name = f"features_gw{gw:02d}.parquet" if gw is not None else "features.parquet"
    out_path = out_dir / out_name
    features.to_parquet(out_path, index=False)

    typer.echo(f"✅ wrote {out_path}  (rows={len(features)})")
    # 便于肉眼检查几个关键列
    preview = features[
        [
            "web_name",
            "position",
            "team_short",
            "price_now",
            "recent_score_wma",
            "fdr_adjusted_recent_score",
            "availability_score",
        ]
    ].head(12)
    typer.echo(preview.to_string(index=False))


if __name__ == "__main__":
    app()
