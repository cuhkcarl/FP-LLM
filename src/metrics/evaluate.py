from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MetricParams:
    k_for_ndcg: int = 11


def _dcg(rels: np.ndarray) -> float:
    if rels.size == 0:
        return 0.0
    ranks = np.arange(1, rels.size + 1)
    return float(np.sum((2**rels - 1) / np.log2(ranks + 1)))


def _ndcg_at_k(pred_scores: np.ndarray, true_scores: np.ndarray, k: int) -> float:
    k = int(min(k, pred_scores.size))
    if k == 0:
        return 0.0
    order_pred = np.argsort(-pred_scores)[:k]
    rels_pred = true_scores[order_pred]
    rels_ideal = np.sort(true_scores)[::-1][:k]
    dcg = _dcg(rels_pred)
    idcg = _dcg(rels_ideal)
    return float(dcg / idcg) if idcg > 0 else 0.0


def compute_metrics(
    preds: pd.DataFrame, actuals: pd.DataFrame, params: MetricParams | None = None
) -> dict:
    params = params or MetricParams()
    p = preds.copy()
    a = actuals.copy()
    p["player_id"] = p["player_id"].astype(int)
    a["player_id"] = a["player_id"].astype(int)
    df = p.merge(a[["player_id", "total_points"]], on="player_id", how="inner")
    df = df.rename(columns={"total_points": "actual_points"})

    # overall
    y_pred = df["expected_points"].to_numpy(dtype=float)
    y_true = df["actual_points"].to_numpy(dtype=float)
    mae = float(np.mean(np.abs(y_pred - y_true)))
    rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))
    # 计算 Spearman：对两个序列分别取秩，再计算 Pearson 相关（避免 SciPy 依赖）
    r_pred = pd.Series(y_pred).rank(method="average")
    r_true = pd.Series(y_true).rank(method="average")
    spearman = float(pd.Series(r_pred).corr(pd.Series(r_true), method="pearson"))
    ndcg11 = _ndcg_at_k(y_pred, y_true, params.k_for_ndcg)

    overall = {"mae": mae, "rmse": rmse, "spearman": spearman, "ndcg_at_11": ndcg11}

    def _by_pos() -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for pos in ["GK", "DEF", "MID", "FWD"]:
            sub = df[df["position"] == pos]
            if sub.empty:
                continue
            yp = sub["expected_points"].to_numpy(dtype=float)
            yt = sub["actual_points"].to_numpy(dtype=float)
            out[pos] = {
                "mae": float(np.mean(np.abs(yp - yt))),
                "rmse": float(np.sqrt(np.mean((yp - yt) ** 2))),
                "ndcg_at_11": _ndcg_at_k(yp, yt, params.k_for_ndcg),
            }
        return out

    return {"overall": overall, "by_pos": _by_pos()}


def write_metrics_json(
    *,
    gw: int,
    preds: pd.DataFrame,
    actuals: pd.DataFrame,
    out_path: Path,
    params: MetricParams | None = None,
) -> dict[str, Any]:
    import json

    metrics = compute_metrics(preds, actuals, params)
    payload = {"gw": int(gw), **metrics}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
