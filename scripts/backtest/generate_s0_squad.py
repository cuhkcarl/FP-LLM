#!/usr/bin/env python3
"""
生成S0策略的群体智慧基准阵容

S0策略概念：
- 使用基于赛季开始时拥有率的预计算最优阵容
- 优化目标：最大化总拥有率百分比
- 约束：£100m预算，2GK/5DEF/5MID/3FWD，每队最多3人
"""

from pathlib import Path

import pandas as pd
import pulp
import yaml


def generate_s0_optimal_squad(gw1_data_path: str, season: str = "2023-24") -> dict:
    """
    基于GW1的拥有率数据生成S0最优阵容

    Args:
        gw1_data_path: GW1数据文件路径
        season: 赛季标识

    Returns:
        包含最优阵容信息的字典
    """
    # 加载GW1数据
    df = pd.read_csv(gw1_data_path)

    # 数据预处理
    df = df.copy()
    df["player_id"] = df["element"].astype(int)
    df["price"] = df["value"] / 10.0  # 转换为百万单位
    df["ownership"] = df["selected"]  # 拥有人数

    # 过滤有效球员（有价格且有名字）
    df = df.dropna(subset=["name", "value"])
    df = df[df["price"] > 0]

    print(f"数据加载完成: {len(df)} 名球员")
    print(f"位置分布: {df['position'].value_counts().to_dict()}")

    # 设置优化问题
    prob = pulp.LpProblem("S0_Optimal_Squad", pulp.LpMaximize)

    # 决策变量：每个球员是否被选择
    players = df["player_id"].tolist()
    x = pulp.LpVariable.dicts("player", players, cat="Binary")

    # 目标函数：最大化总拥有率
    prob += pulp.lpSum(
        [x[pid] * df.loc[df["player_id"] == pid, "ownership"].iloc[0] for pid in players]
    )

    # 约束1: 总预算不超过100M
    prob += (
        pulp.lpSum([x[pid] * df.loc[df["player_id"] == pid, "price"].iloc[0] for pid in players])
        <= 100.0
    )

    # 约束2: 总共15人
    prob += pulp.lpSum([x[pid] for pid in players]) == 15

    # 约束3: 位置要求
    for pos, (min_count, max_count) in [
        ("GK", (2, 2)),
        ("DEF", (5, 5)),
        ("MID", (5, 5)),
        ("FWD", (3, 3)),
    ]:
        pos_players = df[df["position"] == pos]["player_id"].tolist()
        prob += pulp.lpSum([x[pid] for pid in pos_players]) == min_count

    # 约束4: 每队最多3人
    for team in df["team"].unique():
        team_players = df[df["team"] == team]["player_id"].tolist()
        prob += pulp.lpSum([x[pid] for pid in team_players]) <= 3

    print("开始求解优化问题...")
    prob.solve(pulp.PULP_CBC_CMD(msg=True))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"优化求解失败: {pulp.LpStatus[prob.status]}")

    # 提取结果
    selected_ids = [pid for pid in players if pulp.value(x[pid]) > 0.5]
    selected_df = df[df["player_id"].isin(selected_ids)].copy()

    # 按拥有率排序
    selected_df = selected_df.sort_values("ownership", ascending=False)

    # 计算统计信息
    total_cost = selected_df["price"].sum()
    total_ownership = selected_df["ownership"].sum()
    team_distribution = selected_df["team"].value_counts().to_dict()

    print("\n=== 优化结果 ===")
    print(f"总成本: £{total_cost:.1f}M")
    print(f"剩余预算: £{100.0 - total_cost:.1f}M")
    print(f"总拥有率: {total_ownership:,}")
    print(f"球队分布: {team_distribution}")
    print("\n球员详情:")
    print(
        selected_df[["player_id", "name", "position", "team", "price", "ownership"]].to_string(
            index=False
        )
    )

    # 构建输出格式
    players_list = []
    for _, row in selected_df.iterrows():
        players_list.append(
            {
                "id": int(row["player_id"]),
                "name": row["name"],
                "position": row["position"],
                "team": row["team"],
            }
        )

    result = {
        "optimal_squad_"
        + season.replace("-", "_"): {
            "player_ids": [int(pid) for pid in selected_ids],
            "players": players_list,
            "metadata": {
                "season": season,
                "total_value_millions": round(total_cost, 1),
                "remaining_budget_millions": round(100.0 - total_cost, 1),
                "optimization_method": "crowd_wisdom_popularity",
                "constraints_satisfied": [
                    "exactly_15_players",
                    "budget_100m_limit",
                    "position_quota_2gk_5def_5mid_3fwd",
                    "max_3_per_team",
                ],
            },
            "team_distribution": team_distribution,
        }
    }

    return result


def main():
    """主函数"""
    # 数据路径
    gw1_path = "/Users/carl/workspace/FP-LLM/data/backtest/raw/vaastav/2023-24/gws/gw1.csv"
    output_path = "/Users/carl/workspace/FP-LLM/configs/backtest/s0_optimal_squad_generated.yaml"

    try:
        # 生成S0阵容
        result = generate_s0_optimal_squad(gw1_path, "2023-24")

        # 保存结果
        with open(output_path, "w") as f:
            yaml.dump(result, f, default_flow_style=False, sort_keys=False)

        print(f"\n✅ S0最优阵容已生成并保存到: {output_path}")

        # 与现有配置对比
        existing_path = "/Users/carl/workspace/FP-LLM/configs/backtest/s0_optimal_squad.yaml"
        if Path(existing_path).exists():
            with open(existing_path) as f:
                existing = yaml.safe_load(f)

            existing_ids = set(existing["optimal_squad_2023_24"]["player_ids"])
            new_ids = set(result["optimal_squad_2023_24"]["player_ids"])

            print("\n=== 与现有配置对比 ===")
            print(f"完全匹配: {existing_ids == new_ids}")
            if existing_ids != new_ids:
                print(f"仅在现有: {existing_ids - new_ids}")
                print(f"仅在新生成: {new_ids - existing_ids}")

    except Exception as e:
        print(f"❌ 生成失败: {e}")
        raise


if __name__ == "__main__":
    main()
