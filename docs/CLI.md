# CLI 使用参考

本文档汇总项目内各脚本的调用方式与典型组合，按“数据 → 特征 → 预测 → 优化器/筹码 → 评估 → 报告/回填”组织。

> 约定：示例默认已激活虚拟环境 `.fpllm`。

## 0) 环境
```bash
python -m venv .fpllm
source .fpllm/bin/activate
pip install -e ".[dev]"
```

## 1) 数据抓取（M1）
- 拉取公开端点（含 HTTP 缓存）
```bash
python scripts/fetch_fpl.py --out-dir data/raw/fpl --force-refresh
# 指定某一轮（可选）
python scripts/fetch_fpl.py --gw 1 --out-dir data/raw/fpl
```

## 2) 特征生成（M2）
```bash
python scripts/build_features.py --gw 1 --k 3
# 产物：data/processed/features_gw01.parquet（或 features.parquet）
```

## 3) 预测生成（M3）
```bash
python scripts/predict_points.py --gw 1 \
  --min-availability 0.15 \
  --availability-power 1.0
# 产物：data/processed/predictions_gw01.parquet
```

## 4) 优化器与筹码（M4/M5）
- 准备阵容文件：`configs/squad.yaml`（示例见 `configs/squad.sample.yaml`）
```bash
python scripts/optimize_squad.py --gw 1 --squad configs/squad.yaml \
  --use-dgw-adjust \
  --bench-weight-availability 0.5 \
  --respect-blacklist \
  --value-weight 0.0 \
  --min-bank-after 0.0 \
  --max-tv-drop 0.5
```
- 关键参数说明：
  - `--use-dgw-adjust/--no-dgw-adjust`：是否进行双赛/可用性调整（默认开）
  - `--bench-weight-availability`：替补排序中 `availability_score` 权重（默认 0.5）
  - `--respect-blacklist`：遵从 `configs/base.yaml.blacklist` 的姓名/高价过滤
  - `--value-weight`：将队值变化纳入多目标（0 表示仅平手破除）
  - `--min-bank-after`：执行转会后的银行余额下限（单位 m）
  - `--max-tv-drop`：允许的队值最大下降（单位 m）

## 5) 实得分与评估（Actuals + Metrics）
- 抓取真实分（GW 完成后可用）：
```bash
python scripts/fetch_actuals.py --gw 1
# 产物：data/processed/actuals_gw01.parquet
```
- 计算指标并写出 JSON：
```bash
python scripts/evaluate_gw.py --gw 1 --k-for-ndcg 11
# 产物：reports/gw01/metrics.json
```

## 6) 报告生成（M6）
```bash
python scripts/generate_report.py --gw 1
# 产物：reports/gw01/report.md 与 reports/gw01/summary.json
# 若存在 metrics.json，将在报告中附“Model Performance”；若存在 metrics_history.parquet，将附“近 5 轮平均”
```

## 7) 历史回填（可选）
- 批量回填多轮指标，并维护汇总：
```bash
python scripts/backfill_metrics.py --start-gw 1 --end-gw 5
# 产物：reports/gwXX/metrics.json 与 data/processed/metrics_history.parquet
```

## 8) 常用组合
- 单轮全流程（不含实时拉取 raw 数据）：
```bash
GW=1
python scripts/build_features.py --gw $GW --k 3
python scripts/predict_points.py --gw $GW
python scripts/optimize_squad.py --gw $GW --squad configs/squad.yaml --respect-blacklist --use-dgw-adjust
python scripts/fetch_actuals.py --gw $GW || true   # 若当轮未完会失败，可忽略
python scripts/evaluate_gw.py --gw $GW || true    # 仅在有 actuals 时成功
python scripts/generate_report.py --gw $GW
```

## 9) 定时工作流（CI）
- 工作流文件：`.github/workflows/schedule.yml`
  - 触发：每周四/周五 11:00（UTC+8）与手动 `workflow_dispatch`
  - 内容：features → predictions → optimize →（若有 actuals 则 evaluate）→ report → 自动创建 PR
- 手动触发：在 GitHub Actions 选择 `Weekly GW Pipeline` → `Run workflow`

## 10) 配置入口
- `configs/base.yaml`：
  - `blacklist.names` / `blacklist.price_min`
  - `dgw_adjust.*`、`bench_order.weight_availability`
  - `optimizer.value_weight` / `optimizer.min_bank_after` / `optimizer.max_tv_drop`
- `configs/squad.yaml`：
  - `squad`、`bank`、`free_transfers`、`purchase_prices`（可选）

> 更多：`docs/REPORT_SCHEMA.md` 描述 `summary.json` 与指标产物结构；README 列出项目结构、路线图与版本说明。
