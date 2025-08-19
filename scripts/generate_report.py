from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
import yaml

from optimizer.chips import ChipThresholds, suggest_chips
from optimizer.ilp import solve_starting_xi
from optimizer.transfers import best_transfers, load_squad_yaml

app = typer.Typer(add_completion=False)


def _helpers_from_preds(preds: pd.DataFrame):
    pidx = preds.set_index("player_id")

    def name_of(pid: int) -> str:
        return str(pidx.loc[pid, "web_name"]) if pid in pidx.index else str(pid)

    def ep_of(pid: int) -> float:
        return float(pidx.loc[pid, "expected_points"]) if pid in pidx.index else 0.0

    def team_of(pid: int) -> str:
        return str(pidx.loc[pid, "team_short"]) if pid in pidx.index else "UNK"

    def pos_of(pid: int) -> str:
        return str(pidx.loc[pid, "position"]) if pid in pidx.index else "UNK"

    return name_of, ep_of, team_of, pos_of


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

    # transfers
    res = best_transfers(preds, squad)
    bp = res["best_plan"]

    # chips
    chips_available: dict[str, bool] = {}
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

    name, ep_of, team_of, pos_of = _helpers_from_preds(preds)

    # ---------- Markdown ----------
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
    if bp["transfers"] == 0:
        lines.append("- **Best plan**: Keep (0 transfers).")
    else:
        out_names = ", ".join(name(i) for i in bp["out_ids"])
        in_names = ", ".join(name(i) for i in bp["in_ids"])
        lines.append(f"- **Best plan**: {bp['transfers']} transfer(s), hit cost {bp['hit_cost']}")
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

    # ---------- JSON summary ----------
    summary = {
        "gw": gw,
        "generated_at": datetime.now(UTC).isoformat(),
        "formation": xi["formation"],
        "captain": {
            "id": xi["captain_id"],
            "name": name(xi["captain_id"]),
            "ep": ep_of(xi["captain_id"]),
        },
        "vice": {"id": xi["vice_id"], "name": name(xi["vice_id"]), "ep": ep_of(xi["vice_id"])},
        "starting_ids": xi["starting_ids"],
        "bench_ids": xi["bench_ids"],
        "bench_ep_total": bench_ep,
        "xi_ep_incl_captain": xi["expected_points_xi_with_captain"],
        "transfers": {
            "baseline_xi_ep": res["baseline_points"],
            "plan": {
                "transfers": bp["transfers"],
                "hit_cost": bp["hit_cost"],
                "out_ids": bp["out_ids"],
                "in_ids": bp["in_ids"],
                "new_xi_ep": bp["new_points"],
                "net_gain": bp["net_gain"],
            },
        },
        "chips": chips,
        "thresholds": {
            "bench_boost_min_bench_ep": thresholds.bench_boost_min_bench_ep,
            "triple_captain_min_ep": thresholds.triple_captain_min_ep,
            "triple_captain_min_ep_if_double": thresholds.triple_captain_min_ep_if_double,
            "free_hit_min_active_starters": thresholds.free_hit_min_active_starters,
        },
    }
    json_path = out_path.parent / "summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    typer.echo(f"✅ wrote {out_path}")
    typer.echo(f"✅ wrote {json_path}")


if __name__ == "__main__":
    app()
