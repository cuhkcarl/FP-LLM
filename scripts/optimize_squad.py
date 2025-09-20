from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer
import yaml

from optimizer.chips import ChipThresholds, suggest_chips
from optimizer.dgw import DGWParams, adjust_expected_points_for_gw
from optimizer.finance import selling_price
from optimizer.ilp import BenchOrderParams, solve_starting_xi
from optimizer.transfers import best_transfers, load_squad_yaml

app = typer.Typer(add_completion=False)


def _name_lookup(preds: pd.DataFrame):
    pidx = preds.set_index("player_id")

    def name(pid: int) -> str:
        return str(pidx.loc[pid, "web_name"]) if pid in pidx.index else str(pid)

    return name


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


def _resolve_captain_thresholds(
    df: pd.DataFrame,
    min_minutes: float | None,
    min_price: float | None,
    label: str,
) -> tuple[float | None, float | None]:
    cap_minutes = min_minutes
    cap_price = min_price
    if df.empty:
        return None, None
    mask = pd.Series(True, index=df.index)
    if cap_minutes is not None and "minutes" in df.columns:
        mask &= df["minutes"].fillna(0.0) >= cap_minutes
    if cap_price is not None and "price_now" in df.columns:
        mask &= df["price_now"].fillna(0.0) >= cap_price
    if not mask.any():
        typer.echo(
            f"[warn] {label}: captain thresholds filtered out all players; falling back to defaults"
        )
        return None, None
    return cap_minutes, cap_price


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
    respect_blacklist: Annotated[
        bool,
        typer.Option(
            "--respect-blacklist/--no-respect-blacklist",
            help="是否遵从 configs/base.yaml 的黑名单/高价阈值",
        ),
    ] = True,
    use_dgw_adjust: Annotated[
        bool,
        typer.Option("--use-dgw-adjust/--no-dgw-adjust", help="是否对双赛/上场风险做期望分调整"),
    ] = True,
    bench_weight_availability: Annotated[
        float, typer.Option(help="替补排序中 availability 的权重（默认 0.5）")
    ] = 0.5,
    suggest_chips_flag: Annotated[
        bool,
        typer.Option("--suggest-chips/--no-suggest-chips", help="是否输出筹码建议"),
    ] = True,
    value_weight: Annotated[
        float, typer.Option(help="净增分平手时按队值增减破除（或多目标权重）。0 表示仅用作平手破除")
    ] = 0.0,
    min_bank_after: Annotated[
        float | None, typer.Option(help="转会执行后银行余额下限（可选）")
    ] = None,
    max_tv_drop: Annotated[
        float | None, typer.Option(help="允许的队值最大下降（m，默认不限制）")
    ] = None,
    captain_min_minutes: Annotated[
        float | None,
        typer.Option(help="队长候选需达到的分钟阈值（总分钟，默认不限制)"),
    ] = None,
    captain_min_price: Annotated[
        float | None,
        typer.Option(help="队长候选需达到的身价阈值（m，默认不限制)"),
    ] = None,
):
    """
    M4：基于预测结果与当前 15 人阵容，给出首发/队长、0/1/2 次转会建议，并（可选）输出筹码与 DGW 调整。
    """
    # ---------- 读取预测 ----------
    in_name = f"predictions_gw{gw:02d}.parquet" if gw is not None else "predictions.parquet"
    pred_path = data_dir / "processed" / in_name
    preds_raw = pd.read_parquet(pred_path)

    # fixtures
    fixtures_path = data_dir / "interim" / "fixtures_clean.parquet"
    fixtures = pd.read_parquet(fixtures_path) if fixtures_path.exists() else None

    preds = preds_raw.copy()

    # ---------- 读取 squad 与买入价 ----------
    squad = load_squad_yaml(squad_file)
    current_ids = [int(x) for x in squad.player_ids]

    # ---------- 冷启动保护：若不是 15 人阵容，跳过转会与首发 ----------
    if len(current_ids) != 15:
        typer.echo("\n=== Initial Squad Missing ===")
        typer.echo(
            f"Provided squad has {len(current_ids)} players (need 15). Skipping XI and transfer search."
        )
        typer.echo(
            "Please configure configs/squad.yaml with 15 player_ids for normal optimization."
        )
        return

    # 从 YAML 取 purchase_prices（可选）
    purchase_prices: dict[int, float] = {}
    try:
        with open(squad_file, encoding="utf-8") as f:
            sdata = yaml.safe_load(f) or {}
        pp = sdata.get("purchase_prices") or {}
        purchase_prices = {int(k): float(v) for k, v in pp.items()}
    except Exception:
        purchase_prices = {}

    # ---------- 用“卖出价”替换我方阵容成员的 price_now（仅用于转会预算评估） ----------
    price_map = preds.set_index("player_id")["price_now"].to_dict()
    for pid in current_ids:
        cur = float(price_map.get(pid, 0.0))
        buy = float(purchase_prices.get(pid, cur))  # 未提供买入价则认为无涨跌
        sell = selling_price(cur, buy)
        preds.loc[preds["player_id"] == pid, "price_now"] = sell

    # ---------- DGW 调整（不改价，只改 EP） ----------
    if use_dgw_adjust and gw is not None and fixtures is not None:
        preds = adjust_expected_points_for_gw(preds, fixtures, gw, DGWParams())

    # ---------- 优化器默认参数（含队长阈值） ----------
    try:
        cfg_path = Path("configs/base.yaml")
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg_opt: dict[str, Any] = yaml.safe_load(f) or {}
            opt_cfg = cfg_opt.get("optimizer") or {}
            if value_weight == 0.0 and "value_weight" in opt_cfg:
                value_weight = float(opt_cfg.get("value_weight", value_weight))
            if min_bank_after is None and opt_cfg.get("min_bank_after") is not None:
                min_bank_after = float(opt_cfg.get("min_bank_after"))
            if max_tv_drop is None and opt_cfg.get("max_tv_drop") is not None:
                max_tv_drop = float(opt_cfg.get("max_tv_drop"))
            if captain_min_minutes is None and opt_cfg.get("captain_min_minutes") is not None:
                captain_min_minutes = float(opt_cfg.get("captain_min_minutes"))
            if captain_min_price is None and opt_cfg.get("captain_min_price") is not None:
                captain_min_price = float(opt_cfg.get("captain_min_price"))
    except Exception:
        pass

    # ---------- 当前 XI 与替补 ----------
    squad_pred = preds[preds["player_id"].isin(current_ids)].copy()
    cap_minutes, cap_price = _resolve_captain_thresholds(
        squad_pred, captain_min_minutes, captain_min_price, "current XI"
    )

    xi = solve_starting_xi(
        squad_pred,
        bench_params=BenchOrderParams(weight_availability=bench_weight_availability),
        captain_min_minutes=cap_minutes,
        captain_min_price=cap_price,
    )

    # ---------- 黑名单（可选） ----------
    blacklist_names: list[str] | None = None
    blacklist_price_min: float | None = None
    if respect_blacklist:
        bl_names, bl_price = _load_blacklist(Path("configs/base.yaml"))
        blacklist_names, blacklist_price_min = bl_names, bl_price
    # 读取配置白名单
    whitelist_names: list[str] | None = None
    try:
        cfg_path = Path("configs/base.yaml")
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            wl = (cfg.get("whitelist") or {}).get("names")
            if isinstance(wl, list) and len(wl) > 0:
                whitelist_names = [str(x) for x in wl]
    except Exception:
        whitelist_names = None

    # ---------- 从 base.yaml 读取优化器默认参数（若存在） ----------
    # ---------- 转会枚举（此时 preds 的我方成员 price_now 已是卖出价） ----------
    result = best_transfers(
        preds,
        squad,
        pool_size=pool_size,
        max_transfers=max_transfers,
        hit_cost=hit_cost,
        blacklist_names=blacklist_names,
        blacklist_price_min=blacklist_price_min,
        whitelist_names=whitelist_names,
        price_now_market=preds_raw.set_index("player_id")["price_now"].to_dict(),
        purchase_prices=purchase_prices,
        value_weight=value_weight,
        min_bank_after=min_bank_after,
        max_tv_drop=max_tv_drop,
        captain_min_minutes=cap_minutes,
        captain_min_price=cap_price,
    )

    # ---------- 输出摘要 ----------
    name = _name_lookup(preds)
    typer.echo("\n=== Current XI (with captain) ===")
    typer.echo(f"Formation: {xi['formation']}")
    typer.echo(f"Captain: {name(xi['captain_id'])}")
    typer.echo(f"Vice:    {name(xi['vice_id'])}")
    typer.echo(f"Expected XI pts (incl. C): {xi['expected_points_xi_with_captain']:.2f}")

    # 输出当前队值（来自 best_transfers 统一口径）
    typer.echo(f"Current Team Value: {result['best_plan']['team_value_now']:.2f}")

    typer.echo("\n=== Transfers Suggestion ===")
    typer.echo(f"Baseline XI pts: {result['baseline_points']:.2f}")
    bp = result["best_plan"]
    if bp["transfers"] == 0:
        typer.echo("Best: Keep (0 transfers).")
    else:
        typer.echo(f"Best: {bp['transfers']} transfer(s), hit cost {bp['hit_cost']}")
        typer.echo(f"Out: {[name(i) for i in bp['out_ids']]}")
        typer.echo(f"In : {[name(i) for i in bp['in_ids']]}")

        # 输出计划执行后的资金与队值（来自 best_transfers 统一口径）
        typer.echo(f"Funds after plan (bank): {bp['bank_after']:.1f}m")
        typer.echo(
            f"New Team Value (after transfers): {bp['team_value_after']:.2f} (Δ {bp['team_value_delta']:+.2f})"
        )

        typer.echo(f"New XI pts: {bp['new_points']:.2f}")
        typer.echo(f"Net gain vs baseline (after hits): {bp['net_gain']:.2f}")

    # ---------- 筹码建议（可选） ----------
    if suggest_chips_flag and gw is not None:
        # 读取 chips 阈值
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
            chips_available=(
                getattr(squad, "chips_available", {}) if hasattr(squad, "chips_available") else {}
            ),
            thresholds=thresholds,
        )

        typer.echo("\n=== Chips Suggestion ===")
        for k, v in chips.items():
            status = "YES" if v["recommended"] else "no"
            typer.echo(f"{k}: {status} — {v['reason']}  {v['metrics']}")


if __name__ == "__main__":
    app()
