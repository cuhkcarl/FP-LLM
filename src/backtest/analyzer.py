"""
数据驱动的回测分析系统 V2

特点：
- 完全基于数据生成报告
- 可配置的评级标准和模板
- 支持多策略自动对比
- 动态加载球员信息
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


class ConfigurableAnalyzer:
    """
    可配置的回测分析器

    通过配置文件定义：
    - 评级标准
    - 报告模板
    - 策略特征描述
    """

    def __init__(self, config_path: str = None):
        """初始化分析器"""
        self.results = {}
        self.player_data = {}

        # 加载配置
        if config_path and Path(config_path).exists():
            with open(config_path, encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = self._get_default_config()

    def _get_default_config(self) -> dict:
        """获取默认配置"""
        return {
            "grading_standards": {
                "performance": [
                    {"min": 60, "grade": "A", "label": "优秀", "description": "表现超出预期"},
                    {"min": 55, "grade": "B", "label": "良好", "description": "表现符合预期"},
                    {"min": 50, "grade": "C", "label": "一般", "description": "表现略低于预期"},
                    {"min": 0, "grade": "D", "label": "较差", "description": "表现明显低于预期"},
                ],
                "consistency": [
                    {"min": 0.8, "label": "高稳定性"},
                    {"min": 0.6, "label": "中等稳定性"},
                    {"min": 0.0, "label": "低稳定性"},
                ],
            },
            "benchmarks": {
                "fpl_average_per_gw": 52.5,
                "good_consistency_threshold": 0.7,
                "excellent_avg_threshold": 60,
            },
            "strategy_profiles": {
                "S0": {
                    "name": "静态基准策略",
                    "characteristics": [
                        "基于群体智慧的预计算最优阵容",
                        "固定15人阵容，无转会操作",
                        "每周选择最佳11人首发和队长",
                        "策略执行简单，风险可控",
                    ],
                    "expected_performance": "中等偏上",
                    "risk_level": "低",
                }
            },
        }

    def load_result(self, strategy_name: str, result_path: str) -> None:
        """加载策略回测结果"""
        with open(result_path, encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        # 处理数据
        processed = self._process_raw_data(raw_data, strategy_name)
        self.results[strategy_name] = processed

        print(f"✅ 已加载 {strategy_name} 策略结果")
        print(f"   - 赛季: {processed['summary']['season']}")
        print(f"   - 完成周数: {processed['summary']['gameweeks_completed']}")
        print(f"   - 总得分: {processed['summary']['total_points']}")

    def load_player_mapping(self, season: str = "2023-24") -> None:
        """加载球员ID到姓名的映射"""
        try:
            # 从S0配置中获取球员信息
            s0_config_path = "/Users/carl/workspace/FP-LLM/configs/backtest/s0_optimal_squad.yaml"
            if Path(s0_config_path).exists():
                with open(s0_config_path, encoding="utf-8") as f:
                    s0_data = yaml.safe_load(f)

                players_info = s0_data.get("optimal_squad_2023_24", {}).get("players", [])
                for player in players_info:
                    self.player_data[player["id"]] = {
                        "name": player["name"],
                        "position": player["position"],
                        "team": player["team"],
                    }

                print(f"✅ 已加载 {len(self.player_data)} 名球员信息")
        except Exception as e:
            print(f"⚠️ 加载球员信息失败: {e}")

    def _process_raw_data(self, raw_data: dict, strategy_name: str) -> dict:
        """处理原始数据"""
        # 提取gameweek数据
        gw_data = []
        for gw_result in raw_data.get("gameweek_results", []):
            gw_data.append(
                {
                    "gw": gw_result["gw"],
                    "score": gw_result["score"],
                    "cumulative_score": gw_result["cumulative_score"],
                    "captain_id": gw_result["lineup"]["captain_id"],
                    "formation": gw_result["lineup"]["formation"],
                }
            )

        df = pd.DataFrame(gw_data)

        return {
            "strategy_name": strategy_name,
            "raw_data": raw_data,
            "gameweek_df": df,
            "summary": {
                "season": raw_data.get("season"),
                "total_points": raw_data.get("total_points"),
                "gameweeks_completed": raw_data.get("gameweeks_completed"),
                "average_points_per_gw": raw_data.get("average_points_per_gw"),
                "points_std": raw_data.get("points_std"),
            },
        }

    def analyze_strategy(self, strategy_name: str) -> dict:
        """分析单个策略"""
        if strategy_name not in self.results:
            raise KeyError(f"策略 {strategy_name} 尚未加载")

        result = self.results[strategy_name]
        df = result["gameweek_df"]

        analysis = {
            "basic_metrics": self._compute_basic_metrics(df),
            "performance_rating": self._rate_performance(result["summary"]),
            "consistency_analysis": self._analyze_consistency(df),
            "captain_analysis": self._analyze_captains(df),
            "formation_analysis": self._analyze_formations(df),
            "trend_analysis": self._analyze_trends(df),
            "comparative_analysis": self._compare_to_benchmarks(result["summary"]),
        }

        return analysis

    def _compute_basic_metrics(self, df: pd.DataFrame) -> dict:
        """计算基础指标"""
        scores = df["score"]
        return {
            "total_gameweeks": len(df),
            "total_points": scores.sum(),
            "average_points": scores.mean(),
            "median_points": scores.median(),
            "std_points": scores.std(),
            "min_points": scores.min(),
            "max_points": scores.max(),
            "percentiles": {
                "25th": scores.quantile(0.25),
                "75th": scores.quantile(0.75),
                "90th": scores.quantile(0.90),
            },
            "score_distribution": {
                "excellent_weeks": (scores >= 70).sum(),  # 70+分的周数
                "good_weeks": ((scores >= 55) & (scores < 70)).sum(),  # 55-69分
                "average_weeks": ((scores >= 40) & (scores < 55)).sum(),  # 40-54分
                "poor_weeks": (scores < 40).sum(),  # <40分
            },
        }

    def _rate_performance(self, summary: dict) -> dict:
        """评级表现"""
        avg_score = summary["average_points_per_gw"]

        # 根据配置的标准评级
        grade_info = None
        for standard in self.config["grading_standards"]["performance"]:
            if avg_score >= standard["min"]:
                grade_info = standard
                break

        if not grade_info:
            grade_info = self.config["grading_standards"]["performance"][-1]

        return {
            "grade": grade_info["grade"],
            "label": grade_info["label"],
            "description": grade_info["description"],
            "score": avg_score,
            "vs_fpl_average": avg_score - self.config["benchmarks"]["fpl_average_per_gw"],
        }

    def _analyze_consistency(self, df: pd.DataFrame) -> dict:
        """分析一致性"""
        scores = df["score"]
        avg_score = scores.mean()
        cv = scores.std() / avg_score if avg_score > 0 else 0
        consistency_score = 1 / (1 + cv)

        # 评级一致性
        consistency_label = None
        for standard in self.config["grading_standards"]["consistency"]:
            if consistency_score >= standard["min"]:
                consistency_label = standard["label"]
                break

        return {
            "consistency_score": consistency_score,
            "coefficient_of_variation": cv,
            "label": consistency_label,
            "above_average_weeks": (scores >= avg_score).sum(),
            "below_average_weeks": (scores < avg_score).sum(),
            "volatility_assessment": "low" if cv < 0.3 else "medium" if cv < 0.5 else "high",
        }

    def _analyze_captains(self, df: pd.DataFrame) -> dict:
        """分析队长选择"""
        captain_counts = df["captain_id"].value_counts()
        total_games = len(df)

        # 转换为球员姓名
        captain_info = []
        for captain_id, count in captain_counts.items():
            player_info = self.player_data.get(captain_id, {})
            captain_info.append(
                {
                    "id": captain_id,
                    "name": player_info.get("name", f"Player_{captain_id}"),
                    "position": player_info.get("position", "Unknown"),
                    "team": player_info.get("team", "Unknown"),
                    "games_captained": count,
                    "percentage": (count / total_games) * 100,
                }
            )

        # 按使用频率排序
        captain_info.sort(key=lambda x: x["games_captained"], reverse=True)

        return {
            "total_different_captains": len(captain_counts),
            "most_used_captain": captain_info[0] if captain_info else None,
            "captain_distribution": captain_info,
            "captain_diversity": len(captain_counts) / total_games,  # 多样性指标
        }

    def _analyze_formations(self, df: pd.DataFrame) -> dict:
        """分析阵型使用"""
        formation_counts = df["formation"].value_counts()
        total_games = len(df)

        formation_info = []
        for formation, count in formation_counts.items():
            formation_info.append(
                {
                    "formation": formation,
                    "games_used": count,
                    "percentage": (count / total_games) * 100,
                }
            )

        return {
            "total_formations_used": len(formation_counts),
            "primary_formation": formation_info[0]["formation"] if formation_info else None,
            "formation_distribution": formation_info,
            "formation_diversity": len(formation_counts) / total_games,
        }

    def _analyze_trends(self, df: pd.DataFrame) -> dict:
        """分析趋势"""
        scores = df["score"].values
        gws = df["gw"].values

        if len(scores) > 1:
            # 线性趋势
            trend_slope = np.polyfit(gws, scores, 1)[0]

            # 移动平均
            window_size = min(5, len(scores))
            rolling_avg = pd.Series(scores).rolling(window=window_size).mean()

            # 分段分析
            mid_point = len(scores) // 2
            first_half_avg = scores[:mid_point].mean() if mid_point > 0 else scores.mean()
            second_half_avg = (
                scores[mid_point:].mean() if mid_point < len(scores) else scores.mean()
            )
        else:
            trend_slope = 0
            rolling_avg = pd.Series([scores[0]] if len(scores) > 0 else [0])
            first_half_avg = second_half_avg = scores[0] if len(scores) > 0 else 0

        # 趋势判断
        if abs(trend_slope) < 0.1:
            trend_direction = "stable"
        elif trend_slope > 0:
            trend_direction = "improving"
        else:
            trend_direction = "declining"

        return {
            "trend_slope": trend_slope,
            "trend_direction": trend_direction,
            "rolling_average": rolling_avg.tolist(),
            "first_half_average": first_half_avg,
            "second_half_average": second_half_avg,
            "half_performance_change": second_half_avg - first_half_avg,
        }

    def _compare_to_benchmarks(self, summary: dict) -> dict:
        """与基准对比"""
        avg_score = summary["average_points_per_gw"]
        benchmarks = self.config["benchmarks"]

        return {
            "vs_fpl_average": {
                "difference": avg_score - benchmarks["fpl_average_per_gw"],
                "percentage_better": ((avg_score / benchmarks["fpl_average_per_gw"]) - 1) * 100,
                "assessment": "above" if avg_score > benchmarks["fpl_average_per_gw"] else "below",
            },
            "vs_excellence_threshold": {
                "difference": avg_score - benchmarks["excellent_avg_threshold"],
                "reached_excellence": avg_score >= benchmarks["excellent_avg_threshold"],
            },
        }

    def generate_report(self, strategy_name: str, output_path: str = None) -> str:
        """生成数据驱动的报告"""
        if strategy_name not in self.results:
            raise KeyError(f"策略 {strategy_name} 尚未加载")

        result = self.results[strategy_name]
        analysis = self.analyze_strategy(strategy_name)

        # 获取策略配置信息
        strategy_profile = self.config["strategy_profiles"].get(
            strategy_name,
            {
                "name": f"{strategy_name}策略",
                "characteristics": ["待配置"],
                "expected_performance": "待评估",
                "risk_level": "待评估",
            },
        )

        report = self._generate_data_driven_report(
            strategy_name, result, analysis, strategy_profile
        )

        # 保存报告
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report)

            print(f"📊 数据驱动报告已保存到: {output_file}")

        return report

    def _generate_data_driven_report(
        self, strategy_name: str, result: dict, analysis: dict, profile: dict
    ) -> str:
        """生成完全基于数据的报告"""

        basic = analysis["basic_metrics"]
        performance = analysis["performance_rating"]
        consistency = analysis["consistency_analysis"]
        captain = analysis["captain_analysis"]
        formation = analysis["formation_analysis"]
        trends = analysis["trend_analysis"]
        benchmark = analysis["comparative_analysis"]

        # 动态生成策略特征描述
        captain_diversity_desc = (
            "队长选择多样化" if captain["captain_diversity"] > 0.3 else "队长选择相对固定"
        )
        formation_diversity_desc = (
            "阵型使用灵活" if formation["formation_diversity"] > 0.1 else "阵型使用固定"
        )

        report = f"""# {profile['name']}回测分析报告

