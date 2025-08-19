# FP-LLM

一个以**总积分最大化**为目标的 Fantasy Premier League（FPL）工程化项目。
当前已实现：**M0 工程脚手架** → **M1 数据层** → **M2 特征工程** → **M3 基线预测**。
后续将迭代：阵容优化/转会（M4）、筹码启发式（M5）、报告与回测等。

> 免责声明：仅供学习研究，请遵守 FPL 与数据源的服务条款（TOS）。

---

## 功能概览（进度）

- ✅ **M0 工程化**：`uv`/venv、pre-commit、ruff/black/isort/mypy、pytest、CI。
- ✅ **M1 数据层**：拉取 FPL 公开端点（`bootstrap-static/`、`fixtures/` 等），标准化与清洗为 Parquet。
- ✅ **M2 特征工程**：未来 K 场 **FDR/主客修正**、**出场稳定性**、**近期表现代理** → `features[_gwXX].parquet`。
- ✅ **M3 基线预测**：位置内标准化 + 可用性加权 → 下一轮 `expected_points` → `predictions[_gwXX].parquet`。
- ⏳ **M4 优化器**：ILP 首发/阵型与 0/1/2 次转会枚举（预算、每队≤3、黑名单、扣分）。
- ⏳ **M5 筹码**：Wildcard / Bench Boost / Free Hit / Triple Captain 启发式。
- ⏳ **M6 报告**：`reports/gwXX/report.md`，可接入定时 PR。
- ⏳ **M2-HIST / M7 回测**：逐轮与多赛季历史、滚动回测与标定。

---

## 快速开始

### 0) 环境准备
```bash
# 建议使用 uv（或使用 python -m venv）
pip install -U uv

uv venv
# macOS/Linux
source .venv/bin/activate
# Windows (PowerShell)
# .\.venv\Scripts\Activate.ps1

uv pip install -e ".[dev]"
pre-commit install
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

### 4) 优化器与转会（M4）
```bash
# 准备阵容文件（示例见 configs/squad.sample.yaml）
cp configs/squad.sample.yaml configs/squad.yaml
# 替换其中的 player_id / bank / free_transfers

# 生成预测
python scripts/predict_points.py --gw 1

# 运行优化器（首发 + 转会建议）
python scripts/optimize_squad.py --gw 1 --squad configs/squad.yaml --pool-size 12 --max-transfers 2 --hit-cost 4
```

### 5) 优化器 + 筹码建议 + 报告
```bash
# 生成预测
python scripts/predict_points.py --gw 1

# 优化器（含筹码建议输出）
python scripts/optimize_squad.py --gw 1 --squad configs/squad.yaml --pool-size 12 --max-transfers 2 --hit-cost 4

# 生成 Markdown 报告
python scripts/generate_report.py --gw 1
# 输出：reports/gw01/report.md
```

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
- （可选）`schedule.yml`：按台北时区每周四/五自动跑 features→predictions 并创建 PR 固化产物。

---

## 版本与发布

建议使用 **SemVer**：
- `v0.2.0`：完成 M2（features）
- `v0.3.0`：完成 M3（predictions）

打标签：
```bash
git checkout main && git pull --ff-only
git tag -a v0.3.0 -m "M3: baseline predictions"
git push origin v0.3.0
```

（可选）在 GitHub **Releases** 中创建 Release，附上变更说明。

---

## 路线图

- **M4 优化器（下一步）**：ILP 首发 + 合法阵型；0/1/2 转会枚举（超出免费转会按 -4 扣分）；预算、每队≤3、黑名单与价格约束。
- **M5 筹码启发式**：双赛/空白周、Bench Boost 阈值、外卡触发、TC 候选。
- **M6 报告**：Markdown 报告生成与定时工作流固化 PR。
- **M2-HIST / M7 回测**：逐轮与多赛季历史摄取，形成 per-GW 快照，滚动回测与参数标定。
- **Agent 预留**：后续可接入 LLM 做新闻/伤停摘要与解释，不影响主流水线。

---

## 贡献

欢迎以 PR 形式参与开发（建议遵循 Conventional Commits）。
提交前请本地运行格式化、类型检查与单测，确保 CI 通过。

---

## 许可证

MIT License（见 `LICENSE`）。
