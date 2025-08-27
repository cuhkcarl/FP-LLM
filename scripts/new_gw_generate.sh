source .fpllm/bin/activate
GW=$1
export FP_PROGRESS=1 FP_PROGRESS_EVERY=100 PYTHONUNBUFFERED=1

# 1) 拉取第3周数据
python scripts/fetch_fpl.py --gw $GW

# 2) 构建特征
python scripts/build_features.py --gw $GW

# 3) 预测分数：使用 blend（融合前两轮实际+上赛季），按需要调整衰减窗口
python scripts/predict_points.py --gw $GW --mode blend --blend-decay-gws 4

# 4) 优化阵容与转会（读取 configs/squad.yaml 当前阵容与资金/买入价）
python scripts/optimize_squad.py --gw $GW

# 5) 生成报告与 summary（reports/gw03/）
python scripts/generate_report.py --gw $GW | cat
