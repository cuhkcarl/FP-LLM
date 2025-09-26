"""
S0策略群体智慧阵容生成器

基于赛季开始时的球员拥有率，生成最优的15人阵容作为S0策略的基准。
优化目标：最大化总拥有率
约束条件：FPL规则（预算、位置、每队人数限制）
"""

from pathlib import Path

import pandas as pd
import pulp


def generate_s0_squad(
    players_data: pd.DataFrame,
    season: str = "2023-24",
    budget_limit: float = 100.0,
    max_per_team: int = 3,
) -> dict:
    """
    生成S0策略的最优阵容

    Args:
        players_data: 球员数据，必须包含列：
            - player_id/element: 球员ID
            - name: 球员姓名
            - position: 位置 (GK/DEF/MID/FWD)
            - team: 队伍名称
            - value: 价格(以0.1M为单位)
            - selected: 拥有人数
        season: 赛季标识
        budget_limit: 预算限制(百万)
        max_per_team: 每队最大人数

    Returns:
        包含最优阵容信息的字典
    """
    # 数据预处理
    df = players_data.copy()

    # 统一列名
    if "element" in df.columns:
        df["player_id"] = df["element"]
    if "player_id" not in df.columns:
        raise ValueError("数据必须包含 player_id 或 element 列")

    # 确保必要列存在
    required_cols = ["player_id", "name", "position", "team", "value", "selected"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"缺少必要列: {missing_cols}")

    # 数据清理
    df = df.dropna(subset=required_cols)
    df = df[df["value"] > 0]  # 排除无效价格
    df["price"] = df["value"] / 10.0  # 转换为百万单位
    df["ownership"] = df["selected"].astype(int)  # 拥有人数

    print(f"数据预处理完成: {len(df)} 名有效球员")

    # 设置优化问题
    prob = pulp.LpProblem("S0_Optimal_Squad", pulp.LpMaximize)

    # 决策变量
    players = df["player_id"].tolist()
    x = pulp.LpVariable.dicts("select", players, cat="Binary")

    # 目标函数：最大化总拥有率
    ownership_dict = df.set_index("player_id")["ownership"].to_dict()
    prob += pulp.lpSum([x[pid] * ownership_dict[pid] for pid in players])

    # 约束1: 预算限制
    price_dict = df.set_index("player_id")["price"].to_dict()
    prob += pulp.lpSum([x[pid] * price_dict[pid] for pid in players]) <= budget_limit

    # 约束2: 总人数
    prob += pulp.lpSum([x[pid] for pid in players]) == 15

    # 约束3: 位置限制
    position_requirements = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
    for pos, count in position_requirements.items():
        pos_players = df[df["position"] == pos]["player_id"].tolist()
        prob += pulp.lpSum([x[pid] for pid in pos_players]) == count

    # 约束4: 每队人数限制
    for team in df["team"].unique():
        team_players = df[df["team"] == team]["player_id"].tolist()
        prob += pulp.lpSum([x[pid] for pid in team_players]) <= max_per_team

    # 求解
    print("开始优化求解...")
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"优化失败: {pulp.LpStatus[prob.status]}")

    # 提取结果
    selected_ids = [pid for pid in players if pulp.value(x[pid]) > 0.5]
    selected_df = df[df["player_id"].isin(selected_ids)].copy()
    selected_df = selected_df.sort_values("ownership", ascending=False)

    # 计算统计
    total_cost = selected_df["price"].sum()
    total_ownership = selected_df["ownership"].sum()
    team_dist = selected_df["team"].value_counts().to_dict()
    pos_dist = selected_df["position"].value_counts().to_dict()

    print("✅ 优化完成!")
    print(f"总成本: £{total_cost:.1f}M (剩余: £{budget_limit - total_cost:.1f}M)")
    print(f"总拥有率: {total_ownership:,}")
    print(f"队伍分布: {team_dist}")
    print(f"位置分布: {pos_dist}")

    # 验证约束
    assert len(selected_df) == 15, "球员数量错误"
    assert total_cost <= budget_limit, "超出预算"
    assert max(team_dist.values()) <= max_per_team, "违反每队人数限制"
    assert pos_dist == position_requirements, "位置分布错误"

    # 构建返回结果
    players_list = []
    for _, row in selected_df.iterrows():
        players_list.append(
            {
                "id": int(row["player_id"]),
                "name": row["name"],
                "position": row["position"],
                "team": row["team"],
                "price": float(row["price"]),
                "ownership": int(row["ownership"]),
            }
        )

    result = {
        f'optimal_squad_{season.replace("-", "_")}': {
            "player_ids": [int(pid) for pid in selected_ids],
            "players": players_list,
            "metadata": {
                "season": season,
                "total_value_millions": round(total_cost, 1),
                "remaining_budget_millions": round(budget_limit - total_cost, 1),
                "total_ownership": int(total_ownership),
                "optimization_method": "crowd_wisdom_popularity",
                "constraints_satisfied": [
                    "exactly_15_players",
                    "budget_limit",
                    "position_quota_2gk_5def_5mid_3fwd",
                    f"max_{max_per_team}_per_team",
                ],
            },
            "team_distribution": team_dist,
            "position_distribution": pos_dist,
        }
    }

    return result


def load_gw1_data(season: str = "2023-24") -> pd.DataFrame:
    """
    加载指定赛季的GW1数据

    Args:
        season: 赛季标识，如 "2023-24"

    Returns:
        GW1球员数据DataFrame
    """
    data_path = Path(f"/Users/carl/workspace/FP-LLM/data/backtest/raw/vaastav/{season}/gws/gw1.csv")

    if not data_path.exists():
        raise FileNotFoundError(f"未找到 {season} 赛季的GW1数据: {data_path}")

    df = pd.read_csv(data_path)
    print(f"加载 {season} GW1数据: {len(df)} 名球员")

    return df


def save_s0_config(squad_data: dict, output_path: str) -> None:
    """
    保存S0阵容配置到YAML文件

    Args:
        squad_data: generate_s0_squad返回的阵容数据
        output_path: 输出文件路径
    """
    import yaml

    # 确保输出目录存在
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 转换numpy类型为Python原生类型
    def convert_types(obj):
        if isinstance(obj, dict):
            return {k: convert_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_types(v) for v in obj]
        elif hasattr(obj, "item"):  # numpy scalar
            return obj.item()
        else:
            return obj

    clean_data = convert_types(squad_data)

    with open(output_path, "w") as f:
        yaml.dump(clean_data, f, default_flow_style=False, sort_keys=False)

    print(f"S0阵容配置已保存到: {output_path}")


if __name__ == "__main__":
    # 生成并保存S0阵容
    try:
        # 加载23-24 GW1数据
        gw1_data = load_gw1_data("2023-24")

        # 生成最优阵容
        optimal_squad = generate_s0_squad(gw1_data, "2023-24")

        # 保存配置
        output_path = (
            "/Users/carl/workspace/FP-LLM/configs/backtest/s0_optimal_squad_corrected.yaml"
        )
        save_s0_config(optimal_squad, output_path)

        print("\n✅ S0最优阵容生成完成!")
        print(f"球员ID: {optimal_squad['optimal_squad_2023_24']['player_ids']}")

    except Exception as e:
        print(f"❌ 生成失败: {e}")
        raise
