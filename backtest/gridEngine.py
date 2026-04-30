"""网格交易回测主入口（基于 backtrader）。"""

from __future__ import annotations

import backtrader as bt
import pandas as pd

from . import metrics as _metrics
from . import results as _results
from ._gridStrategy import GridStrategy
from ._strategy import EquityAnalyzer, StampTaxCommission
from .engine import _validateKline


def runGridBacktest(kline: pd.DataFrame,
                    *,
                    gridSpacingPct: float = 0.02,
                    gridLevels: int = 10,
                    shareSize: int = 100,
                    centerPrice: float = 0.0,
                    initialCash: float = 100000.0,
                    commission: float = 0.0003,
                    stampTax: float = 0.001,
                    slippage: float = 0.0) -> dict:
    """运行等比网格回测。

    Args:
        kline: 列 date / open / high / low / close / volume
        gridSpacingPct: 每格间距（小数，0.02 = 2%）
        gridLevels: 上下各最多多少档
        shareSize: 每格交易股数（A 股 100 整数倍）
        centerPrice: 中心基准价；0 表示用首根 close 自动
        initialCash / commission / stampTax / slippage: 同 runBacktest

    Returns:
        dict {equityCurve, trades, metrics, summary}
    """
    if gridSpacingPct <= 0:
        raise ValueError("gridSpacingPct 必须 > 0")
    if gridLevels <= 0:
        raise ValueError("gridLevels 必须 > 0")
    if shareSize <= 0 or shareSize % 100 != 0:
        raise ValueError("shareSize 必须是 100 的正整数倍")

    feedDf = _validateKline(kline)

    cerebro = bt.Cerebro(stdstats=False)
    data = bt.feeds.PandasData(
        dataname=feedDf,
        datetime=None,
        open="open", high="high", low="low",
        close="close", volume="volume",
        openinterest="openinterest",
    )
    cerebro.adddata(data)
    cerebro.addstrategy(
        GridStrategy,
        centerPrice=centerPrice,
        gridSpacingPct=gridSpacingPct,
        gridLevels=gridLevels,
        shareSize=shareSize,
    )

    cerebro.broker.setcash(initialCash)
    commInfo = StampTaxCommission(commission=commission, stampTax=stampTax)
    cerebro.broker.addcommissioninfo(commInfo)
    if slippage > 0:
        cerebro.broker.set_slippage_perc(slippage)

    cerebro.addanalyzer(EquityAnalyzer, _name="equity")
    runs = cerebro.run()
    strat = runs[0]

    equityCurve = _results.buildEquityCurve(
        strat.analyzers.equity.get_analysis(), initialCash)
    trades = _results.buildTrades(strat._tradeLog)
    tradeEvents = _results.buildTradeEvents(strat._eventLog)
    lastClose = float(feedDf["close"].iloc[-1]) if not feedDf.empty else 0.0
    openPositions = _results.buildOpenPositions(
        list(strat._openTrades.values()), lastClose)
    metricsDict = _metrics.computeMetrics(equityCurve, trades)

    return {
        "equityCurve": equityCurve,
        "trades": trades,
        "tradeEvents": tradeEvents,
        "openPositions": openPositions,
        "metrics": metricsDict,
        "summary": _metrics.formatSummary(metricsDict),
    }
