"""回测引擎主入口。"""

from __future__ import annotations

import datetime as dt
from typing import Dict

import backtrader as bt
import pandas as pd

from . import metrics as _metrics
from . import results as _results
from ._strategy import EquityAnalyzer, SignalStrategy, StampTaxCommission

_SIZING_OPTS = {"all"}


def _validateKline(kline: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(kline.columns):
        missing = required - set(kline.columns)
        raise ValueError(f"kline 缺少列: {missing}")
    df = kline.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["openinterest"] = 0
    df = df.set_index("date")
    return df


def _buildSignalMap(signals: pd.DataFrame) -> Dict[dt.date, str]:
    if signals is None or signals.empty:
        return {}
    df = signals.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["date", "signal"])
    df["signal"] = df["signal"].astype(str).str.lower()
    df = df[df["signal"].isin(("buy", "sell"))]
    df = df.drop_duplicates(subset=["date"], keep="last")
    return {row["date"].date(): row["signal"] for _, row in df.iterrows()}


def runBacktest(kline: pd.DataFrame,
                signals: pd.DataFrame,
                initialCash: float = 100000.0,
                commission: float = 0.0003,
                stampTax: float = 0.001,
                slippage: float = 0.0,
                sizing: str = "all") -> dict:
    """运行回测。

    Args:
        kline: 列 date / open / high / low / close / volume
        signals: 列 date / signal（'buy' / 'sell'）
        initialCash: 初始现金
        commission: 双边佣金率
        stampTax: 卖出印花税率
        slippage: 滑点比例（0 = 关闭）
        sizing: 仓位算法，目前仅支持 'all'（全仓）

    Returns:
        dict {equityCurve, trades, metrics, summary}
    """
    if sizing not in _SIZING_OPTS:
        raise ValueError(f"sizing 必须是 {_SIZING_OPTS}")

    feedDf = _validateKline(kline)
    signalMap = _buildSignalMap(signals)

    cerebro = bt.Cerebro(stdstats=False)
    data = bt.feeds.PandasData(
        dataname=feedDf,
        datetime=None,
        open="open", high="high", low="low",
        close="close", volume="volume",
        openinterest="openinterest",
    )
    cerebro.adddata(data)
    cerebro.addstrategy(SignalStrategy, signalMap=signalMap, sizing=sizing)

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
    metricsDict = _metrics.computeMetrics(equityCurve, trades)

    return {
        "equityCurve": equityCurve,
        "trades": trades,
        "metrics": metricsDict,
        "summary": _metrics.formatSummary(metricsDict),
    }
