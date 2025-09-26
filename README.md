# FP-LLM

一个以**总积分最大化**为目标的 Fantasy Premier League（FPL）工程化项目。
当前已实现端到端最小可用链路：数据 → 特征 → 预测 → 优化器/转会 → 筹码 → 报告（含结构化摘要）。

> 免责声明：仅供学习研究，请遵守 FPL 与数据源的服务条款（TOS）。

---

## 功能概览（进度）

- ✅ **M0 工程化**：`uv`/venv、ruff/black/isort/mypy、pytest、CI。
- ✅ **M1 数据层**：拉取 FPL 公开端点（`bootstrap-static/`、`fixtures/` 等），标准化与清洗为 Parquet。
- ✅ **M2 特征工程**：未来 K 场 **FDR/主客修正**、**出场稳定性**、**近期表现代理** → `features[_gwXX].parquet`。
- ✅ **M3 基线预测**：位置内标准化 + 可用性加权 → 下一轮 `expected_points` → `predictions[_gwXX].parquet`。
- ✅ **M4 优化器（最小可用）**：ILP 首发/阵型、0/1/2 次转会枚举；预算（含卖出价近似）、每队≤3、位置配额；支持黑名单与高价过滤；支持 DGW 放大与可用性折扣；支持以队值作为平手破除或多目标加成。
- ✅ **M5 筹码启发式（最小版）**：Bench Boost、Triple Captain、Free Hit；Wildcard 不自动触发。
- ✅ **M6 报告（最小版）**：`reports/gwXX/report.md` 与 `summary.json`（结构化摘要）。
- ⏳ **M2-HIST / 回测**：逐轮与多赛季历史、滚动回测与标定。

---

## 快速开始

### 0) 环境准备
```bash
# 建议使用 venv；以下示例使用项目已有的 .fpllm 虚拟环境约定
python -m venv .fpllm
source .fpllm/bin/activate  # macOS/Linux
# .\.fpllm\Scripts\Activate.ps1  # Windows

pip install -e ".[dev]"
```

> 国内加速（仅当前 venv 生效）：在 `.venv/pip.conf` 写入
> ```
> [global]
> index-url = https://pypi.tuna.tsinghua.edu.cn/simple
> extra-index-url = https://pypi.org/simple
> timeout = 15
> ```

### 1) 拉取原始数据（M1）
```bash
python scripts/fetch_fpl.py --out-dir data/raw/fpl --force-refresh
# 可选：指定一轮 live
python scripts/fetch_fpl.py --gw 1 --out-dir data/raw/fpl
```

### 2) 生成特征（M2）
```bash
# 未指定 --gw 时按当前时间判断未来赛程；推荐指定 --gw 与 --k
python scripts/build_features.py --gw 1 --k 3

# 产物（示例）
# data/interim/*.parquet
# data/processed/features_gw01.parquet  （或 features.parquet）
```

### 3) 生成预测（M3）
```bash
python scripts/predict_points.py --gw 1 --min-availability 0.15 --availability-power 1.0

# 产物（示例）
# data/processed/predictions_gw01.parquet
```

### 4) 优化器与转会（M4）（含 DGW 与替补排序）
```bash
# 准备阵容文件（示例见 configs/squad.sample.yaml）
cp configs/squad.sample.yaml configs/squad.yaml
# 替换其中的 player_id / bank / free_transfers

# 生成预测
python scripts/predict_points.py --gw 1

# 默认开启 DGW 调整，可关闭；支持黑名单/高价过滤；支持队值平手破除/多目标；可设置资金/队值约束
python scripts/optimize_squad.py --gw 1 --squad configs/squad.yaml \
  --use-dgw-adjust \
  --bench-weight-availability 0.5 \
  --respect-blacklist \
  --value-weight 0.0 \
  --min-bank-after 0.0 \
  --max-tv-drop 0.5
```
- `--use-dgw-adjust/--no-dgw-adjust`：是否对双赛/上场风险做期望分调整（默认开）
- `--bench-weight-availability`：替补排序中 `availability_score` 的权重（默认 0.5）
- `--respect-blacklist/--no-respect-blacklist`：是否遵从 `configs/base.yaml` 的黑名单/高价过滤
  - `configs/base.yaml.blacklist.names`
  - `configs/base.yaml.blacklist.price_min`
- `--value-weight`：将队值增减纳入多目标（0 表示仅平手破除）
- `--min-bank-after`：执行转会计划后银行余额下限（m）
- `--max-tv-drop`：允许的队值最大下降（m）

### 5) 优化器 + 筹码建议 + 报告
```bash
# 生成预测
python scripts/predict_points.py --gw 1

# 优化器（含筹码建议输出）
python scripts/optimize_squad.py --gw 1 --squad configs/squad.yaml --pool-size 12 --max-transfers 2 --hit-cost 4

# 生成 Markdown 报告
python scripts/generate_report.py --gw 1
# 输出：reports/gw01/report.md
# 同步结构化摘要：reports/gw01/summary.json
```
- `reports/gwXX/report.md`：人类可读报告
- `reports/gwXX/summary.json`：结构化摘要（XI/C/VC/bench EP、转会、资金/队值、筹码、阈值、优化器参数）

更多 CLI 使用示例与组合，见 `docs/CLI.md`。

