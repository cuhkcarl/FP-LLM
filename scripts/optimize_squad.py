from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
import yaml

from optimizer.chips import ChipThresholds, suggest_chips
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
    squad_file: Annotated[Path, typer.Option(help="当前阵容 YAML")] = Path("configs/squad.yaml"),
    pool_size: Annotated[int, typer.Option(help="候选池每位置大小（转会枚举）")] = 12,
    max_transfers: Annotated[int, typer.Option(help="最大转会数（含付费）")] = 2,
    hit_cost: Annotated[int, typer.Option(help="每次付费转会的扣分")] = 4,
    suggest_chips_flag: Annotated[
        bool, typer.Option("--suggest-chips/--no-suggest-chips", help="是否输出筹码建议")
    ] = True,
):
    """
    M4：基于预测结果与当前 15 人阵容，给出首发/队长、0/1/2 次转会建议，并（可选）输出筹码启发式建议。
    """
    # 读取预测
    in_name = f"predictions_gw{gw:02d}.parquet" if gw is not None else "predictions.parquet"
    pred_path = data_dir / "processed" / in_name
    preds = pd.read_parquet(pred_path)

    # 读取 fixtures（用于检测双赛/空白）
    fixtures_path = data_dir / "interim" / "fixtures_clean.parquet"
    fixtures = pd.read_parquet(fixtures_path) if fixtures_path.exists() else None

    # 读取 squad
    squad = load_squad_yaml(squad_file)
    current_ids = [int(x) for x in squad.player_ids]

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
    )

    # 输出摘要
    pidx = preds.set_index("player_id")

    def name(pid: int) -> str:
        return str(pidx.loc[pid, "web_name"]) if pid in pidx.index else str(pid)

    typer.echo("\n=== Current XI (with captain) ===")
    typer.echo(f"Formation: {xi['formation']}")
    typer.echo(f"Captain: {name(xi['captain_id'])}")
    typer.echo(f"Vice:    {name(xi['vice_id'])}")
    typer.echo(f"Expected XI pts (incl. C): {xi['expected_points_xi_with_captain']:.2f}")

    typer.echo("\n=== Transfers Suggestion ===")
    typer.echo(f"Baseline XI pts: {result['baseline_points']:.2f}")
    bp = result["best_plan"]
    if bp["transfers"] == 0:
        typer.echo("Best: Keep (0 transfers).")
    else:
        typer.echo(f"Best: {bp['transfers']} transfer(s), hit cost {bp['hit_cost']}")
        typer.echo(f"Out: {[name(i) for i in bp['out_ids']]}")
        typer.echo(f"In : {[name(i) for i in bp['in_ids']]}")
        typer.echo(f"New XI pts: {bp['new_points']:.2f}")
        typer.echo(f"Net gain vs baseline (after hits): {bp['net_gain']:.2f}")

    if suggest_chips_flag and gw is not None:
        # 从 squad.yaml 读取可用筹码与 configs/base.yaml 的阈值
        chips_available = {}
        try:
            with open(squad_file, encoding="utf-8") as f:
                sdata = yaml.safe_load(f) or {}
            chips_available = sdata.get("chips_available") or {}
        except Exception:
            chips_available = {}

        thresholds = ChipThresholds()
        cfg_path = Path("configs/base.yaml")
        if cfg_path.exists():
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                ch = (cfg.get("chips") or {}).get("thresholds") or {}
                thresholds = ChipThresholds(
                    bench_boost_min_bench_ep=float(
                        ch.get("bench_boost_min_bench_ep", thresholds.bench_boost_min_bench_ep)
                    ),
                    triple_captain_min_ep=float(
                        ch.get("triple_captain_min_ep", thresholds.triple_captain_min_ep)
                    ),
                    triple_captain_min_ep_if_double=float(
                        ch.get(
                            "triple_captain_min_ep_if_double",
                            thresholds.triple_captain_min_ep_if_double,
                        )
                    ),
                    free_hit_min_active_starters=int(
                        ch.get(
                            "free_hit_min_active_starters", thresholds.free_hit_min_active_starters
                        )
                    ),
                )
            except Exception:
                pass

        chips = suggest_chips(
            gw=gw,
            preds=preds,
            fixtures=fixtures,
            starting_ids=xi["starting_ids"],
            bench_ids=xi["bench_ids"],
            captain_id=xi["captain_id"],
            chips_available=chips_available,
            thresholds=thresholds,
        )

        typer.echo("\n=== Chips Suggestion ===")
        for k, v in chips.items():
            status = "YES" if v["recommended"] else "no"
            typer.echo(f"{k}: {status} — {v['reason']}  {v['metrics']}")


if __name__ == "__main__":
    app()
