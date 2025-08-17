from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from prediction.baseline import BaselineParams, predict_from_features

app = typer.Typer(add_completion=False)


@app.command()
def main(
    gw: Annotated[
        int | None,
        typer.Option(help="与 features_gwXX 对应；不填则读取 features.parquet"),
    ] = None,
    in_dir: Annotated[Path, typer.Option(help="特征目录")] = Path("data/processed"),
    out_dir: Annotated[Path, typer.Option(help="预测输出目录")] = Path("data/processed"),
    min_availability: Annotated[float, typer.Option(help="低于该可用性则置零")] = 0.15,
    availability_power: Annotated[
        float, typer.Option(help="可用性幂次（<1 放大影响，>1 收缩）")
    ] = 1.0,
):
    """
    读取 M2 产物，输出 expected_points（M3 基线预测）。
    """
    in_name = f"features_gw{gw:02d}.parquet" if gw is not None else "features.parquet"
    in_path = in_dir / in_name

    out_name = f"predictions_gw{gw:02d}.parquet" if gw is not None else "predictions.parquet"
    out_path = out_dir / out_name

    params = BaselineParams(
        min_availability=min_availability, availability_power=availability_power
    )
    df = predict_from_features(in_path, out_path=out_path, params=params)

    typer.echo(f"✅ wrote {out_path}  (rows={len(df)})")
    preview = df[["web_name", "position", "team_short", "price_now", "expected_points"]].head(12)
    typer.echo(preview.to_string(index=False))


if __name__ == "__main__":
    app()
