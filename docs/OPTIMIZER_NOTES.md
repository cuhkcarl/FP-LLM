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
