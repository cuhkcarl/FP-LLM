"""
策略模块

包含各种FPL回测策略的实现：
- S0: 静态基准策略（群体智慧）
- S1: 纯转会策略（待实现）
- S2: 完整策略（转会+芯片，待实现）
"""

from .s0_strategy import S0Strategy, load_s0_strategy

__all__ = ["S0Strategy", "load_s0_strategy"]
