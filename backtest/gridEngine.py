"""网格交易回测主入口（基于 backtrader 驱动 bar 循环，撮合由策略内部手动完成）。"""

from __future__ import annotations

import backtrader as bt
import pandas as pd

from . import metrics as _metrics
from . import results as _results
from ._gridStrategy import GridStrategy
from .engine import _validateKline


def runGridBacktest(kline: pd.DataFrame,
                    *,
                    gridSpacingPct: float = 0.02,
                    gridLevels: int = 5,
                    shareSize: int = 100,
                    centerPrice: float = 0.0,
                    initialCash: float = 100000.0,
                    commission: float = 0.0003,
                    stampTax: float = 0.001) -> dict:
    """运行静态网格回测。

    Args:
        kline: 列 date / open / high / low / close / volume
        gridSpacingPct: 每格间距（小数，0.02 = 2%）
        gridLevels: 上下各多少层（总层数 = gridLevels × 2）
        shareSize: 每格交易股数（A 股 100 整数倍）
        centerPrice: 基准价；0 表示用首日 close
        initialCash: 初始资金
        commission: 买卖双边佣金比例
        stampTax: 卖出印花税比例

    Returns:
        dict {equityCurve, trades, tradeEvents, openPositions, metrics, summary}
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
        commission=commission,
        stampTax=stampTax,
        initialCash=initialCash,
    )

    runs = cerebro.run()
    strat = runs[0]

    equityCurve = _results.buildEquityCurve(
        strat._equityRecords, initialCash)
    trades = _results.buildTrades(strat._tradeLog)
    tradeEvents = _results.buildTradeEvents(strat._eventLog)
    lastClose = float(feedDf["close"].iloc[-1]) if not feedDf.empty else 0.0
    openPositions = _results.buildOpenPositions(
        list(strat._openTrades.values()), lastClose)
    metricsDict = _metrics.computeMetrics(equityCurve, trades)

    cp = strat._centerPrice
    s = gridSpacingPct
    gl = gridLevels
    gridLines = {lvl: cp * (1 + s) ** lvl
                 for lvl in range(-gl, gl + 1)}
    priceLow = float(feedDf["low"].min()) if not feedDf.empty else 0.0
    priceHigh = float(feedDf["high"].max()) if not feedDf.empty else 0.0
    gridInfo = {
        "centerPrice": cp,
        "gridLines": gridLines,
        "buyRange": (gridLines[-gl], gridLines[0]),
        "sellRange": (gridLines[-gl + 1], gridLines[1]),
        "gridLow": gridLines[-gl],
        "gridHigh": gridLines[gl],
        "priceLow": priceLow,
        "priceHigh": priceHigh,
    }

    return {
        "equityCurve": equityCurve,
        "trades": trades,
        "tradeEvents": tradeEvents,
        "openPositions": openPositions,
        "metrics": metricsDict,
        "summary": _metrics.formatSummary(metricsDict),
        "gridInfo": gridInfo,
    }
