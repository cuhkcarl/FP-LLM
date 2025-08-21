from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

app = typer.Typer(add_completion=False)


def _load_from_predictions(data_dir: Path, gw: int | None) -> pd.DataFrame | None:
    try:
        if gw is not None:
            path = data_dir / "processed" / f"predictions_gw{gw:02d}.parquet"
        else:
            path = data_dir / "processed" / "predictions.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        cols = [
            c
            for c in [
                "player_id",
                "web_name",
                "team_short",
                "position",
                "price_now",
            ]
            if c in df.columns
        ]
        return df[cols].copy()
    except Exception:
        return None


def _load_from_bootstrap(raw_dir: Path) -> pd.DataFrame | None:
    path = raw_dir / "fpl" / "bootstrap-static.json"
    if not path.exists():
        return None
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    elements = data.get("elements") or []
    teams = {int(t.get("code", -1)): t.get("short_name", "") for t in (data.get("teams") or [])}
    rows = []
    for el in elements:
        rows.append(
            dict(
                player_id=int(el.get("id", 0)),
                web_name=str(el.get("web_name", "")),
                team_short=str(teams.get(int(el.get("team_code", -1)), "")),
                position=str(el.get("element_type", "")),
                price_now=float(el.get("now_cost", 0)) / 10.0,
            )
        )
    return pd.DataFrame(rows)


@app.command()
def main(
    query: Annotated[str, typer.Argument(help="要匹配的子串（匹配 web_name，大小写不敏感）")],
    gw: Annotated[
        int | None,
        typer.Option(
            help="优先从 predictions_gwXX 读取；缺省尝试 predictions.parquet/回退 bootstrap-static"
        ),
    ] = None,
    data_dir: Annotated[Path, typer.Option(help="数据目录（含 processed/、raw/）")] = Path("data"),
    limit: Annotated[int, typer.Option(help="最多显示条数")] = 50,
):
    df = _load_from_predictions(data_dir, gw)
    if df is None:
        df = _load_from_bootstrap(data_dir / "raw")
    if df is None or df.empty:
        typer.echo("No data available. Run fetch/predict first.")
        raise typer.Exit(code=1)

    q = str(query).strip().lower()
    mask = df["web_name"].astype(str).str.lower().str.contains(q, na=False)
    out = df.loc[mask].copy()
    if out.empty:
        typer.echo("No match.")
        raise typer.Exit(code=0)

    cols = [
        c
        for c in ["player_id", "web_name", "team_short", "position", "price_now"]
        if c in out.columns
    ]
    out = out[cols].drop_duplicates().sort_values(["web_name", "team_short"]).head(int(limit))
    typer.echo(out.to_string(index=False))


if __name__ == "__main__":
    app()
