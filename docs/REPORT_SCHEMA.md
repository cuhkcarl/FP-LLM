# Report Summary Schema

本文件描述 `reports/gwXX/summary.json` 的结构，便于看板/回测与自动化工作流消费。

## 顶层字段
- `gw` (int)：比赛周。
- `xi` (object)：首发/替补与关键指标。
- `transfers` (object)：转会建议与资金/队值指标。
- `chips` (object)：筹码建议（各筹码一个子对象）。
- `thresholds` (object)：筹码阈值快照。
- `blacklist` (object)：黑名单快照。
- `optimizer` (object)：优化器参数（用于复现实验）。
 - （可选）`skipped_reasons` (object)：跳过某步骤的原因（例如未提供 15 人阵容）。

## xi
- `starting_ids` (int[])：首发 11 人 `player_id`。
- `bench_ids` (int[])：替补 4 人 `player_id`（从前到后）。
- `captain_id` (int)：队长。
- `vice_id` (int)：副队。
- `expected_points_xi_with_captain` (float)：含双倍队长的 XI 期望分。
- `bench_ep` (float)：替补 4 人期望分之和。

## transfers
- `baseline_points` (float)：当前阵容 XI 期望分（含 C）。
- `transfers` (int)：建议转会数（0/1/2）。
- `out_ids` (int[])：卖出球员 id 列表。
- `in_ids` (int[])：买入球员 id 列表（与 `out_ids` 一一对应）。
- `hit_cost` (int)：付费转会扣分。
- `new_points` (float)：执行后 XI 期望分（含 C）。
- `net_gain` (float)：净增分 = `new_points - baseline_points - hit_cost`。
- `bank_after` (float)：执行计划后的银行余额（m）。
- `team_value_now` (float)：队值（卖出价总和 + 银行，执行前）。
- `team_value_after` (float)：队值（执行后，买入者以买入价计入卖出价口径）。
- `team_value_delta` (float)：队值变化。

## chips
每个筹码（`bench_boost`、`triple_captain`、`free_hit`、`wildcard`）为一个对象：
- `recommended` (bool)：是否建议使用。
- `reason` (string)：简要理由。
- `metrics` (object)：关键触发特征（例如 `bench_ep`、`captain_ep`、`captain_double`、`active_likely_starters`）。

## thresholds
- `bench_boost_min_bench_ep` (float)
- `triple_captain_min_ep` (float)
- `triple_captain_min_ep_if_double` (float)
- `free_hit_min_active_starters` (int)

## blacklist
- `names` (string[] | null)：显式黑名单。
- `price_min` (float | null)：价格下限（>= 过滤）。

## optimizer
- `value_weight` (float)：队值在目标函数中的权重（0 表示仅用作平手破除）。
- `min_bank_after` (float | null)：执行后银行下限。
- `max_tv_drop` (float | null)：允许的队值最大下降。

## 备注
- 队值口径：`sum(selling_price(current_price, buy_price)) + bank`；新买入球员的 `buy_price` 视为当前市场价。
- 期望分口径：包含队长双倍；已考虑（可选）DGW 放大与可用性折扣。
