#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/dev_cold_start.sh 2 blend   # 从 GW=2 开始，用 blend 融合模式
#   bash scripts/dev_cold_start.sh           # 默认 GW=1, mode=blend
GW=${1:-1}
MODE=${2:-blend}

echo "[run] cold start orchestration ($MODE)"
python scripts/run_cold_start.py --gw "$GW" --mode "$MODE"
