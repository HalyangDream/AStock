"""backtest 包：基于 backtrader 的薄封装回测层。

输入：K 线 DataFrame + 信号 DataFrame
输出：dict {equityCurve, trades, metrics, summary}
"""

from . import adapters, metrics, results
from .engine import runBacktest
from .gridEngine import runGridBacktest
from .gridOptimizer import gridOptimize

__all__ = ["runBacktest", "runGridBacktest", "gridOptimize",
           "adapters", "metrics", "results"]
