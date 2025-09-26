from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer
import yaml

app = typer.Typer(add_completion=False)


def _load_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"summary.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@app.command()
def main(
    gw: Annotated[int, typer.Option(help="目标 GW（读取对应 reports/gwXX/summary.json）")],
    squad_file: Annotated[Path, typer.Option(help="当前阵容 YAML 路径")] = Path(
        "configs/squad.yaml"
    ),
    summary_path: Annotated[
        Path | None, typer.Option(help="summary.json 路径（默认按 gw 推导）")
    ] = None,
    preds_path: Annotated[
        Path | None,
        typer.Option(help="用于补全新入队员的买入价（price_now）；可为空"),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm/--no-confirm", help="写入前确认（默认只预览）")
    ] = False,
):
    """
    将报告中建议的转会结果写回 configs/squad.yaml：
    - 按 `transfers.new_squad_ids` 更新 `squad`
    - 用 `transfers.bank_after` 更新 `bank`
    - `free_transfers` 置为 1（保守默认，避免与实际规则偏差）
    - 对新加入球员，若提供 `preds_path` 则以其 `price_now` 填充 `purchase_prices`

    注意：本脚本不会调用 FPL 官方转会接口，只是本地文件更新。请在你已经在官网执行转会后再回写。
    """

    sp = summary_path or Path("reports") / f"gw{gw:02d}" / "summary.json"
    summary = _load_summary(sp)
    transfers = summary.get("transfers") or {}
    new_ids = transfers.get("new_squad_ids") or []
    if not new_ids:
        raise typer.Exit("no transfers.new_squad_ids found in summary; nothing to apply")

    bank_after = float(transfers.get("bank_after", 0.0))

    doc = _load_yaml(squad_file)
    before_ids = [int(x) for x in (doc.get("squad") or [])]
    before_pp: dict[int, float] = {
        int(k): float(v) for k, v in (doc.get("purchase_prices") or {}).items()
    }

    # Preserve existing purchase_prices for retained players; add for new ones if preds provided
    after_ids = [int(x) for x in new_ids]
    pp_after: dict[int, float] = {}
    for pid in after_ids:
        if pid in before_pp:
            pp_after[pid] = before_pp[pid]

    if preds_path is None:
        # Try default path by gw
        candidate = Path("data/processed") / f"predictions_gw{gw:02d}.parquet"
        preds_path = candidate if candidate.exists() else None

    if preds_path is not None and Path(preds_path).exists():
        preds = pd.read_parquet(preds_path).set_index("player_id")
        for pid in after_ids:
            if pid not in pp_after and pid in preds.index and "price_now" in preds.columns:
                pp_after[pid] = float(preds.at[pid, "price_now"])

    out_doc = {
        **doc,
        "squad": after_ids,
        "bank": bank_after,
        # 保守：下一轮默认 1 次免费转会
        "free_transfers": 1,
        "purchase_prices": {int(k): float(v) for k, v in sorted(pp_after.items())},
    }

    # Preview / confirm
    typer.echo("=== Preview: apply transfers to squad.yaml ===")
    typer.echo(f"Before squad size: {len(before_ids)}; After: {len(after_ids)}")
    out_only = [pid for pid in before_ids if pid not in after_ids]
    in_only = [pid for pid in after_ids if pid not in before_ids]
    typer.echo(f"Out: {out_only}")
    typer.echo(f"In : {in_only}")
    typer.echo(f"Bank after: {bank_after:.1f}m")
    if not confirm:
        typer.echo("(dry-run) Use --confirm to write changes.")
        raise typer.Exit(code=0)

    _save_yaml(squad_file, out_doc)
    typer.echo(f"✅ wrote {squad_file}")


if __name__ == "__main__":
    app()
