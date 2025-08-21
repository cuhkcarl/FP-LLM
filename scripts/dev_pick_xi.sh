#!/usr/bin/env bash
set -euo pipefail

# Daily pipeline to pick XI/Transfers + report (assumes predictions ready)
# Usage: bash scripts/dev_pick_xi.sh 1

GW=${1:-1}

echo "[1/3] optimize_squad (console summary)"
python scripts/optimize_squad.py --gw "$GW" --squad configs/squad.yaml --respect-blacklist --use-dgw-adjust || true

echo "[2/3] evaluate (if actuals available)"
python scripts/fetch_actuals.py --gw "$GW" || true
python scripts/evaluate_gw.py --gw "$GW" || true

echo "[3/3] generate report"
python scripts/generate_report.py --gw "$GW"
