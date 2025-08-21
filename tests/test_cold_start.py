from __future__ import annotations

import pandas as pd

from optimizer.squad_builder import BuildParams, build_initial_squad


def test_build_initial_squad_toy():
    # toy pool: exact 2/5/5/3 per position to satisfy constraints
    rows = []
    pid = 1
    for pos, n, ep in [("GK", 2, 4.0), ("DEF", 5, 4.5), ("MID", 5, 5.5), ("FWD", 3, 5.0)]:
        for _ in range(n):
            rows.append(
                dict(
                    player_id=pid,
                    web_name=f"P{pid}",
                    team_id=1 + (pid % 5),
                    position=pos,
                    price_now=5.0,
                    expected_points=ep,
                    availability_score=0.9,
                )
            )
            pid += 1
    pred = pd.DataFrame(rows)
    res = build_initial_squad(pred, params=BuildParams(budget=100.0))
    ids = res["player_ids"]
    assert len(ids) == 15
    # budget respected
    assert res["cost"] <= 100.0 + 1e-6
