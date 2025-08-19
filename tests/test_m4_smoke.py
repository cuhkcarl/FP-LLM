from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from optimizer.ilp import solve_starting_xi
from optimizer.transfers import Squad, best_transfers
from scripts.generate_report import main as gen_report_main


def _toy_predictions() -> pd.DataFrame:
    # 构造一个最小可行的 30 人池（确保能组成 15 人阵容与候选）
    rows = []
    pid = 1
    # 2 GK, 10 DEF, 10 MID, 8 FWD，team_id 均匀分布 1..6
    for pos, n, base_ep in [("GK", 6, 3.5), ("DEF", 10, 4.0), ("MID", 10, 5.0), ("FWD", 8, 5.2)]:
        for _ in range(n):
            rows.append(
                dict(
                    player_id=pid,
                    web_name=f"P{pid}",
                    team_id=1 + (pid % 6),
                    team_short=f"T{1 + (pid % 6)}",
                    position=pos,
                    price_now=4.0 + (pid % 7) * 0.5,
                    expected_points=base_ep + (pid % 5) * 0.6,
                    availability_score=0.9,
                )
            )
            pid += 1
    return pd.DataFrame(rows)


def _toy_squad_ids(preds: pd.DataFrame) -> list[int]:
    # 简单挑前 15 个，但强制满足 2/5/5/3 配额
    gk = preds[preds["position"] == "GK"]["player_id"].head(2).tolist()
    de = preds[preds["position"] == "DEF"]["player_id"].head(5).tolist()
    mi = preds[preds["position"] == "MID"]["player_id"].head(5).tolist()
    fw = preds[preds["position"] == "FWD"]["player_id"].head(3).tolist()
    return gk + de + mi + fw


def test_ilp_selects_starting_xi_and_captain(tmp_path: Path):
    preds = _toy_predictions()
    squad_ids = _toy_squad_ids(preds)
    df = preds[preds["player_id"].isin(squad_ids)].copy()
    res = solve_starting_xi(df)
    assert len(res["starting_ids"]) == 11
    assert isinstance(res["captain_id"], int)


def test_best_transfers_respects_blacklist(tmp_path: Path):
    preds = _toy_predictions()
    squad_ids = _toy_squad_ids(preds)
    squad = Squad(player_ids=squad_ids, bank=5.0, free_transfers=1)
    # 人为将一个高 EP 的候选加入黑名单
    black_name = preds.sort_values("expected_points", ascending=False)["web_name"].iloc[0]
    out = best_transfers(
        preds,
        squad,
        pool_size=8,
        max_transfers=1,
        hit_cost=4,
        blacklist_names=[black_name],
        blacklist_price_min=None,
    )
    bp = out["best_plan"]
    assert black_name not in preds.set_index("player_id").loc[bp["in_ids"], "web_name"].tolist()


def test_generate_report_produces_markdown_with_final_newline(tmp_path: Path, monkeypatch):
    # 准备假数据目录结构
    data_dir = tmp_path / "data"
    (data_dir / "processed").mkdir(parents=True, exist_ok=True)
    (data_dir / "interim").mkdir(parents=True, exist_ok=True)

    preds = _toy_predictions()
    preds.to_parquet(data_dir / "processed" / "predictions_gw01.parquet", index=False)

    # fixtures 可选，这里写空表
    pd.DataFrame(columns=["event", "team_h", "team_a"]).to_parquet(
        data_dir / "interim" / "fixtures_clean.parquet", index=False
    )

    # 写 squad.yaml
    squad_yaml = tmp_path / "squad.yaml"
    yaml.safe_dump(
        {
            "squad": _toy_squad_ids(preds),
            "bank": 2.0,
            "free_transfers": 1,
            "chips_available": {
                "bench_boost": True,
                "triple_captain": True,
                "free_hit": True,
                "wildcard": True,
            },
        },
        open(squad_yaml, "w", encoding="utf-8"),
        sort_keys=False,
        allow_unicode=True,
    )

    # 生成报告
    out_dir = tmp_path / "reports"
    gen_report_main(
        gw=1,
        data_dir=data_dir,
        squad_file=squad_yaml,
        out_dir=out_dir,
    )
    out_path = out_dir / "gw01" / "report.md"
    assert out_path.exists()
    # 末行要有换行，避免 EOF fixer 反复修改
    with open(out_path, "rb") as f:
        content = f.read()
    assert content.endswith(b"\n")
