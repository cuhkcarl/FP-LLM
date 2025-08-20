from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from metrics.evaluate import MetricParams, write_metrics_json

app = typer.Typer(add_completion=False)


@app.command()
def main(
    gw: Annotated[int, typer.Option(help="评估目标 GW")],
    data_dir: Annotated[Path, typer.Option(help="数据目录")] = Path("data"),
    out_dir: Annotated[Path, typer.Option(help="报告目录")] = Path("reports"),
    k_for_ndcg: Annotated[int, typer.Option(help="NDCG@K 的 K 值")] = 11,
):
    preds = pd.read_parquet(data_dir / "processed" / f"predictions_gw{gw:02d}.parquet")
    actuals = pd.read_parquet(data_dir / "processed" / f"actuals_gw{gw:02d}.parquet")
    out_path = out_dir / f"gw{gw:02d}" / "metrics.json"
    write_metrics_json(
        gw=gw,
        preds=preds,
        actuals=actuals,
        out_path=out_path,
        params=MetricParams(k_for_ndcg=k_for_ndcg),
    )
    typer.echo(f"✅ wrote {out_path}")


if __name__ == "__main__":
    app()
