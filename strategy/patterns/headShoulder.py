"""头肩底 / 头肩顶形态识别。

头肩底：左肩 L1 → 颈线 H1 → 头 L2（最低）→ 颈线 H2 → 右肩 L3
确认条件：
  - 几何约束：L2 < L1, L2 < L3；|L1-L3|/|L2| ≤ shoulderTolerance；时间对称度 ≤ timeSymmetry
  - 跨度约束：minSpan ≤ t(L3) - t(L1) ≤ maxSpan
  - 颈线突破：收盘价站上 max(H1, H2) + 突破日量 > 形态区间均量 × volumeMultiplier
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from ._utils import (
    findSwingHighs,
    findSwingLows,
    highestBetween,
    lowestBetween,
    normalizeKline,
)

_STATUS_FORMING = "forming"
_STATUS_BREAKOUT = "breakout"
_STATUS_CONFIRMED = "confirmed"


def _score(shoulderGap: float,
           timeGap: float,
           headDepth: float,
           hasBreakout: bool) -> float:
    """综合评分 0~1。shoulderGap/timeGap 越小越好；headDepth 越大越好；突破+0.2。"""
    s1 = max(0.0, 1.0 - shoulderGap / 0.05) * 0.35
    s2 = max(0.0, 1.0 - timeGap / 0.4) * 0.25
    s3 = min(1.0, headDepth / 0.15) * 0.20
    s4 = 0.20 if hasBreakout else 0.0
    return round(s1 + s2 + s3 + s4, 4)


def _findBreakout(df: pd.DataFrame,
                  startIdx: int,
                  necklinePrice: float,
                  volumeMultiplier: float,
                  formWindowAvgVol: float,
                  maxLook: int,
                  isBottom: bool) -> Optional[dict]:
    """从 startIdx 之后开始寻找突破点。找到则返回 dict，否则 None。"""
    end = min(len(df), startIdx + 1 + maxLook)
    for i in range(startIdx + 1, end):
        close = float(df["close"].iloc[i])
        volume = float(df["volume"].iloc[i])
        priceBreak = close > necklinePrice if isBottom else close < necklinePrice
        volBreak = volume >= formWindowAvgVol * volumeMultiplier
        if priceBreak and volBreak:
            # 确认：后续 3 根内收盘未反向跌破颈线
            confirmEnd = min(len(df), i + 4)
            confirmed = True
            for j in range(i + 1, confirmEnd):
                c = float(df["close"].iloc[j])
                if isBottom and c < necklinePrice:
                    confirmed = False
                    break
                if not isBottom and c > necklinePrice:
                    confirmed = False
                    break
            return {
                "breakoutIdx": i,
                "breakoutDate": df["date"].iloc[i],
                "breakoutPrice": close,
                "breakoutVolume": volume,
                "status": _STATUS_CONFIRMED if confirmed else _STATUS_BREAKOUT,
            }
    return None


def _buildMatch(df: pd.DataFrame,
                l1: int, l2: int, l3: int,
                h1: int, h2: int,
                isBottom: bool,
                volumeMultiplier: float,
                conservativeTargetPct: float) -> Optional[dict]:
    """构造匹配记录；失败返回 None。"""
    l1Price = float(df["low" if isBottom else "high"].iloc[l1])
    l2Price = float(df["low" if isBottom else "high"].iloc[l2])
    l3Price = float(df["low" if isBottom else "high"].iloc[l3])
    h1Price = float(df["high" if isBottom else "low"].iloc[h1])
    h2Price = float(df["high" if isBottom else "low"].iloc[h2])

    necklinePrice = max(h1Price, h2Price) if isBottom else min(h1Price, h2Price)
    formWindowAvgVol = float(df["volume"].iloc[l1:l3 + 1].mean())
    totalSpan = l3 - l1
    leftSpan = l2 - l1
    rightSpan = l3 - l2
    shoulderGap = abs(l1Price - l3Price) / abs(l2Price) if l2Price else 1.0
    timeGap = abs(leftSpan - rightSpan) / totalSpan if totalSpan else 1.0
    headDepth = (
        abs(necklinePrice - l2Price) / abs(necklinePrice)
        if necklinePrice else 0.0
    )

    maxLook = min(len(df) - 1 - l3, max(30, totalSpan))
    breakout = _findBreakout(
        df,
        startIdx=l3,
        necklinePrice=necklinePrice,
        volumeMultiplier=volumeMultiplier,
        formWindowAvgVol=formWindowAvgVol,
        maxLook=maxLook,
        isBottom=isBottom,
    )

    if breakout is None:
        status = _STATUS_FORMING
        breakoutDate = None
        breakoutIdx = None
        breakoutPrice = None
    else:
        status = breakout["status"]
        breakoutDate = breakout["breakoutDate"]
        breakoutIdx = breakout["breakoutIdx"]
        breakoutPrice = breakout["breakoutPrice"]

    if isBottom:
        targetClassic = 2 * necklinePrice - l2Price
        targetConservative = necklinePrice * (1 + conservativeTargetPct)
    else:
        targetClassic = 2 * necklinePrice - l2Price
        targetConservative = necklinePrice * (1 - conservativeTargetPct)

    return {
        "leftShoulderIdx": l1,
        "leftShoulderDate": df["date"].iloc[l1],
        "leftShoulderPrice": l1Price,
        "headIdx": l2,
        "headDate": df["date"].iloc[l2],
        "headPrice": l2Price,
        "rightShoulderIdx": l3,
        "rightShoulderDate": df["date"].iloc[l3],
        "rightShoulderPrice": l3Price,
        "leftNecklineIdx": h1,
        "leftNecklineDate": df["date"].iloc[h1],
        "leftNecklinePrice": h1Price,
        "rightNecklineIdx": h2,
        "rightNecklineDate": df["date"].iloc[h2],
        "rightNecklinePrice": h2Price,
        "necklinePrice": necklinePrice,
        "breakoutIdx": breakoutIdx,
        "breakoutDate": breakoutDate,
        "breakoutPrice": breakoutPrice,
        "status": status,
        "targetPriceClassic": targetClassic,
        "targetPriceConservative": targetConservative,
        "formSpan": totalSpan,
        "shoulderGap": shoulderGap,
        "timeGap": timeGap,
        "headDepth": headDepth,
        "score": _score(shoulderGap, timeGap, headDepth, breakout is not None),
    }


def _findHeadShoulder(df: pd.DataFrame,
                      isBottom: bool,
                      minSpan: int,
                      maxSpan: int,
                      pivotWindow: int,
                      shoulderTolerance: float,
                      timeSymmetry: float,
                      volumeMultiplier: float,
                      conservativeTargetPct: float) -> pd.DataFrame:
    df = normalizeKline(df)
    if len(df) < minSpan + 2 * pivotWindow + 1:
        return pd.DataFrame()

    pivots = (findSwingLows(df, pivotWindow)
              if isBottom else findSwingHighs(df, pivotWindow))
    if len(pivots) < 3:
        return pd.DataFrame()

    priceCol = "low" if isBottom else "high"
    prices = df[priceCol].to_numpy()

    matches: List[dict] = []
    # 枚举所有 (L1, L2, L3) 三元组
    for a in range(len(pivots) - 2):
        for b in range(a + 1, len(pivots) - 1):
            for c in range(b + 1, len(pivots)):
                l1, l2, l3 = pivots[a], pivots[b], pivots[c]
                span = l3 - l1
                if span < minSpan or span > maxSpan:
                    continue

                # 头部最低（或最高）
                if isBottom:
                    if not (prices[l2] < prices[l1] and prices[l2] < prices[l3]):
                        continue
                else:
                    if not (prices[l2] > prices[l1] and prices[l2] > prices[l3]):
                        continue

                # 肩对称
                shoulderGap = (
                    abs(prices[l1] - prices[l3]) / abs(prices[l2])
                    if prices[l2] else 1.0
                )
                if shoulderGap > shoulderTolerance:
                    continue

                # 时间对称
                leftSpan = l2 - l1
                rightSpan = l3 - l2
                timeGap = abs(leftSpan - rightSpan) / span
                if timeGap > timeSymmetry:
                    continue

                # 颈线两个端点：两段区间内极值
                if isBottom:
                    h1 = highestBetween(df, l1, l2)
                    h2 = highestBetween(df, l2, l3)
                else:
                    h1 = lowestBetween(df, l1, l2)
                    h2 = lowestBetween(df, l2, l3)

                match = _buildMatch(
                    df, l1, l2, l3, h1, h2,
                    isBottom=isBottom,
                    volumeMultiplier=volumeMultiplier,
                    conservativeTargetPct=conservativeTargetPct,
                )
                if match:
                    matches.append(match)

    if not matches:
        return pd.DataFrame()

    out = pd.DataFrame(matches)
    out = out.sort_values(["score", "headDate"],
                          ascending=[False, False]).reset_index(drop=True)
    return out


def findHeadShoulderBottom(df: pd.DataFrame,
                           minSpan: int = 30,
                           maxSpan: int = 120,
                           pivotWindow: int = 5,
                           shoulderTolerance: float = 0.05,
                           timeSymmetry: float = 0.4,
                           volumeMultiplier: float = 1.5,
                           conservativeTargetPct: float = 0.05) -> pd.DataFrame:
    """查找头肩底形态。返回按 score 降序排序的所有匹配。

    Returns DataFrame 关键列:
        status: 'forming' / 'breakout' / 'confirmed'
        necklinePrice: 颈线（两肩间高点最大值，更保守）
        targetPriceClassic: 2 × 颈线 - 头部低点
        targetPriceConservative: 颈线 × (1 + conservativeTargetPct)
        score: 综合评分 0~1（肩对称 / 时间对称 / 头部深度 / 突破加分）
    """
    return _findHeadShoulder(df, isBottom=True,
                             minSpan=minSpan, maxSpan=maxSpan,
                             pivotWindow=pivotWindow,
                             shoulderTolerance=shoulderTolerance,
                             timeSymmetry=timeSymmetry,
                             volumeMultiplier=volumeMultiplier,
                             conservativeTargetPct=conservativeTargetPct)


def findHeadShoulderTop(df: pd.DataFrame,
                        minSpan: int = 30,
                        maxSpan: int = 120,
                        pivotWindow: int = 5,
                        shoulderTolerance: float = 0.05,
                        timeSymmetry: float = 0.4,
                        volumeMultiplier: float = 1.5,
                        conservativeTargetPct: float = 0.05) -> pd.DataFrame:
    """查找头肩顶形态。与头肩底对称（targetPriceConservative = 颈线 × (1 - pct)）。"""
    return _findHeadShoulder(df, isBottom=False,
                             minSpan=minSpan, maxSpan=maxSpan,
                             pivotWindow=pivotWindow,
                             shoulderTolerance=shoulderTolerance,
                             timeSymmetry=timeSymmetry,
                             volumeMultiplier=volumeMultiplier,
                             conservativeTargetPct=conservativeTargetPct)