## 📋 策略概览

### 基本信息
- **策略代码**: {strategy_name}
- **策略名称**: {profile['name']}
- **分析赛季**: {result['summary']['season']}
- **完成进度**: {basic['total_gameweeks']}/38周 ({basic['total_gameweeks']/38*100:.1f}%)
- **数据完整性**: {"✅ 完整" if basic['total_gameweeks'] == 38 else f"⚠️ 缺失{38-basic['total_gameweeks']}周数据"}
- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 策略特征
"""

        # 动态添加策略特征
        for characteristic in profile["characteristics"]:
            report += f"- {characteristic}\n"

        report += f"""
### 核心指标概览
- **总得分**: {basic['total_points']:.0f}分
- **平均得分**: {basic['average_points']:.1f}分/周
- **表现评级**: {performance['label']} ({performance['grade']}级)
- **稳定性**: {consistency['label']} (得分: {consistency['consistency_score']:.3f})
- **主要特征**: {captain_diversity_desc}, {formation_diversity_desc}

## 📊 表现分析

### 得分统计
- **总得分**: {basic['total_points']:.0f}分
- **平均得分**: {basic['average_points']:.1f}分/周
- **中位数**: {basic['median_points']:.1f}分
- **标准差**: {basic['std_points']:.1f}分
- **得分区间**: {basic['min_points']:.0f} - {basic['max_points']:.0f}分

