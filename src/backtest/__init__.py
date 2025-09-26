"""
FPL回测框架

这个包实现了完整的FPL策略回测系统，包括：
- S0/S1/S2策略实现
- 历史数据管理和回测执行引擎
- 数据驱动的结果分析和报告生成
- 可扩展的策略对比分析
"""

from .analyzer import ConfigurableAnalyzer, create_analyzer
from .engine import BacktestEngine, run_s0_backtest
from .strategies import S0Strategy, load_s0_strategy

__version__ = "0.1.0"
__all__ = [
    "BacktestEngine",
    "run_s0_backtest",
    "ConfigurableAnalyzer",
    "create_analyzer",
    "S0Strategy",
    "load_s0_strategy",
]
