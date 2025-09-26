"""
S0策略实现

S0是最简单的静态基准策略：
- 使用预计算的15人最优阵容
- 每周从中选择11人首发阵容
- 选择队长
- 不进行转会，不使用芯片
"""

from pathlib import Path

import pandas as pd
import yaml


class S0Strategy:
    """
    S0静态策略实现

    核心逻辑：
    1. 加载预计算的15人最优阵容
    2. 每个gameweek从15人中选择11人首发
    3. 根据预期得分选择队长
    4. 不进行任何转会操作
    """

    def __init__(self, squad_config_path: str, season: str = "2023-24"):
        """
        初始化S0策略

        Args:
            squad_config_path: S0阵容配置文件路径
            season: 赛季标识
        """
        self.season = season
        self.squad_config_path = squad_config_path
        self.squad_data = self._load_squad_config()
        self.player_ids = self.squad_data["player_ids"]
        self.players_info = {p["id"]: p for p in self.squad_data["players"]}

        print(f"S0策略初始化完成，固定阵容: {len(self.player_ids)} 人")
        print(f"位置分布: {self.squad_data['position_distribution']}")
        print(f"队伍分布: {self.squad_data['team_distribution']}")

    def _load_squad_config(self) -> dict:
        """加载S0阵容配置"""
        config_path = Path(self.squad_config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"S0阵容配置文件不存在: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        season_key = f'optimal_squad_{self.season.replace("-", "_")}'
        if season_key not in data:
            raise KeyError(f"配置文件中未找到赛季 {self.season} 的数据")

        return data[season_key]

    def select_lineup(self, gw: int, predictions: pd.DataFrame, formation: str = "3-5-2") -> dict:
        """
        为指定gameweek选择首发阵容

        Args:
            gw: gameweek编号
            predictions: 包含球员预期得分的DataFrame
            formation: 阵型 (默认3-5-2，也支持3-4-3, 4-5-1等)

        Returns:
            包含首发阵容信息的字典
        """
        # 解析阵型
        formation_counts = self._parse_formation(formation)

        # 过滤预测数据，只保留S0阵容中的球员
        squad_predictions = predictions[predictions["player_id"].isin(self.player_ids)].copy()

        if len(squad_predictions) == 0:
            raise ValueError(f"GW{gw}: 未找到S0阵容球员的预测数据")

        # 按位置分组选择首发球员
        lineup = {}
        bench = []

        # 1. 选择门将 (总是选择预期得分最高的1个)
        gk_data = squad_predictions[squad_predictions["position"] == "GK"]
        if len(gk_data) == 0:
            raise ValueError("S0阵容中没有门将数据")

        gk_starter = gk_data.nlargest(1, "predicted_points")
        lineup["GK"] = gk_starter["player_id"].tolist()

        # 剩余门将进替补席
        gk_bench = gk_data[~gk_data["player_id"].isin(lineup["GK"])]
        bench.extend(gk_bench["player_id"].tolist())

        # 2. 选择其他位置球员
        for pos, count in formation_counts.items():
            if pos == "GK":
                continue

            pos_data = squad_predictions[squad_predictions["position"] == pos]
            if len(pos_data) < count:
                raise ValueError(
                    f"S0阵容中{pos}位置球员不足 (需要{count}人，只有{len(pos_data)}人)"
                )

            # 按预期得分排序，选择前N名首发
            starters = pos_data.nlargest(count, "predicted_points")
            lineup[pos] = starters["player_id"].tolist()

            # 剩余球员进替补席
            bench_players = pos_data[~pos_data["player_id"].isin(lineup[pos])]
            bench.extend(bench_players["player_id"].tolist())

        # 3. 选择队长 (所有首发球员中预期得分最高的)
        all_starters = []
        for pos_players in lineup.values():
            all_starters.extend(pos_players)

        starter_predictions = squad_predictions[squad_predictions["player_id"].isin(all_starters)]
        captain_id = int(starter_predictions.nlargest(1, "predicted_points")["player_id"].iloc[0])

        # 4. 构建结果
        result = {
            "gw": gw,
            "strategy": "S0",
            "formation": formation,
            "lineup": lineup,
            "captain_id": captain_id,
            "bench": bench,
            "transfers": [],  # S0策略不进行转会
            "chips_used": [],  # S0策略不使用芯片
            "total_starters": sum(len(players) for players in lineup.values()),
            "metadata": {
                "strategy_type": "static_baseline",
                "squad_unchanged": True,
                "decision_method": "predicted_points_ranking",
            },
        }

        # 验证阵容合法性
        self._validate_lineup(result)

        return result

    def _parse_formation(self, formation: str) -> dict[str, int]:
        """
        解析阵型字符串

        Args:
            formation: 阵型字符串，如 "3-5-2", "4-4-2", "3-4-3"

        Returns:
            各位置人数字典
        """
        parts = formation.split("-")
        if len(parts) != 3:
            raise ValueError(f"无效的阵型格式: {formation}")

        def_count, mid_count, fwd_count = map(int, parts)

        # 验证总人数
        if def_count + mid_count + fwd_count != 10:
            raise ValueError(
                f"阵型人数错误: {formation} (应为10人，实际{def_count + mid_count + fwd_count}人)"
            )

        # 验证位置限制 (根据FPL规则)
        if not (3 <= def_count <= 5):
            raise ValueError(f"后卫人数必须在3-5之间，当前: {def_count}")
        if not (2 <= mid_count <= 5):
            raise ValueError(f"中场人数必须在2-5之间，当前: {mid_count}")
        if not (1 <= fwd_count <= 3):
            raise ValueError(f"前锋人数必须在1-3之间，当前: {fwd_count}")

        return {"GK": 1, "DEF": def_count, "MID": mid_count, "FWD": fwd_count}

    def _validate_lineup(self, lineup_result: dict) -> None:
        """验证阵容是否符合FPL规则"""
        lineup = lineup_result["lineup"]

        # 检查总人数
        total_starters = sum(len(players) for players in lineup.values())
        if total_starters != 11:
            raise ValueError(f"首发人数错误: {total_starters} (应为11人)")

        # 检查位置人数
        if len(lineup.get("GK", [])) != 1:
            raise ValueError("门将必须且只能有1人")

        def_count = len(lineup.get("DEF", []))
        mid_count = len(lineup.get("MID", []))
        fwd_count = len(lineup.get("FWD", []))

        if not (3 <= def_count <= 5):
            raise ValueError(f"后卫人数违规: {def_count}")
        if not (2 <= mid_count <= 5):
            raise ValueError(f"中场人数违规: {mid_count}")
        if not (1 <= fwd_count <= 3):
            raise ValueError(f"前锋人数违规: {fwd_count}")

        # 检查队长是否在首发阵容中
        all_starters = []
        for pos_players in lineup.values():
            all_starters.extend(pos_players)

        if lineup_result["captain_id"] not in all_starters:
            raise ValueError("队长必须在首发阵容中")

        print(f"✅ GW{lineup_result['gw']} 阵容验证通过")

    def get_squad_info(self) -> dict:
        """获取S0策略的固定阵容信息"""
        return {
            "strategy": "S0",
            "player_count": len(self.player_ids),
            "player_ids": self.player_ids,
            "players": list(self.players_info.values()),
            "team_distribution": self.squad_data["team_distribution"],
            "position_distribution": self.squad_data["position_distribution"],
            "metadata": self.squad_data["metadata"],
        }


def load_s0_strategy(config_path: str = None, season: str = "2023-24") -> S0Strategy:
    """
    快速加载S0策略实例

    Args:
        config_path: 配置文件路径，默认使用标准路径
        season: 赛季标识

    Returns:
        S0Strategy实例
    """
    if config_path is None:
        config_path = "/Users/carl/workspace/FP-LLM/configs/backtest/s0_optimal_squad.yaml"

    return S0Strategy(config_path, season)


if __name__ == "__main__":
    # 测试S0策略
    try:
        # 加载策略
        s0 = load_s0_strategy()

        # 打印阵容信息
        squad_info = s0.get_squad_info()
        print("\n=== S0策略阵容信息 ===")
        print(f"球员总数: {squad_info['player_count']}")
        print(f"队伍分布: {squad_info['team_distribution']}")
        print(f"位置分布: {squad_info['position_distribution']}")

        # 创建模拟预测数据进行测试
        import numpy as np

        # 确保使用正确的位置信息
        players_with_positions = []
        for p in squad_info["players"]:
            players_with_positions.append(
                {
                    "player_id": p["id"],
                    "position": p["position"],
                    "predicted_points": np.random.uniform(2, 12),  # 模拟预期得分
                }
            )

        test_predictions = pd.DataFrame(players_with_positions)

        # 测试阵容选择
        lineup = s0.select_lineup(gw=1, predictions=test_predictions, formation="3-5-2")

        print("\n=== GW1 阵容选择测试 ===")
        print(f"阵型: {lineup['formation']}")
        print(f"首发球员: {lineup['total_starters']}人")
        print(f"队长ID: {lineup['captain_id']}")
        print(f"替补: {len(lineup['bench'])}人")

        for pos, players in lineup["lineup"].items():
            print(f"{pos}: {players}")

        print("\n✅ S0策略测试成功!")

    except Exception as e:
        print(f"❌ S0策略测试失败: {e}")
        raise
