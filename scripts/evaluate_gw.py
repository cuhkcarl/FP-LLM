from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from metrics.evaluate import MetricParams, compute_team_score, write_metrics_json

app = typer.Typer(add_completion=False)


@app.command()
def main(
    gw: Annotated[int, typer.Option(help="评估目标 GW")],
    data_dir: Annotated[Path, typer.Option(help="数据目录")] = Path("data"),
    out_dir: Annotated[Path, typer.Option(help="报告目录")] = Path("reports"),
    k_for_ndcg: Annotated[int, typer.Option(help="NDCG@K 的 K 值")] = 11,
):
    preds = pd.read_parquet(data_dir / "processed" / f"predictions_gw{gw:02d}.parquet")
    actuals = pd.read_parquet(data_dir / "processed" / f"actuals_gw{gw:02d}.parquet")

    # Load existing metrics and add team scoring if summary exists
    out_path = out_dir / f"gw{gw:02d}" / "metrics.json"
    metrics_payload = write_metrics_json(
        gw=gw,
        preds=preds,
        actuals=actuals,
        out_path=out_path,
        params=MetricParams(k_for_ndcg=k_for_ndcg),
    )

    # Try to add actual team scoring information from summary.json
    summary_path = out_dir / f"gw{gw:02d}" / "summary.json"
    if summary_path.exists():
        try:
            with open(summary_path, encoding="utf-8") as f:
                summary = json.load(f)

            # Calculate actual scores for recommended team
            xi_info = summary.get("xi", {})
            starting_ids = xi_info.get("starting_ids", [])
            captain_id = xi_info.get("captain_id")
            bench_ids = xi_info.get("bench_ids", [])

            if starting_ids and captain_id:
                team_actual = compute_team_score(starting_ids, captain_id, actuals, bench_ids)

                # Calculate prediction accuracy for the team
                predicted_total = xi_info.get("expected_points_xi_with_captain", 0)
                actual_total = team_actual["total_score"]

                metrics_payload["team_performance"] = {
                    "predicted_total": predicted_total,
                    "actual_total": actual_total,
                    "prediction_error": actual_total - predicted_total,
                    "prediction_accuracy": abs(actual_total - predicted_total),
                    **team_actual,
                }

                # Also check transfers if applicable
                transfers = summary.get("transfers", {})
                if not transfers.get("skipped") and summary.get("xi_after"):
                    xi_after = summary["xi_after"]
                    after_starting_ids = xi_after.get("starting_ids", [])
                    after_captain_id = xi_after.get("captain_id")

                    if after_starting_ids and after_captain_id:
                        after_actual = compute_team_score(
                            after_starting_ids, after_captain_id, actuals
                        )
                        after_predicted = xi_after.get("expected_points_xi_with_captain", 0)

                        metrics_payload["transfer_performance"] = {
                            "predicted_gain": transfers.get("net_gain", 0),
                            "actual_gain": after_actual["total_score"] - team_actual["total_score"],
                            "after_predicted_total": after_predicted,
                            "after_actual_total": after_actual["total_score"],
                            **after_actual,
                        }

                # Re-write the enhanced metrics
                out_path.write_text(
                    json.dumps(metrics_payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

        except Exception as e:
            typer.echo(f"[warn] Could not add team scoring: {e}")

    typer.echo(f"✅ wrote {out_path}")


if __name__ == "__main__":
    app()
