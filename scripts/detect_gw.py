from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

import typer

from fpl_data.clients import BOOTSTRAP_STATIC, get_json

app = typer.Typer(add_completion=False)


@dataclass
class GwInfo:
    current: int | None
    next: int | None
    previous: int | None


def _detect_from_bootstrap() -> GwInfo:
    bs = get_json(BOOTSTRAP_STATIC, force_refresh=False)
    events = bs.get("events") or []
    current = None
    nxt = None
    for e in events:
        try:
            if e.get("is_current"):
                current = int(e.get("id"))
            if e.get("is_next"):
                nxt = int(e.get("id"))
        except Exception:
            continue
    # fallback by deadline_time if needed
    if current is None:
        now = datetime.now(UTC)
        past = [
            (int(e.get("id")), e.get("deadline_time")) for e in events if e.get("deadline_time")
        ]
        past_sorted = sorted(
            ((gid, datetime.fromisoformat(dt.replace("Z", "+00:00"))) for gid, dt in past),
            key=lambda x: x[1],
        )
        for gid, dt in reversed(past_sorted):
            if dt <= now:
                current = gid
                break
    if nxt is None and current is not None:
        nxt = current + 1
    prev = current - 1 if isinstance(current, int) and current > 1 else None
    return GwInfo(current=current, next=nxt, previous=prev)


@app.command()
def main(
    mode: Annotated[
        str,
        typer.Option(help="输出哪一个：current|next|previous"),
    ] = "next",
):
    gi = _detect_from_bootstrap()
    if mode == "current":
        v = gi.current
    elif mode == "next":
        v = gi.next
    elif mode == "previous":
        v = gi.previous
    else:
        raise typer.BadParameter("mode must be one of current|next|previous")
    if v is None:
        raise typer.Exit(code=1)
    print(int(v))


if __name__ == "__main__":
    app()
