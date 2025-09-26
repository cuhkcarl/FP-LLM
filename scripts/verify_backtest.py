#!/usr/bin/env python3
"""
验证回测结果的准确性

手动计算GW1得分并与自动计算结果对比
"""

import pandas as pd
import yaml


def verify_gw1_calculation():
    """验证GW1得分计算的准确性"""

    # 1. 加载GW1数据
    gw1_data = pd.read_csv(
        "/Users/carl/workspace/FP-LLM/data/backtest/raw/vaastav/2023-24/gws/gw1.csv"
    )
    gw1_data["player_id"] = gw1_data["element"].astype(int)

    # 2. 加载S0配置
    with open("/Users/carl/workspace/FP-LLM/configs/backtest/s0_optimal_squad.yaml") as f:
        s0_config = yaml.safe_load(f)

    s0_squad = s0_config["optimal_squad_2023_24"]["player_ids"]

    # 3. 加载自动计算的结果
    with open("/Users/carl/workspace/FP-LLM/data/backtest/results/s0_test_results.yaml") as f:
        results = yaml.safe_load(f)

    gw1_result = results["gameweek_results"][0]  # 第一个是GW1
    auto_lineup = gw1_result["lineup"]["lineup"]
    auto_captain = gw1_result["lineup"]["captain_id"]
    auto_score = gw1_result["score"]

    print("=== GW1 得分验证 ===")
    print(f"自动计算得分: {auto_score}")
    print(f"队长: {auto_captain}")

    # 4. 手动计算得分
    manual_score = 0
    print("\n=== 手动计算明细 ===")

    # 获取所有首发球员
    all_starters = []
    for pos, players in auto_lineup.items():
        all_starters.extend(players)

    player_scores = {}

    for player_id in all_starters:
        player_data = gw1_data[gw1_data["player_id"] == player_id]
        if not player_data.empty:
            score = int(player_data["total_points"].iloc[0])
            name = player_data["name"].iloc[0]
            position = player_data["position"].iloc[0]

            player_scores[player_id] = score
            manual_score += score

            # 队长得分翻倍
            if player_id == auto_captain:
                manual_score += score
                print(
                    f"{name} ({position}) [{player_id}]: {score}分 + {score}分(队长) = {score*2}分"
                )
            else:
                print(f"{name} ({position}) [{player_id}]: {score}分")
        else:
            print(f"⚠️  未找到球员 {player_id} 的数据")

    print(f"\n手动计算总分: {manual_score}")
    print(f"自动计算总分: {auto_score}")
    print(f"差异: {abs(manual_score - auto_score)}")

    if manual_score == auto_score:
        print("✅ 得分计算正确!")
    else:
        print("❌ 得分计算有误!")

    # 5. 验证首发阵容组成
    print("\n=== 阵容验证 ===")
    pos_counts = {}
    for pos, players in auto_lineup.items():
        pos_counts[pos] = len(players)
        print(f"{pos}: {len(players)}人 - {players}")

    print(f"总首发人数: {sum(pos_counts.values())}")

    return manual_score == auto_score


def verify_s0_squad_in_data():
    """验证S0阵容中的所有球员都在GW1数据中"""

    gw1_data = pd.read_csv(
        "/Users/carl/workspace/FP-LLM/data/backtest/raw/vaastav/2023-24/gws/gw1.csv"
    )
    gw1_data["player_id"] = gw1_data["element"].astype(int)

    with open("/Users/carl/workspace/FP-LLM/configs/backtest/s0_optimal_squad.yaml") as f:
        s0_config = yaml.safe_load(f)

    s0_squad = s0_config["optimal_squad_2023_24"]["player_ids"]

    print("=== S0阵容数据验证 ===")

    missing_players = []
    for player_id in s0_squad:
        player_data = gw1_data[gw1_data["player_id"] == player_id]
        if player_data.empty:
            missing_players.append(player_id)
        else:
            name = player_data["name"].iloc[0]
            position = player_data["position"].iloc[0]
            team = player_data["team"].iloc[0]
            points = player_data["total_points"].iloc[0]
            print(f"✓ {player_id}: {name} ({position}, {team}) - {points}分")

    if missing_players:
        print(f"\n❌ 缺少数据的球员: {missing_players}")
        return False
    else:
        print(f"\n✅ 所有S0球员在GW1都有数据 ({len(s0_squad)}人)")
        return True


if __name__ == "__main__":
    print("开始验证回测计算准确性...\n")

    # 验证S0阵容数据完整性
    data_ok = verify_s0_squad_in_data()

    if data_ok:
        # 验证得分计算
        score_ok = verify_gw1_calculation()

        if score_ok:
            print("\n🎉 回测计算验证成功! 所有计算都是正确的。")
        else:
            print("\n⚠️  回测计算有问题，需要进一步检查。")
    else:
        print("\n⚠️  数据完整性检查失败。")
