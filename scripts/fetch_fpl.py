from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from fpl_data.clients import (
    BOOTSTRAP_STATIC,
    DEFAULT_CACHE_DIR,
    ELEMENT_SUMMARY,
    EVENT_LIVE,
    FIXTURES,
    get_json,
)

app = typer.Typer(add_completion=False)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@app.command()
def main(
    season: str = typer.Option("2025_26", help="Season label (placeholder for now)"),
    gw: int | None = typer.Option(None, help="If given, fetch event/{gw}/live"),
    out_dir: Path = typer.Option(Path("data/raw/fpl"), help="Where to write raw JSON files"),
    force_refresh: bool = typer.Option(False, help="Ignore cache and force refresh"),
    element_summaries: int = typer.Option(
        0, help="Fetch element-summary for first N player ids from bootstrap (0=skip)"
    ),
):
    """
    Fetch key public endpoints from FPL official API and write JSON to disk.
    """
    _ensure_dir(out_dir)

    # bootstrap-static
    bs = get_json(BOOTSTRAP_STATIC, force_refresh=force_refresh)
    (out_dir / "bootstrap-static.json").write_text(json.dumps(bs, ensure_ascii=False), "utf-8")
    typer.echo(f"wrote {out_dir/'bootstrap-static.json'}")

    # fixtures
    fx = get_json(FIXTURES, force_refresh=force_refresh)
    (out_dir / "fixtures.json").write_text(json.dumps(fx, ensure_ascii=False), "utf-8")
    typer.echo(f"wrote {out_dir/'fixtures.json'}")

    # event/{gw}/live (optional)
    if gw is not None:
        ev = get_json(EVENT_LIVE(gw), force_refresh=force_refresh)
        path = out_dir / f"event_gw{gw:02d}_live.json"
        path.write_text(json.dumps(ev, ensure_ascii=False), "utf-8")
        typer.echo(f"wrote {path}")

    # element-summary/{player_id} for first N players (optional, to avoid heavy traffic)
    if element_summaries and element_summaries > 0:
        elements = bs.get("elements", [])
        count = min(element_summaries, len(elements))
        summary_dir = out_dir / "element_summaries"
        _ensure_dir(summary_dir)
        for i in range(count):
            pid = elements[i]["id"]
            data = get_json(ELEMENT_SUMMARY(pid), force_refresh=force_refresh)
            (summary_dir / f"{pid}.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        typer.echo(f"wrote {count} element summaries -> {summary_dir}")

    # note cache dir for transparency
    typer.echo(f"(http cache at {DEFAULT_CACHE_DIR})")


if __name__ == "__main__":
    app()
