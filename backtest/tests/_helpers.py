"""回测测试辅助：合成 K 线。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def buildLinearKline(days: int = 60, startPrice: float = 10.0,
                     dailyReturn: float = 0.01,
                     baseVolume: float = 1000.0,
                     startDate: str = "2024-01-02") -> pd.DataFrame:
    """构造线性上涨 K 线（每日恒定收益率）。"""
    dates = pd.bdate_range(start=startDate, periods=days)
    closes = startPrice * (1 + dailyReturn) ** np.arange(days)
    opens = np.concatenate([[startPrice], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.005
    lows = np.minimum(opens, closes) * 0.995
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(days, baseVolume, dtype=float),
    })


def buildFlatKline(days: int = 60, price: float = 10.0,
                   baseVolume: float = 1000.0,
                   startDate: str = "2024-01-02") -> pd.DataFrame:
    """构造横盘 K 线，用于检验无收益场景。"""
    dates = pd.bdate_range(start=startDate, periods=days)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": np.full(days, price),
        "high": np.full(days, price * 1.001),
        "low": np.full(days, price * 0.999),
        "close": np.full(days, price),
        "volume": np.full(days, baseVolume, dtype=float),
    })
