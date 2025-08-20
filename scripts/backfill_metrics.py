from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from metrics.evaluate import MetricParams, compute_metrics

app = typer.Typer(add_completion=False)


def _history_row(gw: int, metrics: dict) -> dict:
    overall = metrics.get("overall", {})
    by_pos = metrics.get("by_pos", {})
    row: dict[str, float | int] = {
        "gw": int(gw),
        "mae": float(overall.get("mae", 0.0)),
        "rmse": float(overall.get("rmse", 0.0)),
        "spearman": float(overall.get("spearman", 0.0)),
        "ndcg_at_11": float(overall.get("ndcg_at_11", 0.0)),
    }
    for pos in ["GK", "DEF", "MID", "FWD"]:
        sub = by_pos.get(pos, {})
        row[f"mae_{pos.lower()}"] = float(sub.get("mae", 0.0))
        row[f"ndcg_{pos.lower()}"] = float(sub.get("ndcg_at_11", 0.0))
    return row


@app.command()
def main(
    start_gw: Annotated[int, typer.Option(help="起始 GW（含）")],
    end_gw: Annotated[int, typer.Option(help="结束 GW（含）")],
    data_dir: Annotated[Path, typer.Option(help="数据目录")] = Path("data"),
    out_dir: Annotated[Path, typer.Option(help="报告目录")] = Path("reports"),
    k_for_ndcg: Annotated[int, typer.Option(help="NDCG@K 的 K 值")] = 11,
):
    hist_path = data_dir / "processed" / "metrics_history.parquet"
    rows: list[dict] = []
    for gw in range(int(start_gw), int(end_gw) + 1):
        pred_p = data_dir / "processed" / f"predictions_gw{gw:02d}.parquet"
        act_p = data_dir / "processed" / f"actuals_gw{gw:02d}.parquet"
        if not (pred_p.exists() and act_p.exists()):
            continue
        preds = pd.read_parquet(pred_p)
        actuals = pd.read_parquet(act_p)
        m = compute_metrics(preds, actuals, MetricParams(k_for_ndcg=k_for_ndcg))
        # 写 metrics.json
        out_path = out_dir / f"gw{gw:02d}" / "metrics.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        out_path.write_text(
            json.dumps({"gw": int(gw), **m}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        rows.append(_history_row(gw, m))

    if rows:
        df_new = pd.DataFrame(rows).sort_values("gw").reset_index(drop=True)
        if hist_path.exists():
            try:
                df_old = pd.read_parquet(hist_path)
            except Exception:
                df_old = pd.DataFrame(columns=df_new.columns)
            df_all = (
                pd.concat([df_old, df_new], axis=0, ignore_index=True)
                .drop_duplicates(subset=["gw"], keep="last")
                .sort_values("gw")
                .reset_index(drop=True)
            )
        else:
            df_all = df_new
        df_all.to_parquet(hist_path, index=False)
        typer.echo(f"✅ wrote {hist_path} ({len(df_all)} rows)")
    else:
        typer.echo("no metrics to backfill")


if __name__ == "__main__":
    app()
