from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from fpl_data.clients import FIXTURES, get_json

app = typer.Typer(add_completion=False)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_fixtures(*, raw_dir: Path | None, force_refresh: bool) -> pd.DataFrame:
    """
    Load fixtures from local raw dump if present; otherwise fetch from API.

    Returns a DataFrame with at least: event, finished, kickoff_time.
    """
    if raw_dir is not None:
        raw_path = raw_dir / "fixtures.json"
        if raw_path.exists():
            try:
                import json

                fx = json.loads(raw_path.read_text(encoding="utf-8"))
                return pd.DataFrame(fx)
            except Exception:
                pass
    # fallback to API
    fx = get_json(FIXTURES, force_refresh=force_refresh)
    return pd.DataFrame(fx)


@app.command()
def main(
    gw: Annotated[int, typer.Option(help="要检测是否完赛的 GW")],
    raw_dir: Annotated[
        Path | None,
        typer.Option(help="若提供，则优先从该目录的 fixtures.json 读取（可选）"),
    ] = None,
    force_refresh: Annotated[
        bool, typer.Option("--force-refresh/--no-force-refresh", help="强制刷新 API 缓存")
    ] = False,
    github_output: Annotated[
        Path | None,
        typer.Option(
            help="若提供，则以 key=value 形式写入 GITHUB_OUTPUT（供 GitHub Actions 使用）"
        ),
    ] = None,
    assert_finished: Annotated[
        bool,
        typer.Option(
            "--assert-finished/--no-assert-finished",
            help="若指定，且未完赛则以非 0 退出码结束（CI 可用）",
        ),
    ] = False,
):
    """
    判断指定 GW 是否“全部完赛”。

    规则：在 fixtures 中筛选 event==gw 的比赛，若条目数>0 且所有 finished==True，则视为完赛。
    注意：对 event 为空（延期/未定）的比赛不计入该 GW。
    """
    fixtures = _load_fixtures(raw_dir=raw_dir, force_refresh=force_refresh)
    # 仅保留该 GW 的条目
    df = fixtures.copy()
    # 兼容字段类型
    if "event" not in df.columns:
        typer.echo("[error] fixtures missing 'event' column", err=True)
        raise typer.Exit(code=2)
    if "finished" not in df.columns:
        df["finished"] = False

    # 过滤该 gw
    df_gw = df[df["event"].astype("Int64") == pd.Series([gw], dtype="Int64")[0]].copy()

    total = int(len(df_gw))
    finished = int(df_gw["finished"].fillna(False).sum()) if total > 0 else 0
    all_finished = total > 0 and finished == total

    msg = f"GW{gw:02d}: total={total}, finished={finished}, all_finished={all_finished}"
    typer.echo(msg)

    if github_output is not None:
        try:
            content = (
                f"gw={gw}\n"
                f"total={total}\n"
                f"finished={finished}\n"
                f"all_finished={'true' if all_finished else 'false'}\n"
            )
            _ensure_dir(github_output.parent)
            with github_output.open("a", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            # 不阻断主流程
            pass

    if assert_finished and not all_finished:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
