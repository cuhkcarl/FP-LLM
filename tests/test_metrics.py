from __future__ import annotations

from pathlib import Path

import pandas as pd

from metrics.evaluate import MetricParams, compute_metrics, write_metrics_json


def test_compute_metrics_basic(tmp_path: Path):
    # toy predictions and actuals
    preds = pd.DataFrame(
        {
            "player_id": [1, 2, 3, 4, 5],
            "position": ["MID", "MID", "DEF", "GK", "FWD"],
            "expected_points": [5.0, 4.0, 3.0, 2.0, 6.0],
        }
    )
    actuals = pd.DataFrame({"player_id": [1, 2, 3, 4, 5], "total_points": [6, 3, 3, 1, 7]})
    m = compute_metrics(preds, actuals, MetricParams(k_for_ndcg=3))
    assert set(m.keys()) == {"overall", "by_pos"}
    assert m["overall"]["mae"] >= 0
    assert 0.0 <= m["overall"]["ndcg_at_11"] <= 1.0


def test_write_metrics_json(tmp_path: Path):
    preds = pd.DataFrame(
        {
            "player_id": [1, 2, 3],
            "position": ["MID", "DEF", "FWD"],
            "expected_points": [5.0, 4.0, 3.0],
        }
    )
    actuals = pd.DataFrame({"player_id": [1, 2, 3], "total_points": [6, 3, 2]})
    out = tmp_path / "reports" / "gw01" / "metrics.json"
    payload = write_metrics_json(gw=1, preds=preds, actuals=actuals, out_path=out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert payload["gw"] == 1
