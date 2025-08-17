from __future__ import annotations

from pathlib import Path

import pandas as pd

from prediction.baseline import predict_from_features


def test_predict_from_features(tmp_path: Path):
    # 构造一个极小的 features 表
    df = pd.DataFrame(
        [
            {
                "player_id": 1,
                "web_name": "A",
                "team_id": 1,
                "team_short": "AAA",
                "position": "MID",
                "price_now": 7.0,
                "selected_by_pct": 10.0,
                "fdr_adjusted_recent_score": 6.0,
                "availability_score": 0.9,
            },
            {
                "player_id": 2,
                "web_name": "B",
                "team_id": 1,
                "team_short": "AAA",
                "position": "MID",
                "price_now": 6.5,
                "selected_by_pct": 5.0,
                "fdr_adjusted_recent_score": 4.0,
                "availability_score": 0.8,
            },
            {
                "player_id": 3,
                "web_name": "C",
                "team_id": 2,
                "team_short": "BBB",
                "position": "FWD",
                "price_now": 8.0,
                "selected_by_pct": 12.0,
                "fdr_adjusted_recent_score": 5.0,
                "availability_score": 0.6,
            },
        ]
    )
    fpath = tmp_path / "features.parquet"
    df.to_parquet(fpath, index=False)

    out = predict_from_features(fpath)
    assert {"expected_points", "rank_pos", "rank_overall"}.issubset(out.columns)
    # 排名与非负
    assert (out["expected_points"] >= 0).all()
    assert out["rank_overall"].min() == 1
