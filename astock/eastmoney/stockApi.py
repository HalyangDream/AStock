"""东方财富数据源：股票基础函数封装。"""

from __future__ import annotations

from typing import Optional

import akshare as ak
import pandas as pd

from .._common import (
    DateLike,
    renameColumns,
    safeCall,
    splitSymbolAndMarket,
    toCompactDate,
    withMarketPrefix,
)

# ---------------- 列名映射 ----------------
_KLINE_COLS = {
    "日期": "date",
    "股票代码": "symbol",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "changePct",
    "涨跌额": "changeAmount",
    "换手率": "turnoverRate",
    "时间": "datetime",
}

_SPOT_COLS = {
    "序号": "rank",
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "涨跌幅": "changePct",
    "涨跌额": "changeAmount",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "最高": "high",
    "最低": "low",
    "今开": "open",
    "昨收": "preClose",
    "量比": "volumeRatio",
    "换手率": "turnoverRate",
    "市盈率-动态": "peDynamic",
    "市净率": "pb",
    "总市值": "totalMarketCap",
    "流通市值": "floatMarketCap",
    "涨速": "changeSpeed",
    "5分钟涨跌": "change5min",
    "60日涨跌幅": "change60d",
    "年初至今涨跌幅": "changeYtd",
}

_INDUSTRY_LIST_COLS = {
    "排名": "rank",
    "板块名称": "name",
    "板块代码": "symbol",
    "最新价": "price",
    "涨跌额": "changeAmount",
    "涨跌幅": "changePct",
    "总市值": "totalMarketCap",
    "换手率": "turnoverRate",
    "上涨家数": "upCount",
    "下跌家数": "downCount",
    "领涨股票": "leadingStock",
    "领涨股票-涨跌幅": "leadingStockChangePct",
}

_FUND_FLOW_COLS = {
    "日期": "date",
    "收盘价": "close",
    "涨跌幅": "changePct",
    "主力净流入-净额": "mainNetInflow",
    "主力净流入-净占比": "mainNetInflowPct",
    "超大单净流入-净额": "superLargeNetInflow",
    "超大单净流入-净占比": "superLargeNetInflowPct",
    "大单净流入-净额": "largeNetInflow",
    "大单净流入-净占比": "largeNetInflowPct",
    "中单净流入-净额": "mediumNetInflow",
    "中单净流入-净占比": "mediumNetInflowPct",
    "小单净流入-净额": "smallNetInflow",
    "小单净流入-净占比": "smallNetInflowPct",
}

_STOCK_LIST_COLS = {
    "code": "symbol",
    "name": "name",
    "A股代码": "symbol",
    "A股简称": "name",
    "证券代码": "symbol",
    "证券简称": "name",
}

_VALID_ADJUST = {"", "qfq", "hfq"}
_MARKET_FN = {
    "sh": ak.stock_info_sh_name_code,
    "sz": ak.stock_info_sz_name_code,
    "bj": ak.stock_info_bj_name_code,
}


# ---------------- 股票列表 ----------------
@safeCall(emptyColumns=["symbol", "name"])
def getStockListA() -> pd.DataFrame:
    """全部 A 股代码与名称。Returns 列: symbol, name"""
    df = ak.stock_info_a_code_name()
    return renameColumns(df, _STOCK_LIST_COLS, keepOnly=["symbol", "name"])


@safeCall(emptyColumns=["symbol", "name"])
def getStockListByMarket(market: str) -> pd.DataFrame:
    """按市场获取股票列表。

    Args:
        market: 'sh' / 'sz' / 'bj'
    """
    key = market.lower()
    if key not in _MARKET_FN:
        raise ValueError(f"market 必须是 sh/sz/bj，收到 {market!r}")
    df = _MARKET_FN[key]()
    return renameColumns(df, _STOCK_LIST_COLS, keepOnly=["symbol", "name"])


# ---------------- 实时行情 ----------------
@safeCall()
def getRealtimeQuote() -> pd.DataFrame:
    """全 A 股实时快照（东方财富）。"""
    df = ak.stock_zh_a_spot_em()
    return renameColumns(df, _SPOT_COLS)


# ---------------- 历史行情 ----------------
@safeCall()
def getDailyKline(symbol: str,
                  startDate: DateLike = None,
                  endDate: DateLike = None,
                  adjust: str = "qfq") -> pd.DataFrame:
    """日 K 线（东方财富）。

    Args:
        symbol: 6 位代码（如 '600000'）
        adjust: '' 不复权 / 'qfq' 前复权 / 'hfq' 后复权
    """
    if adjust not in _VALID_ADJUST:
        raise ValueError(f"adjust 必须是 {_VALID_ADJUST}")
    code, _ = splitSymbolAndMarket(symbol)
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=toCompactDate(startDate, default="19700101"),
        end_date=toCompactDate(endDate, default="20500101"),
        adjust=adjust,
    )
    return renameColumns(df, _KLINE_COLS)


