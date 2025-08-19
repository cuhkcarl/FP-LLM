from __future__ import annotations

import pandas as pd

from optimizer.dgw import DGWParams, adjust_expected_points_for_gw
from optimizer.ilp import BenchOrderParams, solve_starting_xi


def _toy_preds_for_dgw() -> pd.DataFrame:
    # 4 名同队（team_id=1）的球员 + 1 名队友 GK；另有单赛队的球员
    rows = []
    # 双赛队：team 1
    rows += [
        dict(
            player_id=1,
            web_name="A1",
            team_id=1,
            team_short="T1",
            position="MID",
            price_now=8.0,
            expected_points=6.0,
            availability_score=0.9,
        ),
        dict(
            player_id=2,
            web_name="A2",
            team_id=1,
            team_short="T1",
            position="FWD",
            price_now=7.5,
            expected_points=5.5,
            availability_score=0.9,
        ),
        dict(
            player_id=3,
            web_name="A3",
            team_id=1,
            team_short="T1",
            position="DEF",
            price_now=5.0,
            expected_points=4.0,
            availability_score=0.45,
        ),  # 低可用性
        dict(
            player_id=4,
            web_name="A4",
            team_id=1,
            team_short="T1",
            position="GK",
            price_now=4.5,
            expected_points=3.8,
            availability_score=0.95,
        ),
    ]
    # 单赛队：team 2
    rows += [
        dict(
            player_id=11,
            web_name="B1",
            team_id=2,
            team_short="T2",
            position="MID",
            price_now=6.0,
            expected_points=6.2,
            availability_score=0.9,
        ),
        dict(
            player_id=12,
            web_name="B2",
            team_id=2,
            team_short="T2",
            position="DEF",
            price_now=4.5,
            expected_points=3.1,
            availability_score=0.9,
        ),
    ]
    return pd.DataFrame(rows)


def _toy_fixtures_double_gw(gw: int) -> pd.DataFrame:
    # team 1 在该 GW 踢两场；team 2 一场
    return pd.DataFrame(
        [
            {"event": gw, "team_h": 1, "team_a": 2},
            {"event": gw, "team_h": 3, "team_a": 1},
            {"event": gw, "team_h": 3, "team_a": 4},
        ]
    )


def test_dgw_adjust_scales_up_and_penalizes_low_availability():
    gw = 1
    preds = _toy_preds_for_dgw()
    fixtures = _toy_fixtures_double_gw(gw)
    params = DGWParams(alpha_per_extra_match=0.65, availability_floor=0.5, availability_penalty=0.8)

    adj = adjust_expected_points_for_gw(preds, fixtures, gw, params)

    # team 1（双赛）的 A1/A2 应该被放大
    before = preds.set_index("player_id")["expected_points"]
    after = adj.set_index("player_id")["expected_points"]

    print(before)
    print(after)

    assert after.loc[1] > before.loc[1]  # A1
    assert after.loc[2] > before.loc[2]  # A2

    # 低可用性的 A3：放大后再被惩罚，最终不应高于简单放大值
    simple_scaled = before.loc[3] * (1 + params.alpha_per_extra_match)  # 2 场
    assert after.loc[3] < simple_scaled

    # 单赛队 B1/B2 不应被放大
    assert after.loc[11] == before.loc[11]  # 单赛队 B1
    assert after.loc[12] == before.loc[12]  # 单赛队 B2


def test_bench_order_prefers_outfield_and_availability():
    # 构造一个 15 人阵容：首发 11 由 EP 决定，替补里有 GK 与低可用性外场
    rows = []
    pid = 100
    # 1 GK + 4 DEF + 4 MID + 2 FWD = 11 首发候选
    for pos, n, base_ep in [("GK", 1, 3.5), ("DEF", 4, 4.0), ("MID", 4, 4.5), ("FWD", 2, 5.0)]:
        for _ in range(n):
            rows.append(
                dict(
                    player_id=pid,
                    web_name=f"S{pid}",
                    team_id=5,
                    team_short="S",
                    position=pos,
                    price_now=4.5,
                    expected_points=base_ep + 0.1,
                    availability_score=0.95,
                )
            )
            pid += 1
    # 4 个替补候选：2 外场（一个可用性很低）、2 GK
    bench = [
        dict(
            player_id=pid,
            web_name="BenchOutHigh",
            team_id=6,
            team_short="B",
            position="DEF",
            price_now=4.0,
            expected_points=3.5,
            availability_score=0.9,
        ),
        dict(
            player_id=pid + 1,
            web_name="BenchOutLow",
            team_id=6,
            team_short="B",
            position="MID",
            price_now=4.5,
            expected_points=3.6,
            availability_score=0.2,
        ),
        dict(
            player_id=pid + 2,
            web_name="BenchGK1",
            team_id=6,
            team_short="B",
            position="GK",
            price_now=4.0,
            expected_points=3.4,
            availability_score=0.95,
        ),
        dict(
            player_id=pid + 3,
            web_name="BenchGK2",
            team_id=6,
            team_short="B",
            position="GK",
            price_now=4.0,
            expected_points=3.2,
            availability_score=0.95,
        ),
    ]
    rows.extend(bench)
    df = pd.DataFrame(rows)

    res = solve_starting_xi(
        df, bench_params=BenchOrderParams(weight_ep=1.0, weight_availability=0.8, gk_last=True)
    )
    bench_ids = res["bench_ids"]
    bench_names = df.set_index("player_id").loc[bench_ids, "web_name"].tolist()

    # 断言：外场优先，且低可用性的外场在高可用性外场之后；GK 最后
    assert bench_names[0].startswith("BenchOutHigh")
    assert bench_names[1].startswith("BenchOutLow")
    assert bench_names[-1].startswith("BenchGK")
