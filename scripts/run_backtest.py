#!/usr/bin/env python3
"""
FPL回测系统主入口

提供简单易用的接口来运行各种策略的回测
"""

import argparse
import sys
from pathlib import Path

# 添加src到路径
sys.path.append(str(Path(__file__).parent.parent / "src"))

from backtest.engine import run_s0_backtest


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="FPL策略回测系统")
    parser.add_argument("--strategy", default="s0", choices=["s0"], help="策略类型")
    parser.add_argument("--season", default="2023-24", help="赛季")
    parser.add_argument("--start-gw", type=int, default=1, help="开始gameweek")
    parser.add_argument("--end-gw", type=int, default=5, help="结束gameweek")
    parser.add_argument("--formation", default="3-5-2", help="阵型")
    parser.add_argument("--output", help="结果输出文件路径")

    args = parser.parse_args()

    print("=== FPL策略回测 ===")
    print(f"策略: {args.strategy.upper()}")
    print(f"赛季: {args.season}")
    print(f"范围: GW{args.start_gw}-{args.end_gw}")
    print(f"阵型: {args.formation}")

    try:
        if args.strategy == "s0":
            results = run_s0_backtest(
                season=args.season,
                start_gw=args.start_gw,
                end_gw=args.end_gw,
                formation=args.formation,
            )

            # 输出结果摘要
            print("\n=== 回测结果 ===")
            print(f"总得分: {results['total_points']}")
            print(f"平均得分: {results['average_points_per_gw']}")
            print(f"完成周数: {results['gameweeks_completed']}")
            print(f"最佳周: GW{results['best_gw']['gw']} ({results['best_gw']['score']}分)")
            print(f"最差周: GW{results['worst_gw']['gw']} ({results['worst_gw']['score']}分)")

            # 保存结果
            if args.output:
                output_path = args.output
            else:
                output_path = f"data/backtest/results/{args.strategy}_{args.season.replace('-', '_')}_gw{args.start_gw}_{args.end_gw}.yaml"

            from backtest.engine import BacktestEngine

            engine = BacktestEngine()
            engine.save_results(results, output_path)

            print(f"\n✅ 回测完成! 结果已保存到: {output_path}")

        else:
            print(f"❌ 不支持的策略: {args.strategy}")
            return 1

    except Exception as e:
        print(f"❌ 回测失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
