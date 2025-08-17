from __future__ import annotations

from pathlib import Path

import pandas as pd

POS_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _ensure_dir(p: Path) -> None:
    Path(p).mkdir(parents=True, exist_ok=True)


def clean_players(players_parquet: str | Path, teams_parquet: str | Path) -> pd.DataFrame:
    """
    Normalize key columns:
      - element_type -> position (GK/DEF/MID/FWD)
      - now_cost (0.1m units) -> price_now (£m float)
      - merge team name/short_name
      - selected_by_percent -> selected_by_pct (float)
    """
    players = pd.read_parquet(players_parquet)
    teams = pd.read_parquet(teams_parquet)[["id", "name", "short_name"]].rename(
        columns={"id": "team_id", "name": "team_name", "short_name": "team_short"}
    )

    df = players.copy()

    # position
    df["position"] = df["element_type"].map(POS_MAP).astype("string")

    # price in £m
    df["price_now"] = (df["now_cost"].astype("float") / 10.0).round(1)

    # selected_by_percent is a string like "23.4"
    if "selected_by_percent" in df.columns:
        df["selected_by_pct"] = pd.to_numeric(df["selected_by_percent"], errors="coerce")
    else:
        # older dumps might use selected_by_percent without underscore variations; keep safe default
        df["selected_by_pct"] = pd.NA

    # minimal useful columns（保留一些常用字段，后续可扩展）
    keep_cols = [
        "id",
        "web_name",
        "first_name",
        "second_name",
        "team",
        "position",
        "price_now",
        "status",
        "minutes",
        "total_points",
        "form",
        "selected_by_pct",
        "chance_of_playing_next_round",
        "news",
    ]
    for c in keep_cols:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[keep_cols].rename(columns={"team": "team_id"})

    # merge team names
    df = df.merge(teams, on="team_id", how="left")

    # types
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0).astype("int64")
    df["total_points"] = (
        pd.to_numeric(df["total_points"], errors="coerce").fillna(0).astype("int64")
    )
    df["form"] = pd.to_numeric(df["form"], errors="coerce")

    return df


def clean_fixtures(
    fixtures_parquet: str | Path,
    teams_parquet: str | Path,
) -> pd.DataFrame:
    """
    Produce a tidy fixtures table with:
      - event (gw), kickoff_time (datetime), finished
      - team_h/team_a ids & names
      - team_h_difficulty / team_a_difficulty
      - home/away short names for readability
    """
    fixtures = pd.read_parquet(fixtures_parquet)
    teams = pd.read_parquet(teams_parquet)[["id", "name", "short_name"]].rename(
        columns={"id": "team_id", "name": "team_name", "short_name": "team_short"}
    )

    df = fixtures.copy()

    # parse kickoff_time
    if "kickoff_time" in df.columns:
        df["kickoff_time"] = pd.to_datetime(df["kickoff_time"], utc=True, errors="coerce")

    # minimal keep
    keep_cols = [
        "id",
        "event",
        "kickoff_time",
        "finished",
        "team_h",
        "team_a",
        "team_h_difficulty",
        "team_a_difficulty",
    ]
    for c in keep_cols:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[keep_cols]

    # merge team names
    df = df.merge(teams.rename(columns={"team_id": "team_h"}), on="team_h", how="left")
    df = df.rename(columns={"team_name": "home_team", "team_short": "home_short"})
    df = df.merge(teams.rename(columns={"team_id": "team_a"}), on="team_a", how="left")
    df = df.rename(columns={"team_name": "away_team", "team_short": "away_short"})

    # friendly aliases
    df = df.rename(
        columns={
            "team_h_difficulty": "home_fdr",
            "team_a_difficulty": "away_fdr",
        }
    )

    # ensure integer types where possible
    df["event"] = pd.to_numeric(df["event"], errors="coerce").astype("Int64")
    df["home_fdr"] = pd.to_numeric(df["home_fdr"], errors="coerce").astype("Int64")
    df["away_fdr"] = pd.to_numeric(df["away_fdr"], errors="coerce").astype("Int64")

    return df


def run_clean(interim_dir: str | Path, out_dir: str | Path) -> None:
    """
    Orchestrate cleaning to produce:
      - data/interim/players_clean.parquet
      - data/interim/fixtures_clean.parquet
    """
    interim_dir = Path(interim_dir)
    out_dir = Path(out_dir)
    _ensure_dir(out_dir)

    players_clean = clean_players(interim_dir / "players.parquet", interim_dir / "teams.parquet")
    fixtures_clean = clean_fixtures(interim_dir / "fixtures.parquet", interim_dir / "teams.parquet")

    players_clean.to_parquet(out_dir / "players_clean.parquet", index=False)
    fixtures_clean.to_parquet(out_dir / "fixtures_clean.parquet", index=False)
