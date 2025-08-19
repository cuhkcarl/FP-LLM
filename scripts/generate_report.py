from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer
import yaml

from optimizer.chips import ChipThresholds, suggest_chips
from optimizer.ilp import solve_starting_xi
from optimizer.transfers import best_transfers, load_squad_yaml

app = typer.Typer(add_completion=False)


def _name_map(preds: pd.DataFrame):
    pidx = preds.set_index("player_id")
    return (
        lambda pid: pidx.loc[pid, "web_name"] if pid in pidx.index else str(pid),
        lambda pid: float(pidx.loc[pid, "expected_points"]) if pid in pidx.index else 0.0,
        lambda pid: pidx.loc[pid, "team_short"] if pid in pidx.index else "UNK",
        lambda pid: pidx.loc[pid, "position"] if pid in pidx.index else "UNK",
    )


def _load_blacklist(cfg_path: Path) -> tuple[list[str] | None, float | None]:
    if not cfg_path.exists():
        return None, None
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg: dict[str, Any] = yaml.safe_load(f) or {}
        bl = cfg.get("blacklist") or {}
        names = bl.get("names")
        price_min = bl.get("price_min")
        if isinstance(names, list) and len(names) == 0:
            names = None
        if price_min is not None:
            price_min = float(price_min)
        return names, price_min
    except Exception:
        return None, None


