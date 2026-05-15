"""webapp 服务层：封装对底层 astock 函数的调用 + 简单整形。

UI 层（streamlit pages）只关心 DataFrame 与异常文案，所有数据查询走这里。
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from typing import Callable, Optional

from astock import fund as _fund
from astock import stock as _stock
from astock._common import padCode
from strategy import scan as _scan

logger = logging.getLogger(__name__)

_KIND_OPTS = ("股票", "ETF", "LOF")

# K 线列中文映射；未知列原样保留
_KLINE_COL_LABELS = {
    "date": "日期",
    "name": "名称",
    "open": "开盘",
    "high": "最高",
    "low": "最低",
    "close": "收盘",
    "volume": "成交量(千万)",
    "amount": "成交额(千万)",
    "preClose": "昨收",
    "change": "涨跌额",
    "changePct": "涨跌幅",
    "turnover": "换手率(%)",
    "outstandingShare": "流通股本",
}

_TEN_MILLION = 1e7

# 名称表懒加载缓存：kind -> DataFrame
_nameCache: dict = {}


def _toDate(d) -> Optional[str]:
    if d is None or d == "":
        return None
    if isinstance(d, str):
        return d
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def fetchKline(kind: str, symbol: str,
               startDate=None, endDate=None) -> pd.DataFrame:
    """按类型分发到不同底层接口。

    Args:
        kind: '股票' / 'ETF' / 'LOF'
        symbol: 6 位代码
        startDate / endDate: 日期或 'YYYY-MM-DD' 字符串
    """
    if kind not in _KIND_OPTS:
        raise ValueError(f"kind 必须是 {_KIND_OPTS}")
    if not symbol or not str(symbol).strip():
        raise ValueError("代码不能为空")

    sd, ed = _toDate(startDate), _toDate(endDate)
    if kind == "股票":
        df = _stock.getDailyKline(symbol, startDate=sd, endDate=ed)
    elif kind == "ETF":
        df = _fund.getEtfKline(symbol, startDate=sd, endDate=ed)
    else:  # LOF
        df = _fund.getLofKline(symbol, startDate=sd, endDate=ed)

    if df is None:
        return pd.DataFrame()
    return df


def fetchIndustryList() -> pd.DataFrame:
    """行业板块列表。"""
    return _stock.getIndustryList()


def fetchIndustryConstituents(industryName: str) -> pd.DataFrame:
    """指定行业的成分股。"""
    if not industryName or not str(industryName).strip():
        raise ValueError("行业名不能为空")
    return _stock.getIndustryConstituents(industryName)


def fetchFundFlow(symbol: str) -> pd.DataFrame:
    """个股资金流。"""
    if not symbol or not str(symbol).strip():
        raise ValueError("股票代码不能为空")
    return _stock.getFundFlowIndividual(symbol)


def fetchFinancialAbstract(symbol: str) -> pd.DataFrame:
    """财务摘要。"""
    if not symbol or not str(symbol).strip():
        raise ValueError("股票代码不能为空")
    return _stock.getFinancialAbstract(symbol)


def labelKline(df: pd.DataFrame) -> pd.DataFrame:
    """K 线列名转中文 + 单位换算。

    - volume / amount：除 10^7（千万），保留 2 位小数
    - turnover：× 100（小数 → 百分比数值），保留 2 位小数
    - 未知列原样保留
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    if "volume" in out.columns:
        out["volume"] = (pd.to_numeric(out["volume"], errors="coerce")
                         / _TEN_MILLION).round(2)
    if "amount" in out.columns:
        out["amount"] = (pd.to_numeric(out["amount"], errors="coerce")
                         / _TEN_MILLION).round(2)
    if "turnover" in out.columns:
        out["turnover"] = (pd.to_numeric(out["turnover"], errors="coerce")
                           * 100).round(2)
    rename = {c: _KLINE_COL_LABELS[c]
              for c in out.columns if c in _KLINE_COL_LABELS}
    return out.rename(columns=rename) if rename else out


def _loadNameTable(kind: str) -> pd.DataFrame:
    """懒加载并缓存 kind 对应的名称表。"""
    if kind in _nameCache:
        return _nameCache[kind]
    if kind == "股票":
        df = _stock.getRealtimeQuote()
    elif kind == "ETF":
        df = _fund.getEtfList()
    elif kind == "LOF":
        df = _fund.getLofList()
    else:
        df = pd.DataFrame()
    _nameCache[kind] = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    return _nameCache[kind]


def lookupName(kind: str, symbol: str) -> str:
    """按 6 位代码查名称；找不到返回空串。"""
    if not symbol or not str(symbol).strip():
        return ""
    if kind not in _KIND_OPTS:
        return ""
    code = padCode(symbol)
    table = _loadNameTable(kind)
    if table is None or table.empty:
        return ""
    if "symbol" not in table.columns or "name" not in table.columns:
        return ""
    hit = table.loc[
        table["symbol"].astype(str).str.zfill(6) == code, "name"
    ]
    return str(hit.iloc[0]) if not hit.empty else ""


def clearNameCache() -> None:
    """清空名称缓存（测试 / 强制刷新用）。"""
    _nameCache.clear()


def runFullScan(
    days: int = 250,
    workers: int = 8,
    markets: Optional[list] = None,
    progressCb: Optional[Callable[[int, int], None]] = None,
) -> pd.DataFrame:
    """全市场扫描，返回原始汇总结果（未按形态过滤）。"""
    if markets is None:
        markets = ["sh", "sz"]
    return _scan.scanAll(
        markets=markets,
        lookbackDays=days,
        workers=workers,
        hitOnly=True,
        progress=False,
        progressCb=progressCb,
    )