### 冷启动（首轮/空阵容）
- 一键入口（推荐）：
```bash
python scripts/run_cold_start.py --gw 2 --mode blend
# 或纯冷启动：
python scripts/run_cold_start.py --gw 2 --mode cold_start
```
- 组成步骤（可单独运行）：
  - `scripts/fetch_last_season.py`：抓取上季 totals（幂等，已存在则跳过）
  - `scripts/predict_points.py --mode cold_start|blend`：使用上季 per90 + 可用性构造 EP（或与 baseline 融合）
  - `scripts/build_squad.py`：在预算/配额/每队≤3 下构建 15 人初始阵容
- 报告在阵容非 15 人时会自动给出“Initial Squad Suggestion”，并跳过“Transfers Suggestion”

### 6) 资金（可选）
在 `configs/squad.yaml` 填写买入价（仅对持有球员需要）：
```yaml
purchase_prices:
  123: 7.0
  456: 4.5
```
优化器会自动按 FPL 规则计算卖出价并纳入预算；并在分数平手时可使用队值变化作为决策辅助。

---

## 目录结构（核心）

```
configs/               # 配置（基线参数、黑名单、优化器阈值等）
data/
  raw/fpl/             # 原始 JSON
  raw/http_cache/      # HTTP 缓存（URL sha1）
  interim/             # 标准化 & 清洗后的中间结果
  processed/           # 特征与预测产物（M2/M3）
docs/
  ARCHITECTURE.md      # 架构与数据字典
  PREDICTION_NOTES.md  # 特征与预测说明（M2/M3）
reports/               # 每轮报告（M6）
scripts/
  fetch_fpl.py         # M1：拉取公开端点
  build_features.py    # M2：清洗+特征流水线
  predict_points.py    # M3：基线预测
src/
  fpl_data/            # clients / loaders / transforms
  prediction/          # baseline 预测
tests/                 # 单测与夹具
.github/workflows/     # CI / （可选）定时任务
```

---

## 配置（节选）

建议新增/维护 `configs/base.yaml`：

```yaml
season: 2025_26
current_gw: 1

blacklist:         # 可禁用超高价球员（示例：含萨拉赫/哈兰德）
  names: ["Mohamed Salah", "Erling Haaland"]
  price_min: 13.0  # >= 则禁用；设为 null 仅用显式名单

prediction:
  mode: "baseline"
  min_availability: 0.15
  availability_power: 1.0
  base_by_pos: { GK: 3.4, DEF: 3.7, MID: 4.5, FWD: 4.8 }
  spread_by_pos: { GK: 1.1, DEF: 1.2, MID: 1.4, FWD: 1.4 }

chips:
  thresholds:
    bench_boost_min_bench_ep: 20.0
    triple_captain_min_ep: 9.0
    triple_captain_min_ep_if_double: 7.5
    free_hit_min_active_starters: 9

dgw_adjust:
  alpha_per_extra_match: 0.65
  availability_floor: 0.50
  availability_penalty: 0.80

bench_order:
  weight_availability: 0.5

optimizer:          # 可选：优化器默认参数（CLI 可覆盖）
  value_weight: 0.0
  min_bank_after: null
  max_tv_drop: null
```

> 注：M2 的赛程窗口 K、位置 α/β（FDR/主客修正强度）目前在 `scripts/build_features.py` 中有默认值；后续会统一外置到 `configs/`。

---

## 预测说明（M3 简要）

- **输入**：`features[_gwXX].parquet`（来自 M2）
- **步骤**：
  1. 对 `fdr_adjusted_recent_score` 在**位置内**做 z-score；
  2. 映射为 `expected_points = base_pos + spread_pos * z`（裁剪到 `[0,12]`）；
  3. 按 `availability_score` 做加权（低于阈值置 0）。
- **输出**：`predictions[_gwXX].parquet`，含
  `player_id, web_name, position, team_short, price_now, selected_by_pct, expected_points, rank_pos, rank_overall`。
- 详细公式与默认参数见 `docs/PREDICTION_NOTES.md`。

---

## 测试与 CI

本地：
```bash
ruff check .
black --check .
isort --check-only .
mypy src
pytest -q
```

GitHub Actions：
- `ci.yml`：push/PR 自动运行 lint + type check + tests。
- （计划）`schedule.yml`：按台北时区每周四/五自动跑 features→predictions→optimize→report 并创建 PR 固化产物（产物包含 `report.md` 与 `summary.json`）。

---

## 版本与发布

建议使用 **SemVer**：
- `v0.2.0`：完成 M2（features）
- `v0.3.0`：完成 M3（predictions）
- `v0.4.0`：完成 M4/M5/M6 最小链路（黑名单修复、资金/队值指标、报告与 summary.json、最小单测）

打标签：
```bash
git checkout main && git pull --ff-only
git tag -a v0.4.0 -m "M4-M6 minimal pipeline"
git push origin v0.4.0
```

（可选）在 GitHub **Releases** 中创建 Release，附上变更说明。

---

## 路线图

- **P1（可用性）**：`summary.json` 扩展与可视化、定时流水线 PR、替补排序启发式增强。
- **P2（稳健性）**：DGW 参数化与轮换风险折扣、资金模型进一步完善（队值与银行的约束策略）。
- **P3（评估）**：Actuals 摄取与指标（MAE/NDCG@K/top11）与回测框架。
- **Agent 预留**：后续可接入 LLM 做新闻/伤停摘要与解释，不影响主流水线。

---

## 贡献

欢迎以 PR 形式参与开发（建议遵循 Conventional Commits）。
提交前请本地运行格式化、类型检查与单测，确保 CI 通过。

---

## 许可证

MIT License（见 `LICENSE`）。
