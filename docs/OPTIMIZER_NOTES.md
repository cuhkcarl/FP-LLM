# Optimizer Notes (M4)

## 目标
在 FPL 规则约束下最大化下一轮阵容的**期望分**（含队长加成），并在 0/1/2 次转会内给出收益最高的方案。

## 输入
- `data/processed/predictions[_gwXX].parquet`（M3 产物）
  - 关键列：`player_id, web_name, team_id, team_short, position, price_now, expected_points`
- `configs/squad.yaml`
  - `squad`: 15 名球员的 id
  - `bank`: 银行余额（£m）
  - `free_transfers`: 免费转会数（通常 1 或 2）
- 可选：`configs/base.yaml` 的 `blacklist`（禁用超高价球员或特定姓名）

## 首发选择（ILP）
- 决策变量：
  - `x_i ∈ {0,1}`：是否进入首发 11
  - `c_i ∈ {0,1}`：是否为队长（且 `c_i ≤ x_i`, `∑ c_i = 1`）
- 目标：`max ∑ x_i·EP_i + ∑ c_i·EP_i`（队长等价于再加一次该球员分）
- 约束：
  - GK 恰好 1；DEF ∈ [3,5]；MID ∈ [2,5]；FWD ∈ [1,3]；总计 11
  - （无需额外每队≤3，因为阵容层面已经满足）

## 转会枚举
- 基线：不转会，计算当前阵容的首发 + 队长分。
- 1 次转会：对每个 out（15 人），用**同位置**候选池（按 EP 前 K 名）替换，检查：
  - 每队≤3，预算（用 `price_now` 近似），位置配额（2GK/5DEF/5MID/3FWD）
- 2 次转会：枚举 out 对，并组合两个同位置候选池直积；用同样的约束剪枝。
- 收益：`Δ = NewXI_withC - Baseline_withC - 4·max(0, transfers - free_transfers)`

> 局限：未考虑历史买入价/卖出税；预算用 `price_now` 近似。回测阶段会补充更精细的资金流模型。

## CLI
```bash
# 生成预测（M3）
python scripts/predict_points.py --gw 1

# 运行优化器（M4）
python scripts/optimize_squad.py --gw 1 \
  --squad configs/squad.yaml \
  --pool-size 12 --max-transfers 2 --hit-cost 4
```

## 输出
- 当前阵容的最优首发与队长、预期分
- 最优转会方案（0/1/2），含：
  - 转出/转入名单、命中约束、命中预算
  - 新阵容的预期分与相对基线的净增益（扣除 hits）

## 后续扩展
- 资金模型（买入价/卖出税/队值、自动跟踪）
- 候选池裁剪（按赛程窗口、出场稳定性）
- 更智能的 Bench 顺序（主客/对手难度/分钟风险）
- 筹码决策（M5）：双赛/空白、BB、WC、FH、TC 启发式

# Chips Heuristics (M5)

- **Bench Boost**：替补四人期望分 ≥ 阈值（默认 20）则建议；双赛周替补强时更偏向建议。
- **Triple Captain**：队长期望分 ≥ 9（单赛）或 ≥ 7.5（双赛）建议开启。
- **Free Hit**：预测可上场人数 < 9 则建议考虑（空白周兜底）。
- **Wildcard**：默认不自动触发（需结构性判断：长期赛程、资金、队伍分布等）。

阈值在 `configs/base.yaml -> chips.thresholds` 可调。

# Report (M6)
`scripts/generate_report.py --gw XX` 生成
`reports/gwXX/report.md`：包含首发/阵型、C/VC、替补、转会建议、筹码建议和关键数值。

# DGW 调整（M4+）
- 如果某队在该 GW 有多于 1 场比赛，按 `EP' = EP * (1 + α * (m-1))` 放大（默认 α=0.65）。
- 若 `availability_score < 0.5`，额外乘以 0.8 的折扣，抑制轮换/受伤风险导致的过度乐观。
- 参数可在 `configs/base.yaml -> dgw_adjust` 调整；也可通过 CLI `--use-dgw-adjust/--no-dgw-adjust` 开关控制。

# 替补排序启发式（M4+）
- 计算 `bench_score = EP * w_ep + availability * w_avail`（默认 `w_ep=1.0`, `w_avail=0.5`）。
- 外场优先，GK 固定最后（可通过 `BenchOrderParams.gk_last` 控制）。
- CLI 可通过 `--bench-weight-availability` 覆盖可用性权重。


# 资金模型（简化版）
- 阵容 YAML 可选字段 `purchase_prices` 记录买入价（单位：百万）。
- 卖出价规则：若 `current <= buy`，卖出价 = `current`；否则 = `buy + floor((current-buy)/0.2)*0.1`。
- 在优化阶段，我们把“我方阵容成员”的 `price_now` 临时替换为“卖出价”，让预算与队值自然生效；不改动预测与其它逻辑。
- 报告中会显示“计划执行后银行余额”，便于核对。
