"""头肩底 / 头肩顶形态识别（v2）。

头肩底：左肩 L1 → 颈线 H1 → 头 L2（最低）→ 颈线 H2 → 右肩 L3
确认条件：
  - 几何约束：L2 < L1, L2 < L3；|L1-L3|/|L2| ≤ shoulderTolerance；时间对称度 ≤ timeSymmetry
  - 跨度约束：minSpan ≤ t(L3) - t(L1) ≤ maxSpan
  - 头→右肩约束（isBottom）：headToShoulderMinSpan ≤ (L3-L2) ≤ headToShoulderMaxSpan
  - 颈线突破：收盘价站上动态颈线价 + 突破日量 > 前5日均量 × volumeMultiplier
  - confirmed 要求：后3根不跌破颈线 + 突破日收盘 ≥ necklinePrice × (1 + breakoutConfirmPct)
  - isBottom 专属：前置趋势过滤、颈线斜率过滤、成交量分布评分、回抽识别

isBottom=False（头肩顶）时，v2 新增逻辑全部跳过，行为与改动前一致。
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from ._utils import (
    calcTrendSlope,
    findSwingHighs,
    findSwingLows,
    highestBetween,
    lowestBetween,
    normalizeKline,
)

_STATUS_FORMING = "forming"
_STATUS_BREAKOUT = "breakout"
_STATUS_CONFIRMED = "confirmed"


def _volumeDistScore(df: pd.DataFrame,
                     l1: int, l2: int, l3: int) -> tuple:
    """成交量分布评分 + 量能递减检测（仅 isBottom 调用）。

    三段划分：左肩段 [L1, L2)、头部段 [L2-2, L2+2]（±2 根）、右肩段 (L2, L3]
    评分规则（0~1）：
    - 头部均量是三段最小：+0.6
    - 右肩均量 ≥ 左肩均量：+0.4
    递减判定：avgLeft > avgHead > avgRight（严格递减）。

    Returns (score: float, volumeDecay: bool)
    """
    vols = df["volume"].to_numpy(dtype=float)
    avgLeft = float(vols[l1:l2].mean()) if l2 > l1 else float(vols[l1])
    headStart = max(l1, l2 - 2)
    headEnd = min(l3, l2 + 3)
    avgHead = float(vols[headStart:headEnd].mean()) if headEnd > headStart else float(vols[l2])
    avgRight = float(vols[l2 + 1:l3 + 1].mean()) if l3 > l2 else float(vols[l3])

    score = 0.0
    if avgHead <= avgLeft and avgHead <= avgRight:
        score += 0.6
    elif avgHead <= max(avgLeft, avgRight):
        score += 0.3
    if avgRight >= avgLeft:
        score += 0.4

    decay = avgLeft > avgHead and avgHead > avgRight
    return min(1.0, score), decay


def _deriveBuyPoint(status: str, volumeDecay: bool,
                    hasPullback: bool, isBottom: bool) -> Optional[str]:
    """根据状态和量能递减推导买点类型（仅 isBottom=True 有效）。"""
    if not isBottom:
        return None
    if status == _STATUS_CONFIRMED:
        return "rightShoulder"
    if status == _STATUS_FORMING:
        return "rightShoulder" if volumeDecay else None
    if hasPullback:
        return "pullback"
    if status == _STATUS_BREAKOUT:
        return "breakout"
    return None


def _score(shoulderGap: float,
           timeGap: float,
           headDepth: float,
           hasBreakout: bool,
           trendSlope: float,
           volDistScore: float) -> float:
    """综合评分 0~1（v3 权重）。

    肩对称 0.20 / 时间对称 0.15 / 头深 0.20 / 突破 0.10 / 趋势 0.10 / 成交量 0.25
    """
    s1 = max(0.0, 1.0 - shoulderGap / 0.05) * 0.20
    s2 = max(0.0, 1.0 - timeGap / 0.4) * 0.15
    s3 = min(1.0, headDepth / 0.15) * 0.20
    s4 = 0.10 if hasBreakout else 0.0
    s5 = min(1.0, abs(trendSlope) / 0.005) * 0.10
    s6 = volDistScore * 0.25
    return round(s1 + s2 + s3 + s4 + s5 + s6, 4)


def _findBreakout(df: pd.DataFrame,
                  startIdx: int,
                  necklinePrice: float,
                  h1Idx: int,
                  necklineSlope: float,
                  staticNecklinePrice: float,
                  breakoutConfirmPct: float,
                  volumeMultiplier: float,
                  maxLook: int,
                  isBottom: bool) -> Optional[dict]:
    """从 startIdx 之后开始寻找突破点。

    isBottom=True 时突破用动态颈线外推价，confirmed 额外要求收盘 ≥ staticNecklinePrice × (1+pct)。
    isBottom=False 时沿用固定颈线价。
    """
    end = min(len(df), startIdx + 1 + maxLook)
    for i in range(startIdx + 1, end):
        close = float(df["close"].iloc[i])
        volume = float(df["volume"].iloc[i])

        vol5 = float(df["volume"].iloc[max(0, i - 5):i].mean())

        if isBottom:
            breakThreshold = necklinePrice + necklineSlope * (i - h1Idx)
        else:
            breakThreshold = necklinePrice

        priceBreak = close > breakThreshold if isBottom else close < breakThreshold
        volBreak = volume >= vol5 * volumeMultiplier

        if priceBreak and volBreak:
            confirmEnd = min(len(df), i + 4)
            priceHeld = True
            for j in range(i + 1, confirmEnd):
                c = float(df["close"].iloc[j])
                if isBottom:
                    dynNeck = necklinePrice + necklineSlope * (j - h1Idx)
                    confirmThreshold = dynNeck * (1 + 0.01)
                    if c < confirmThreshold:
                        priceHeld = False
                        break
                else:
                    if c > necklinePrice:
                        priceHeld = False
                        break

            if isBottom:
                pctBreak = close >= staticNecklinePrice * (1 + breakoutConfirmPct)
                has3Bars = (confirmEnd - i - 1) >= 3
                lastClose = float(df["close"].iloc[-1])
                nearNeckline = lastClose <= staticNecklinePrice * 1.10
                aboveNeckline = lastClose >= staticNecklinePrice
                confirmed = (priceHeld and pctBreak and has3Bars
                             and aboveNeckline and nearNeckline)
            else:
                confirmed = priceHeld

            return {
                "breakoutIdx": i,
                "breakoutDate": df["date"].iloc[i],
                "breakoutPrice": close,
                "breakoutVolume": volume,
                "status": _STATUS_CONFIRMED if confirmed else _STATUS_BREAKOUT,
            }
    return None


def _findPullback(df: pd.DataFrame,
                  breakoutIdx: int,
                  h1Idx: int,
                  h1Price: float,
                  necklineSlope: float,
                  pullbackWindow: int,
                  pullbackTolerance: float) -> dict:
    """突破后 pullbackWindow 日内寻找首次回抽颈线机会（仅 isBottom=True 调用）。"""
    end = min(len(df), breakoutIdx + 1 + pullbackWindow)
    for i in range(breakoutIdx + 1, end):
        dynNeck = h1Price + necklineSlope * (i - h1Idx)
        if dynNeck <= 0:
            continue
        close = float(df["close"].iloc[i])
        if abs(close - dynNeck) / dynNeck <= pullbackTolerance:
            return {
                "hasPullback": True,
                "pullbackDate": df["date"].iloc[i],
                "pullbackPrice": close,
            }
    return {"hasPullback": False, "pullbackDate": None, "pullbackPrice": None}


def _buildMatch(df: pd.DataFrame,
                l1: int, l2: int, l3: int,
                h1: int, h2: int,
                isBottom: bool,
                volumeMultiplier: float,
                conservativeTargetPct: float,
                breakoutConfirmPct: float,
                trendSlope: float,
                pullbackWindow: int,
                pullbackTolerance: float) -> Optional[dict]:
    """构造匹配记录；失败返回 None。"""
    l1Price = float(df["low" if isBottom else "high"].iloc[l1])
    l2Price = float(df["low" if isBottom else "high"].iloc[l2])
    l3Price = float(df["low" if isBottom else "high"].iloc[l3])
    h1Price = float(df["high" if isBottom else "low"].iloc[h1])
    h2Price = float(df["high" if isBottom else "low"].iloc[h2])

    necklineSlope = 0.0
    if isBottom:
        span = h2 - h1
        necklineSlope = (h2Price - h1Price) / span if span != 0 else 0.0

    # v2 修正：necklinePrice = max(H1, H2)（经典颈线定义）
    if isBottom:
        necklinePrice = max(h1Price, h2Price)
    else:
        necklinePrice = min(h1Price, h2Price)

    totalSpan = l3 - l1
    leftSpan = l2 - l1
    rightSpan = l3 - l2
    shoulderGap = abs(l1Price - l3Price) / abs(l2Price) if l2Price else 1.0
    timeGap = abs(leftSpan - rightSpan) / totalSpan if totalSpan else 1.0
    headDepth = (
        abs(necklinePrice - l2Price) / abs(necklinePrice)
        if necklinePrice else 0.0
    )

    if isBottom:
        volDistScore, volumeDecay = _volumeDistScore(df, l1, l2, l3)
    else:
        volDistScore, volumeDecay = 0.0, False

    maxLook = min(len(df) - 1 - l3, max(30, totalSpan))
    breakout = _findBreakout(
        df,
        startIdx=l3,
        necklinePrice=h1Price,
        h1Idx=h1,
        necklineSlope=necklineSlope,
        staticNecklinePrice=necklinePrice,
        breakoutConfirmPct=breakoutConfirmPct,
        volumeMultiplier=volumeMultiplier,
        maxLook=maxLook,
        isBottom=isBottom,
    )

    if breakout is None:
        status = _STATUS_FORMING
        breakoutDate = None
        breakoutIdx = None
        breakoutPrice = None
        necklinePriceAtBreakout = None
        pullbackResult = {"hasPullback": False, "pullbackDate": None, "pullbackPrice": None}
    else:
        status = breakout["status"]
        breakoutDate = breakout["breakoutDate"]
        breakoutIdx = breakout["breakoutIdx"]
        breakoutPrice = breakout["breakoutPrice"]
        if isBottom:
            necklinePriceAtBreakout = h1Price + necklineSlope * (breakoutIdx - h1)
            pullbackResult = _findPullback(
                df, breakoutIdx, h1, h1Price, necklineSlope,
                pullbackWindow, pullbackTolerance,
            )
        else:
            necklinePriceAtBreakout = None
            pullbackResult = {"hasPullback": False, "pullbackDate": None, "pullbackPrice": None}

    if isBottom:
        targetClassic = 2 * necklinePrice - l2Price
        targetConservative = necklinePrice * (1 + conservativeTargetPct)
    else:
        targetClassic = 2 * necklinePrice - l2Price
        targetConservative = necklinePrice * (1 - conservativeTargetPct)

    if isBottom:
        rightShoulderAge = len(df) - 1 - l3
        if rightShoulderAge > 30:
            return None

    if isBottom and status == _STATUS_FORMING:
        lastClose = float(df["close"].iloc[-1])
        if lastClose < l2Price:
            return None
        if lastClose > l3Price and lastClose < necklinePrice:
            status = _STATUS_CONFIRMED

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
        "necklineSlope": necklineSlope,
        "breakoutIdx": breakoutIdx,
        "breakoutDate": breakoutDate,
        "breakoutPrice": breakoutPrice,
        "status": status,
        "necklinePriceAtBreakout": necklinePriceAtBreakout,
        "hasPullback": pullbackResult["hasPullback"],
        "pullbackDate": pullbackResult["pullbackDate"],
        "pullbackPrice": pullbackResult["pullbackPrice"],
        "targetPriceClassic": targetClassic,
        "targetPriceConservative": targetConservative,
        "formSpan": totalSpan,
        "shoulderGap": shoulderGap,
        "timeGap": timeGap,
        "headDepth": headDepth,
        "volumeDistScore": volDistScore,
        "volumeDecay": volumeDecay,
        "buyPoint": _deriveBuyPoint(status, volumeDecay,
                                    pullbackResult["hasPullback"], isBottom),
        "score": _score(shoulderGap, timeGap, headDepth,
                        breakout is not None, trendSlope, volDistScore),
    }


def _findHeadShoulder(df: pd.DataFrame,
                      isBottom: bool,
                      minSpan: int,
                      maxSpan: int,
                      pivotWindow: int,
                      shoulderTolerance: float,
                      timeSymmetry: float,
                      volumeMultiplier: float,
                      conservativeTargetPct: float,
                      trendWindow: int,
                      trendMinSlope: float,
                      necklineSlopeMin: float,
                      pullbackWindow: int,
                      pullbackTolerance: float,
                      headToShoulderMinSpan: int,
                      headToShoulderMaxSpan: int,
                      breakoutConfirmPct: float,
                      volumeDecayFilter: bool = False,
                      headDepthMin: float = 0.0,
                      maxPivotGap: int = 1) -> pd.DataFrame:
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
    for a in range(len(pivots) - 2):
        for b in range(a + 1, len(pivots) - 1):
            if (b - a) > maxPivotGap:
                break
            for c in range(b + 1, len(pivots)):
                if (c - b) > maxPivotGap:
                    break
                l1, l2, l3 = pivots[a], pivots[b], pivots[c]
                span = l3 - l1
                if span < minSpan or span > maxSpan:
                    continue

                if isBottom:
                    if not (prices[l2] < prices[l1] and prices[l2] < prices[l3]):
                        continue
                    segMin = float(df["low"].iloc[l1:l3 + 1].min())
                    if prices[l2] > segMin:
                        continue
                else:
                    if not (prices[l2] > prices[l1] and prices[l2] > prices[l3]):
                        continue

                shoulderGap = (
                    abs(prices[l1] - prices[l3]) / abs(prices[l2])
                    if prices[l2] else 1.0
                )
                if shoulderGap > shoulderTolerance:
                    continue

                if headDepthMin > 0 and isBottom:
                    minShoulder = min(prices[l1], prices[l3])
                    if minShoulder > 0:
                        depth = (minShoulder - prices[l2]) / minShoulder
                        if depth < headDepthMin:
                            continue

                leftSpan = l2 - l1
                rightSpan = l3 - l2
                timeGap = abs(leftSpan - rightSpan) / span
                if timeGap > timeSymmetry:
                    continue

                if isBottom:
                    h1 = highestBetween(df, l1, l2)
                    h2 = highestBetween(df, l2, l3)
                else:
                    h1 = lowestBetween(df, l1, l2)
                    h2 = lowestBetween(df, l2, l3)

                # ── isBottom 专属过滤 ─────────────────────────────
                trendSlope = 0.0
                if isBottom:
                    # 头→右肩时间约束
                    headToShoulder = l3 - l2
                    if headToShoulderMinSpan <= headToShoulderMaxSpan:
                        if headToShoulder < headToShoulderMinSpan or headToShoulder > headToShoulderMaxSpan:
                            continue

                    # 前置趋势过滤
                    pre = df["close"].iloc[max(0, l1 - trendWindow): l1]
                    if len(pre) >= trendWindow:
                        trendSlope = calcTrendSlope(pre, trendWindow)
                        if trendSlope > trendMinSlope:
                            continue

                    # 颈线斜率过滤
                    h1Price = float(df["high"].iloc[h1])
                    h2Price = float(df["high"].iloc[h2])
                    necklineSlope = (
                        (h2Price - h1Price) / (h2 - h1) if h2 != h1 else 0.0
                    )
                    if necklineSlope < necklineSlopeMin:
                        continue

                    if volumeDecayFilter:
                        _, decay = _volumeDistScore(df, l1, l2, l3)
                        if not decay:
                            continue
                # ──────────────────────────────────────────────────

                match = _buildMatch(
                    df, l1, l2, l3, h1, h2,
                    isBottom=isBottom,
                    volumeMultiplier=volumeMultiplier,
                    conservativeTargetPct=conservativeTargetPct,
                    breakoutConfirmPct=breakoutConfirmPct,
                    trendSlope=trendSlope,
                    pullbackWindow=pullbackWindow,
                    pullbackTolerance=pullbackTolerance,
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
                           conservativeTargetPct: float = 0.05,
                           trendWindow: int = 60,
                           trendMinSlope: float = -0.0001,
                           necklineSlopeMin: float = -0.002,
                           pullbackWindow: int = 10,
                           pullbackTolerance: float = 0.02,
                           headToShoulderMinSpan: int = 20,
                           headToShoulderMaxSpan: int = 65,
                           breakoutConfirmPct: float = 0.03,
                           volumeDecayFilter: bool = False,
                           headDepthMin: float = 0.03,
                           maxPivotGap: int = 1) -> pd.DataFrame:
    """查找头肩底形态（v3）。返回按 score 降序排序的所有匹配。

    Returns DataFrame 关键列:
        status: 'forming' / 'breakout' / 'confirmed'
        necklinePrice: max(H1, H2)，经典颈线定义
        necklineSlope: 颈线斜率（正=右上倾斜）
        necklinePriceAtBreakout: 突破日颈线外推价（forming 时为 None）
        targetPriceClassic: 2 × 颈线 - 头部低点（等幅测距）
        volumeDistScore: 成交量分布评分 0~1
        volumeDecay: 三段量能是否严格递减
        score: 综合评分 0~1（六维：肩对称/时间/头深/突破/趋势/成交量）
    """
    return _findHeadShoulder(
        df, isBottom=True,
        minSpan=minSpan, maxSpan=maxSpan,
        pivotWindow=pivotWindow,
        shoulderTolerance=shoulderTolerance,
        timeSymmetry=timeSymmetry,
        volumeMultiplier=volumeMultiplier,
        conservativeTargetPct=conservativeTargetPct,
        trendWindow=trendWindow,
        trendMinSlope=trendMinSlope,
        necklineSlopeMin=necklineSlopeMin,
        pullbackWindow=pullbackWindow,
        pullbackTolerance=pullbackTolerance,
        headToShoulderMinSpan=headToShoulderMinSpan,
        headToShoulderMaxSpan=headToShoulderMaxSpan,
        breakoutConfirmPct=breakoutConfirmPct,
        volumeDecayFilter=volumeDecayFilter,
        headDepthMin=headDepthMin,
        maxPivotGap=maxPivotGap,
    )


def findHeadShoulderTop(df: pd.DataFrame,
                        minSpan: int = 30,
                        maxSpan: int = 120,
                        pivotWindow: int = 5,
                        shoulderTolerance: float = 0.05,
                        timeSymmetry: float = 0.4,
                        volumeMultiplier: float = 1.5,
                        conservativeTargetPct: float = 0.05,
                        trendWindow: int = 60,
                        trendMinSlope: float = -0.0001,
                        necklineSlopeMin: float = -0.002,
                        pullbackWindow: int = 10,
                        pullbackTolerance: float = 0.02,
                        headToShoulderMinSpan: int = 20,
                        headToShoulderMaxSpan: int = 65,
                        breakoutConfirmPct: float = 0.03,
                        volumeDecayFilter: bool = False,
                        headDepthMin: float = 0.0,
                        maxPivotGap: int = 1) -> pd.DataFrame:
    """查找头肩顶形态。v3 新增参数透传但不启用 isBottom 专属逻辑。"""
    return _findHeadShoulder(
        df, isBottom=False,
        minSpan=minSpan, maxSpan=maxSpan,
        pivotWindow=pivotWindow,
        shoulderTolerance=shoulderTolerance,
        timeSymmetry=timeSymmetry,
        volumeMultiplier=volumeMultiplier,
        conservativeTargetPct=conservativeTargetPct,
        trendWindow=trendWindow,
        trendMinSlope=trendMinSlope,
        necklineSlopeMin=necklineSlopeMin,
        pullbackWindow=pullbackWindow,
        pullbackTolerance=pullbackTolerance,
        headToShoulderMinSpan=headToShoulderMinSpan,
        headToShoulderMaxSpan=headToShoulderMaxSpan,
        breakoutConfirmPct=breakoutConfirmPct,
        volumeDecayFilter=volumeDecayFilter,
        headDepthMin=headDepthMin,
        maxPivotGap=maxPivotGap,
    )
