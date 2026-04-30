"""把 strategy.patterns 输出转成回测引擎使用的信号 DataFrame。

信号 schema:
    date    pd.Timestamp
    signal  'buy' | 'sell'

约定：信号日 T 的 buy / sell 由引擎在 T+1 开盘成交。
"""

from __future__ import annotations

from typing import List

import pandas as pd

_SIGNAL_COLS = ["date", "signal"]


def _alignToKline(date: pd.Timestamp, klineDates: pd.Series) -> pd.Timestamp | None:
    """把任意日期吸附到 kline 中 >= 该日期的第一个交易日。"""
    pos = klineDates.searchsorted(date, side="left")
    if pos >= len(klineDates):
        return None
    return klineDates.iloc[pos]


def _shiftBars(klineDates: pd.Series, anchor: pd.Timestamp,
               bars: int) -> pd.Timestamp | None:
    """从 anchor 向后第 bars 个交易日；越界则取最后一根。"""
    pos = klineDates.searchsorted(anchor, side="left")
    if pos >= len(klineDates):
        return None
    target = min(pos + bars, len(klineDates) - 1)
    return klineDates.iloc[target]


def _buildDf(rows: List[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=_SIGNAL_COLS)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = (df.dropna(subset=["date"])
            .drop_duplicates(subset=["date"], keep="last")
            .sort_values("date")
            .reset_index(drop=True))
    return df[_SIGNAL_COLS]


def fromBottomFractal(bottomDf: pd.DataFrame,
                      kline: pd.DataFrame,
                      holdDays: int = 10) -> pd.DataFrame:
    """底分型 → 信号：centerDate 当日 buy，holdDays 个交易日后 sell。"""
    if bottomDf is None or bottomDf.empty or kline is None or kline.empty:
        return pd.DataFrame(columns=_SIGNAL_COLS)

    klineDates = pd.to_datetime(kline["date"]).reset_index(drop=True)
    rows: List[dict] = []
    for _, row in bottomDf.iterrows():
        d = pd.Timestamp(row["centerDate"]).normalize()
        buyDate = _alignToKline(d, klineDates)
        if buyDate is None:
            continue
        sellDate = _shiftBars(klineDates, buyDate, holdDays)
        rows.append({"date": buyDate, "signal": "buy"})
        if sellDate is not None and sellDate != buyDate:
            rows.append({"date": sellDate, "signal": "sell"})
    return _buildDf(rows)


def fromHeadShoulderBottom(hsbDf: pd.DataFrame,
                           kline: pd.DataFrame,
                           holdDays: int = 20) -> pd.DataFrame:
    """头肩底 → 信号：突破日 buy，holdDays 个交易日后 sell。"""
    if hsbDf is None or hsbDf.empty or kline is None or kline.empty:
        return pd.DataFrame(columns=_SIGNAL_COLS)

    klineDates = pd.to_datetime(kline["date"]).reset_index(drop=True)
    rows: List[dict] = []
    for _, row in hsbDf.iterrows():
        breakoutDate = row.get("breakoutDate")
        if breakoutDate is None or pd.isna(breakoutDate):
            continue
        d = pd.Timestamp(breakoutDate).normalize()
        buyDate = _alignToKline(d, klineDates)
        if buyDate is None:
            continue
        sellDate = _shiftBars(klineDates, buyDate, holdDays)
        rows.append({"date": buyDate, "signal": "buy"})
        if sellDate is not None and sellDate != buyDate:
            rows.append({"date": sellDate, "signal": "sell"})
    return _buildDf(rows)