### 得分分布
- **优秀表现** (≥70分): {basic['score_distribution']['excellent_weeks']}周 ({basic['score_distribution']['excellent_weeks']/basic['total_gameweeks']*100:.1f}%)
- **良好表现** (55-69分): {basic['score_distribution']['good_weeks']}周 ({basic['score_distribution']['good_weeks']/basic['total_gameweeks']*100:.1f}%)
- **平均表现** (40-54分): {basic['score_distribution']['average_weeks']}周 ({basic['score_distribution']['average_weeks']/basic['total_gameweeks']*100:.1f}%)
- **较差表现** (<40分): {basic['score_distribution']['poor_weeks']}周 ({basic['score_distribution']['poor_weeks']/basic['total_gameweeks']*100:.1f}%)

### 分位数分析
- **25%分位数**: {basic['percentiles']['25th']:.1f}分
- **75%分位数**: {basic['percentiles']['75th']:.1f}分
- **90%分位数**: {basic['percentiles']['90th']:.1f}分

## 📈 趋势分析

### 赛季表现趋势
- **整体趋势**: {trends['trend_direction']} (斜率: {trends['trend_slope']:+.3f}分/周)
- **前半程平均**: {trends['first_half_average']:.1f}分
- **后半程平均**: {trends['second_half_average']:.1f}分
- **进步幅度**: {trends['half_performance_change']:+.1f}分

