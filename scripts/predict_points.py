from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from prediction.baseline import BaselineParams, predict_from_features
from prediction.cold_start import ColdStartParams, compute_cold_start_ep

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
        float, typer.Option(help="可用性幂次（<1 放大影响，>1 收缩)")
    ] = 1.0,
    mode: Annotated[str, typer.Option(help="baseline / cold_start / blend")] = "baseline",
    blend_decay_gws: Annotated[int, typer.Option(help="冷启动权重衰减窗口（GW1→GWk 渐退)")] = 4,
    data_root: Annotated[Path, typer.Option(help="数据根目录（raw/interim/processed)")] = Path(
        "data"
    ),
):
    """
    读取 M2 产物，输出 expected_points（M3 基线预测）。
    """
    in_name = f"features_gw{gw:02d}.parquet" if gw is not None else "features.parquet"
    in_path = in_dir / in_name

    out_name = f"predictions_gw{gw:02d}.parquet" if gw is not None else "predictions.parquet"
    out_path = out_dir / out_name

    # Baseline
    params = BaselineParams(
        min_availability=min_availability, availability_power=availability_power
    )
    df_base = predict_from_features(in_path, out_path=None, params=params)

    # Cold-start EP (optional)
    df_final = df_base.copy()
    if mode in ("cold_start", "blend"):
        # 尝试从 interim/ 与 processed/ 读取依赖
        players_path = data_root / "interim" / "players.parquet"
        last_totals_path = out_dir / "last_season_totals.parquet"
        players = pd.read_parquet(players_path) if players_path.exists() else None
        last_totals = pd.read_parquet(last_totals_path) if last_totals_path.exists() else None
        if players is None or last_totals is None:
            typer.echo(
                "[warn] cold_start requires interim players & last_season_totals; falling back to baseline"
            )
        else:
            cs = compute_cold_start_ep(
                bootstrap_players=players,
                last_season_totals=last_totals,
                fixtures=None,
                gw=(gw or 1),
                params=ColdStartParams(),
            )
            # merge cs_ep
            df_final = df_base.merge(cs[["player_id", "cs_ep"]], on="player_id", how="left")
            df_final["cs_ep"] = df_final["cs_ep"].fillna(df_final["expected_points"])  # fallback
            if mode == "cold_start":
                df_final["expected_points"] = df_final["cs_ep"]
            else:
                # blend weight by gw
                if gw is None:
                    w_cs = 0.0
                else:
                    w_cs = max(0.0, 1.0 - (max(gw, 1) - 1) / max(1, blend_decay_gws))
                df_final["expected_points"] = (
                    w_cs * df_final["cs_ep"] + (1.0 - w_cs) * df_final["expected_points"]
                )

    # 写出
    out = df_final.copy()
    out.to_parquet(out_path, index=False)

    typer.echo(f"✅ wrote {out_path}  (rows={len(out)})  mode={mode}")
    preview = out[["web_name", "position", "team_short", "price_now", "expected_points"]].head(12)
    typer.echo(preview.to_string(index=False))


if __name__ == "__main__":
    app()
