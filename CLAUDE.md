# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

FP-LLM is an end-to-end Fantasy Premier League (FPL) engineering project that maximizes total points through a data → features → prediction → optimization → reports pipeline. The project uses Python with a modular architecture spanning data fetching, feature engineering, baseline prediction models, integer linear programming optimization, and automated reporting.

## Core Architecture

The system follows a pipeline approach with distinct modules:

- **M1 Data Layer** (`src/fpl_data/`): Fetches and standardizes FPL public API endpoints
- **M2 Feature Engineering** (`scripts/build_features.py`): Generates player features with fixture difficulty rating (FDR) adjustments and availability scoring
- **M3 Prediction** (`src/prediction/`): Baseline and cold-start prediction models generating expected points
- **M4 Optimization** (`src/optimizer/`): Integer linear programming for squad selection and transfers with budget constraints
- **M5 Chip Strategy** (`src/optimizer/chips.py`): Heuristic chip activation (Bench Boost, Triple Captain, Free Hit)
- **M6 Reporting** (`scripts/generate_report.py`): Markdown reports with structured JSON summaries

### Key Data Flow

1. Raw FPL JSON → standardized Parquet files (`data/interim/`)
2. Players + fixtures → feature engineering → `features_gwXX.parquet`
3. Features → prediction models → `predictions_gwXX.parquet`
4. Predictions + current squad → optimization → transfer suggestions + starting XI
5. Results → markdown report + structured summary JSON

## Essential Commands

### Development Environment
```bash
# Setup virtual environment (recommended: .fpllm)
python -m venv .fpllm
source .fpllm/bin/activate  # macOS/Linux
pip install -e ".[dev]"
pre-commit install
```

### Code Quality Checks
```bash
# Run all checks (lint, format, type check, tests)
bash scripts/dev_check.sh

# Individual checks
ruff check .
black --check .
isort --check-only .
mypy src
pytest -q
```

### Full Pipeline Execution
```bash
# Cold start (for new season/empty squad)
python scripts/run_cold_start.py --gw 2 --mode blend

# Regular gameweek workflow
GW=3
python scripts/fetch_fpl.py --out-dir data/raw/fpl --force-refresh
python scripts/build_features.py --gw $GW --k 3
python scripts/predict_points.py --gw $GW
python scripts/optimize_squad.py --gw $GW --squad configs/squad.yaml --respect-blacklist --use-dgw-adjust
python scripts/generate_report.py --gw $GW
```

### Testing
```bash
# Run all tests
pytest -q

# Run specific test modules
pytest tests/test_prediction_baseline.py -v
pytest tests/test_optimizer.py -v
```

## Configuration Management

### Primary Config Files

- **`configs/base.yaml`**: Core system parameters including blacklists, prediction settings, chip thresholds, and optimizer defaults
- **`configs/squad.yaml`**: Current 15-player squad with bank balance and free transfers (copy from `squad.sample.yaml`)

### Key Configuration Sections

**Blacklist/Whitelist**: Control player eligibility in optimization
```yaml
blacklist:
  names: ["Mohamed Salah", "Erling Haaland"]  # Explicit exclusions
  price_min: 13.0  # Auto-exclude players above price threshold
whitelist:
  names: []  # Override blacklist for specific players
```

**Prediction Parameters**: Control expected points generation
```yaml
prediction:
  min_availability: 0.15  # Minimum availability threshold
  base_by_pos: {GK: 3.4, DEF: 3.7, MID: 4.5, FWD: 4.8}  # Position baselines
```

**Optimizer Settings**: ILP solver parameters
```yaml
optimizer:
  value_weight: 0.0  # Weight for team value in objective function
  min_bank_after: null  # Minimum bank balance after transfers
  max_tv_drop: null  # Maximum team value drop allowed
```

## Key Scripts and Usage Patterns

### Data Pipeline Scripts

- `scripts/fetch_fpl.py`: Pull raw FPL API data with HTTP caching
- `scripts/build_features.py`: Generate engineered features from raw data
- `scripts/predict_points.py`: Create expected points predictions (baseline or cold-start modes)
- `scripts/optimize_squad.py`: Run ILP optimization for transfers and starting XI
- `scripts/generate_report.py`: Create markdown reports with structured summaries

### Development Helpers

- `scripts/dev_check.sh`: Run complete code quality pipeline
- `scripts/dev_cold_start.sh`: Quick cold start for development/testing
- `scripts/run_cold_start.py`: One-click cold start orchestration

### Evaluation and Metrics

- `scripts/fetch_actuals.py`: Get real gameweek scores after matches complete
- `scripts/evaluate_gw.py`: Calculate prediction metrics (MAE, NDCG@11)
- `scripts/backfill_metrics.py`: Batch process historical metrics

## Important Implementation Details

### Squad Configuration
The `configs/squad.yaml` file must contain exactly 15 player IDs representing your current FPL team. Update `bank`, `free_transfers`, and `chips_available` to match your actual FPL account state.

### Prediction Modes
- **baseline**: Uses current season form and fixture difficulty ratings
- **cold_start**: Uses previous season data for early gameweeks
- **blend**: Combines both approaches with decay over first few gameweeks

### Optimization Constraints
The optimizer enforces FPL rules: exactly 11 starters (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD), max 3 players per team, budget constraints, and position quotas for full 15-player squad.

### DGW (Double Gameweek) Handling
The system can adjust expected points for players with multiple fixtures using `--use-dgw-adjust`, scaling points by extra match factor while applying availability penalties for rotation risk.

## File Structure Conventions

```
data/
  raw/fpl/           # Raw JSON from FPL API
  interim/           # Standardized Parquet files
  processed/         # Features, predictions, actuals
reports/gwXX/        # Generated reports per gameweek
  report.md          # Human-readable analysis
  summary.json       # Structured data summary
  metrics.json       # Model performance metrics
```

## CI/CD Pipeline

The project uses GitHub Actions for continuous integration:
- `ci.yaml`: Runs on push/PR with lint, format, type check, and tests
- `schedule.yaml`: Weekly automated pipeline (planned feature)

All code must pass ruff linting, black formatting, isort import ordering, mypy type checking, and pytest test suite before merging.
