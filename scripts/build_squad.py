from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import numpy as np
import pandas as pd
import typer
import yaml

from optimizer.squad_builder import BuildParams, build_initial_squad

app = typer.Typer(add_completion=False)


@app.command()
def main(
    preds_path: Annotated[
        Path, typer.Option(help="预测 parquet 路径（含 expected_points 或 cs_ep）")
    ],
    budget: Annotated[float, typer.Option(help="初始预算（m）")] = 100.0,
    respect_blacklist: Annotated[
        bool,
        typer.Option(
            "--respect-blacklist/--no-respect-blacklist",
            help="是否遵从 configs/base.yaml 的黑名单/高价过滤",
        ),
    ] = True,
    config_path: Annotated[Path, typer.Option(help="配置文件路径")] = Path("configs/base.yaml"),
):
    pred = pd.read_parquet(preds_path)
    # 加载黑名单
    bl_names: list[str] | None = None
    bl_price_min: float | None = None
    wl_names: list[str] | None = None
    if respect_blacklist and config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg: dict[str, Any] = yaml.safe_load(f) or {}
            bl = cfg.get("blacklist") or {}
            names = bl.get("names")
            price_min = bl.get("price_min")
            if isinstance(names, list) and len(names) == 0:
                names = None
            if price_min is not None:
                price_min = float(price_min)
            bl_names, bl_price_min = names, price_min
            wl_cfg = (cfg.get("whitelist") or {}).get("names")
            if isinstance(wl_cfg, list) and len(wl_cfg) > 0:
                wl_names = [str(x) for x in wl_cfg]
        except Exception:
            bl_names, bl_price_min = None, None
            wl_names = None

    res = build_initial_squad(
        pred,
        params=BuildParams(budget=budget),
        blacklist_names=bl_names,
        blacklist_price_min=bl_price_min,
        whitelist_names=wl_names,
    )
    ids = res["player_ids"]
    typer.echo(f"Selected 15 players, cost={res['cost']:.1f}, bank={res['bank']:.1f}")
    typer.echo(str(ids))
    # Explain flags: EP, availability, value-for-money tertiles
    p = pred.set_index("player_id")
    df = p.loc[ids, ["web_name", "position", "price_now"]].copy()
    df["ep"] = p.loc[ids, "expected_points" if "expected_points" in p.columns else "cs_ep"].astype(
        float
    )
    df["avail"] = (
        p.loc[ids, "availability_score"].fillna(0.8).astype(float)
        if "availability_score" in p.columns
        else 0.8
    )
    df["vpm"] = df["ep"] / np.maximum(df["price_now"], 1e-6)

    def flag(s):
        q = s.rank(pct=True)
        return np.where(q >= 0.67, "H", np.where(q <= 0.33, "L", "M"))

    df["EP_flag"], df["AV_flag"], df["VFM_flag"] = (
        flag(df["ep"]),
        flag(df["avail"]),
        flag(df["vpm"]),
    )
    typer.echo("\nTop-line flags (H/M/L) per selected player:")
    typer.echo(
        df[["web_name", "position", "price_now", "ep", "EP_flag", "AV_flag", "VFM_flag"]].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    app()
