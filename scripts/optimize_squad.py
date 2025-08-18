from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
import yaml

from optimizer.ilp import solve_starting_xi
from optimizer.transfers import best_transfers, load_squad_yaml

app = typer.Typer(add_completion=False)


@app.command()
def main(
    gw: Annotated[
        int | None, typer.Option(help="与 predictions_gwXX 对应；不填读 predictions.parquet")
    ] = None,
    data_dir: Annotated[Path, typer.Option(help="数据目录（含 processed/、interim/）")] = Path(
        "data"
    ),
    squad_file: Annotated[
        Path, typer.Option("--squad", "--squad-file", help="当前阵容 YAML")
    ] = Path("configs/squad.yaml"),
    pool_size: Annotated[int, typer.Option(help="候选池每位置大小（转会枚举）")] = 12,
    max_transfers: Annotated[int, typer.Option(help="最大转会数（含付费）")] = 2,
    hit_cost: Annotated[int, typer.Option(help="每次付费转会的扣分")] = 4,
    respect_blacklist: Annotated[
        bool, typer.Option(help="遵从 configs/base.yaml 的黑名单/价格阈值")
    ] = True,
):
    """
    M4：基于预测结果与当前 15 人阵容，给出首发/队长与 0/1/2 次转会建议。
    """
    # 读取预测
    in_name = f"predictions_gw{gw:02d}.parquet" if gw is not None else "predictions.parquet"
    pred_path = data_dir / "processed" / in_name
    preds = pd.read_parquet(pred_path)

    # 读取 squad
    squad = load_squad_yaml(squad_file)
    current_ids = [int(x) for x in squad.player_ids]

    # 黑名单
    blacklist_names = None
    blacklist_price_min = None
    if respect_blacklist:
        cfg_path = Path("configs/base.yaml")
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            bl = cfg.get("blacklist") or {}
            blacklist_names = bl.get("names")
            blacklist_price_min = bl.get("price_min")

    # 当前阵容的首发与队长
    squad_pred = preds[preds["player_id"].isin(current_ids)].copy()
    xi = solve_starting_xi(squad_pred)

    # 转会枚举
    result = best_transfers(
        preds,
        squad,
        pool_size=pool_size,
        max_transfers=max_transfers,
        hit_cost=hit_cost,
        blacklist_names=blacklist_names,
        blacklist_price_min=blacklist_price_min,
    )

    # 打印摘要
    def fmt_names(ids):
        m = preds.set_index("player_id")["web_name"].to_dict()
        return [m.get(int(i), str(i)) for i in ids]

    typer.echo("\n=== Current XI (with captain) ===")
    typer.echo(f"Formation: {xi['formation']}")
    typer.echo(f"Captain: {preds.set_index('player_id').loc[xi['captain_id'],'web_name']}")
    typer.echo(f"Vice:    {preds.set_index('player_id').loc[xi['vice_id'],'web_name']}")
    typer.echo(f"Expected XI pts (incl. C): {xi['expected_points_xi_with_captain']:.2f}")

    typer.echo("\n=== Transfers Suggestion ===")
    typer.echo(f"Baseline XI pts: {result['baseline_points']:.2f}")
    bp = result["best_plan"]
    if bp["transfers"] == 0:
        typer.echo("Best: Keep (0 transfers).")
    else:
        typer.echo(f"Best: {bp['transfers']} transfer(s), hit cost {bp['hit_cost']}")
        typer.echo(f"Out: {fmt_names(bp['out_ids'])}")
        typer.echo(f"In : {fmt_names(bp['in_ids'])}")
        typer.echo(f"New XI pts: {bp['new_points']:.2f}")
        typer.echo(f"Net gain vs baseline (after hits): {bp['net_gain']:.2f}")


if __name__ == "__main__":
    app()
