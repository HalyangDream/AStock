"""strategy 包：基于 K 线的形态 / 信号 / 回测等策略层工具。

与数据层 astock 完全解耦：
- 输入：pandas.DataFrame（列: date, open, high, low, close, volume）
- 输出：pandas.DataFrame（形态结果 / 信号序列 / 回测指标）
"""

from . import patterns
from . import scan

__all__ = ["patterns", "scan"]
