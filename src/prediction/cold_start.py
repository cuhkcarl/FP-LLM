from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ColdStartParams:
    availability_floor: float = 0.5
    status_penalty: float = 0.8
    beta_fixture: float = 0.15
    min_minutes_last_threshold: float = 450.0
    minutes_penalty_factor: float = 0.5


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def compute_cold_start_ep(
    *,
    bootstrap_players: pd.DataFrame,
    last_season_totals: pd.DataFrame,
    fixtures: pd.DataFrame | None,
    gw: int,
    params: ColdStartParams | None = None,
) -> pd.DataFrame:
    params = params or ColdStartParams()
    p = bootstrap_players.copy()
    t = last_season_totals.copy()
    p["player_id"] = p["id"].astype(int)
    t["player_id"] = t["player_id"].astype(int)

    df = p.merge(t, on="player_id", how="left", suffixes=("_now", "_last"))
    # 使用上赛季的分钟与总分（带后缀 _last）；若不存在则回退到无后缀或 0
    if "minutes_last" in df.columns:
        minutes = _safe_num(df["minutes_last"]).clip(lower=0.0)
    elif "minutes" in df.columns:
        minutes = _safe_num(df["minutes"]).clip(lower=0.0)
    else:
        minutes = pd.Series(0.0, index=df.index)

    if "total_points_last" in df.columns:
        total_points = _safe_num(df["total_points_last"]).clip(lower=0.0)
    elif "total_points" in df.columns:
        total_points = _safe_num(df["total_points"]).clip(lower=0.0)
    else:
        total_points = pd.Series(0.0, index=df.index)

    df["pp90_last"] = np.where(minutes > 0, total_points / minutes * 90.0, 0.0)
    df["reliability"] = (minutes / 3420.0).clip(0.0, 1.0)
    df["minutes_last"] = minutes

    # position labels
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["position"] = df["element_type"].map(pos_map)
    df = df.dropna(subset=["position"]).copy()

    # z-score within position
    cs_vals = []
    for pos, sub in df.groupby("position", group_keys=False):
        x = sub["pp90_last"].to_numpy(dtype=float)
        mean = float(np.mean(x))
        std = float(np.std(x)) or 1e-6
        z = (x - mean) / std
        base_by_pos = {"GK": 3.4, "DEF": 3.7, "MID": 4.5, "FWD": 4.8}
        spread_by_pos = {"GK": 1.1, "DEF": 1.2, "MID": 1.4, "FWD": 1.4}
        ep_raw = base_by_pos[pos] + spread_by_pos[pos] * z
        ep_raw = np.clip(ep_raw, 0.0, 12.0)
        rel = sub["reliability"].to_numpy(dtype=float)
        avail = np.maximum(rel, params.availability_floor)
        # status/news penalty
        status = sub["status"].astype(str).to_numpy()
        news = sub.get("news", pd.Series(["" for _ in range(len(sub))])).astype(str).to_numpy()
        status_pen = np.where((status != "a") | (news != ""), params.status_penalty, 1.0)
        ep = ep_raw * avail * status_pen
        # 对上季分钟过低者施加额外折扣
        mins = sub["minutes_last"].to_numpy(dtype=float)
        ep = np.where(
            mins < params.min_minutes_last_threshold, ep * params.minutes_penalty_factor, ep
        )
        tmp = sub.copy()
        tmp["cs_ep"] = ep
        cs_vals.append(tmp)
    out = pd.concat(cs_vals, axis=0, ignore_index=True)

    # mild fixture scaling for first K GWs (optional, here omitted or set beta small; fixtures could be integrated later)

    # final columns for compatibility
    out = out.rename(
        columns={
            "now_cost": "price_now",
            "web_name": "web_name",
            "team": "team_id",
            "team_code": "team_code",
        }
    )
    out["price_now"] = _safe_num(out["price_now"]) / 10.0
    out = out[
        [
            "player_id",
            "web_name",
            "team_id",
            "element_type",
            "position",
            "price_now",
            "cs_ep",
            "minutes_last",
        ]
    ].copy()
    return out
