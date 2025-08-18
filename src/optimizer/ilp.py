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


def solve_starting_xi(
    squad_pred: pd.DataFrame,
    *,
    formation: FormationBounds | None = None,
) -> dict:
    """
    给定 15 人阵容的预测表（含 expected_points / position），求最优首发 + 队长。
    线性目标：sum(x_i * ep_i) + sum(c_i * ep_i)，其中 c_i 约束: c_i ≤ x_i, sum c_i = 1。
    返回：starting_ids, captain_id, vice_id, bench_ids(有序), formation_used
    """
    df = squad_pred.copy()
    required_cols = {"player_id", "position", "expected_points"}
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"solve_starting_xi: missing column '{c}'")

    formation = formation or FormationBounds()

    # 变量
    players = df["player_id"].astype(int).tolist()
    ep = {int(r.player_id): float(r.expected_points) for r in df.itertuples()}

    x = pulp.LpVariable.dicts("x", players, lowBound=0, upBound=1, cat=pulp.LpBinary)
    c = pulp.LpVariable.dicts("c", players, lowBound=0, upBound=1, cat=pulp.LpBinary)

    prob = pulp.LpProblem("fpl_starting_xi", pulp.LpMaximize)

    # 目标：首发 + 队长（队长相当于再加一次该球员分）
    prob += pulp.lpSum(x[i] * ep[i] for i in players) + pulp.lpSum(c[i] * ep[i] for i in players)

    # 约束：人数与位置
    pos_map = df.set_index("player_id")["position"].to_dict()

    # GK 恰好 1
    prob += pulp.lpSum(x[i] for i in players if pos_map[i] == "GK") == formation.gk_exact

    # DEF/MID/FWD 范围
    for p, (lo, hi) in {
        "DEF": (formation.def_min, formation.def_max),
        "MID": (formation.mid_min, formation.mid_max),
        "FWD": (formation.fwd_min, formation.fwd_max),
    }.items():
        prob += pulp.lpSum(x[i] for i in players if pos_map[i] == p) >= lo
        prob += pulp.lpSum(x[i] for i in players if pos_map[i] == p) <= hi

    # 首发总人数
    prob += pulp.lpSum(x[i] for i in players) == formation.total_xi

    # 队长：从首发中选 1 人
    for i in players:
        prob += c[i] <= x[i]
    prob += pulp.lpSum(c[i] for i in players) == 1

    # 求解
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"ILP not optimal: {pulp.LpStatus[prob.status]}")

    # 读取解
    df["x"] = df["player_id"].map(lambda i: int(pulp.value(x[int(i)]) > 0.5))
    df["c"] = df["player_id"].map(lambda i: int(pulp.value(c[int(i)]) > 0.5))

    starting = df[df["x"] == 1].copy().sort_values("expected_points", ascending=False)
    bench = df[df["x"] == 0].copy().sort_values("expected_points")  # 替补按 EP 低到高

    # 队长/副队：解中 c==1 的为队长；副队选首发中剩余最高 EP
    if starting.empty:
        raise RuntimeError("no starting XI selected")
    captain_row = starting[starting["c"] == 1]
    if captain_row.empty:
        captain_row = starting.iloc[[0]]
    captain_id = int(captain_row.iloc[0]["player_id"])

    vice_candidates = starting[starting["player_id"] != captain_id]
    vice_id = int(vice_candidates.iloc[0]["player_id"]) if not vice_candidates.empty else captain_id

    # Bench 顺序（GK 通常最后一个）
    bench_outfield = bench[bench["position"] != "GK"]
    bench_gk = bench[bench["position"] == "GK"]
    bench_order = bench_outfield["player_id"].tolist() + bench_gk["player_id"].tolist()

    # 统计阵型
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
