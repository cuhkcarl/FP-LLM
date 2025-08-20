from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from fpl_data.clients import EVENT_LIVE, get_json

app = typer.Typer(add_completion=False)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@app.command()
def main(
    gw: Annotated[int, typer.Option(help="要抓取的比赛周 (Gameweek)")],
    out_dir: Annotated[Path, typer.Option(help="输出目录（默认 data/processed）")] = Path(
        "data/processed"
    ),
    force_refresh: Annotated[bool, typer.Option("--force-refresh/--no-force-refresh")] = False,
):
    """
    抓取 `event/{gw}/live/`，抽取逐球员真实分，写入 `actuals_gwXX.parquet`。
    """
    url = EVENT_LIVE(gw)
    data = get_json(url, force_refresh=force_refresh)
    # 结构：{"elements": [{"id": pid, "stats": {"total_points": .., "minutes": .., ...}}, ...]}
    elements = data.get("elements") or []
    rows = []
    for el in elements:
        pid = int(el.get("id"))
        st = el.get("stats") or {}
        rows.append(
            dict(
                player_id=pid,
                total_points=int(st.get("total_points", 0)),
                minutes=int(st.get("minutes", 0)),
                goals_scored=int(st.get("goals_scored", 0)),
                assists=int(st.get("assists", 0)),
                clean_sheets=int(st.get("clean_sheets", 0)),
                goals_conceded=int(st.get("goals_conceded", 0)),
                saves=int(st.get("saves", 0)),
                bonus=int(st.get("bonus", 0)),
                bps=int(st.get("bps", 0)),
                yellow_cards=int(st.get("yellow_cards", 0)),
                red_cards=int(st.get("red_cards", 0)),
            )
        )
    df = pd.DataFrame(rows)
    _ensure_dir(out_dir)
    out_path = out_dir / f"actuals_gw{gw:02d}.parquet"
    df.to_parquet(out_path, index=False)
    typer.echo(f"✅ wrote {out_path} ({len(df)} rows)")


if __name__ == "__main__":
    app()
