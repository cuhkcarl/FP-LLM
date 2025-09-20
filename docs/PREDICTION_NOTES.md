# Prediction Notes (M2)

> 本文解释 M2「特征工程」从输入到输出的**数据流**、每个数据文件的意义、做了哪些加工/聚合、产出了哪些特征，以及这些特征存在的理由与使用方式。该特征表将直接供 M3 预测模块消费。

---

## 0) 输入与输出总览

**输入（来自 M1 清洗产物）**
- `data/interim/players_clean.parquet`
  - 每名球员的当前赛季聚合字段（来自 FPL 官方 `bootstrap-static`），含：`player_id(id)`、`web_name`、`team_id`、`position(GK/DEF/MID/FWD)`、`price_now(£m)`、`minutes`、`total_points`、`form`、`status`、`chance_of_playing_next_round`、`selected_by_pct` 等。
- `data/interim/fixtures_clean.parquet`
  - 赛程表（来自 `fixtures`），含：`event(GW)`、`kickoff_time(UTC)`、`team_h/team_a`、`home_fdr/away_fdr`、`finished`、主客队名称缩写等。

**输出（供 M3 使用）**
- `data/processed/features.parquet`（或 `features_gwXX.parquet`）
  - 主键/画像：`player_id, web_name, team_id, team_short, position, price_now, selected_by_pct`
  - 近期表现代理：`recent_score_wma`
  - 赛程窗口（未来 K 场）：`upcoming_mean_fdr, upcoming_home_ratio, days_to_next`
  - 出场稳定性：`availability_score (0-1), likely_starter (bool)`
  - 赛程修正后分：`fdr_adjusted_recent_score`（供 M3 直接当作“基线预测”或其一）

---

## 1) 数据流（Data Flow）

### Step A：加载清洗产物
从 `players_clean.parquet` 与 `fixtures_clean.parquet` 读取标准化表。这里的数据是**当前赛季的快照聚合**（非逐轮历史）。

### Step B：计算球队未来 K 场赛程特征（team-level → player merge）
对每支球队，按 `event`（或 `kickoff_time`）排序，截取未来 `K` 场（默认 `K=3`），计算：
- `upcoming_mean_fdr`：己方视角的平均对阵难度（FDR 1..5，3为中性）
- `upcoming_home_ratio`：这 `K` 场中主场占比 ∈ [0,1]
- `days_to_next`：距离最近一场比赛的天数（用于体现时间临近度）

将上述球队级别统计 **回填** 给该队所有球员。

### Step C：出场稳定性（availability）
用 `status`（a/d/i/s）与 `chance_of_playing_next_round`（0..100）组合出：
- `availability_score` ∈ [0,1]：0.5×`status_weight` + 0.5×`chance/100`
- `likely_starter`：`availability_score >= 0.70` 的布尔判定

> 目的：避免选到「很可能不出场」的球员，把这类风险以一个可解释分数反映到后续的预测/优化中。

### Step D：近期表现代理（recent）
基于当前赛季聚合值构造一个**可解释且零训练成本**的代理分：
- `points_per_90` = `total_points` / max(1, minutes/90)
- `recent_score_wma` = 0.7 * form + 0.3 * `points_per_90`

- `form`：FPL 官方的近况指标（字符串数字，已转 float）
- `points_per_90`：单位时间效率，缓解“出场时长差异”的干扰

> 目的：尚未引入逐轮历史与外部 xG/xA 的情况下，快速得到一个与近期状态相关的强基线。

### Step E：FDR / 主客修正（future-aware）
对 `recent_score_wma` 做赛程感知修正（位置敏感）：
alpha_pos, beta_pos 由位置决定（默认 GK/DEF: α=0.10, MID=0.08, FWD=0.06；主场奖励 β ~ 0.02~0.04）

- fdr_adjusted_recent_score =
recent_score_wma * (1 - alpha_pos * (mean_fdr - 3) / 2) * (1 + beta_pos * home_ratio)

- FDR > 3 → 惩罚，FDR < 3 → 奖励；主场比例越高加成越大

> 目的：把**未来赛程**的强弱和主客优势引入到「近期表现」的评分中，使其更贴近日常策略的直觉（“接下来 2-3 轮好赛程更值得买”）。

### Step F：导出特征表
保留画像字段与上述特征列，写出 `features.parquet / features_gwXX.parquet`。该表是 M3 的**唯一输入源**（也可叠加更丰富的特征）。

---

## 2) 字段字典（Features Schema）

