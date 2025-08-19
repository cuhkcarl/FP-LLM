from __future__ import annotations

import math
from collections.abc import Iterable


def selling_price(current: float, buy: float) -> float:
    """
    FPL 卖出价规则（简化且符合官方逻辑）：
    - 若 current <= buy：卖出价 = current（亏损全额计算）
    - 若 current >  buy：卖出价 = buy + floor((current - buy) / 0.2) * 0.1
      （相当于“涨幅的一半，向下取整到 0.1”）
    价格保留一位小数。
    """
    current = round(float(current), 1)
    buy = round(float(buy), 1)
    if current <= buy:
        return current
    rise = current - buy
    steps = math.floor((rise + 1e-9) / 0.2)  # 避免浮点误差
    return round(buy + steps * 0.1, 1)


def compute_available_funds(
    bank: float,
    out_ids: Iterable[int],
    in_ids: Iterable[int],
    price_now: dict[int, float],
    buy_price: dict[int, float],
) -> float:
    """
    计算一次转会计划后的剩余资金：
    bank + sum(sell(out)) - sum(price_now(in))
    其中 sell(out) 用 selling_price(current, buy) 计算；未提供 buy 时回退为 current。
    返回一位小数。
    """
    out_value = 0.0
    for pid in out_ids:
        cur = float(price_now.get(pid, 0.0))
        buy = float(buy_price.get(pid, cur))
        out_value += selling_price(cur, buy)
    in_cost = sum(float(price_now.get(pid, 0.0)) for pid in in_ids)
    remain = round(bank + out_value - in_cost, 1)
    return remain
