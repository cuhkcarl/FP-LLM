from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _read_json(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def load_bootstrap(bootstrap_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return (players_df_raw, teams_df_raw) directly from bootstrap-static.
    """
    bs = _read_json(bootstrap_path)
    players = pd.DataFrame(bs["elements"])
    teams = pd.DataFrame(bs["teams"])
    return players, teams


def load_fixtures(fixtures_path: Path) -> pd.DataFrame:
    """
    Return fixtures_df_raw directly from fixtures endpoint.
    """
    fx = _read_json(fixtures_path)
    fixtures = pd.DataFrame(fx)
    return fixtures


def build_all(raw_dir: str | Path, interim_dir: str | Path) -> None:
    """
    Convenience entrypoint:
      - read raw jsons from data/raw/fpl/
      - write normalized parquet to data/interim/
    """
    raw_dir = Path(raw_dir)
    interim_dir = Path(interim_dir)
    interim_dir.mkdir(parents=True, exist_ok=True)

    players_raw, teams_raw = load_bootstrap(raw_dir / "bootstrap-static.json")
    fixtures_raw = load_fixtures(raw_dir / "fixtures.json")

    # minimal column subsets (still "raw-like"); transforms will clean/enrich later
    players_raw.to_parquet(interim_dir / "players.parquet", index=False)
    teams_raw.to_parquet(interim_dir / "teams.parquet", index=False)
    fixtures_raw.to_parquet(interim_dir / "fixtures.parquet", index=False)