## 🎯 稳定性评估

### 一致性指标
- **稳定性评级**: {consistency['label']}
- **一致性得分**: {consistency['consistency_score']:.3f} (0-1区间，越高越稳定)
- **变异系数**: {consistency['coefficient_of_variation']:.3f}
- **波动性评估**: {consistency['volatility_assessment']}

### 表现分布
- **高于平均表现**: {consistency['above_average_weeks']}周 ({consistency['above_average_weeks']/basic['total_gameweeks']*100:.1f}%)
- **低于平均表现**: {consistency['below_average_weeks']}周 ({consistency['below_average_weeks']/basic['total_gameweeks']*100:.1f}%)

## 👑 队长策略分析

### 队长使用统计
- **不同队长数量**: {captain['total_different_captains']}人
- **队长多样性指数**: {captain['captain_diversity']:.3f}
"""

        # 动态生成队长分布
        if captain["most_used_captain"]:
            most_used = captain["most_used_captain"]
            report += f"- **最常用队长**: {most_used['name']} ({most_used['position']}, {most_used['team']}) - {most_used['games_captained']}次 ({most_used['percentage']:.1f}%)\n"

        report += "\n### 队长使用分布\n"
        for captain_info in captain["captain_distribution"][:5]:  # 显示前5名
            report += f"- **{captain_info['name']}** ({captain_info['position']}, {captain_info['team']}): {captain_info['games_captained']}次 ({captain_info['percentage']:.1f}%)\n"

        report += f"""