_CBF_COL_MAP = {
    "symbol":               "代码",
    "name":                 "名称",
    "currentBottomPattern": "形态",
    "currentBottomDate":    "信号日期",
    "currentBottomLow":     "支撑位",
    "currentPrice":         "现价",
}
_CBF_DISPLAY_COLS = list(_CBF_COL_MAP.keys())


def filterCurrentBottomFractal(scanResult: pd.DataFrame) -> pd.DataFrame:
    """从 scanAll 结果中过滤出底分型命中行，整形为展示 DataFrame。"""
    if scanResult is None or scanResult.empty:
        return pd.DataFrame()
    df = scanResult[scanResult["isCurrentBottom"] == True].copy()
    if df.empty:
        return pd.DataFrame()
    df = df.reindex(columns=_CBF_DISPLAY_COLS)
    df = df.rename(columns=_CBF_COL_MAP)
    for col in ("支撑位", "现价"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
    return df.reset_index(drop=True)


_HSB_COL_MAP = {
    "symbol":                      "代码",
    "name":                        "名称",
    "bestHsbLeftShoulderDate":     "形态起始日",
    "bestHsbBreakoutDate":         "突破日",
    "bestHsbNeckline":             "颈线价",
    "bestHsbBreakoutPrice":        "买点价",
    "bestHsbNecklinePriceAtBreakout": "动态颈线价",
    "bestHsbTargetClassic":        "目标价(经典)",
    "bestHsbScore":                "评分",
    "bestHsbStatus":               "状态",
    "currentPrice":                "现价",
}

_HSB_DISPLAY_COLS = list(_HSB_COL_MAP.keys())


def scanHeadShoulderBottom(
    days: int = 250,
    workers: int = 8,
    onlyBreakout: bool = True,
    markets: Optional[list] = None,
    progressCb: Optional[Callable[[int, int], None]] = None,
    scanResult: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """扫描全 A 股头肩底形态，返回整理好列名的展示 DataFrame。

    Args:
        days: 回溯交易日数，默认 250（约 1 年）
        workers: 并发线程数
        onlyBreakout: True 时只返回 breakout/confirmed 状态的股票
        markets: 市场过滤列表，默认 ['sh','sz']（跳过北交所，数据覆盖差）
        progressCb: 进度回调 (doneCount, total)；None 则不回调
        scanResult: 预计算的 scanAll 结果；传入时跳过 scanAll 调用
    """
    if markets is None:
        markets = ["sh", "sz"]
    if scanResult is not None:
        df = scanResult
    else:
        df = _scan.scanAll(
            markets=markets,
            lookbackDays=days,
            workers=workers,
            hitOnly=True,
            progress=False,
            progressCb=progressCb,
        )
    if df is None or df.empty:
        return pd.DataFrame()

    hsb = df[df["bestHsbStatus"].notna()].copy()
    if onlyBreakout:
        hsb = hsb[hsb["bestHsbStatus"].isin(["breakout", "confirmed"])]
    if hsb.empty:
        return pd.DataFrame()

    # 只保留展示列（部分列可能因旧扫描结果缺失，用 reindex 兜底）
    hsb = hsb.reindex(columns=_HSB_DISPLAY_COLS)
    hsb = hsb.rename(columns=_HSB_COL_MAP)

    # 数值列保留 2 位小数
    for col in ("颈线价", "买点价", "动态颈线价", "目标价(经典)", "现价"):
        if col in hsb.columns:
            hsb[col] = pd.to_numeric(hsb[col], errors="coerce").round(2)
    if "评分" in hsb.columns:
        hsb["评分"] = pd.to_numeric(hsb["评分"], errors="coerce").round(4)

    return hsb.reset_index(drop=True)


def fetchHsbChartData(symbol: str, days: int = 250) -> dict:
    """获取单只股票 K 线 + 头肩底详细匹配数据，用于绘图。

    Returns dict:
        kline: 原始日 K 线 DataFrame（date/open/high/low/close/volume）
        matches: 头肩底匹配 DataFrame（含 L1/L2/L3/H1/H2 坐标、颈线、评分等）
        name: 股票名称
    """
    code = padCode(symbol)
    kline = _stock.getDailyKline(code)
    if kline is None or kline.empty:
        return {"kline": pd.DataFrame(), "matches": pd.DataFrame(), "name": ""}
    if days and days > 0:
        kline = kline.tail(days).reset_index(drop=True)

    result = _scan.scanSingle(code, lookbackDays=days, kline=kline)
    return {
        "kline": kline,
        "matches": result.get("headShoulderBottoms", pd.DataFrame()),
        "name": result.get("name", ""),
    }


def runGridOptimize(kline: pd.DataFrame,
                    totalAmount: float,
                    progressCb=None) -> dict:
    """对 K 线运行网格策略二维寻优（步长 × 层数）。

    中心价由引擎自动取首日 close（避免未来函数偏差），用户只需提供总金额。
    步长 / 层数候选集由 backtest 层默认值决定。

    Args:
        kline: 含 date / open / high / low / close / volume
        totalAmount: 总金额（用户输入，用于初始现金）
        progressCb: 进度回调 (idx, total, summaryDict)

    Returns:
        backtest.gridOptimize 的输出 (candidates / top / best)
    """
    from backtest import gridOptimize

    if totalAmount <= 0:
        raise ValueError("总金额必须 > 0")
    if kline is None or kline.empty:
        raise ValueError("K 线为空，无法寻优")
    return gridOptimize(kline,
                        totalAmount=float(totalAmount),
                        progressCb=progressCb)
