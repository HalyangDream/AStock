"""东方财富数据源：基金基础函数封装（公募 / ETF / LOF）。"""

from __future__ import annotations

import re
from typing import Optional

import akshare as ak
import pandas as pd

from .._common import DateLike, padCode, renameColumns, safeCall, toCompactDate

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}")
_ESTIMATE_DYNAMIC = {
    "估算数据-估算值": "estimateValue",
    "估算数据-估算增长率": "estimateChangePct",
    "公布数据-单位净值": "publishedUnitNav",
    "公布数据-日增长率": "publishedDailyChangePct",
    "单位净值": "prevUnitNav",
}

_FUND_LIST_COLS = {
    "基金代码": "symbol",
    "拼音缩写": "pinyinAbbr",
    "基金简称": "name",
    "基金类型": "fundType",
    "拼音全称": "pinyinFull",
}

_FUND_NAV_COLS = {
    "净值日期": "navDate",
    "单位净值": "unitNav",
    "累计净值": "accNav",
    "日增长率": "dailyChangePct",
    "申购状态": "subscribeStatus",
    "赎回状态": "redeemStatus",
    "分红送配": "dividend",
}

_FUND_ESTIMATE_COLS = {
    "序号": "rank",
    "基金代码": "symbol",
    "基金名称": "name",
    "估算偏差": "estimateDeviation",
}

_FUND_RANK_COLS = {
    "序号": "rank",
    "基金代码": "symbol",
    "基金简称": "name",
    "日期": "date",
    "单位净值": "unitNav",
    "累计净值": "accNav",
    "日增长率": "dailyChangePct",
    "近1周": "return1w",
    "近1月": "return1m",
    "近3月": "return3m",
    "近6月": "return6m",
    "近1年": "return1y",
    "近2年": "return2y",
    "近3年": "return3y",
    "今年来": "returnYtd",
    "成立来": "returnSinceInception",
    "自定义": "returnCustom",
    "手续费": "fee",
}

_ETF_SPOT_COLS = {
    "序号": "rank",
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "IOPV实时估值": "iopv",
    "基金折价率": "discountRate",
    "涨跌额": "changeAmount",
    "涨跌幅": "changePct",
    "成交量": "volume",
    "成交额": "amount",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "昨收": "preClose",
    "振幅": "amplitude",
    "换手率": "turnoverRate",
    "量比": "volumeRatio",
    "委比": "orderRatio",
    "外盘": "outerVolume",
    "内盘": "innerVolume",
    "主力净流入-净额": "mainNetInflow",
    "主力净流入-净占比": "mainNetInflowPct",
    "现手": "currentVolume",
    "买一": "bid1",
    "卖一": "ask1",
    "最新份额": "latestShare",
    "流通市值": "floatMarketCap",
    "总市值": "totalMarketCap",
    "数据日期": "dataDate",
    "更新时间": "updateTime",
}

_ETF_HIST_COLS = {
    "日期": "date",
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
}

_FUND_HOLD_COLS = {
    "序号": "rank",
    "股票代码": "stockSymbol",
    "股票名称": "stockName",
    "占净值比例": "navRatio",
    "持股数": "shareCount",
    "持仓市值": "holdMarketCap",
    "季度": "quarter",
}

_FUND_MANAGER_COLS = {
    "序号": "rank",
    "姓名": "name",
    "所属公司": "company",
    "现任基金代码": "currentFundSymbol",
    "现任基金": "currentFund",
    "累计从业时间": "totalExperienceDays",
    "现任基金资产总规模": "currentFundAum",
    "现任基金最佳回报": "bestReturn",
}

_VALID_ADJUST = {"", "qfq", "hfq"}


@safeCall()
def getFundList() -> pd.DataFrame:
    """全部公募基金列表。"""
    df = ak.fund_name_em()
    return renameColumns(df, _FUND_LIST_COLS)


@safeCall()
def getFundListByType(fundType: str) -> pd.DataFrame:
    """按基金类型过滤。"""
    df = getFundList()
    if df.empty or "fundType" not in df.columns:
        return df
    return df[df["fundType"].str.contains(fundType, na=False)].reset_index(drop=True)


