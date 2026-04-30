"""腾讯财经数据源：股票基础函数封装。

覆盖：日 K 线（腾讯财经仅提供此项独立接口）。
"""

from __future__ import annotations

import akshare as ak
import pandas as pd

from .._common import (
    DateLike,
    renameColumns,
    safeCall,
    toCompactDate,
    withMarketPrefix,
)

# stock_zh_a_hist_tx 原生列：date / open / close / high / low / amount
_DAILY_COLS = {
    "amount": "volume",
}

_VALID_ADJUST = {"", "qfq", "hfq"}


@safeCall()
def getDailyKline(symbol: str,
                  startDate: DateLike = None,
                  endDate: DateLike = None,
                  adjust: str = "qfq") -> pd.DataFrame:
    """日 K 线（腾讯财经）。symbol: '000001' 或 'sz000001'。

    Returns 列: date / open / close / high / low / volume
    注：腾讯接口 `amount` 字段在 AKShare 中代表成交量（单位：万手），
    归一化列名为 `volume`；不提供成交额字段。
    """
    if adjust not in _VALID_ADJUST:
        raise ValueError(f"adjust 必须是 {_VALID_ADJUST}")
    sym = withMarketPrefix(symbol)
    df = ak.stock_zh_a_hist_tx(
        symbol=sym,
        start_date=toCompactDate(startDate, default="19000101"),
        end_date=toCompactDate(endDate, default="20500101"),
        adjust=adjust,
    )
    return renameColumns(df, _DAILY_COLS)
