from __future__ import annotations

from optimizer.finance import compute_available_funds, selling_price


def test_selling_price_rules():
    # 涨价 0.3 → 卖出回收 0.1
    assert selling_price(7.3, 7.0) == 7.1
    # 涨价 0.4 → 卖出回收 0.2
    assert selling_price(7.4, 7.0) == 7.2
    # 跌价：直接按 current
    assert selling_price(6.8, 7.0) == 6.8
    # 无涨跌：等于 current
    assert selling_price(5.5, 5.5) == 5.5


def test_compute_available_funds():
    price_now = {1: 7.3, 2: 6.0, 99: 4.5}  # 1、99 为我方；2 为拟买入
    buy_price = {1: 7.0, 99: 4.5}  # 1 涨了 0.3，99 无涨跌
    # 卖 1 和 99，买 2：卖出回收 7.1 + 4.5 = 11.6，买入花费 6.0
    remain = compute_available_funds(
        bank=0.5, out_ids=[1, 99], in_ids=[2], price_now=price_now, buy_price=buy_price
    )
    # 0.5 + 11.6 - 6.0 = 6.1
    assert abs(remain - 6.1) < 1e-9