@safeCall()
def getMinuteKline(symbol: str,
                   period: str = "5",
                   startDate: DateLike = None,
                   endDate: DateLike = None,
                   adjust: str = "") -> pd.DataFrame:
    """分钟 K 线（东方财富）。period: '1' / '5' / '15' / '30' / '60'"""
    if period not in {"1", "5", "15", "30", "60"}:
        raise ValueError("period 必须是 1/5/15/30/60")
    if adjust not in _VALID_ADJUST:
        raise ValueError(f"adjust 必须是 {_VALID_ADJUST}")
    code, _ = splitSymbolAndMarket(symbol)
    kwargs = {"symbol": code, "period": period, "adjust": adjust}
    if startDate is not None:
        kwargs["start_date"] = f"{toCompactDate(startDate)[:4]}-" \
                               f"{toCompactDate(startDate)[4:6]}-" \
                               f"{toCompactDate(startDate)[6:8]} 09:30:00"
    if endDate is not None:
        kwargs["end_date"] = f"{toCompactDate(endDate)[:4]}-" \
                             f"{toCompactDate(endDate)[4:6]}-" \
                             f"{toCompactDate(endDate)[6:8]} 15:00:00"
    df = ak.stock_zh_a_hist_min_em(**kwargs)
    return renameColumns(df, _KLINE_COLS)


# ---------------- 指数 ----------------
@safeCall()
def getIndexKline(symbol: str,
                  startDate: DateLike = None,
                  endDate: DateLike = None) -> pd.DataFrame:
    """指数日线（东财）。symbol: 支持 'sh000001' / '000001'（自动加前缀）"""
    sym = symbol.strip().lower()
    if not sym[:2].isalpha():
        sym = withMarketPrefix(sym)
    df = ak.stock_zh_index_daily_em(
        symbol=sym,
        start_date=toCompactDate(startDate, default="19900101"),
        end_date=toCompactDate(endDate, default="20500101"),
    )
    return df if df is not None else pd.DataFrame()


# ---------------- 板块 ----------------
@safeCall()
def getIndustryList() -> pd.DataFrame:
    """东财行业板块列表。"""
    df = ak.stock_board_industry_name_em()
    return renameColumns(df, _INDUSTRY_LIST_COLS)


@safeCall()
def getIndustryConstituents(name: str) -> pd.DataFrame:
    """行业板块成分股。"""
    df = ak.stock_board_industry_cons_em(symbol=name)
    return renameColumns(df, _SPOT_COLS)


# ---------------- 资金流 ----------------
@safeCall()
def getFundFlowIndividual(symbol: str) -> pd.DataFrame:
    """个股历史资金流。"""
    code, market = splitSymbolAndMarket(symbol)
    df = ak.stock_individual_fund_flow(stock=code, market=market)
    return renameColumns(df, _FUND_FLOW_COLS)


# ---------------- 财务 ----------------
@safeCall()
def getFinancialAbstract(symbol: str) -> pd.DataFrame:
    """财务摘要（按报告期展开）。"""
    code, _ = splitSymbolAndMarket(symbol)
    df = ak.stock_financial_abstract(symbol=code)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.rename(columns={"选项": "category", "指标": "indicator"})


# ---------------- 交易日历 ----------------
_tradeCalendarCache: Optional[pd.DataFrame] = None


@safeCall(emptyColumns=["tradeDate"])
def getTradeCalendar(useCache: bool = True) -> pd.DataFrame:
    """交易日列表（升序）。"""
    global _tradeCalendarCache
    if useCache and _tradeCalendarCache is not None:
        return _tradeCalendarCache.copy()
    df = ak.tool_trade_date_hist_sina()
    df = df.rename(columns={"trade_date": "tradeDate"})
    df["tradeDate"] = pd.to_datetime(df["tradeDate"])
    df = df.sort_values("tradeDate").reset_index(drop=True)
    _tradeCalendarCache = df
    return df.copy()


def isTradingDay(day: DateLike) -> bool:
    """判断指定日期是否交易日。"""
    target = pd.Timestamp(toCompactDate(day))
    cal = getTradeCalendar()
    if cal.empty:
        return False
    return bool((cal["tradeDate"] == target).any())
