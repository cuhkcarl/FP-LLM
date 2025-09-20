#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <GW> [--respect-blacklist|--no-respect-blacklist]" >&2
  exit 1
fi

GW=$1
shift || true

RESPECT_BLACKLIST="--respect-blacklist"
if [[ "${1:-}" == "--no-respect-blacklist" ]]; then
  RESPECT_BLACKLIST="--no-respect-blacklist"
  shift
fi

source .fpllm/bin/activate
export FP_PROGRESS=1 FP_PROGRESS_EVERY=100 PYTHONUNBUFFERED=1

CONFIG_PATH="configs/base.yaml"
PRED_PATH="data/processed/predictions_gw$(printf '%02d' "$GW").parquet"

python scripts/fetch_fpl.py --gw "$GW"
python scripts/build_features.py --gw "$GW" --config-path "$CONFIG_PATH"
python scripts/predict_points.py --gw "$GW" --mode baseline --config-path "$CONFIG_PATH"
python scripts/build_squad.py \
  --preds-path "$PRED_PATH" \
  --budget 100.0 \
  $RESPECT_BLACKLIST \
  --config-path "$CONFIG_PATH"

echo
echo "✅ Wildcard 建议已生成。请将上方打印的 15 位球员及银行信息手动写入 configs/squad.yaml。"
echo "随后可继续运行 optimize_squad.py / generate_report.py 进行后续流程。"