## ⚽ 阵型分析

### 阵型使用统计
- **使用阵型数量**: {formation['total_formations_used']}种
- **主要阵型**: {formation['primary_formation']}
- **阵型多样性**: {formation['formation_diversity']:.3f}

### 阵型分布
"""

        # 动态生成阵型分布
        for form_info in formation["formation_distribution"]:
            report += f"- **{form_info['formation']}**: {form_info['games_used']}次 ({form_info['percentage']:.1f}%)\n"

        report += f"""

## 📊 基准对比

### 与FPL平均水平对比
- **FPL典型平均**: {self.config['benchmarks']['fpl_average_per_gw']:.1f}分/周
- **本策略平均**: {basic['average_points']:.1f}分/周
- **相对表现**: {benchmark['vs_fpl_average']['assessment']} ({benchmark['vs_fpl_average']['difference']:+.1f}分, {benchmark['vs_fpl_average']['percentage_better']:+.1f}%)

### 卓越表现基准
- **卓越门槛**: {self.config['benchmarks']['excellent_avg_threshold']:.0f}分/周
- **距离卓越**: {benchmark['vs_excellence_threshold']['difference']:+.1f}分
- **达到卓越**: {'是' if benchmark['vs_excellence_threshold']['reached_excellence'] else '否'}

## 🏆 极值分析

### 最佳表现
- **最佳周**: GW{result['raw_data']['best_gw']['gw']} - {result['raw_data']['best_gw']['score']}分

### 最差表现
- **最差周**: GW{result['raw_data']['worst_gw']['gw']} - {result['raw_data']['worst_gw']['score']}分

## ⚠️ 数据完整性说明

### {'数据缺失情况' if basic['total_gameweeks'] < 38 else '数据完整性'}
- **{'缺失周数' if basic['total_gameweeks'] < 38 else '数据状态'}**: {str(38-basic['total_gameweeks']) + '周' if basic['total_gameweeks'] < 38 else '完整覆盖38周'}
- **影响评估**: {'结果基于部分数据，实际表现可能有差异' if basic['total_gameweeks'] < 38 else '完整赛季数据，结果可靠'}
{('- **建议**: 补充缺失数据后重新分析以获得更准确的评估' + chr(10)) if basic['total_gameweeks'] < 38 else ''}

## 📋 综合评估

### 总体评级
**{performance['label']} ({performance['grade']}级)** - {performance['description']}

### 关键优势
"""

        # 动态生成优势
        advantages = []
        if benchmark["vs_fpl_average"]["assessment"] == "above":
            advantages.append(
                f"表现超越FPL平均水平 {benchmark['vs_fpl_average']['percentage_better']:.1f}%"
            )
        if (
            consistency["consistency_score"]
            > self.config["benchmarks"]["good_consistency_threshold"]
        ):
            advantages.append(
                f"具备良好的稳定性 (一致性得分 {consistency['consistency_score']:.3f})"
            )
        if basic["score_distribution"]["excellent_weeks"] > basic["total_gameweeks"] * 0.2:
            advantages.append(
                f"优秀表现周数占比较高 ({basic['score_distribution']['excellent_weeks']/basic['total_gameweeks']*100:.1f}%)"
            )

        for advantage in advantages:
            report += f"- {advantage}\n"

        report += "\n### 改进空间\n"

        # 动态生成改进建议
        improvements = []
        if captain["captain_diversity"] < 0.2:
            improvements.append("队长选择相对单一，可考虑更多样化的队长策略")
        if trends["trend_direction"] == "declining":
            improvements.append("赛季表现呈下降趋势，需要策略调整优化")
        if basic["score_distribution"]["poor_weeks"] > basic["total_gameweeks"] * 0.15:
            improvements.append("较差表现周数偏多，需要提升风险控制能力")
        if not benchmark["vs_excellence_threshold"]["reached_excellence"]:
            improvements.append(
                f"距离卓越表现还有 {abs(benchmark['vs_excellence_threshold']['difference']):.1f}分提升空间"
            )

        for improvement in improvements:
            report += f"- {improvement}\n"

        report += f"""

