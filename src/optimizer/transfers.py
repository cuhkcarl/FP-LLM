from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import pandas as pd
import yaml

from optimizer.ilp import solve_starting_xi


@dataclass
class Squad:
    player_ids: list[int]
    bank: float
    free_transfers: int


def load_squad_yaml(path: str | bytes | Path) -> Squad:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    squad_ids = [int(x) for x in data.get("squad", [])]
    bank = float(data.get("bank", 0.0))
    ft = int(data.get("free_transfers", 1))
    return Squad(player_ids=squad_ids, bank=bank, free_transfers=ft)


def _validate_squad_positions(squad_pred: pd.DataFrame) -> None:
    counts = squad_pred["position"].value_counts().to_dict()
    need = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
    for pos, n in need.items():
        if counts.get(pos, 0) != n:
            raise ValueError(f"Squad position counts invalid: {counts} (need {need})")


def _team_limit_ok(player_team_ids: Iterable[int]) -> bool:
    # 每队≤3
    s = pd.Series(list(player_team_ids)).value_counts()
    return (s <= 3).all()


def _budget_ok(current_value: float, bank: float, prices_out: float, prices_in: float) -> bool:
    # 用 price_now 近似总价值；新阵容价值 <= current_value + bank
    return (current_value - prices_out + prices_in) <= (current_value + bank + 1e-9)


def _squad_value(pred_all: pd.DataFrame, squad_ids: list[int]) -> float:
    price = pred_all.set_index("player_id")["price_now"]
    return float(price.loc[squad_ids].sum())


def _select_candidates(
    pred_all: pd.DataFrame,
    *,
    exclude_ids: set[int],
    position: str,
    pool_size: int,
    blacklist_names: list[str] | None = None,
    blacklist_price_min: float | None = None,
) -> pd.DataFrame:
    df = pred_all[pred_all["position"] == position].copy()
    if blacklist_names:
        df = df[~df["web_name"].isin(blacklist_names)]
    if blacklist_price_min is not None:
        df = df[df["price_now"] < float(blacklist_price_min)]
    df = df[~df["player_id"].isin(exclude_ids)]
    df = df.sort_values("expected_points", ascending=False).head(pool_size)
    return df


def evaluate_squad_points(pred_all: pd.DataFrame, squad_ids: list[int]) -> float:
    squad_pred = pred_all[pred_all["player_id"].isin(squad_ids)].copy()
    _validate_squad_positions(squad_pred)
    res = solve_starting_xi(squad_pred)
    return float(res["expected_points_xi_with_captain"])


def best_transfers(
    pred_all: pd.DataFrame,
    squad: Squad,
    *,
    pool_size: int = 12,
    max_transfers: int = 2,
    hit_cost: int = 4,
    blacklist_names: list[str] | None = None,
    blacklist_price_min: float | None = None,
) -> dict:
    """
    在 0/1/2 次转会内搜索最优方案。
    - 预算：用 price_now 近似；总价值≤当前价值+bank
    - 每队≤3；阵容位置配额固定（2GK/5DEF/5MID/3FWD）
    - 返回：baseline / best_plan（out_ids/in_ids/new_points/net_gain）
    """
    pred_all = pred_all.copy()
    pred_all["player_id"] = pred_all["player_id"].astype(int)
    pred_all["team_id"] = pred_all["team_id"].astype(int)

    current_ids = [int(x) for x in squad.player_ids]
    current_value = _squad_value(pred_all, current_ids)
    baseline_points = evaluate_squad_points(pred_all, current_ids)

    price_map = pred_all.set_index("player_id")["price_now"].to_dict()
    team_map = pred_all.set_index("player_id")["team_id"].to_dict()
    pos_map = pred_all.set_index("player_id")["position"].to_dict()

    best = {
        "transfers": 0,
        "out_ids": [],
        "in_ids": [],
        "new_points": baseline_points,
        "net_gain": 0.0,
        "hit_cost": 0,
        "new_squad_ids": current_ids,
    }

    def _make_new_ids(out_ids: list[int], in_ids: list[int]) -> list[int] | None:
        new_ids = current_ids.copy()
        # 替换：按 out_id 逐个 replace
        for o, n in zip(out_ids, in_ids, strict=True):
            idx = new_ids.index(o)
            new_ids[idx] = n
        # 约束：每队≤3
        if not _team_limit_ok([team_map[i] for i in new_ids]):
            return None
        # 预算：用 price_now 近似
        if not _budget_ok(
            current_value,
            squad.bank,
            sum(price_map[i] for i in out_ids),
            sum(price_map[i] for i in in_ids),
        ):
            return None
        # 位置配额
        pos_counts = pd.Series([pos_map[i] for i in new_ids]).value_counts().to_dict()
        if not (
            pos_counts.get("GK", 0) == 2
            and pos_counts.get("DEF", 0) == 5
            and pos_counts.get("MID", 0) == 5
            and pos_counts.get("FWD", 0) == 3
        ):
            return None
        return new_ids

    # 0 transfers：baseline
    plans = [([], [])]

    # 1 transfer：枚举每个 out，用同位置候选 pool 替换
    if max_transfers >= 1:
        for o in current_ids:
            pos = pos_map[o]
            cands = _select_candidates(
                pred_all,
                exclude_ids=set(current_ids),
                position=pos,
                pool_size=pool_size,
                blacklist_names=blacklist_names,
                blacklist_price_min=blacklist_price_min,
            )
            for n in cands["player_id"].tolist():
                plans.append(([o], [n]))

    # 2 transfers：枚举对数 + 同位置候选 pool 直积（剪枝靠预算/队数）
    if max_transfers >= 2:
        for o1, o2 in combinations(current_ids, 2):
            pos1, pos2 = pos_map[o1], pos_map[o2]
            pool1 = _select_candidates(
                pred_all,
                exclude_ids=set(current_ids),
                position=pos1,
                pool_size=pool_size,
                blacklist_names=blacklist_names,
                blacklist_price_min=blacklist_price_min,
            )["player_id"].tolist()
            pool2 = _select_candidates(
                pred_all,
                exclude_ids=set(current_ids),
                position=pos2,
                pool_size=pool_size,
                blacklist_names=blacklist_names,
                blacklist_price_min=blacklist_price_min,
            )["player_id"].tolist()
            for n1 in pool1:
                for n2 in pool2:
                    if n1 == n2:
                        continue
                    plans.append(([o1, o2], [n1, n2]))

    # 评估所有 plan
    for out_ids, in_ids in plans:
        new_ids = _make_new_ids(out_ids, in_ids)
        if new_ids is None:
            continue
        new_points = evaluate_squad_points(pred_all, new_ids)
        transfers_cnt = len(out_ids)
        paid_hits = max(0, transfers_cnt - squad.free_transfers)
        cost = paid_hits * hit_cost
        net_gain = new_points - baseline_points - cost
        if net_gain > best["net_gain"] + 1e-9:
            best = {
                "transfers": transfers_cnt,
                "out_ids": out_ids,
                "in_ids": in_ids,
                "new_points": new_points,
                "net_gain": float(net_gain),
                "hit_cost": cost,
                "new_squad_ids": new_ids,
            }

    return {
        "baseline_points": baseline_points,
        "best_plan": best,
    }