@safeCall(emptyColumns=["navDate", "unitNav", "accNav", "dailyChangePct"])
def getFundNav(symbol: str) -> pd.DataFrame:
    """开放式基金历史净值（单位净值 + 累计净值）。"""
    code = padCode(symbol)
    accDf = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
    unitDf = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")

    accDf = renameColumns(accDf, _FUND_NAV_COLS)
    unitDf = renameColumns(unitDf, _FUND_NAV_COLS)

    if unitDf.empty and accDf.empty:
        return pd.DataFrame(columns=["navDate", "unitNav", "accNav", "dailyChangePct"])
    if not unitDf.empty and not accDf.empty:
        merged = pd.merge(unitDf, accDf, on="navDate", how="outer")
    else:
        merged = unitDf if not unitDf.empty else accDf

    merged["navDate"] = pd.to_datetime(merged["navDate"])
    return merged.sort_values("navDate").reset_index(drop=True)


@safeCall()
def getFundRealtimeEstimate() -> pd.DataFrame:
    """全市场基金实时估值快照。动态日期列已归一化为英文列名。"""
    df = ak.fund_value_estimation_em(symbol="全部")
    if df is None or df.shape[1] == 0:
        return pd.DataFrame()
    newCols = []
    for col in df.columns:
        if col in _FUND_ESTIMATE_COLS:
            newCols.append(_FUND_ESTIMATE_COLS[col])
            continue
        if _DATE_PATTERN.match(col):
            suffix = col[11:]
            newCols.append(_ESTIMATE_DYNAMIC.get(suffix, col))
        else:
            newCols.append(col)
    df = df.copy()
    df.columns = newCols
    return df


@safeCall()
def getFundRank(fundType: str = "全部",
                startDate: DateLike = None,
                endDate: DateLike = None) -> pd.DataFrame:
    """开放式基金阶段排行。"""
    _ = startDate, endDate
    df = ak.fund_open_fund_rank_em(symbol=fundType)
    return renameColumns(df, _FUND_RANK_COLS)


@safeCall(emptyColumns=["symbol", "name"])
def getEtfList() -> pd.DataFrame:
    """全部 ETF 代码与简称。"""
    df = ak.fund_etf_spot_em()
    df = renameColumns(df, _ETF_SPOT_COLS)
    cols = [c for c in ("symbol", "name") if c in df.columns]
    return df[cols].drop_duplicates().reset_index(drop=True) if cols else pd.DataFrame()


@safeCall()
def getEtfRealtimeQuote() -> pd.DataFrame:
    """ETF 实时行情快照。"""
    df = ak.fund_etf_spot_em()
    return renameColumns(df, _ETF_SPOT_COLS)


@safeCall()
def getEtfKline(symbol: str,
                startDate: DateLike = None,
                endDate: DateLike = None,
                adjust: str = "qfq") -> pd.DataFrame:
    """ETF 日 K 线。"""
    if adjust not in _VALID_ADJUST:
        raise ValueError(f"adjust 必须是 {_VALID_ADJUST}")
    df = ak.fund_etf_hist_em(
        symbol=padCode(symbol),
        period="daily",
        start_date=toCompactDate(startDate, default="19700101"),
        end_date=toCompactDate(endDate, default="20500101"),
        adjust=adjust,
    )
    return renameColumns(df, _ETF_HIST_COLS)


@safeCall(emptyColumns=["symbol", "name"])
def getLofList() -> pd.DataFrame:
    """全部 LOF 基金代码与简称。"""
    df = ak.fund_lof_spot_em()
    df = renameColumns(df, _ETF_SPOT_COLS)
    cols = [c for c in ("symbol", "name") if c in df.columns]
    return df[cols].drop_duplicates().reset_index(drop=True) if cols else pd.DataFrame()


@safeCall()
def getLofKline(symbol: str,
                startDate: DateLike = None,
                endDate: DateLike = None,
                adjust: str = "qfq") -> pd.DataFrame:
    """LOF 基金日 K 线。"""
    if adjust not in _VALID_ADJUST:
        raise ValueError(f"adjust 必须是 {_VALID_ADJUST}")
    df = ak.fund_lof_hist_em(
        symbol=padCode(symbol),
        period="daily",
        start_date=toCompactDate(startDate, default="19700101"),
        end_date=toCompactDate(endDate, default="20500101"),
        adjust=adjust,
    )
    return renameColumns(df, _ETF_HIST_COLS)


@safeCall()
def getFundHoldings(symbol: str, year: Optional[int] = None) -> pd.DataFrame:
    """基金十大重仓持股明细。"""
    kwargs = {"symbol": padCode(symbol)}
    if year is not None:
        kwargs["date"] = str(year)
    df = ak.fund_portfolio_hold_em(**kwargs)
    return renameColumns(df, _FUND_HOLD_COLS)


@safeCall()
def getFundManagers() -> pd.DataFrame:
    """全市场基金经理榜。"""
    df = ak.fund_manager_em()
    return renameColumns(df, _FUND_MANAGER_COLS)
