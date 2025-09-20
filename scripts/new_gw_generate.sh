#!/usr/bin/env bash
set -euo pipefail

source .fpllm/bin/activate
GW=$1
export FP_PROGRESS=1 FP_PROGRESS_EVERY=100 PYTHONUNBUFFERED=1

CONFIG_PATH="configs/base.yaml"

python scripts/fetch_fpl.py --gw "$GW"

python scripts/build_features.py --gw "$GW" --config-path "$CONFIG_PATH"

python scripts/predict_points.py \
  --gw "$GW" \
  --mode blend \
  --blend-decay-gws 4 \
  --config-path "$CONFIG_PATH"

python scripts/optimize_squad.py --gw "$GW"

python scripts/generate_report.py --gw "$GW" | cat
