from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import cast

import pandas as pd
import yaml  # type: ignore[import-untyped]

from optimizer.finance import compute_available_funds, selling_price
from optimizer.ilp import solve_starting_xi


@dataclass
class Squad:
    player_ids: list[int]
    bank: float
    free_transfers: int


def load_squad_yaml(path: str | Path) -> Squad:
    text = Path(str(path)).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    squad_ids = [int(x) for x in data.get("squad", [])]
    bank = float(data.get("bank", 0.0))
    ft = int(data.get("free_transfers", 1))
    return Squad(player_ids=squad_ids, bank=bank, free_transfers=ft)


def _progress(msg: str) -> None:
    if os.getenv("FP_PROGRESS"):
        print(f"[progress] {msg}")


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
    whitelist_names: list[str] | None = None,
) -> pd.DataFrame:
    df = pred_all[pred_all["position"] == position].copy()
    whitelist_names_set = set(whitelist_names or [])
    if blacklist_names:
        df = df[~(df["web_name"].isin(blacklist_names) & ~df["web_name"].isin(whitelist_names_set))]
    if blacklist_price_min is not None:
        df = df[
            (df["price_now"] < float(blacklist_price_min))
            | df["web_name"].isin(whitelist_names_set)
        ]
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
    whitelist_names: list[str] | None = None,
    # 资金/队值增强（可选）
    price_now_market: dict[int, float] | None = None,
    purchase_prices: dict[int, float] | None = None,
    value_weight: float = 0.0,
    min_bank_after: float | None = None,
    max_tv_drop: float | None = None,
) -> dict:
    """
    在 0/1/2 次转会内搜索最优方案。
    - 预算：用 price_now 近似；总价值≤当前价值+bank
    - 每队≤3；阵容位置配额固定（2GK/5DEF/5MID/3FWD）
    - 返回：baseline / best_plan（out_ids/in_ids/new_points/net_gain）
    """
    _progress("best_transfers: start")
    pred_all = pred_all.copy()
    pred_all["player_id"] = pred_all["player_id"].astype(int)
    pred_all["team_id"] = pred_all["team_id"].astype(int)

    current_ids = [int(x) for x in squad.player_ids]
    _progress(f"current squad loaded: {len(current_ids)} players; bank={squad.bank}")
    current_value = _squad_value(pred_all, current_ids)
    baseline_points = evaluate_squad_points(pred_all, current_ids)
    _progress(f"baseline XI solved: {baseline_points:.3f} pts (current_value≈{current_value:.1f})")

    price_map = pred_all.set_index("player_id")["price_now"].to_dict()
    team_map = pred_all.set_index("player_id")["team_id"].to_dict()
    pos_map = pred_all.set_index("player_id")["position"].to_dict()

    # --- 资金/队值准备（容错） ---
    market_price = price_now_market or price_map
    buy_price_map = purchase_prices or {}

    def _team_value(
        ids: list[int], bank: float, buy_price_override: dict[int, float] | None = None
    ) -> float:
        # 按 FPL 卖出价规则计算队值：sum(selling_price(market, buy)) + bank
        bpo = buy_price_override or buy_price_map
        total = 0.0
        for pid in ids:
            cur = float(market_price.get(pid, price_map.get(pid, 0.0)))
            buy = float(bpo.get(pid, cur))
            total += selling_price(cur, buy)
        return float(total + float(bank))

    team_value_now = _team_value(current_ids, float(squad.bank))

    best = {
        "transfers": 0,
        "out_ids": [],
        "in_ids": [],
        "new_points": baseline_points,
        "net_gain": 0.0,
        "hit_cost": 0,
        "new_squad_ids": current_ids,
        # 资金/队值附加
        "bank_after": float(squad.bank),
        "team_value_now": float(team_value_now),
        "team_value_after": float(team_value_now),
        "team_value_delta": 0.0,
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
    plans: list[tuple[list[int], list[int]]] = [([], [])]

    # 1 transfer：枚举每个 out，用同位置候选 pool 替换
    if max_transfers >= 1:
        _progress("enumerating 1-transfer plans")
        for o in current_ids:
            pos = pos_map[o]
            cands = _select_candidates(
                pred_all,
                exclude_ids=set(current_ids),
                position=pos,
                pool_size=pool_size,
                blacklist_names=blacklist_names,
                blacklist_price_min=blacklist_price_min,
                whitelist_names=whitelist_names,
            )
            for n in cands["player_id"].tolist():
                plans.append(([o], [n]))

    # 2 transfers：枚举对数 + 同位置候选 pool 直积（剪枝靠预算/队数）
    if max_transfers >= 2:
        _progress("enumerating 2-transfer plans")
        for o1, o2 in combinations(current_ids, 2):
            pos1, pos2 = pos_map[o1], pos_map[o2]
            pool1 = _select_candidates(
                pred_all,
                exclude_ids=set(current_ids),
                position=pos1,
                pool_size=pool_size,
                blacklist_names=blacklist_names,
                blacklist_price_min=blacklist_price_min,
                whitelist_names=whitelist_names,
            )["player_id"].tolist()
            pool2 = _select_candidates(
                pred_all,
                exclude_ids=set(current_ids),
                position=pos2,
                pool_size=pool_size,
                blacklist_names=blacklist_names,
                blacklist_price_min=blacklist_price_min,
                whitelist_names=whitelist_names,
            )["player_id"].tolist()
            for n1 in pool1:
                for n2 in pool2:
                    if n1 == n2:
                        continue
                    plans.append(([o1, o2], [n1, n2]))

    total_plans = len(plans)
    _progress(f"plans prepared: {total_plans} -> evaluating")
    try:
        progress_every = max(1, int(os.getenv("FP_PROGRESS_EVERY", "200")))
    except ValueError:
        progress_every = 200
    # 评估所有 plan
    for idx, (out_ids, in_ids) in enumerate(plans, start=1):
        new_ids = _make_new_ids(out_ids, in_ids)
        if new_ids is None:
            continue
        new_points = evaluate_squad_points(pred_all, new_ids)
        transfers_cnt = len(out_ids)
        paid_hits = max(0, transfers_cnt - squad.free_transfers)
        cost = paid_hits * hit_cost
        net_gain = new_points - baseline_points - cost

        # 资金/队值：计算 bank_after 与 team_value_after
        bank_after = compute_available_funds(
            bank=float(squad.bank),
            out_ids=out_ids,
            in_ids=in_ids,
            price_now=market_price,
            buy_price=buy_price_map,
        )

        # 更新后的买入价字典：保留者沿用旧买入价；新买入者设置为市场价
        buy_after: dict[int, float] = dict(buy_price_map)
        for nid in in_ids:
            buy_after[int(nid)] = float(market_price.get(int(nid), price_map.get(int(nid), 0.0)))

        team_value_after = _team_value(new_ids, bank_after, buy_price_override=buy_after)
        tv_delta = float(team_value_after - team_value_now)

        # 约束（可选）
        if min_bank_after is not None and bank_after < float(min_bank_after) - 1e-9:
            continue
        if (
            max_tv_drop is not None
            and (team_value_now - team_value_after) > float(max_tv_drop) + 1e-9
        ):
            continue

        # 多目标：以净增分为主；value_weight 为 0 时，仅作平手破除
        score_new = float(float(net_gain) + float(value_weight) * float(tv_delta))
        score_best = float(
            float(cast(float, best["net_gain"]))
            + float(value_weight) * float(cast(float, best.get("team_value_delta", 0.0)))
        )

        better = score_new > score_best + 1e-9
        if not better and abs(score_new - score_best) <= 1e-9:
            # 平手：偏好更高的队值
            better = float(tv_delta) > float(cast(float, best.get("team_value_delta", 0.0))) + 1e-9

        if better:
            best = {
                "transfers": transfers_cnt,
                "out_ids": out_ids,
                "in_ids": in_ids,
                "new_points": new_points,
                "net_gain": float(net_gain),
                "hit_cost": cost,
                "new_squad_ids": new_ids,
                "bank_after": float(bank_after),
                "team_value_now": float(team_value_now),
                "team_value_after": float(team_value_after),
                "team_value_delta": float(tv_delta),
            }
        if idx % progress_every == 0:
            _progress(f"evaluated {idx}/{total_plans} plans")

    _progress("best_transfers: done")
    return {
        "baseline_points": baseline_points,
        "best_plan": best,
    }
