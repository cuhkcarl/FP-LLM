from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pulp


@dataclass(frozen=True)
class FormationBounds:
    gk_exact: int = 1
    def_min: int = 3
    def_max: int = 5
    mid_min: int = 2
    mid_max: int = 5
    fwd_min: int = 1
    fwd_max: int = 3
    total_xi: int = 11


@dataclass(frozen=True)
class BenchOrderParams:
    weight_ep: float = 1.0
    weight_availability: float = 0.5  # 放大“更可能出场”的替补
    gk_last: bool = True


def _bench_order(df_bench: pd.DataFrame, params: BenchOrderParams) -> list[int]:
    tmp = df_bench.copy()
    if "availability_score" not in tmp.columns:
        tmp["availability_score"] = 1.0
    tmp["bench_score"] = (
        params.weight_ep * tmp["expected_points"]
        + params.weight_availability * tmp["availability_score"]
    )
    # 外场优先，按 bench_score 从高到低；GK 固定最后
    outfield = tmp[tmp["position"] != "GK"].sort_values(
        ["bench_score", "expected_points"], ascending=False
    )
    gk = tmp[tmp["position"] == "GK"].sort_values("expected_points", ascending=True)
    order = outfield["player_id"].tolist()
    if params.gk_last:
        order += gk["player_id"].tolist()
    else:
        # 如果不强制 GK 最后，则把 GK 插入 bench_score 序列
        order = tmp.sort_values(["bench_score", "expected_points"], ascending=False)[
            "player_id"
        ].tolist()
    return order


def solve_starting_xi(
    squad_pred: pd.DataFrame,
    *,
    formation: FormationBounds | None = None,
    bench_params: BenchOrderParams | None = None,
) -> dict:
    """
    给定 15 人阵容的预测表（含 expected_points / position），求最优首发 + 队长。
    返回：starting_ids, captain_id, vice_id, bench_ids(有序), formation_used, expected_points_xi_with_captain
    """
    df = squad_pred.copy()
    required_cols = {"player_id", "position", "expected_points"}
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"solve_starting_xi: missing column '{c}'")
    formation = formation or FormationBounds()
    bench_params = bench_params or BenchOrderParams()

    players = df["player_id"].astype(int).tolist()
    ep = {int(r.player_id): float(r.expected_points) for r in df.itertuples()}

    x = pulp.LpVariable.dicts("x", players, lowBound=0, upBound=1, cat=pulp.LpBinary)
    c = pulp.LpVariable.dicts("c", players, lowBound=0, upBound=1, cat=pulp.LpBinary)

    prob = pulp.LpProblem("fpl_starting_xi", pulp.LpMaximize)
    prob += pulp.lpSum(x[i] * ep[i] for i in players) + pulp.lpSum(c[i] * ep[i] for i in players)

    pos_map = df.set_index("player_id")["position"].to_dict()

    prob += pulp.lpSum(x[i] for i in players if pos_map[i] == "GK") == formation.gk_exact
    for p, (lo, hi) in {
        "DEF": (formation.def_min, formation.def_max),
        "MID": (formation.mid_min, formation.mid_max),
        "FWD": (formation.fwd_min, formation.fwd_max),
    }.items():
        prob += pulp.lpSum(x[i] for i in players if pos_map[i] == p) >= lo
        prob += pulp.lpSum(x[i] for i in players if pos_map[i] == p) <= hi
    prob += pulp.lpSum(x[i] for i in players) == formation.total_xi

    for i in players:
        prob += c[i] <= x[i]
    prob += pulp.lpSum(c[i] for i in players) == 1

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"ILP not optimal: {pulp.LpStatus[prob.status]}")

    df["x"] = df["player_id"].map(lambda i: int(pulp.value(x[int(i)]) > 0.5))
    df["c"] = df["player_id"].map(lambda i: int(pulp.value(c[int(i)]) > 0.5))

    starting = df[df["x"] == 1].copy().sort_values("expected_points", ascending=False)
    bench = df[df["x"] == 0].copy()

    # 队长/副队
    if starting.empty:
        raise RuntimeError("no starting XI selected")
    captain_row = starting[starting["c"] == 1]
    if captain_row.empty:
        captain_row = starting.iloc[[0]]
    captain_id = int(captain_row.iloc[0]["player_id"])
    vice_candidates = starting[starting["player_id"] != captain_id]
    vice_id = int(vice_candidates.iloc[0]["player_id"]) if not vice_candidates.empty else captain_id

    # 替补排序（启发式）
    bench_order = _bench_order(bench, params=bench_params)

    def_cnt = int(starting[starting["position"] == "DEF"].shape[0])
    mid_cnt = int(starting[starting["position"] == "MID"].shape[0])
    fwd_cnt = int(starting[starting["position"] == "FWD"].shape[0])
    formation_used = f"1-{def_cnt}-{mid_cnt}-{fwd_cnt}"

    return {
        "starting_ids": starting["player_id"].tolist(),
        "captain_id": captain_id,
        "vice_id": vice_id,
        "bench_ids": bench_order,
        "formation": formation_used,
        "expected_points_xi_with_captain": float(
            starting["expected_points"].sum()
            + starting[starting["player_id"] == captain_id]["expected_points"].iloc[0]
        ),
    }
