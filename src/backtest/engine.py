"""
回测执行引擎

实现基础的单线程回测循环，支持：
- 历史数据加载
- 策略执行
- 结果收集
- 基础评估指标计算
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

# Note: Import will be done dynamically in functions to avoid circular imports


class BacktestEngine:
    """
    回测执行引擎

    核心功能：
    1. 管理历史数据
    2. 执行策略决策
    3. 计算实际得分
    4. 收集和汇总结果
    """

    def __init__(
        self, season: str = "2023-24", data_path: str = None, start_gw: int = 1, end_gw: int = 38
    ):
        """
        初始化回测引擎

        Args:
            season: 赛季标识
            data_path: 历史数据路径
            start_gw: 开始gameweek
            end_gw: 结束gameweek
        """
        self.season = season
        self.start_gw = start_gw
        self.end_gw = end_gw

        # 设置数据路径
        if data_path is None:
            data_path = f"/Users/carl/workspace/FP-LLM/data/backtest/raw/vaastav/{season}/gws"
        self.data_path = Path(data_path)

        # 初始化结果存储
        self.results = []
        self.strategy_decisions = {}
        self.performance_metrics = {}

        print("回测引擎初始化完成")
        print(f"赛季: {season}")
        print(f"Gameweek范围: {start_gw}-{end_gw}")
        print(f"数据路径: {self.data_path}")

    def load_gw_data(self, gw: int) -> pd.DataFrame:
        """
        加载指定gameweek的数据

        Args:
            gw: gameweek编号

        Returns:
            该gameweek的球员数据
        """
        gw_file = self.data_path / f"gw{gw}.csv"
        if not gw_file.exists():
            raise FileNotFoundError(f"未找到GW{gw}数据文件: {gw_file}")

        df = pd.read_csv(gw_file)

        # 数据预处理
        df["player_id"] = df["element"].astype(int)
        df["predicted_points"] = df.get(
            "ep_next", df.get("total_points", 0)
        )  # 使用预期得分或实际得分

        # 确保必要列存在
        required_cols = ["player_id", "name", "position", "team", "total_points"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"⚠️  GW{gw}数据缺少列: {missing_cols}")

        return df

    def run_backtest(self, strategy: Any, config: dict = None) -> dict:
        """
        执行完整回测

        Args:
            strategy: 策略实例 (如S0Strategy)
            config: 回测配置

        Returns:
            回测结果汇总
        """
        if config is None:
            config = {"formation": "3-5-2"}

        print("\n=== 开始回测 ===")
        print(f"策略: {strategy.__class__.__name__}")
        print(f"时间范围: GW{self.start_gw} - GW{self.end_gw}")

        total_points = 0
        gw_results = []

        for gw in range(self.start_gw, self.end_gw + 1):
            try:
                print(f"\n--- GW{gw} ---")

                # 1. 加载该周数据
                gw_data = self.load_gw_data(gw)
                print(f"加载数据: {len(gw_data)} 名球员")

                # 2. 执行策略决策
                if hasattr(strategy, "select_lineup"):
                    # S0等静态策略
                    lineup_decision = strategy.select_lineup(
                        gw=gw, predictions=gw_data, formation=config.get("formation", "3-5-2")
                    )
                else:
                    raise ValueError(
                        f"策略 {strategy.__class__.__name__} 不支持 select_lineup 方法"
                    )

                # 3. 计算该周得分
                gw_score = self._calculate_gw_score(lineup_decision, gw_data)
                total_points += gw_score

                # 4. 记录结果
                gw_result = {
                    "gw": gw,
                    "score": gw_score,
                    "cumulative_score": total_points,
                    "lineup": lineup_decision,
                    "top_scorer": self._get_top_scorer(lineup_decision, gw_data),
                }
                gw_results.append(gw_result)

                print(f"GW{gw}得分: {gw_score}分 (累计: {total_points}分)")
                print(
                    f"队长: {lineup_decision.get('captain_id')} (得分: {gw_score - self._calculate_gw_score_without_captain(lineup_decision, gw_data)}分额外)"
                )

            except FileNotFoundError as e:
                print(f"⚠️  跳过GW{gw}: {e}")
                continue
            except Exception as e:
                print(f"❌ GW{gw}执行失败: {e}")
                continue

        # 5. 计算整体统计
        final_results = self._compute_summary_stats(gw_results, strategy)

        print("\n=== 回测完成 ===")
        print(f"总得分: {total_points}")
        print(f"平均每周: {total_points / len(gw_results):.1f}")
        print(f"完成周数: {len(gw_results)}/{self.end_gw - self.start_gw + 1}")

        return final_results

    def _calculate_gw_score(self, lineup_decision: dict, gw_data: pd.DataFrame) -> int:
        """
        计算gameweek得分

        Args:
            lineup_decision: 策略决策结果
            gw_data: 该周球员数据

        Returns:
            该周总得分
        """
        total_score = 0

        # 获取所有首发球员
        all_starters = []
        for pos_players in lineup_decision["lineup"].values():
            all_starters.extend(pos_players)

        # 计算首发球员得分
        for player_id in all_starters:
            player_data = gw_data[gw_data["player_id"] == player_id]
            if not player_data.empty:
                score = int(player_data["total_points"].iloc[0])
                total_score += score

                # 队长得分翻倍
                if player_id == lineup_decision.get("captain_id"):
                    total_score += score

        return total_score

    def _calculate_gw_score_without_captain(
        self, lineup_decision: dict, gw_data: pd.DataFrame
    ) -> int:
        """计算不含队长加成的得分（用于显示队长贡献）"""
        total_score = 0

        all_starters = []
        for pos_players in lineup_decision["lineup"].values():
            all_starters.extend(pos_players)

        for player_id in all_starters:
            player_data = gw_data[gw_data["player_id"] == player_id]
            if not player_data.empty:
                score = int(player_data["total_points"].iloc[0])
                total_score += score

        return total_score

    def _get_top_scorer(self, lineup_decision: dict, gw_data: pd.DataFrame) -> dict:
        """获取该周首发阵容中的最高分球员"""
        all_starters = []
        for pos_players in lineup_decision["lineup"].values():
            all_starters.extend(pos_players)

        best_score = 0
        best_player = None

        for player_id in all_starters:
            player_data = gw_data[gw_data["player_id"] == player_id]
            if not player_data.empty:
                score = int(player_data["total_points"].iloc[0])
                if score > best_score:
                    best_score = score
                    best_player = {
                        "id": player_id,
                        "name": player_data["name"].iloc[0],
                        "position": player_data["position"].iloc[0],
                        "score": score,
                    }

        return best_player

    def _compute_summary_stats(self, gw_results: list[dict], strategy: Any) -> dict:
        """计算汇总统计信息"""
        if not gw_results:
            return {"error": "无有效结果数据"}

        scores = [r["score"] for r in gw_results]
        total_score = sum(scores)
        avg_score = np.mean(scores)
        std_score = np.std(scores)

        summary = {
            "strategy_name": strategy.__class__.__name__,
            "season": self.season,
            "gameweeks_completed": len(gw_results),
            "gameweek_range": f"GW{self.start_gw}-GW{self.end_gw}",
            "total_points": total_score,
            "average_points_per_gw": round(avg_score, 2),
            "points_std": round(std_score, 2),
            "best_gw": max(gw_results, key=lambda x: x["score"]),
            "worst_gw": min(gw_results, key=lambda x: x["score"]),
            "consistency_score": round(avg_score / std_score if std_score > 0 else 0, 2),
            "gameweek_results": gw_results,
            "execution_timestamp": datetime.now().isoformat(),
        }

        return summary

    def save_results(self, results: dict, output_path: str) -> None:
        """
        保存回测结果

        Args:
            results: 回测结果字典
            output_path: 输出文件路径
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 处理numpy类型
        def convert_types(obj):
            if isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(v) for v in obj]
            elif hasattr(obj, "item"):  # numpy scalar
                return obj.item()
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            else:
                return obj

        clean_results = convert_types(results)

        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(
                clean_results, f, default_flow_style=False, sort_keys=False, allow_unicode=True
            )

        print(f"回测结果已保存到: {output_file}")


