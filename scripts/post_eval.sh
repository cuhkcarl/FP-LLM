source .fpllm/bin/activate
GW=$1
export FP_PROGRESS=1 FP_PROGRESS_EVERY=100 PYTHONUNBUFFERED=1

# 1) 抓 live（若已抓可跳过；为空可加 --force-refresh）
python scripts/fetch_fpl.py --gw $GW --force-refresh

# 2) 生成实际分 actuals
python scripts/fetch_actuals.py --gw $GW --force-refresh

# 3) 评估（会写 reports/gw02/metrics.json 与累计 metrics_history.parquet）
python scripts/evaluate_gw.py --gw $GW

# 4) 重新生成报告（整合模型表现指标）
python scripts/generate_report.py --gw $GW --metrics-only | cat
