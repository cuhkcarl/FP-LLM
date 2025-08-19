from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ChipThresholds:
    bench_boost_min_bench_ep: float = 20.0
    triple_captain_min_ep: float = 9.0
    triple_captain_min_ep_if_double: float = 7.5
    free_hit_min_active_starters: int = 9


def _team_fixture_count(fixtures: pd.DataFrame, gw: int, team_id: int) -> int:
    df = fixtures
    if "event" not in df.columns:
        return 1
    f = df[(df["event"] == gw) & ((df["team_h"] == team_id) | (df["team_a"] == team_id))]
    return int(len(f))


def _likely_starters_count(preds_subset: pd.DataFrame) -> int:
    # 粗略认为 availability_score >= 0.70 视为“很可能出场”
    if "availability_score" not in preds_subset.columns:
        return int(len(preds_subset))
    return int((preds_subset["availability_score"] >= 0.70).sum())


def suggest_chips(
    *,
    gw: int,
    preds: pd.DataFrame,
    fixtures: pd.DataFrame | None,
    starting_ids: list[int],
    bench_ids: list[int],
    captain_id: int,
    chips_available: dict[str, bool],
    thresholds: ChipThresholds | None = None,
) -> dict[str, dict]:
    """
    返回一个 dict：每种筹码的 {recommended: bool, reason: str, metrics: {...}}
    """
    thresholds = thresholds or ChipThresholds()
    preds = preds.copy()
    pidx = preds.set_index("player_id")

    def get_ep(pid: int) -> float:
        return float(pidx.loc[pid, "expected_points"]) if pid in pidx.index else 0.0

    def get_team(pid: int) -> int:
        return int(pidx.loc[pid, "team_id"]) if pid in pidx.index else -1

    # bench boost: 替补四人 EP 总和
    bench_ep = float(sum(get_ep(pid) for pid in bench_ids))
    recommend_bb = False
    bb_reason = "bench EP below threshold"
    if (
        chips_available.get("bench_boost", False)
        and bench_ep >= thresholds.bench_boost_min_bench_ep
    ):
        recommend_bb = True
        bb_reason = f"bench EP {bench_ep:.1f} ≥ {thresholds.bench_boost_min_bench_ep}"

    # triple captain: 队长 EP + 是否双赛程
    cap_ep = get_ep(captain_id)
    cap_team = get_team(captain_id)
    is_double = False
    if fixtures is not None and cap_team != -1:
        is_double = _team_fixture_count(fixtures, gw, cap_team) >= 2
    tc_th = (
        thresholds.triple_captain_min_ep_if_double
        if is_double
        else thresholds.triple_captain_min_ep
    )
    recommend_tc = False
    tc_reason = "captain EP below threshold"
    if chips_available.get("triple_captain", False) and cap_ep >= tc_th:
        recommend_tc = True
        tc_reason = f"captain EP {cap_ep:.1f} ≥ {tc_th:.1f}" + (" (double GW)" if is_double else "")

    # free hit: 活跃首发（含 bench 里可换位的出场人数）
    current_squad = preds[preds["player_id"].isin(starting_ids + bench_ids)]
    active_cnt = _likely_starters_count(current_squad)
    recommend_fh = False
    fh_reason = "enough active starters"
    if (
        chips_available.get("free_hit", False)
        and active_cnt < thresholds.free_hit_min_active_starters
    ):
        recommend_fh = True
        fh_reason = f"only {active_cnt} likely starters < {thresholds.free_hit_min_active_starters}"

    # wildcard：保守不自动建议（需要结构性判断/长期赛程）
    recommend_wc = False
    wc_reason = "not auto-triggered (needs structural check)"

    return {
        "bench_boost": {
            "recommended": recommend_bb,
            "reason": bb_reason,
            "metrics": {"bench_ep": bench_ep},
        },
        "triple_captain": {
            "recommended": recommend_tc,
            "reason": tc_reason,
            "metrics": {"captain_ep": cap_ep, "captain_double": is_double},
        },
        "free_hit": {
            "recommended": recommend_fh,
            "reason": fh_reason,
            "metrics": {"active_likely_starters": active_cnt},
        },
        "wildcard": {
            "recommended": recommend_wc,
            "reason": wc_reason,
            "metrics": {},
        },
    }