@app.command()
def main(
    gw: Annotated[int, typer.Option(help="生成报告的 GW")],
    data_dir: Annotated[Path, typer.Option(help="数据目录")] = Path("data"),
    squad_file: Annotated[Path, typer.Option(help="阵容 YAML")] = Path("configs/squad.yaml"),
    out_dir: Annotated[Path, typer.Option(help="报告输出目录")] = Path("reports"),
):
    preds = pd.read_parquet(data_dir / "processed" / f"predictions_gw{gw:02d}.parquet")
    fixtures_path = data_dir / "interim" / "fixtures_clean.parquet"
    fixtures = pd.read_parquet(fixtures_path) if fixtures_path.exists() else None

    squad = load_squad_yaml(squad_file)
    current_ids = [int(x) for x in squad.player_ids]
    current_pred = preds[preds["player_id"].isin(current_ids)].copy()

    xi = solve_starting_xi(current_pred)

    # transfers（尊重黑名单/高价阈值，与 CLI 行为保持一致）
    bl_names: list[str] | None = None
    bl_price_min: float | None = None
    cfg_path = Path("configs/base.yaml")
    if cfg_path.exists():
        n, p = _load_blacklist(cfg_path)
        bl_names, bl_price_min = n, p
    res = best_transfers(
        preds,
        squad,
        blacklist_names=bl_names,
        blacklist_price_min=bl_price_min,
        price_now_market=preds.set_index("player_id")["price_now"].to_dict(),
        purchase_prices={},  # 报告不掌握买入价，回退为当前价（仅用于共同口径展示）
        value_weight=0.0,
    )
    bp = res["best_plan"]

    # chips
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
                    ch.get("free_hit_min_active_starters", thresholds.free_hit_min_active_starters)
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

    name, ep_of, team_of, pos_of = _name_map(preds)

    # render markdown
    lines = []
    lines.append(f"# Gameweek {gw} — Squad Report")
    lines.append("")
    lines.append("## Starting XI")
    lines.append(f"- Formation: **{xi['formation']}**")
    lines.append(f"- Captain: **{name(xi['captain_id'])}**")
    lines.append(f"- Vice: **{name(xi['vice_id'])}**")
    lines.append(f"- Expected XI points (incl. C): **{xi['expected_points_xi_with_captain']:.2f}**")
    lines.append("")
    lines.append("| Player | Pos | Team | EP |")
    lines.append("|---|---|---|---:|")
    for pid in xi["starting_ids"]:
        lines.append(f"| {name(pid)} | {pos_of(pid)} | {team_of(pid)} | {ep_of(pid):.2f} |")

    lines.append("")
    lines.append("## Bench")
    lines.append("| Player | Pos | Team | EP |")
    lines.append("|---|---|---|---:|")
    for pid in xi["bench_ids"]:
        lines.append(f"| {name(pid)} | {pos_of(pid)} | {team_of(pid)} | {ep_of(pid):.2f} |")
    bench_ep = sum(ep_of(pid) for pid in xi["bench_ids"])
    lines.append(f"\n> Bench EP total: **{bench_ep:.2f}**")
    lines.append("")

    lines.append("## Transfers Suggestion")
    lines.append(f"- Baseline XI pts: **{res['baseline_points']:.2f}**")
    lines.append(
        f"- Team Value (now → after): **{res['best_plan']['team_value_now']:.2f} → {res['best_plan']['team_value_after']:.2f}**"
    )
    if bp["transfers"] == 0:
        lines.append("- **Best plan**: Keep (0 transfers).")
    else:
        lines.append(f"- **Best plan**: {bp['transfers']} transfer(s), hit cost {bp['hit_cost']}")
        out_names = ", ".join(name(i) for i in bp["out_ids"])
        in_names = ", ".join(name(i) for i in bp["in_ids"])
        lines.append(f"- Out: {out_names}")
        lines.append(f"- In : {in_names}")
        lines.append(f"- New XI pts: **{bp['new_points']:.2f}**")
        lines.append(f"- Net gain (after hits): **{bp['net_gain']:.2f}**")
    lines.append("")

    lines.append("## Chips")
    for k, v in chips.items():
        status = "YES ✅" if v["recommended"] else "no"
        lines.append(f"- **{k}**: {status} — {v['reason']}  `{v['metrics']}`")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gw{gw:02d}" / "report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.echo(f"✅ wrote {out_path}")

    # 写 summary.json（结构化指标）
    summary = {
        "gw": int(gw),
        "xi": {
            "starting_ids": xi["starting_ids"],
            "bench_ids": xi["bench_ids"],
            "captain_id": xi["captain_id"],
            "vice_id": xi["vice_id"],
            "expected_points_xi_with_captain": float(xi["expected_points_xi_with_captain"]),
            "bench_ep": float(bench_ep),
        },
        "transfers": {
            "baseline_points": float(res["baseline_points"]),
            "transfers": int(bp["transfers"]),
            "out_ids": [int(x) for x in bp["out_ids"]],
            "in_ids": [int(x) for x in bp["in_ids"]],
            "hit_cost": int(bp["hit_cost"]),
            "new_points": float(bp["new_points"]),
            "net_gain": float(bp["net_gain"]),
            "bank_after": float(bp.get("bank_after", 0.0)),
            "team_value_now": float(bp.get("team_value_now", 0.0)),
            "team_value_after": float(bp.get("team_value_after", 0.0)),
            "team_value_delta": float(bp.get("team_value_delta", 0.0)),
        },
        "chips": chips,
        "thresholds": {
            "bench_boost_min_bench_ep": float(thresholds.bench_boost_min_bench_ep),
            "triple_captain_min_ep": float(thresholds.triple_captain_min_ep),
            "triple_captain_min_ep_if_double": float(thresholds.triple_captain_min_ep_if_double),
            "free_hit_min_active_starters": int(thresholds.free_hit_min_active_starters),
        },
        "blacklist": {"names": bl_names, "price_min": bl_price_min},
    }

    # 可选：带上优化器默认参数（若存在）
    try:
        opt_cfg: dict[str, Any] = {}
        cfg_path = Path("configs/base.yaml")
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg: dict[str, Any] = yaml.safe_load(f) or {}
            opt_cfg = cfg.get("optimizer") or {}
        summary["optimizer"] = {
            "value_weight": float(opt_cfg.get("value_weight", 0.0)),
            "min_bank_after": opt_cfg.get("min_bank_after"),
            "max_tv_drop": opt_cfg.get("max_tv_drop"),
        }
    except Exception:
        pass

    summary_path = out_dir / f"gw{gw:02d}" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    typer.echo(f"✅ wrote {summary_path}")


if __name__ == "__main__":
    app()
