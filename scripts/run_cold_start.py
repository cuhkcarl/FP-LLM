from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

app = typer.Typer(add_completion=False)


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _read_cfg(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@app.command()
def main(
    gw: Annotated[int, typer.Option(help="从该 GW 启动（例如 2 表示赛季从 GW2 冷启动）")],
    mode: Annotated[str, typer.Option(help="预测模式：cold_start 或 blend")] = "blend",
    data_dir: Annotated[Path, typer.Option(help="数据根目录（raw/interim/processed）")] = Path(
        "data"
    ),
    out_reports: Annotated[Path, typer.Option(help="报告输出目录")] = Path("reports"),
    config_path: Annotated[Path, typer.Option(help="配置文件路径")] = Path("configs/base.yaml"),
    write_squad: Annotated[
        bool,
        typer.Option(
            "--write-squad/--no-write-squad", help="是否将冷启动产出回填 configs/squad.yaml"
        ),
    ] = True,
    update_current_gw: Annotated[
        bool,
        typer.Option(
            "--update-current-gw/--no-update-current-gw", help="是否更新 base.yaml 的 current_gw"
        ),
    ] = True,
):
    """
    一键冷启动入口：抓取→特征→预测（冷启动/融合）→建队（黑/白名单/预算）→报告/summary→（可选）评估。
    产物：
      - data/processed/predictions_gwXX.parquet
      - reports/gwXX/report.md 与 summary.json
    """

    cfg = _read_cfg(config_path)
    budget = float(((cfg.get("optimizer") or {}).get("squad_builder") or {}).get("budget", 100.0))

    # 1) 抓数（含 bootstrap-static / fixtures / live）
    _run(
        [
            sys.executable,
            "scripts/fetch_fpl.py",
            "--gw",
            str(gw),
            "--out-dir",
            str(data_dir / "raw" / "fpl"),
            "--force-refresh",
        ]
    )

    # 2) 上季汇总（若存在则跳过）
    _run([sys.executable, "scripts/fetch_last_season.py", "--skip-if-exists"])

    # 3) 特征（未来K场赛程、可用性、最近表现代理、FDR修正）
    _run([sys.executable, "scripts/build_features.py", "--gw", str(gw)])

    # 4) 预测（冷启动/融合）
    _run([sys.executable, "scripts/predict_points.py", "--gw", str(gw), "--mode", mode])

    # 5) 冷启动建队（读取黑/白名单、预算）
    preds_path = data_dir / "processed" / f"predictions_gw{gw:02d}.parquet"
    _run(
        [
            sys.executable,
            "scripts/build_squad.py",
            "--preds-path",
            str(preds_path),
            "--budget",
            f"{budget:.1f}",
            "--respect-blacklist",
            "--config-path",
            str(config_path),
        ]
    )

    # 6) 报告与summary.json（包含 Initial Squad Suggestion 或 Transfers 视情况）
    _run([sys.executable, "scripts/generate_report.py", "--gw", str(gw)])

    # 6.1) 可选：将初始阵容写回 configs/squad.yaml，并更新 current_gw
    if write_squad:
        try:
            import json as _json

            import pandas as _pd
            import yaml as _yaml

            summary_path = out_reports / f"gw{gw:02d}" / "summary.json"
            if summary_path.exists():
                summary = _json.loads(summary_path.read_text(encoding="utf-8"))
                init = summary.get("initial_squad")
                if init and init.get("player_ids"):
                    ids = [int(x) for x in init["player_ids"]]
                    pred_path = data_dir / "processed" / f"predictions_gw{gw:02d}.parquet"
                    pred = (
                        _pd.read_parquet(pred_path).set_index("player_id")
                        if pred_path.exists()
                        else None
                    )
                    purchase = {}
                    if pred is not None and not pred.empty and "price_now" in pred.columns:
                        for pid in ids:
                            if pid in pred.index:
                                purchase[int(pid)] = float(pred.at[int(pid), "price_now"])
                    squad_doc: dict[str, Any] = {
                        "squad": ids,
                        "bank": float(init.get("bank", 0.0)),
                        "free_transfers": 1,
                        "purchase_prices": purchase,
                        "chips_available": {
                            "bench_boost": True,
                            "triple_captain": True,
                            "free_hit": True,
                            "wildcard": True,
                        },
                    }
                    squad_path = Path("configs/squad.yaml")
                    squad_path.write_text(
                        _yaml.safe_dump(squad_doc, allow_unicode=True, sort_keys=False),
                        encoding="utf-8",
                    )
                    typer.echo(f"✅ wrote {squad_path}")
            # 更新 current_gw
            if update_current_gw and config_path.exists():
                cfg = _read_cfg(config_path)
                cfg["current_gw"] = int(gw)
                config_path.write_text(
                    yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8"
                )
                typer.echo(f"✅ updated current_gw={gw} in {config_path}")
        except Exception as e:
            typer.echo(f"[warn] write-back skipped: {e}")

    typer.echo("✅ cold-start pipeline completed.")


if __name__ == "__main__":
    app()