| 列名 | 类型 | 含义与来源 | 典型范围/备注 |
|---|---|---|---|
| player_id | int | 球员ID（来自 players_clean） | 主键 |
| web_name | string | 展示名 | - |
| team_id / team_short | int / string | 球队ID / 缩写 | - |
| position | string | {GK, DEF, MID, FWD} | - |
| price_now | float | 现价（£m） | >0 |
| selected_by_pct | float | 所有率 | [0,100] |
| status | string | 出场状态（a/d/i/s） | - |
| availability_score | float | 出场稳定性分 | [0,1] |
| likely_starter | bool | 是否可能首发 | availability_score>=0.70 |
| form | float | 近况（FPL 官方） | ≥0 |
| minutes | int | 本季总出场分钟 | ≥0 |
| total_points | int | 本季总分 | ≥0 |
| recent_score_wma | float | 近期表现代理 = 0.7*form + 0.3*points_per_90 | ≥0 为主 |
| upcoming_mean_fdr | float | 未来 K 场平均 FDR（己方视角） | 1..5 |
| upcoming_home_ratio | float | 未来 K 场主场占比 | [0,1] |
| days_to_next | float | 距离最近一场比赛的天数 | 可负/正，正常≥0 |
| fdr_adjusted_recent_score | float | 赛程/主客修正后的近期分 | 用于 M3 基线 |

---

## 3) 为什么需要这些特征？

- **recent_score_wma**：转会/首发决策基本都在意“近期状态 + 单位时间效率”，它是无需历史明细就能构造的强信号，训练成本为 0。
- **upcoming_mean_fdr / home_ratio**：FPL 策略的共识是“看未来几轮赛程”；这里把直觉量化为可解释的两个维度。
- **fdr_adjusted_recent_score**：把“状态 × 未来赛程”合并成一个分数，直接可用于排序（M3 的 baseline 甚至可以把它当作 expected_points 的近似）。
- **availability_score / likely_starter**：把“能不能上”的风险显式量化，防止纯粹按分排序选到伤停/轮换。
- **价格与所有率（price_now / selected_by_pct）**：为 M4 优化器与差异化策略准备；价格约束直接进入优化；所有率用于“风险/差异化”后续扩展。

---

## 4) 局限与扩展（重要）

当前 M2 的特征**不包含逐轮历史或多赛季数据**，因此：
- `recent_score_wma` 以聚合字段近似“近期”，在赛季初可偏噪。
- 未使用 xG/xA 等外部高级数据。
- 回测（多赛季滚动）暂不可直接用该表，需要扩展历史摄取。

**扩展路线（建议）**
- **M2-HIST**：抓取 `element-summary/{player_id}` 逐球员逐轮历史（仅当前赛季/近几个赛季），构建 per-GW 面板数据，再真正计算“最近 N 轮 WMA”等特征。
- **M2-X**：接入公开的历史赛季数据集（多赛季），用于回测与模型训练；将输出 `data/history/<season>/...` 与统一的 `features_gwXX.parquet` 快照。
- **M2-ADV**：融合 xG/xA/BPS 等高级指标；在 M3 才引入轻量回归/集成模型。

---

## 5) 配置与参数（默认）

- 未来赛程窗口 `K=3`
- 位置惩罚/奖励：`alpha_pos={GK:0.10, DEF:0.10, MID:0.08, FWD:0.06}`；`beta_pos={GK:0.02, DEF:0.03, MID:0.03, FWD:0.04}`
- 首发阈值：`availability_score>=0.70`
- 输出文件：`data/processed/features.parquet`（或 `features_gwXX.parquet`）

## 5) 配置与参数（默认）

- `build_features.py`
  - `--gw`: 指定构建哪一轮（不填则按当前时间判定未来赛程窗口）
  - `--k`: 未来赛程窗口大小（默认 3）
  - `--config-path`: 读取 `configs/base.yaml` 中的排名参数
- `predict_points.py`
  - `--mode baseline | cold_start | blend`
  - `--blend-decay-gws`: blend 模式的衰减窗口（默认 4）
  - `--min-availability` & `--availability-power`: 可用性阈值与幂次
  - `--config-path`: 与特征构建保持一致，确保排名参数一致

### `prediction.ranking` 可调项

```yaml
prediction:
  ranking:
    shrink_k: 3.0                # 分钟收缩强度（分钟/90 的伪场次）
    minutes_penalty: 1.0         # 低分钟回落幅度
    price_weight: 0.1            # 价格轻量加权（用于区分平分）
    minutes_for_full_weight: 180 # 达到该分钟视为权重满额
    minutes_weight_exponent: 0.5 # 低分钟折扣的指数
```

参数为空时会退回默认值；修改配置后需要重新运行 `build_features.py` 或使用辅助脚本回写历史 features，再重新执行 `predict_points.py`。
