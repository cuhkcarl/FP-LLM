from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from fpl_data.loaders import build_all
from fpl_data.transforms import run_clean


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_build_and_clean_pipeline(tmp_path: Path):
    # 准备 raw 文件
    raw_dir = tmp_path / "data" / "raw" / "fpl"
    interim_dir = tmp_path / "data" / "interim"

    bootstrap = json.loads((Path("tests/fixtures/bootstrap-static.sample.json")).read_text("utf-8"))
    fixtures = json.loads((Path("tests/fixtures/fixtures.sample.json")).read_text("utf-8"))

    _write(raw_dir / "bootstrap-static.json", bootstrap)
    _write(raw_dir / "fixtures.json", fixtures)

    # 执行：raw json -> parquet
    build_all(raw_dir, interim_dir)
    assert (interim_dir / "players.parquet").exists()
    assert (interim_dir / "teams.parquet").exists()
    assert (interim_dir / "fixtures.parquet").exists()

    # 清洗：生成 clean parquet
    run_clean(interim_dir, interim_dir)
    p_clean = interim_dir / "players_clean.parquet"
    f_clean = interim_dir / "fixtures_clean.parquet"
    assert p_clean.exists() and f_clean.exists()

    # 校验关键字段
    p = pd.read_parquet(p_clean)
    assert {"position", "price_now", "team_name", "team_short"}.issubset(p.columns)
    # Saka: element_type=3 -> MID, now_cost=90 -> 9.0
    saka = p[p["web_name"] == "Saka"].iloc[0]
    assert saka["position"] == "MID"
    assert abs(saka["price_now"] - 9.0) < 1e-6
    assert saka["team_name"] == "Arsenal"
    assert saka["team_short"] == "ARS"

    f = pd.read_parquet(f_clean)
    assert {"home_team", "away_team", "home_fdr", "away_fdr"}.issubset(f.columns)
    row = f.iloc[0]
    assert row["home_team"] == "Arsenal"
    assert row["away_team"] == "Aston Villa"
    assert row["home_fdr"] == 2
    assert row["away_fdr"] == 3
