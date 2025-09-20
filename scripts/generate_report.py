from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer
import yaml

from optimizer.chips import ChipThresholds, suggest_chips
from optimizer.ilp import solve_starting_xi
from optimizer.squad_builder import BuildParams, build_initial_squad
from optimizer.transfers import best_transfers, load_squad_yaml

app = typer.Typer(add_completion=False)


def _progress(msg: str) -> None:
    if os.getenv("FP_PROGRESS"):
        typer.echo(f"[progress] {msg}")


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


def _render_model_performance_section(metrics_path: Path) -> list[str]:
    try:
        import json as _json

        m = _json.loads(metrics_path.read_text(encoding="utf-8"))
        ov = m.get("overall", {})
        lines = []
        lines.append("")
        lines.append("## Model Performance")
        lines.append(
            f"- Overall: MAE **{ov.get('mae', 0):.3f}**, RMSE **{ov.get('rmse', 0):.3f}**, NDCG@11 **{ov.get('ndcg_at_11', 0):.3f}**"
        )

        # Add team performance if available
        team_perf = m.get("team_performance", {})
        if team_perf:
            lines.append("")
            lines.append("### Team Scoring Summary")
            predicted = team_perf.get("predicted_total", 0)
            actual = team_perf.get("actual_total", 0)
            error = team_perf.get("prediction_error", 0)
            lines.append(f"- **Predicted Team Total**: {predicted:.2f} points")
            lines.append(f"- **Actual Team Total**: {actual:.0f} points")
            lines.append(f"- **Prediction Error**: {error:+.2f} points")

            # Captain performance
            captain_score = team_perf.get("captain_score", 0)
            captain_bonus = team_perf.get("captain_bonus", 0)
            lines.append(f"- **Captain Score**: {captain_score} points (bonus: +{captain_bonus})")

            # Bench information
            bench_total = team_perf.get("bench_total", 0)
            lines.append(f"- **Bench Total**: {bench_total} points")

        # Add transfer performance if available
        transfer_perf = m.get("transfer_performance", {})
        if transfer_perf:
            lines.append("")
            lines.append("### Transfer Analysis")
            predicted_gain = transfer_perf.get("predicted_gain", 0)
            actual_gain = transfer_perf.get("actual_gain", 0)
            lines.append(f"- **Predicted Transfer Gain**: {predicted_gain:.2f} points")
            lines.append(f"- **Actual Transfer Gain**: {actual_gain:.0f} points")
            if predicted_gain != 0:
                transfer_accuracy = abs(actual_gain - predicted_gain)
                lines.append(f"- **Transfer Prediction Error**: {transfer_accuracy:.2f} points")

        return lines
    except Exception:
        return []


def _update_report_metrics_only(report_path: Path, metrics_path: Path) -> None:
    if not metrics_path.exists():
        typer.echo(f"[warn] metrics not found: {metrics_path}; skip metrics-only update")
        return
    new_block = _render_model_performance_section(metrics_path)
    if not new_block:
        typer.echo("[warn] failed to render metrics block; skip")
        return
    if report_path.exists():
        content = report_path.read_text(encoding="utf-8")
    else:
        content = ""
    # 查找并替换已有的 Model Performance 段落（从标题到下一个二级标题或 EOF）
    pattern = re.compile(r"\n## Model Performance[\s\S]*?(?=\n##\s|\Z)")
    block_text = "\n" + "\n".join(new_block)
    if re.search(pattern, content):
        updated = re.sub(pattern, block_text, content)
    else:
        updated = content.rstrip() + block_text + "\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(updated, encoding="utf-8")
    typer.echo(f"✅ metrics section updated -> {report_path}")