---
*本报告基于 {basic['total_gameweeks']} 周回测数据自动生成，数据驱动，客观准确*
*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

        return report

    def save_analysis(self, strategy_name: str, output_path: str) -> None:
        """保存完整的分析结果到JSON文件"""
        if strategy_name not in self.results:
            raise KeyError(f"策略 {strategy_name} 尚未加载")

        analysis = self.analyze_strategy(strategy_name)

        # 转换为JSON兼容格式
        def convert_for_json(obj):
            if hasattr(obj, "item"):
                return obj.item()
            elif hasattr(obj, "tolist"):
                return obj.tolist()
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            else:
                return obj

        def deep_convert(obj):
            if isinstance(obj, dict):
                return {k: deep_convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [deep_convert(v) for v in obj]
            else:
                return convert_for_json(obj)

        json_data = {
            "strategy_name": strategy_name,
            "analysis_timestamp": datetime.now().isoformat(),
            "summary": self.results[strategy_name]["summary"],
            "detailed_analysis": deep_convert(analysis),
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        print(f"💾 分析数据已保存到: {output_file}")

    def compare_strategies(self, strategy_names: list[str]) -> dict:
        """对比多个策略"""
        if not all(name in self.results for name in strategy_names):
            missing = [name for name in strategy_names if name not in self.results]
            raise KeyError(f"以下策略尚未加载: {missing}")

        comparison = {
            "strategies": strategy_names,
            "summary_table": {},
            "rankings": {},
            "detailed_comparison": {},
        }

        # 生成对比表格
        for strategy in strategy_names:
            analysis = self.analyze_strategy(strategy)
            comparison["summary_table"][strategy] = {
                "total_points": analysis["basic_metrics"]["total_points"],
                "avg_points": analysis["basic_metrics"]["average_points"],
                "consistency": analysis["consistency_analysis"]["consistency_score"],
                "grade": analysis["performance_rating"]["grade"],
                "vs_fpl_avg": analysis["comparative_analysis"]["vs_fpl_average"]["difference"],
            }

        # 生成排名
        metrics = ["total_points", "avg_points", "consistency"]
        for metric in metrics:
            sorted_strategies = sorted(
                strategy_names, key=lambda x: comparison["summary_table"][x][metric], reverse=True
            )
            comparison["rankings"][metric] = sorted_strategies

        return comparison


def create_analyzer(config_path: str = None) -> ConfigurableAnalyzer:
    """创建分析器实例"""
    return ConfigurableAnalyzer(config_path)


if __name__ == "__main__":
    try:
        print("🔧 初始化数据驱动分析器...")
        analyzer = create_analyzer()

        # 加载球员映射
        analyzer.load_player_mapping()

        # 加载S0结果
        s0_path = "/Users/carl/workspace/FP-LLM/data/backtest/results/s0_full_season_2023_24.yaml"
        if Path(s0_path).exists():
            analyzer.load_result("S0", s0_path)

            # 生成数据驱动报告
            report = analyzer.generate_report(
                "S0", "/Users/carl/workspace/FP-LLM/data/backtest/analysis/s0_data_driven_report.md"
            )

            print("\n✅ 数据驱动的S0分析报告生成完成!")
        else:
            print("⚠️ S0结果文件不存在")

    except Exception as e:
        print(f"❌ 分析失败: {e}")
        raise
