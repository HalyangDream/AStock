"""顶层门面：基金数据统一接口，按源优先级 fallback。

用法：
    from astock import fund
    df = fund.getEtfList()                       # auto
    df = fund.getEtfKline('510050', source='sina')
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

import pandas as pd

from ._common import DateLike
from .eastmoney import fundApi as _em
from .sina import fundApi as _sina

logger = logging.getLogger(__name__)

_VALID_SOURCES = {"auto", "eastmoney", "sina"}

_SOURCE_PRIORITY = {
    "getEtfList": ["sina", "eastmoney"],
    "getLofList": ["sina", "eastmoney"],
    "getEtfKline": ["sina", "eastmoney"],
    "getLofKline": ["sina", "eastmoney"],
    "getEtfRealtimeQuote": ["eastmoney"],
    "getFundList": ["eastmoney"],
    "getFundListByType": ["eastmoney"],
    "getFundNav": ["eastmoney"],
    "getFundRealtimeEstimate": ["eastmoney"],
    "getFundRank": ["eastmoney"],
    "getFundHoldings": ["eastmoney"],
    "getFundManagers": ["eastmoney"],
}

_SOURCE_MOD = {
    "eastmoney": _em,
    "sina": _sina,
}


def _resolveSources(funcName: str, source: str) -> List[str]:
    if source not in _VALID_SOURCES:
        raise ValueError(f"source 必须是 {_VALID_SOURCES}，收到 {source!r}")
    if source != "auto":
        return [source]
    return list(_SOURCE_PRIORITY.get(funcName, ["eastmoney"]))


def _callFallback(funcName: str, source: str, *args, **kwargs) -> pd.DataFrame:
    for src in _resolveSources(funcName, source):
        mod = _SOURCE_MOD[src]
        fn: Callable = getattr(mod, funcName, None)
        if fn is None:
            logger.debug("source=%s 不支持 %s", src, funcName)
            continue
        df = fn(*args, **kwargs)
        if isinstance(df, pd.DataFrame) and not df.empty:
            logger.debug("%s 命中源: %s", funcName, src)
            return df
    return pd.DataFrame()


# ================================================================
# 公募基金（仅 eastmoney 覆盖）
# ================================================================
def getFundList(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFundList", source)


def getFundListByType(fundType: str, source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFundListByType", source, fundType)


def getFundNav(symbol: str, source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFundNav", source, symbol)


def getFundRealtimeEstimate(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFundRealtimeEstimate", source)


def getFundRank(fundType: str = "全部",
                startDate: DateLike = None,
                endDate: DateLike = None,
                source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFundRank", source, fundType, startDate, endDate)


def getFundHoldings(symbol: str, year: Optional[int] = None,
                    source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFundHoldings", source, symbol, year)


def getFundManagers(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFundManagers", source)


# ================================================================
# ETF
# ================================================================
def getEtfList(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getEtfList", source)


def getEtfRealtimeQuote(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getEtfRealtimeQuote", source)


def getEtfKline(symbol: str,
                startDate: DateLike = None,
                endDate: DateLike = None,
                adjust: str = "qfq",
                source: str = "auto") -> pd.DataFrame:
    """ETF 日 K。注：sina 源不支持 adjust，会忽略该参数。"""
    for src in _resolveSources("getEtfKline", source):
        mod = _SOURCE_MOD[src]
        if src == "sina":
            df = mod.getEtfKline(symbol, startDate=startDate, endDate=endDate)
        else:
            df = mod.getEtfKline(symbol, startDate=startDate,
                                 endDate=endDate, adjust=adjust)
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    return pd.DataFrame()


# ================================================================
# LOF
# ================================================================
def getLofList(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getLofList", source)


def getLofKline(symbol: str,
                startDate: DateLike = None,
                endDate: DateLike = None,
                adjust: str = "qfq",
                source: str = "auto") -> pd.DataFrame:
    """LOF 日 K。注：sina 源不支持 adjust。"""
    for src in _resolveSources("getLofKline", source):
        mod = _SOURCE_MOD[src]
        if src == "sina":
            df = mod.getLofKline(symbol, startDate=startDate, endDate=endDate)
        else:
            df = mod.getLofKline(symbol, startDate=startDate,
                                 endDate=endDate, adjust=adjust)
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    return pd.DataFrame()
