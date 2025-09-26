# Backtest Scripts

This directory will contain command-line tools for running backtests.

## Planned Scripts
- `run_backtest.py` - Main entry point for backtest execution
- `analyze_results.py` - Post-analysis and visualization tools
- `data_preparation.py` - Historical data download and processing

## Usage
```bash
# Run comprehensive backtest
python scripts/backtest/run_backtest.py configs/backtest/exp1_full_benchmarks.yaml

# Analyze results
python scripts/backtest/analyze_results.py results/backtest/latest/
```
