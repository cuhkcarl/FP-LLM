#!/usr/bin/env python3
"""
数据完整性检查工具

检查回测数据的完整性和质量问题
"""

from pathlib import Path

import pandas as pd


def check_data_integrity(season: str = "2023-24") -> dict:
    """检查指定赛季的数据完整性"""

    data_dir = Path(f"/Users/carl/workspace/FP-LLM/data/backtest/raw/vaastav/{season}/gws")
    s0_players = [368, 398, 5, 143, 135, 538, 131, 430, 396, 524, 597, 19, 355, 226, 14]

    report = {"season": season, "total_gameweeks": 38, "issues": [], "summary": {}}

    missing_files = []
    incomplete_data = []
    s0_coverage_issues = []

    print(f"🔍 检查 {season} 赛季数据完整性...")

    for gw in range(1, 39):
        gw_file = data_dir / f"gw{gw}.csv"

        if not gw_file.exists():
            missing_files.append(gw)
            print(f"❌ GW{gw}: 文件缺失")
            continue

        try:
            df = pd.read_csv(gw_file)
            total_players = len(df)

            # 检查数据量是否异常
            if total_players < 500:
                incomplete_data.append({"gw": gw, "player_count": total_players})
                print(f"⚠️  GW{gw}: 数据量异常 ({total_players} 名球员)")

            # 检查S0阵容球员覆盖情况
            s0_found = df[df["element"].isin(s0_players)]
            s0_count = len(s0_found)

            if s0_count < 15:
                missing_s0_ids = set(s0_players) - set(s0_found["element"].tolist())
                s0_coverage_issues.append(
                    {
                        "gw": gw,
                        "found": s0_count,
                        "missing_count": 15 - s0_count,
                        "missing_ids": list(missing_s0_ids),
                    }
                )
                print(f"⚠️  GW{gw}: S0球员缺失 ({s0_count}/15 找到)")

        except Exception as e:
            print(f"❌ GW{gw}: 读取错误 - {e}")
            incomplete_data.append({"gw": gw, "error": str(e)})

    # 汇总问题
    report["issues"] = {
        "missing_files": missing_files,
        "incomplete_data": incomplete_data,
        "s0_coverage_issues": s0_coverage_issues,
    }

    # 生成汇总
    total_issues = len(missing_files) + len(incomplete_data) + len(s0_coverage_issues)
    usable_gameweeks = 38 - len(missing_files) - len(incomplete_data) - len(s0_coverage_issues)

    report["summary"] = {
        "total_issues": total_issues,
        "usable_gameweeks": usable_gameweeks,
        "data_completeness": f"{usable_gameweeks}/38 ({usable_gameweeks/38*100:.1f}%)",
        "missing_file_count": len(missing_files),
        "incomplete_data_count": len(incomplete_data),
        "s0_coverage_issue_count": len(s0_coverage_issues),
    }

    return report


def print_detailed_report(report: dict):
    """打印详细的数据完整性报告"""

    print(f"\n📊 {report['season']} 赛季数据完整性报告")
    print("=" * 50)

    summary = report["summary"]
    print(f"📈 数据可用性: {summary['data_completeness']}")
    print(f"🎯 可用周数: {summary['usable_gameweeks']}")
    print(f"⚠️  问题总数: {summary['total_issues']}")

    issues = report["issues"]

    if issues["missing_files"]:
        print(f"\n❌ 文件缺失 ({len(issues['missing_files'])}周):")
        for gw in issues["missing_files"]:
            print(f"   - GW{gw}: 数据文件不存在")

    if issues["incomplete_data"]:
        print(f"\n⚠️  数据异常 ({len(issues['incomplete_data'])}周):")
        for item in issues["incomplete_data"]:
            if "error" in item:
                print(f"   - GW{item['gw']}: {item['error']}")
            else:
                print(f"   - GW{item['gw']}: 只有{item['player_count']}名球员 (正常应该>600)")

    if issues["s0_coverage_issues"]:
        print(f"\n⚠️  S0阵容覆盖问题 ({len(issues['s0_coverage_issues'])}周):")
        for item in issues["s0_coverage_issues"]:
            print(
                f"   - GW{item['gw']}: 找到{item['found']}/15名球员，缺失{item['missing_count']}名"
            )

    print("\n💡 影响分析:")
    if summary["usable_gameweeks"] == 38:
        print("   ✅ 数据完整，分析结果可靠")
    elif summary["usable_gameweeks"] >= 35:
        print("   🟡 数据基本完整，分析结果可参考，建议补充缺失数据")
    elif summary["usable_gameweeks"] >= 30:
        print("   🟠 数据不够完整，分析结果仅供参考")
    else:
        print("   🔴 数据严重不完整，分析结果不可靠")

    print("\n📋 建议:")
    if issues["missing_files"]:
        print("   1. 从vaastav/FPL仓库获取缺失的gameweek数据文件")
    if issues["incomplete_data"] or issues["s0_coverage_issues"]:
        print("   2. 检查数据源质量，确保包含所有球员信息")
    if summary["total_issues"] > 0:
        print("   3. 修复数据问题后重新运行回测以获得更准确的结果")


def main():
    """主函数"""
    try:
        report = check_data_integrity("2023-24")
        print_detailed_report(report)

        # 保存报告
        import json

        output_path = (
            "/Users/carl/workspace/FP-LLM/data/backtest/analysis/data_integrity_report.json"
        )

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n💾 详细报告已保存到: {output_path}")

    except Exception as e:
        print(f"❌ 检查失败: {e}")


if __name__ == "__main__":
    main()
