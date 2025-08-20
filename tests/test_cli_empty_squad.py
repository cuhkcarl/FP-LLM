from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.optimize_squad import main as optimize_main


def _toy_predictions() -> pd.DataFrame:
    rows = []
    pid = 1
    for pos, n, base_ep in [("GK", 2, 3.5), ("DEF", 5, 4.0), ("MID", 5, 5.0), ("FWD", 3, 5.2)]:
        for _ in range(n):
            rows.append(
                dict(
                    player_id=pid,
                    web_name=f"P{pid}",
                    team_id=1 + (pid % 6),
                    team_short=f"T{1 + (pid % 6)}",
                    position=pos,
                    price_now=4.0 + (pid % 7) * 0.5,
                    expected_points=base_ep,
                    availability_score=0.9,
                )
            )
            pid += 1
    return pd.DataFrame(rows)


def test_cli_skips_when_squad_incomplete(tmp_path: Path, capsys: pytest.CaptureFixture):
    data_dir = tmp_path / "data"
    (data_dir / "processed").mkdir(parents=True, exist_ok=True)
    preds = _toy_predictions()
    preds.to_parquet(data_dir / "processed" / "predictions_gw01.parquet", index=False)

    squad_yaml = tmp_path / "squad.yaml"
    squad_yaml.write_text("squad: []\nbank: 0.0\nfree_transfers: 1\n", encoding="utf-8")

    # 运行 CLI 主函数（直接调用）
    optimize_main(gw=1, data_dir=data_dir, squad_file=squad_yaml)
    out = capsys.readouterr().out
    assert "Initial Squad Missing" in out
