from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from fpl_data.clients import ELEMENT_SUMMARY, get_json

app = typer.Typer(add_completion=False)


@app.command()
def main(
    raw_dir: Annotated[Path, typer.Option(help="原始 bootstrap-static 路径所在目录")] = Path(
        "data/raw/fpl"
    ),
    out_dir: Annotated[Path, typer.Option(help="输出目录（processed）")] = Path("data/processed"),
    force_refresh: Annotated[
        bool,
        typer.Option(
            "--force-refresh/--no-force-refresh", help="是否强制刷新 HTTP 缓存并重写输出文件"
        ),
    ] = False,
    skip_if_exists: Annotated[
        bool,
        typer.Option("--skip-if-exists/--no-skip-if-exists", help="若输出文件已存在则跳过本次运行"),
    ] = True,
):
    """
    拉取上赛季汇总（per player），写入 last_season_totals.parquet。
    数据来源：element-summary/{id} 的 history_past 中最新一季。
    """
    # 若输出文件已存在且不强制刷新，则直接跳过
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "last_season_totals.parquet"
    if out_path.exists() and not force_refresh and skip_if_exists:
        typer.echo(
            f"✅ exists {out_path} -> skip (use --no-skip-if-exists or --force-refresh to regenerate)"
        )
        return

    # 读取 bootstrap-static 以获取当前 element 列表
    bs_path = raw_dir / "bootstrap-static.json"
    if not bs_path.exists():
        raise FileNotFoundError(f"missing {bs_path}")
    import json

    elements = json.loads(bs_path.read_text(encoding="utf-8")).get("elements") or []
    rows = []
    for el in elements:
        pid = int(el["id"])  # current season id
        # 上赛季汇总为历史静态数据，默认允许长期缓存
        summ = get_json(ELEMENT_SUMMARY(pid), force_refresh=force_refresh, ttl_hours=24 * 365)
        hp = summ.get("history_past") or []
        if not hp:
            continue
        last = hp[-1]
        rows.append(
            dict(
                player_id=pid,
                season=str(last.get("season_name", "")),
                minutes=int(last.get("minutes", 0)),
                total_points=int(last.get("total_points", 0)),
                goals_scored=int(last.get("goals_scored", 0)),
                assists=int(last.get("assists", 0)),
                clean_sheets=int(last.get("clean_sheets", 0)),
                goals_conceded=int(last.get("goals_conceded", 0)),
                starts=int(last.get("starts", 0)),
            )
        )
    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)
    typer.echo(f"✅ wrote {out_path} (rows={len(df)})")


if __name__ == "__main__":
    app()
