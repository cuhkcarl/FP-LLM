from __future__ import annotations

from pathlib import Path

import typer

from fpl_data.loaders import build_all
from fpl_data.transforms import run_clean

app = typer.Typer(add_completion=False)


@app.command()
def main(
    raw_dir: Path = typer.Option(Path("data/raw/fpl")),
    interim_dir: Path = typer.Option(Path("data/interim")),
):
    """
    For M1: normalize raw json -> parquet, then basic cleaning.
    (Real 'features' will be added in M2.)
    """
    build_all(raw_dir, interim_dir)
    run_clean(interim_dir, interim_dir)
    typer.echo(
        f"✅ wrote {interim_dir/'players_clean.parquet'} and {interim_dir/'fixtures_clean.parquet'}"
    )


if __name__ == "__main__":
    app()
