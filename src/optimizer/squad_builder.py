from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pulp


@dataclass(frozen=True)
class BuildParams:
    budget: float = 100.0
    w_ep: float = 1.0
    w_avail: float = 0.5
    w_vpm: float = 0.05


def build_initial_squad(
    pred: pd.DataFrame,
    *,
    params: BuildParams | None = None,
    blacklist_names: list[str] | None = None,
    blacklist_price_min: float | None = None,
    whitelist_names: list[str] | None = None,
) -> dict:
    params = params or BuildParams()
    df = pred.copy()
    df["player_id"] = df["player_id"].astype(int)
    df["team_id"] = df["team_id"].astype(int)
    df["price_now"] = df["price_now"].astype(float)
    whitelist_names_set = set(whitelist_names or [])
    if blacklist_names:
        # 若在白名单中，则不受黑名单姓名过滤
        df = df[~(df["web_name"].isin(blacklist_names) & ~df["web_name"].isin(whitelist_names_set))]
    if blacklist_price_min is not None:
        # 价格过高者若在白名单中，允许保留
        df = df[
            (df["price_now"] < float(blacklist_price_min))
            | df["web_name"].isin(whitelist_names_set)
        ]

    # decision variables
    players = df["player_id"].tolist()
    x = pulp.LpVariable.dicts("y", players, lowBound=0, upBound=1, cat=pulp.LpBinary)

    # objective
    ep = df.set_index("player_id")[
        "expected_points" if "expected_points" in df.columns else "cs_ep"
    ].to_dict()
    avail = (
        df.set_index("player_id")["availability_score"].fillna(0.8).to_dict()
        if "availability_score" in df.columns
        else {pid: 0.8 for pid in players}
    )
    price = df.set_index("player_id")["price_now"].to_dict()
    vpm = {pid: (ep.get(pid, 0.0) / (price.get(pid, 1e-6))) for pid in players}
    prob = pulp.LpProblem("cold_start_squad", pulp.LpMaximize)
    prob += pulp.lpSum(
        x[i]
        * (
            params.w_ep * ep.get(i, 0.0)
            + params.w_avail * avail.get(i, 0.8)
            + params.w_vpm * vpm.get(i, 0.0)
        )
        for i in players
    )

    # constraints
    pos_map = df.set_index("player_id")["position"].to_dict()
    # 强制：白名单球员必须被选择（若存在）
    if whitelist_names:
        name_map = df.set_index("player_id")["web_name"].to_dict()
        whitelist_set = set(whitelist_names)
        for pid in players:
            if name_map.get(pid) in whitelist_set:
                prob += x[pid] == 1
    prob += pulp.lpSum(x[i] for i in players) == 15
    # position counts
    prob += pulp.lpSum(x[i] for i in players if pos_map[i] == "GK") == 2
    prob += pulp.lpSum(x[i] for i in players if pos_map[i] == "DEF") == 5
    prob += pulp.lpSum(x[i] for i in players if pos_map[i] == "MID") == 5
    prob += pulp.lpSum(x[i] for i in players if pos_map[i] == "FWD") == 3
    # team limit (<=3)
    team_map = df.set_index("player_id")["team_id"].to_dict()
    for tid in df["team_id"].unique().tolist():
        prob += pulp.lpSum(x[i] for i in players if team_map[i] == int(tid)) <= 3
    # budget
    prob += pulp.lpSum(x[i] * price[i] for i in players) <= params.budget

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError("initial squad ILP not optimal")

    selected = [pid for pid in players if pulp.value(x[pid]) > 0.5]
    cost = float(sum(price[i] for i in selected))
    return {
        "player_ids": selected,
        "cost": cost,
        "bank": float(params.budget - cost),
    }