def run_s0_backtest(
    season: str = "2023-24",
    start_gw: int = 1,
    end_gw: int = 5,  # 默认只测试前5周
    formation: str = "3-5-2",
) -> dict:
    """
    运行S0策略回测的便捷函数

    Args:
        season: 赛季
        start_gw: 开始gameweek
        end_gw: 结束gameweek
        formation: 阵型

    Returns:
        回测结果
    """
    # 初始化引擎
    engine = BacktestEngine(season=season, start_gw=start_gw, end_gw=end_gw)

    # 加载S0策略
    import os
    import sys

    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from strategies.s0_strategy import load_s0_strategy

    s0_strategy = load_s0_strategy(season=season)

    # 执行回测
    config = {"formation": formation}
    results = engine.run_backtest(s0_strategy, config)

    return results


if __name__ == "__main__":
    # 测试S0策略回测
    try:
        print("=== S0策略回测测试 ===")

        # 运行前3周的回测
        results = run_s0_backtest(season="2023-24", start_gw=1, end_gw=3, formation="3-5-2")

        # 保存结果
        output_path = "/Users/carl/workspace/FP-LLM/data/backtest/results/s0_test_results.yaml"
        engine = BacktestEngine()
        engine.save_results(results, output_path)

        print("\n✅ S0回测测试完成!")
        print(f"总得分: {results['total_points']}")
        print(f"平均得分: {results['average_points_per_gw']}")

    except Exception as e:
        print(f"❌ 回测测试失败: {e}")
        raise
