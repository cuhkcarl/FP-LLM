from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DGWParams:
    alpha_per_extra_match: float = 0.65  # 每多一场的增益系数（2 场时乘以 1+0.65）
    availability_floor: float = 0.50  # 低于该可用性视为“风险高”
    availability_penalty: float = 0.80  # 高风险时的折扣（乘以 0.8）


def _team_matches_in_gw(fixtures: pd.DataFrame, gw: int, team_id: int) -> int:
    if "event" not in fixtures.columns:
        return 1
    f = fixtures[
        (fixtures["event"] == gw)
        & ((fixtures["team_h"] == team_id) | (fixtures["team_a"] == team_id))
    ]
    return max(1, int(len(f)))


def adjust_expected_points_for_gw(
    preds: pd.DataFrame,
    fixtures: pd.DataFrame | None,
    gw: int,
    params: DGWParams | None = None,
) -> pd.DataFrame:
    """
    返回一个副本，新增/覆盖列 `expected_points` 为调整后的值。
    规则：
    - 若该队在本 GW 有多于 1 场：EP *= (1 + alpha * (matches-1))
    - 若 availability_score < floor：额外乘以 penalty
    """
    if fixtures is None:
        return preds.copy()

    params = params or DGWParams()
    df = preds.copy()
    df["team_id"] = df["team_id"].astype(int)

    # 统计各队本轮场次
    team_ids = df["team_id"].unique().tolist()
    match_count = {int(tid): _team_matches_in_gw(fixtures, gw, int(tid)) for tid in team_ids}

    def _scale_row(r: pd.Series) -> float:
        ep = float(r["expected_points"])
        m = match_count.get(int(r["team_id"]), 1)
        if m > 1:
            ep *= 1.0 + params.alpha_per_extra_match * (m - 1)
        av = float(r.get("availability_score", 1.0))
        if av < params.availability_floor:
            ep *= params.availability_penalty
        return ep

    df["expected_points"] = df.apply(_scale_row, axis=1)
    return df
