"""顶层门面：股票数据统一接口，按源优先级 fallback。

用法：
    from astock import stock
    df = stock.getDailyKline('600000', '2024-01-02', '2024-01-10')        # auto
    df = stock.getDailyKline('600000', source='sina')                       # 指定源

当 source='auto' 时，按 _SOURCE_PRIORITY 定义的顺序依次尝试，
第一个返回非空 DataFrame 的源即停止。
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable, List

import pandas as pd

from ._common import DateLike
from .eastmoney import stockApi as _em
from .sina import stockApi as _sina
from .tencent import stockApi as _tx

logger = logging.getLogger(__name__)

_VALID_SOURCES = {"auto", "eastmoney", "sina", "tencent"}

# 默认源优先级（东财被 DPI 拦的环境下新浪/腾讯优先）
_SOURCE_PRIORITY = {
    "getDailyKline": ["sina", "tencent", "eastmoney"],
    "getMinuteKline": ["sina", "eastmoney"],
    "getRealtimeQuote": ["sina", "eastmoney"],
    "getIndexKline": ["sina", "eastmoney"],
    "getIndexRealtimeQuote": ["sina"],
    "getStockListA": ["eastmoney"],
    "getStockListByMarket": ["eastmoney"],
    "getIndustryList": ["eastmoney"],
    "getIndustryConstituents": ["eastmoney"],
    "getFundFlowIndividual": ["eastmoney"],
    "getFinancialAbstract": ["eastmoney"],
    "getTradeCalendar": ["eastmoney"],
    "isTradingDay": ["eastmoney"],
}

_SOURCE_MOD = {
    "eastmoney": _em,
    "sina": _sina,
    "tencent": _tx,
}


def _resolveSources(funcName: str, source: str) -> List[str]:
    if source not in _VALID_SOURCES:
        raise ValueError(f"source 必须是 {_VALID_SOURCES}，收到 {source!r}")
    if source != "auto":
        return [source]
    return list(_SOURCE_PRIORITY.get(funcName, ["eastmoney"]))


def _callFallback(funcName: str, source: str,
                  *args, **kwargs) -> pd.DataFrame:
    """按源顺序调用下层同名函数，返回首个非空 DataFrame。"""
    for src in _resolveSources(funcName, source):
        mod = _SOURCE_MOD[src]
        fn: Callable = getattr(mod, funcName, None)
        if fn is None:
            logger.debug("source=%s 不支持 %s，跳过", src, funcName)
            continue
        df = fn(*args, **kwargs)
        if isinstance(df, pd.DataFrame) and not df.empty:
            logger.debug("%s 命中源: %s", funcName, src)
            return df
    return pd.DataFrame()


# ================================================================
# 历史行情
# ================================================================
def getDailyKline(symbol: str,
                  startDate: DateLike = None,
                  endDate: DateLike = None,
                  adjust: str = "qfq",
                  source: str = "auto") -> pd.DataFrame:
    """日 K 线。支持 sina / tencent / eastmoney。"""
    return _callFallback("getDailyKline", source,
                         symbol, startDate, endDate, adjust)


def getMinuteKline(symbol: str,
                   period: str = "5",
                   startDate: DateLike = None,
                   endDate: DateLike = None,
                   adjust: str = "",
                   source: str = "auto") -> pd.DataFrame:
    """分钟 K 线。"""
    if source == "auto":
        for src in _resolveSources("getMinuteKline", source):
            mod = _SOURCE_MOD[src]
            if src == "sina":
                df = mod.getMinuteKline(symbol, period=period, adjust=adjust)
            else:
                df = mod.getMinuteKline(symbol, period=period,
                                        startDate=startDate, endDate=endDate,
                                        adjust=adjust)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        return pd.DataFrame()
    mod = _SOURCE_MOD[source]
    if source == "sina":
        return mod.getMinuteKline(symbol, period=period, adjust=adjust)
    return mod.getMinuteKline(symbol, period=period,
                              startDate=startDate, endDate=endDate, adjust=adjust)


# ================================================================
# 实时行情
# ================================================================
def getRealtimeQuote(source: str = "auto") -> pd.DataFrame:
    """全 A 实时快照。"""
    return _callFallback("getRealtimeQuote", source)


def getIndexRealtimeQuote(source: str = "auto") -> pd.DataFrame:
    """指数实时快照。"""
    return _callFallback("getIndexRealtimeQuote", source)


# ================================================================
# 指数
# ================================================================
def getIndexKline(symbol: str,
                  startDate: DateLike = None,
                  endDate: DateLike = None,
                  source: str = "auto") -> pd.DataFrame:
    """指数日线。"""
    return _callFallback("getIndexKline", source, symbol, startDate, endDate)


# ================================================================
# 股票列表 / 板块 / 资金流 / 财务（均只有 eastmoney 覆盖）
# ================================================================
def getStockListA(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getStockListA", source)


def getStockListByMarket(market: str, source: str = "auto") -> pd.DataFrame:
    return _callFallback("getStockListByMarket", source, market)


def getIndustryList(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getIndustryList", source)


def getIndustryConstituents(name: str, source: str = "auto") -> pd.DataFrame:
    return _callFallback("getIndustryConstituents", source, name)


def getFundFlowIndividual(symbol: str, source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFundFlowIndividual", source, symbol)


def getFinancialAbstract(symbol: str, source: str = "auto") -> pd.DataFrame:
    return _callFallback("getFinancialAbstract", source, symbol)


# ================================================================
# 交易日历
# ================================================================
def getTradeCalendar(source: str = "auto") -> pd.DataFrame:
    return _callFallback("getTradeCalendar", source)


def isTradingDay(day: DateLike, source: str = "auto") -> bool:
    """判断是否交易日。源回退策略同上。"""
    for src in _resolveSources("isTradingDay", source):
        mod = _SOURCE_MOD[src]
        fn = getattr(mod, "isTradingDay", None)
        if fn is None:
            continue
        try:
            return bool(fn(day))
        except Exception as exc:  # noqa: BLE001
            logger.warning("isTradingDay 源 %s 失败: %s", src, exc)
    return False