@app.command()
def main(
    gw: Annotated[int, typer.Option(help="生成报告的 GW")],
    data_dir: Annotated[Path, typer.Option(help="数据目录")] = Path("data"),
    squad_file: Annotated[Path, typer.Option(help="阵容 YAML")] = Path("configs/squad.yaml"),
    out_dir: Annotated[Path, typer.Option(help="报告输出目录")] = Path("reports"),
    metrics_only: Annotated[
        bool,
        typer.Option("--metrics-only/--no-metrics-only", help="仅更新/写入 Model Performance 段落"),
    ] = False,
):
    # 指标-only 模式：不重生成其它内容，只更新报告中的指标段
    if metrics_only:
        _progress(f"metrics-only mode for gw={gw}")
        metrics_path = out_dir / f"gw{gw:02d}" / "metrics.json"
        report_path = out_dir / f"gw{gw:02d}" / "report.md"
        _update_report_metrics_only(report_path, metrics_path)
        return
    _progress("loading predictions parquet")
    preds = pd.read_parquet(data_dir / "processed" / f"predictions_gw{gw:02d}.parquet")
    _progress(f"predictions loaded: {len(preds)} rows")
    fixtures_path = data_dir / "interim" / "fixtures_clean.parquet"
    fixtures = pd.read_parquet(fixtures_path) if fixtures_path.exists() else None
    _progress("fixtures loaded" if fixtures is not None else "fixtures missing, skip")

    _progress("loading squad.yaml")
    squad = load_squad_yaml(squad_file)
    _progress(f"squad loaded: {len(squad.player_ids)} players, bank={squad.bank}")
    current_ids = [int(x) for x in squad.player_ids]
    current_pred = preds[preds["player_id"].isin(current_ids)].copy()
    if len(current_ids) != 15:
        _progress("initial squad missing -> build_initial_squad begin")
        xi = {
            "starting_ids": [],
            "bench_ids": [],
            "captain_id": -1,
            "vice_id": -1,
            "formation": "-",
            "expected_points_xi_with_captain": 0.0,
        }
        skip_transfers = True
        # 尝试构建初始阵容建议（冷启动）
        init_budget = 100.0
        try:
            cfg_path = Path("configs/base.yaml")
            if cfg_path.exists():
                with open(cfg_path, encoding="utf-8") as f:
                    cfg: dict[str, Any] = yaml.safe_load(f) or {}
                sb = (cfg.get("optimizer") or {}).get("squad_builder") or {}
                if sb.get("budget") is not None:
                    init_budget = float(sb.get("budget"))
        except Exception:
            pass
        # 黑/白名单（对初始阵容建议同样生效）
        bl_names: list[str] | None = None
        bl_price_min: float | None = None
        wl_names: list[str] | None = None
        cfg_path = Path("configs/base.yaml")
        if cfg_path.exists():
            n, p = _load_blacklist(cfg_path)
            bl_names, bl_price_min = n, p
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg_wh = yaml.safe_load(f) or {}
                wl = (cfg_wh.get("whitelist") or {}).get("names")
                if isinstance(wl, list) and len(wl) > 0:
                    wl_names = [str(x) for x in wl]
            except Exception:
                wl_names = None
        init_res = build_initial_squad(
            preds,
            params=BuildParams(budget=init_budget),
            blacklist_names=bl_names,
            blacklist_price_min=bl_price_min,
            whitelist_names=wl_names,
        )
        _progress("build_initial_squad done")
        init_ids = init_res["player_ids"]
        init_pred = preds[preds["player_id"].isin(init_ids)].copy()
        _progress("solve_starting_xi for initial suggestion begin")
        xi_initial = solve_starting_xi(init_pred)
        _progress("solve_starting_xi for initial suggestion done")
        # 顶部展示直接采用初始阵容的 XI/Bench，避免空表
        xi = xi_initial
    else:
        _progress("solve_starting_xi begin")
        xi = solve_starting_xi(current_pred)
        _progress("solve_starting_xi done")
        skip_transfers = False

    # transfers（尊重黑名单/高价阈值，与 CLI 行为保持一致）
    bl_names: list[str] | None = None
    bl_price_min: float | None = None
    cfg_path = Path("configs/base.yaml")
    wl_names_for_transfer: list[str] | None = None
    if cfg_path.exists():
        n, p = _load_blacklist(cfg_path)
        bl_names, bl_price_min = n, p
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg_wh = yaml.safe_load(f) or {}
            wl = (cfg_wh.get("whitelist") or {}).get("names")
            if isinstance(wl, list) and len(wl) > 0:
                wl_names_for_transfer = [str(x) for x in wl]
        except Exception:
            wl_names_for_transfer = None
    # 读取买入价（用于更贴近真实预算/队值计算）
    purchase_prices: dict[int, float] = {}
    try:
        with open(squad_file, encoding="utf-8") as f:
            sdata_pp = yaml.safe_load(f) or {}
        pp = sdata_pp.get("purchase_prices") or {}
        purchase_prices = {int(k): float(v) for k, v in pp.items()}
    except Exception:
        purchase_prices = {}

    if skip_transfers:
        res = {"baseline_points": 0.0}
        bp = {
            "transfers": 0,
            "hit_cost": 0,
            "out_ids": [],
            "in_ids": [],
            "new_points": 0.0,
            "net_gain": 0.0,
            "team_value_now": 0.0,
            "team_value_after": 0.0,
        }
    else:
        _progress("best_transfers begin")
        res = best_transfers(
            preds,
            squad,
            blacklist_names=bl_names,
            blacklist_price_min=bl_price_min,
            whitelist_names=wl_names_for_transfer,
            price_now_market=preds.set_index("player_id")["price_now"].to_dict(),
            purchase_prices=purchase_prices,
            value_weight=0.0,
        )
        _progress("best_transfers done")
        bp = res["best_plan"]
        # 计算转会后的 XI/Bench
        try:
            after_ids = bp.get("new_squad_ids", [])
            after_pred = preds[preds["player_id"].isin(after_ids)].copy()
            _progress("solve_starting_xi for after-transfers begin")
            xi_after = solve_starting_xi(after_pred)
            _progress("solve_starting_xi for after-transfers done")
        except Exception:
            xi_after = None

    # chips
    _progress("suggest_chips begin")
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
    _progress("suggest_chips done")

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

    if skip_transfers:
        lines.append("## Initial Squad Suggestion")
        lines.append(
            f"- Budget: **{init_budget:.1f}** — Cost: **{init_res['cost']:.1f}**, Bank: **{init_res['bank']:.1f}**"
        )
        # 黑/白名单快照（便于可解释）
        try:
            _cfg = {}
            if Path("configs/base.yaml").exists():
                with open(Path("configs/base.yaml"), encoding="utf-8") as f:
                    _cfg = yaml.safe_load(f) or {}
            bls = (_cfg.get("blacklist") or {}).get("names")
            blp = (_cfg.get("blacklist") or {}).get("price_min")
            wls = (_cfg.get("whitelist") or {}).get("names")
            lines.append(f"- Blacklist: names={bls} price_min={blp}")
            lines.append(f"- Whitelist: names={wls}")
        except Exception:
            pass
        lines.append("")
        lines.append(f"- Formation: **{xi_initial['formation']}**")
        lines.append("| Player | Pos | Team | EP |")
        lines.append("|---|---|---|---:|")
        for pid in xi_initial["starting_ids"]:
            lines.append(f"| {name(pid)} | {pos_of(pid)} | {team_of(pid)} | {ep_of(pid):.2f} |")
        bench_ep_init = (
            sum(ep_of(pid) for pid in xi_initial.get("bench_ids", []))
            if xi_initial.get("bench_ids")
            else 0.0
        )
        lines.append(f"\n> Bench EP total: **{bench_ep_init:.2f}**")
        lines.append("")
        # 输出初始建议的替补表格
        if xi_initial.get("bench_ids"):
            lines.append("### Bench (Initial Suggestion)")
            lines.append("| Player | Pos | Team | EP |")
            lines.append("|---|---|---|---:|")
            for pid in xi_initial["bench_ids"]:
                lines.append(f"| {name(pid)} | {pos_of(pid)} | {team_of(pid)} | {ep_of(pid):.2f} |")
            lines.append("")
        lines.append("## Transfers Suggestion")
        lines.append("- 初始阵容未提供（非 15 人），转会建议不适用。")
    else:
        lines.append("## Transfers Suggestion")
        lines.append(f"- Baseline XI pts: **{res['baseline_points']:.2f}**")
        lines.append(
            f"- Team Value (now → after): **{res['best_plan']['team_value_now']:.2f} → {res['best_plan']['team_value_after']:.2f}**"
        )
        if bp["transfers"] == 0:
            lines.append("- **Best plan**: Keep (0 transfers).")
        else:
            lines.append(
                f"- **Best plan**: {bp['transfers']} transfer(s), hit cost {bp['hit_cost']}"
            )
            out_names = ", ".join(name(i) for i in bp["out_ids"])
            in_names = ", ".join(name(i) for i in bp["in_ids"])
            lines.append(f"- Out: {out_names}")
            lines.append(f"- In : {in_names}")
            lines.append(f"- New XI pts: **{bp['new_points']:.2f}**")
            lines.append(f"- Net gain (after hits): **{bp['net_gain']:.2f}**")
        # 展示转会后建议首发/替补
        if xi_after:
            lines.append("")
            lines.append("### Proposed XI After Transfers")
            lines.append(f"- Formation: **{xi_after['formation']}**")
            lines.append(f"- Captain: **{name(xi_after['captain_id'])}**")
            lines.append(f"- Vice: **{name(xi_after['vice_id'])}**")
            lines.append(
                f"- Expected XI points (incl. C): **{xi_after['expected_points_xi_with_captain']:.2f}**"
            )
            lines.append("")
            lines.append("| Player | Pos | Team | EP |")
            lines.append("|---|---|---|---:|")
            for pid in xi_after["starting_ids"]:
                lines.append(f"| {name(pid)} | {pos_of(pid)} | {team_of(pid)} | {ep_of(pid):.2f} |")
            lines.append("")
            lines.append("### Bench (After Transfers)")
            lines.append("| Player | Pos | Team | EP |")
            lines.append("|---|---|---|---:|")
            for pid in xi_after["bench_ids"]:
                lines.append(f"| {name(pid)} | {pos_of(pid)} | {team_of(pid)} | {ep_of(pid):.2f} |")
            bench_ep_after = sum(ep_of(pid) for pid in xi_after["bench_ids"])
            lines.append(f"\n> Bench EP total: **{bench_ep_after:.2f}**")
    lines.append("")

    lines.append("## Chips")
    for k, v in chips.items():
        status = "YES ✅" if v["recommended"] else "no"
        lines.append(f"- **{k}**: {status} — {v['reason']}  `{v['metrics']}`")

    # Model performance snapshot (if metrics.json exists)
    metrics_path = out_dir / f"gw{gw:02d}" / "metrics.json"
    if metrics_path.exists():
        lines.extend(_render_model_performance_section(metrics_path))

    # Cumulative scoring summary across gameweeks
    try:
        import glob
        import json as _json

        import pandas as _pd

        # Collect all metrics files to build cumulative summary
        metrics_files = glob.glob(str(out_dir / "gw*" / "metrics.json"))
        if metrics_files:
            scoring_data = []
            for metrics_file in sorted(metrics_files):
                try:
                    with open(metrics_file, encoding="utf-8") as f:
                        metrics = _json.load(f)
                    gw_num = metrics.get("gw", 0)
                    team_perf = metrics.get("team_performance", {})

                    if team_perf:
                        scoring_data.append(
                            {
                                "gw": gw_num,
                                "predicted": team_perf.get("predicted_total", 0),
                                "actual": team_perf.get("actual_total", 0),
                                "error": team_perf.get("prediction_error", 0),
                            }
                        )
                except Exception:
                    continue

            if scoring_data and len(scoring_data) > 1:
                df = _pd.DataFrame(scoring_data)
                lines.append("")
                lines.append("### Cumulative Performance")

                total_predicted = df["predicted"].sum()
                total_actual = df["actual"].sum()
                total_error = df["error"].sum()
                avg_weekly_actual = df["actual"].mean()

                lines.append(
                    f"- **Total Points ({len(df)} GWs)**: {total_actual:.0f} (predicted: {total_predicted:.1f})"
                )
                lines.append(f"- **Average Per GW**: {avg_weekly_actual:.1f} points")
                lines.append(f"- **Cumulative Error**: {total_error:+.1f} points")

                # Recent form
                if len(df) >= 3:
                    recent_3 = df.tail(3)
                    recent_avg = recent_3["actual"].mean()
                    lines.append(f"- **Recent 3 GW Average**: {recent_avg:.1f} points")

                # Best and worst gameweeks
                best_gw = df.loc[df["actual"].idxmax()]
                worst_gw = df.loc[df["actual"].idxmin()]
                lines.append(
                    f"- **Best GW**: GW{best_gw['gw']:.0f} ({best_gw['actual']:.0f} points)"
                )
                lines.append(
                    f"- **Worst GW**: GW{worst_gw['gw']:.0f} ({worst_gw['actual']:.0f} points)"
                )

    except Exception:
        pass

    # Rolling average (if history exists)
    hist_path = Path("data/processed/metrics_history.parquet")
    if hist_path.exists():
        try:
            import pandas as _pd

            hist = _pd.read_parquet(hist_path)
            if not hist.empty:
                last_n = 5
                recent = hist.tail(last_n)
                mae_avg = float(_pd.to_numeric(recent["mae"], errors="coerce").mean())
                ndcg_avg = float(_pd.to_numeric(recent["ndcg_at_11"], errors="coerce").mean())
                lines.append("")
                lines.append(
                    f"> Recent {min(len(recent), last_n)} GWs avg — MAE: **{mae_avg:.3f}**, NDCG@11: **{ndcg_avg:.3f}**"
                )
        except Exception:
            pass

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gw{gw:02d}" / "report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _progress("writing report.md")
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
        "transfers": (
            {
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
                "new_squad_ids": [int(x) for x in bp.get("new_squad_ids", [])],
            }
            if not skip_transfers
            else {"skipped": True, "reason": "initial squad missing (need 15)"}
        ),
        "xi_after": (
            {
                "starting_ids": xi_after["starting_ids"],
                "bench_ids": xi_after["bench_ids"],
                "captain_id": xi_after["captain_id"],
                "vice_id": xi_after["vice_id"],
                "expected_points_xi_with_captain": float(
                    xi_after["expected_points_xi_with_captain"]
                ),
            }
            if (not skip_transfers and xi_after)
            else None
        ),
        "initial_squad": (
            {
                "player_ids": init_res["player_ids"],
                "cost": float(init_res["cost"]),
                "bank": float(init_res["bank"]),
                "xi": {
                    "starting_ids": xi_initial["starting_ids"],
                    "bench_ids": xi_initial["bench_ids"],
                    "captain_id": xi_initial["captain_id"],
                    "vice_id": xi_initial["vice_id"],
                    "formation": xi_initial["formation"],
                },
            }
            if skip_transfers
            else None
        ),
        "chips": chips,
        "thresholds": {
            "bench_boost_min_bench_ep": float(thresholds.bench_boost_min_bench_ep),
            "triple_captain_min_ep": float(thresholds.triple_captain_min_ep),
            "triple_captain_min_ep_if_double": float(thresholds.triple_captain_min_ep_if_double),
            "free_hit_min_active_starters": int(thresholds.free_hit_min_active_starters),
        },
        "blacklist": {"names": bl_names, "price_min": bl_price_min},
        "whitelist": {
            "names": wl_names_for_transfer,
        },
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

    _progress("writing summary.json")
    summary_path = out_dir / f"gw{gw:02d}" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    typer.echo(f"✅ wrote {summary_path}")


if __name__ == "__main__":
    app()
