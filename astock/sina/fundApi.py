"""新浪财经数据源：ETF / LOF 基础函数封装。"""

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

_ETF_LIST_COLS = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "涨跌额": "changeAmount",
    "涨跌幅": "changePct",
    "买入": "bid",
    "卖出": "ask",
    "昨收": "preClose",
    "今开": "open",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
}

# 新浪 ETF/LOF 历史 K 线原生列：date / prevclose / open / high / low / close / volume / amount
_ETF_KLINE_COLS = {
    "day": "date",
    "prevclose": "preClose",
}


def _filterByDate(df: pd.DataFrame, startDate: DateLike, endDate: DateLike,
                  col: str = "date") -> pd.DataFrame:
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


def _listByCategory(category: str) -> pd.DataFrame:
    """category: 'ETF基金' / 'LOF基金'。"""
    df = ak.fund_etf_category_sina(symbol=category)
    df = renameColumns(df, _ETF_LIST_COLS)
    cols = [c for c in ("symbol", "name") if c in df.columns]
    return df[cols].drop_duplicates().reset_index(drop=True) if cols else pd.DataFrame()


# ---------------- ETF ----------------
@safeCall(emptyColumns=["symbol", "name"])
def getEtfList() -> pd.DataFrame:
    """ETF 列表（新浪）。返回 symbol / name。"""
    return _listByCategory("ETF基金")


@safeCall()
def getEtfKline(symbol: str,
                startDate: DateLike = None,
                endDate: DateLike = None) -> pd.DataFrame:
    """ETF 日 K 线（新浪）。symbol: 6 位代码或 'sh510050' 形式。"""
    sym = withMarketPrefix(symbol)
    df = ak.fund_etf_hist_sina(symbol=sym)
    df = renameColumns(df, _ETF_KLINE_COLS)
    return _filterByDate(df, startDate, endDate, col="date")


# ---------------- LOF ----------------
@safeCall(emptyColumns=["symbol", "name"])
def getLofList() -> pd.DataFrame:
    """LOF 列表（新浪）。返回 symbol / name。"""
    return _listByCategory("LOF基金")


@safeCall()
def getLofKline(symbol: str,
                startDate: DateLike = None,
                endDate: DateLike = None) -> pd.DataFrame:
    """LOF 基金日 K 线（新浪）。与 ETF 共用底层接口。"""
    sym = withMarketPrefix(symbol)
    df = ak.fund_etf_hist_sina(symbol=sym)
    df = renameColumns(df, _ETF_KLINE_COLS)
    return _filterByDate(df, startDate, endDate, col="date")
