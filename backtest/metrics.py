"""绩效指标计算。

输入：buildEquityCurve / buildTrades 的输出 DataFrame。
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

_TRADING_DAYS_PER_YEAR = 252

_EMPTY_METRICS: Dict[str, float] = {
    "totalReturn": 0.0,
    "annualReturn": 0.0,
    "sharpe": 0.0,
    "maxDrawdown": 0.0,
    "winRate": 0.0,
    "tradeCount": 0,
    "avgHoldDays": 0.0,
    "avgPnlPct": 0.0,
}


def computeMetrics(equity: pd.DataFrame, trades: pd.DataFrame) -> Dict[str, float]:
    """根据净值曲线 + 交易明细计算指标。"""
    if equity is None or equity.empty:
        return dict(_EMPTY_METRICS)

    values = equity["value"].astype(float).to_numpy()
    initial = float(values[0])
    final = float(values[-1])
    totalReturn = (final / initial) - 1 if initial else 0.0

    days = (equity["date"].iloc[-1] - equity["date"].iloc[0]).days
    years = max(days / 365.0, 1 / _TRADING_DAYS_PER_YEAR)
    annualReturn = (final / initial) ** (1 / years) - 1 if initial > 0 else 0.0

    daily = pd.Series(values).pct_change().dropna()
    if len(daily) > 1 and daily.std(ddof=0) > 0:
        sharpe = float(daily.mean() / daily.std(ddof=0)
                       * np.sqrt(_TRADING_DAYS_PER_YEAR))
    else:
        sharpe = 0.0

    runningMax = pd.Series(values).cummax()
    drawdown = (pd.Series(values) - runningMax) / runningMax
    maxDrawdown = float(drawdown.min()) if len(drawdown) else 0.0

    tradeCount = 0 if trades is None else int(len(trades))
    winRate = 0.0
    avgHoldDays = 0.0
    avgPnlPct = 0.0
    if tradeCount > 0:
        if "pnlNet" in trades.columns:
            winRate = float((trades["pnlNet"] > 0).sum() / tradeCount)
        elif "pnl" in trades.columns:
            winRate = float((trades["pnl"] > 0).sum() / tradeCount)
        if "barsHeld" in trades.columns:
            avgHoldDays = float(trades["barsHeld"].mean())
        if ("pnlNet" in trades.columns
                and "entryPrice" in trades.columns
                and "size" in trades.columns):
            costs = trades["entryPrice"] * trades["size"]
            avgPnlPct = float((trades["pnlNet"] / costs).mean())
        elif "pnlPct" in trades.columns:
            avgPnlPct = float(trades["pnlPct"].mean())

    return {
        "totalReturn": float(totalReturn),
        "annualReturn": float(annualReturn),
        "sharpe": sharpe,
        "maxDrawdown": maxDrawdown,
        "winRate": winRate,
        "tradeCount": tradeCount,
        "avgHoldDays": avgHoldDays,
        "avgPnlPct": avgPnlPct,
    }


def formatSummary(metricsDict: Dict[str, float]) -> str:
    """单行可读摘要。"""
    return (
        f"trades={metricsDict.get('tradeCount', 0)} "
        f"totalReturn={metricsDict.get('totalReturn', 0):.2%} "
        f"annualReturn={metricsDict.get('annualReturn', 0):.2%} "
        f"sharpe={metricsDict.get('sharpe', 0):.2f} "
        f"maxDD={metricsDict.get('maxDrawdown', 0):.2%} "
        f"winRate={metricsDict.get('winRate', 0):.2%} "
        f"avgHold={metricsDict.get('avgHoldDays', 0):.1f}d"
    )
