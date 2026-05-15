"""形态识别内部工具：输入校验 / 包含处理 / 摆动高低点。"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

REQUIRED_COLS = ("date", "open", "high", "low", "close", "volume")


def normalizeKline(df: pd.DataFrame) -> pd.DataFrame:
    """校验必需列、按 date 升序、重置索引。"""
    if df is None or df.empty:
        return pd.DataFrame(columns=list(REQUIRED_COLS))
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"K 线缺少必需列: {missing}")
    out = df[list(REQUIRED_COLS)].copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)
    return out


def mergeContaining(df: pd.DataFrame) -> pd.DataFrame:
    """缠论 K 线包含处理。

    相邻两根 K 若存在包含关系则合并，方向按合并时刻前的整体走势决定：
      - 向上时：高取两者最高、低取两者最高
      - 向下时：高取两者最低、低取两者最低
    合并保留最新 K 的收盘、最早 K 的开盘、累加成交量。

    Returns 包含列: date, open, high, low, close, volume, mergedCount
    """
    df = normalizeKline(df)
    if len(df) < 2:
        out = df.copy()
        out["mergedCount"] = 1
        return out

    merged: List[dict] = []
    direction = 0  # 1=up, -1=down, 0=未知

    for bar in df.to_dict("records"):
        bar = dict(bar)
        bar.setdefault("mergedCount", 1)

        if not merged:
            merged.append(bar)
            continue

        prev = merged[-1]

        # 根据最近两根已处理的 K 判定当前方向
        if len(merged) >= 2:
            ref = merged[-2]
            if prev["high"] > ref["high"] and prev["low"] > ref["low"]:
                direction = 1
            elif prev["high"] < ref["high"] and prev["low"] < ref["low"]:
                direction = -1

        prevContainsCur = prev["high"] >= bar["high"] and prev["low"] <= bar["low"]
        curContainsPrev = bar["high"] >= prev["high"] and bar["low"] <= prev["low"]

        if not (prevContainsCur or curContainsPrev):
            merged.append(bar)
            continue

        # 合并：方向未知时默认按向下（保守）
        if direction >= 1:
            newHigh = max(prev["high"], bar["high"])
            newLow = max(prev["low"], bar["low"])
        else:
            newHigh = min(prev["high"], bar["high"])
            newLow = min(prev["low"], bar["low"])

        merged[-1] = {
            "date": bar["date"],
            "open": prev["open"],
            "high": newHigh,
            "low": newLow,
            "close": bar["close"],
            "volume": prev["volume"] + bar["volume"],
            "mergedCount": prev["mergedCount"] + 1,
        }

    return pd.DataFrame(merged).reset_index(drop=True)


def findSwingLows(df: pd.DataFrame, window: int = 5) -> List[int]:
    """返回摆动低点索引：前后 window 根内严格最低的位置。"""
    n = len(df)
    if n < 2 * window + 1:
        return []
    lows = df["low"].to_numpy()
    out: List[int] = []
    for i in range(window, n - window):
        leftMin = lows[i - window:i].min()
        rightMin = lows[i + 1:i + 1 + window].min()
        if lows[i] < leftMin and lows[i] < rightMin:
            out.append(i)
    return out


def findSwingHighs(df: pd.DataFrame, window: int = 5) -> List[int]:
    """返回摆动高点索引。"""
    n = len(df)
    if n < 2 * window + 1:
        return []
    highs = df["high"].to_numpy()
    out: List[int] = []
    for i in range(window, n - window):
        leftMax = highs[i - window:i].max()
        rightMax = highs[i + 1:i + 1 + window].max()
        if highs[i] > leftMax and highs[i] > rightMax:
            out.append(i)
    return out


def highestBetween(df: pd.DataFrame, lo: int, hi: int) -> int:
    """返回 df[lo:hi+1] 内 high 最大的索引（闭区间）。"""
    segment = df["high"].iloc[lo:hi + 1]
    return int(segment.idxmax())


def lowestBetween(df: pd.DataFrame, lo: int, hi: int) -> int:
    """返回 df[lo:hi+1] 内 low 最小的索引。"""
    segment = df["low"].iloc[lo:hi + 1]
    return int(segment.idxmin())


def rollingMean(series: pd.Series, window: int) -> pd.Series:
    """滚动均值，首 window-1 行用扩展均值兜底（避免形态末端信息缺失）。"""
    return series.rolling(window=window, min_periods=1).mean()


def calcTrendSlope(series: pd.Series, window: int) -> float:
    """返回 series 末尾 window 个点的线性回归斜率，已按首值归一化（price/price/day）。

    归一化后的斜率可跨价格量级比较：-0.001 ≈ 每日跌 0.1%。
    数据不足 2 点或 window < 2 时返回 0.0。
    """
    if window < 2 or len(series) < 2:
        return 0.0
    tail = series.iloc[-window:]
    if len(tail) < 2:
        return 0.0
    x = np.arange(len(tail), dtype=float)
    coeffs = np.polyfit(x, tail.values.astype(float), 1)
    base = float(tail.iloc[0])
    if base == 0.0:
        return 0.0
    return float(coeffs[0]) / base
