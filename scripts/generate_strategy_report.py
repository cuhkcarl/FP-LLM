#!/usr/bin/env python3
"""
策略报告生成器

演示如何为任何策略生成标准化的分析报告
"""

import sys
from pathlib import Path

# 添加src到路径
sys.path.append(str(Path(__file__).parent.parent / "src"))

from backtest.analyzer import ConfigurableAnalyzer


def generate_report_for_strategy(strategy_name: str, result_file: str, config_file: str = None):
    """
    为指定策略生成标准化报告

    Args:
        strategy_name: 策略名称 (如 "S0", "S1", "S2")
        result_file: 回测结果文件路径
        config_file: 分析器配置文件路径 (可选)
    """

    print(f"🔧 为 {strategy_name} 策略生成分析报告...")

    try:
        # 1. 初始化分析器
        if config_file and Path(config_file).exists():
            analyzer = ConfigurableAnalyzer(config_file)
            print(f"✅ 使用自定义配置: {config_file}")
        else:
            analyzer = ConfigurableAnalyzer()
            print("✅ 使用默认配置")

        # 2. 加载球员映射 (用于显示球员姓名而非ID)
        analyzer.load_player_mapping()

        # 3. 加载策略结果
        if not Path(result_file).exists():
            raise FileNotFoundError(f"结果文件不存在: {result_file}")

        analyzer.load_result(strategy_name, result_file)

        # 4. 生成报告
        output_dir = Path("/Users/carl/workspace/FP-LLM/data/backtest/analysis")
        output_file = output_dir / f"{strategy_name.lower()}_strategy_report.md"

        report = analyzer.generate_report(strategy_name, str(output_file))

        # 5. 生成JSON格式的详细分析数据
        json_output = output_dir / f"{strategy_name.lower()}_analysis_data.json"
        analyzer.save_analysis(strategy_name, str(json_output))

        print(f"✅ {strategy_name} 策略报告生成完成!")
        print(f"   📄 Markdown报告: {output_file}")
        print(f"   📊 JSON数据: {json_output}")

        return str(output_file), str(json_output)

    except Exception as e:
        print(f"❌ 生成 {strategy_name} 报告失败: {e}")
        raise


def compare_strategies(strategy_list: list, result_files: list, config_file: str = None):
    """
    对比多个策略的表现

    Args:
        strategy_list: 策略名称列表
        result_files: 对应的结果文件列表
        config_file: 配置文件路径
    """

    if len(strategy_list) != len(result_files):
        raise ValueError("策略数量与结果文件数量不匹配")

    print(f"🔍 对比分析 {len(strategy_list)} 个策略...")

    try:
        # 初始化分析器
        analyzer = ConfigurableAnalyzer(config_file)
        analyzer.load_player_mapping()

        # 加载所有策略结果
        for strategy, result_file in zip(strategy_list, result_files, strict=False):
            if Path(result_file).exists():
                analyzer.load_result(strategy, result_file)
            else:
                print(f"⚠️ 跳过 {strategy}: 结果文件不存在 ({result_file})")

        # 生成对比分析
        loaded_strategies = [
            s for s, f in zip(strategy_list, result_files, strict=False) if Path(f).exists()
        ]
        if len(loaded_strategies) < 2:
            print("❌ 需要至少2个策略才能进行对比分析")
            return

        comparison = analyzer.compare_strategies(loaded_strategies)

        # 保存对比结果
        import json

        output_path = "/Users/carl/workspace/FP-LLM/data/backtest/analysis/strategy_comparison.json"

        # 转换numpy类型
        def convert_for_json(obj):
            if hasattr(obj, "item"):
                return obj.item()
            elif hasattr(obj, "tolist"):
                return obj.tolist()
            else:
                return obj

        def deep_convert(obj):
            if isinstance(obj, dict):
                return {k: deep_convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [deep_convert(v) for v in obj]
            else:
                return convert_for_json(obj)

        clean_comparison = deep_convert(comparison)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(clean_comparison, f, indent=2, ensure_ascii=False)

        print(f"✅ 策略对比分析完成: {output_path}")

        # 显示简要对比结果
        print("\n📊 对比结果摘要:")
        print(f"{'策略':<8} {'总分':<8} {'平均':<8} {'稳定性':<8} {'评级':<6}")
        print("-" * 40)

        for strategy in loaded_strategies:
            summary = comparison["summary_table"][strategy]
            print(
                f"{strategy:<8} {summary['total_points']:<8.0f} {summary['avg_points']:<8.1f} {summary['consistency']:<8.3f} {summary['grade']:<6}"
            )

        return output_path

    except Exception as e:
        print(f"❌ 策略对比失败: {e}")
        raise


def main():
    """演示如何使用"""

    # 配置文件路径
    config_file = "/Users/carl/workspace/FP-LLM/configs/backtest/analyzer_config.yaml"

    print("🎯 策略报告生成器演示")
    print("=" * 50)

    # 示例1: 生成S0策略报告
    print("\n1️⃣ 生成S0策略报告")
    s0_result_file = (
        "/Users/carl/workspace/FP-LLM/data/backtest/results/s0_full_season_2023_24.yaml"
    )

    if Path(s0_result_file).exists():
        generate_report_for_strategy("S0", s0_result_file, config_file)
    else:
        print("⚠️ S0结果文件不存在，跳过演示")

    # 示例2: 如何为S1策略生成报告 (假设S1已实现)
    print("\n2️⃣ 如何为S1策略生成报告 (示例)")
    print("代码示例:")
    print(
        """
# 当S1策略完成回测后：
s1_result_file = "data/backtest/results/s1_full_season_2023_24.yaml"
generate_report_for_strategy("S1", s1_result_file, config_file)
"""
    )

    # 示例3: 如何对比多个策略 (假设有多个策略)
    print("\n3️⃣ 如何对比多个策略 (示例)")
    print("代码示例:")
    print(
        """
# 当有多个策略结果时：
strategies = ["S0", "S1", "S2"]
result_files = [
    "data/backtest/results/s0_full_season_2023_24.yaml",
    "data/backtest/results/s1_full_season_2023_24.yaml",
    "data/backtest/results/s2_full_season_2023_24.yaml"
]
compare_strategies(strategies, result_files, config_file)
"""
    )

    print("\n🎉 演示完成!")
    print("\n📋 使用说明:")
    print("1. 配置策略特征: 编辑 configs/backtest/analyzer_config.yaml")
    print("2. 运行回测: python scripts/run_backtest.py --strategy [策略名]")
    print("3. 生成报告: 调用 generate_report_for_strategy() 函数")
    print("4. 对比策略: 调用 compare_strategies() 函数")


if __name__ == "__main__":
    main()
