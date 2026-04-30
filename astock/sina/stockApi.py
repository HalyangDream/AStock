"""新浪财经数据源：股票基础函数封装。

覆盖：日 K 线、分钟 K 线、全 A 实时快照、指数日线、指数实时快照。
"""

from __future__ import annotations

import akshare as ak
import pandas as pd

from .._common import (
    DateLike,
    padCode,
    renameColumns,
    safeCall,
    toCompactDate,
    withMarketPrefix,
)

# ---------------- 列名映射 ----------------
# sina 日线列名原生已为英文（date/open/high/low/close/volume/...）
_DAILY_COLS = {
    "day": "date",
    "outstanding_share": "outstandingShare",
    "turnover": "turnover",
}

_MINUTE_COLS = {
    "day": "datetime",
}

_A_SPOT_COLS = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "买入": "bid",
    "卖出": "ask",
    "昨收": "preClose",
    "今开": "open",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "时间戳": "timestamp",
    "涨跌额": "changeAmount",
    "涨跌幅": "changePct",
}

_INDEX_SPOT_COLS = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "涨跌额": "changeAmount",
    "涨跌幅": "changePct",
    "昨收": "preClose",
    "今开": "open",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
}

_VALID_ADJUST = {"", "qfq", "hfq"}


def _filterByDate(df: pd.DataFrame, startDate: DateLike, endDate: DateLike,
                  col: str = "date") -> pd.DataFrame:
    """本地按日期过滤（sina 接口不支持服务器端范围参数）。"""
    if df.empty or col not in df.columns:
        return df
    if startDate is None and endDate is None:
        return df
    dt = pd.to_datetime(df[col])
    mask = pd.Series(True, index=df.index)
    if startDate is not None:
        mask &= dt >= pd.Timestamp(toCompactDate(startDate))
    if endDate is not None:
        mask &= dt <= pd.Timestamp(toCompactDate(endDate))
    return df.loc[mask].reset_index(drop=True)


# ---------------- 日 K 线 ----------------
@safeCall()
def getDailyKline(symbol: str,
                  startDate: DateLike = None,
                  endDate: DateLike = None,
                  adjust: str = "qfq") -> pd.DataFrame:
    """日 K 线（新浪）。symbol: 支持 '600000' / 'sh600000'。"""
    if adjust not in _VALID_ADJUST:
        raise ValueError(f"adjust 必须是 {_VALID_ADJUST}")
    sym = withMarketPrefix(symbol)
    df = ak.stock_zh_a_daily(symbol=sym, adjust=adjust)
    df = renameColumns(df, _DAILY_COLS)
    return _filterByDate(df, startDate, endDate, col="date")


# ---------------- 分钟 K 线 ----------------
@safeCall()
def getMinuteKline(symbol: str,
                   period: str = "5",
                   adjust: str = "") -> pd.DataFrame:
    """分钟 K 线（新浪）。period: '1' / '5' / '15' / '30' / '60'"""
    if period not in {"1", "5", "15", "30", "60"}:
        raise ValueError("period 必须是 1/5/15/30/60")
    if adjust not in _VALID_ADJUST:
        raise ValueError(f"adjust 必须是 {_VALID_ADJUST}")
    sym = withMarketPrefix(symbol)
    df = ak.stock_zh_a_minute(symbol=sym, period=period, adjust=adjust)
    return renameColumns(df, _MINUTE_COLS)


# ---------------- 实时快照 ----------------
@safeCall()
def getRealtimeQuote() -> pd.DataFrame:
    """全 A 股实时快照（新浪）。"""
    df = ak.stock_zh_a_spot()
    return renameColumns(df, _A_SPOT_COLS)


# ---------------- 指数 ----------------
@safeCall()
def getIndexKline(symbol: str,
                  startDate: DateLike = None,
                  endDate: DateLike = None) -> pd.DataFrame:
    """指数日线（新浪）。symbol: 支持 'sh000001' / '000001'。"""
    sym = symbol.strip().lower()
    if not sym[:2].isalpha():
        sym = withMarketPrefix(sym)
    df = ak.stock_zh_index_daily(symbol=sym)
    df = renameColumns(df, _DAILY_COLS)
    return _filterByDate(df, startDate, endDate, col="date")


@safeCall()
def getIndexRealtimeQuote() -> pd.DataFrame:
    """指数实时快照（新浪）。"""
    df = ak.stock_zh_index_spot_sina()
    return renameColumns(df, _INDEX_SPOT_COLS)
