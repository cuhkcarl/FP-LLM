from __future__ import annotations

import pandas as pd

from optimizer.chips import ChipThresholds, suggest_chips


def test_bench_boost_triggers_with_high_bench_ep():
    # 构造 15 人：首发 11 人 EP 较低；替补 4 人 EP 很高，使 bench EP >= 阈值（默认 20）
    rows = []
    pid = 1
    # 11 个首发
    for _ in range(11):
        rows.append(
            dict(
                player_id=pid,
                web_name=f"S{pid}",
                team_id=1 + (pid % 3),
                position="MID",
                expected_points=3.0,
            )
        )
        pid += 1
    # 4 个替补（高 EP）
    bench_ids = []
    for _ in range(4):
        rows.append(
            dict(
                player_id=pid,
                web_name=f"B{pid}",
                team_id=1 + (pid % 3),
                position="DEF",
                expected_points=6.0,  # 4*6=24 >= 20
            )
        )
        bench_ids.append(pid)
        pid += 1

    preds = pd.DataFrame(rows)
    starting_ids = preds[~preds["player_id"].isin(bench_ids)]["player_id"].tolist()
    captain_id = starting_ids[0]

    chips_available = {
        "bench_boost": True,
        "triple_captain": True,
        "free_hit": True,
        "wildcard": True,
    }

    out = suggest_chips(
        gw=1,
        preds=preds,
        fixtures=None,  # 不需要双赛信息，测试 BB 即可
        starting_ids=starting_ids,
        bench_ids=bench_ids,
        captain_id=captain_id,
        chips_available=chips_available,
        thresholds=ChipThresholds(),
    )

    assert out["bench_boost"]["recommended"] is True
    assert out["bench_boost"]["metrics"]["bench_ep"] >= ChipThresholds().bench_boost_min_bench_ep
