"""底分型 / 顶分型 识别。

底分型（缠论定义）：连续 3 根 K 线，中间一根的低点最低、高点不高于邻根。
经 K 线包含处理后判定更稳定（可选）。

过滤器（独立开关，结果写入 grade 列）：
  A. 后续走高持续性：之后 lookAhead 根内最高收盘 > 分型中心高点 × (1+upThreshold)
  B. 放量：分型窗口内最大成交量 > 前 lookBack 根均量 × volumeMultiplier

grade 分级：
  - weak        ：仅满足几何定义
  - validTrend  ：+ 过滤器 A
  - validVolume ：+ 过滤器 B
  - strong      ：+ A + B
"""

from __future__ import annotations

from typing import List

import pandas as pd

from ._utils import calcTrendSlope, mergeContaining, normalizeKline, rollingMean

_GRADES = ("weak", "validTrend", "validVolume", "strong")


def _gradeOrder(grade: str) -> int:
    return _GRADES.index(grade)


def _matchGrade(trendOk: bool, volumeOk: bool) -> str:
    if trendOk and volumeOk:
        return "strong"
    if trendOk:
        return "validTrend"
    if volumeOk:
        return "validVolume"
    return "weak"


def _detectFractals(processed: pd.DataFrame, isBottom: bool) -> List[dict]:
    """在已包含处理后的 K 线上识别分型位置。返回中心位置字典列表。"""
    out: List[dict] = []
    highs = processed["high"].to_numpy()
    lows = processed["low"].to_numpy()
    for i in range(1, len(processed) - 1):
        if isBottom:
            isMatch = (
                lows[i] < lows[i - 1] and lows[i] < lows[i + 1] and
                highs[i] < highs[i - 1] and highs[i] < highs[i + 1]
            )
        else:
            isMatch = (
                highs[i] > highs[i - 1] and highs[i] > highs[i + 1] and
                lows[i] > lows[i - 1] and lows[i] > lows[i + 1]
            )
        if isMatch:
            out.append({
                "centerIdx": i,
                "leftIdx": i - 1,
                "rightIdx": i + 1,
                "centerDate": processed["date"].iloc[i],
                "centerHigh": float(highs[i]),
                "centerLow": float(lows[i]),
            })
    return out


def _mapToOriginalIdx(processed: pd.DataFrame,
                      original: pd.DataFrame) -> List[int]:
    """处理后的每根 K 线 → 原始 df 中对应的尾部索引。"""
    result: List[int] = []
    originalDates = original["date"].tolist()
    cursor = 0
    for procDate in processed["date"].tolist():
        while cursor < len(originalDates) and originalDates[cursor] != procDate:
            cursor += 1
        result.append(cursor)
        cursor += 1
    return result


def _evaluateFractal(match: dict,
                     original: pd.DataFrame,
                     procToOrigIdx: List[int],
                     isBottom: bool,
                     lookAhead: int,
                     upThreshold: float,
                     lookBack: int,
                     volumeMultiplier: float,
                     volMa: pd.Series) -> dict:
    """用原始 K 线（未合并）评估过滤器 A / B。"""
    leftOrig = procToOrigIdx[match["leftIdx"]]
    rightOrig = procToOrigIdx[match["rightIdx"]]
    centerOrig = procToOrigIdx[match["centerIdx"]]

    trendOk = False
    if rightOrig + 1 < len(original):
        window = original["close"].iloc[
            rightOrig + 1: rightOrig + 1 + lookAhead
        ]
        if not window.empty:
            if isBottom:
                trendOk = bool(window.max() >= match["centerHigh"] * (1 + upThreshold))
            else:
                trendOk = bool(window.min() <= match["centerLow"] * (1 - upThreshold))

    volumeOk = False
    if centerOrig - 1 >= 0:
        refMa = volMa.iloc[max(0, leftOrig - 1)]
        if refMa > 0:
            peakVol = original["volume"].iloc[leftOrig: rightOrig + 1].max()
            volumeOk = bool(peakVol >= refMa * volumeMultiplier)

    return {
        **match,
        "leftDate": original["date"].iloc[leftOrig],
        "rightDate": original["date"].iloc[rightOrig],
        "originalCenterIdx": centerOrig,
        "trendOk": trendOk,
        "volumeOk": volumeOk,
        "grade": _matchGrade(trendOk, volumeOk),
    }


def _findFractals(df: pd.DataFrame,
                  isBottom: bool,
                  merge: bool,
                  lookAhead: int,
                  upThreshold: float,
                  lookBack: int,
                  volumeMultiplier: float,
                  minGrade: str) -> pd.DataFrame:
    original = normalizeKline(df)
    if len(original) < 3:
        return pd.DataFrame()

    processed = mergeContaining(original) if merge else original.assign(mergedCount=1)
    if len(processed) < 3:
        return pd.DataFrame()

    matches = _detectFractals(processed, isBottom=isBottom)
    if not matches:
        return pd.DataFrame()

    procToOrig = _mapToOriginalIdx(processed, original)
    volMa = rollingMean(original["volume"], lookBack)

    evaluated = [
        _evaluateFractal(m, original, procToOrig,
                         isBottom=isBottom,
                         lookAhead=lookAhead,
                         upThreshold=upThreshold,
                         lookBack=lookBack,
                         volumeMultiplier=volumeMultiplier,
                         volMa=volMa)
        for m in matches
    ]

    minRank = _gradeOrder(minGrade)
    filtered = [e for e in evaluated if _gradeOrder(e["grade"]) >= minRank]
    if not filtered:
        return pd.DataFrame()

    cols = [
        "centerDate", "centerIdx", "originalCenterIdx",
        "leftDate", "rightDate", "leftIdx", "rightIdx",
        "centerHigh", "centerLow",
        "trendOk", "volumeOk", "grade",
    ]
    return pd.DataFrame(filtered)[cols].reset_index(drop=True)


def findBottomFractal(df: pd.DataFrame,
                      merge: bool = True,
                      lookAhead: int = 10,
                      upThreshold: float = 0.03,
                      lookBack: int = 20,
                      volumeMultiplier: float = 2.0,
                      minGrade: str = "weak") -> pd.DataFrame:
    """查找底分型。默认全量返回（weak 以上），按 grade 列过滤。

    Args:
        df: 输入 K 线（列 date/open/high/low/close/volume）
        merge: 是否先做包含处理（推荐 True）
        lookAhead: 过滤器 A 的向前窗口（交易日）
        upThreshold: 过滤器 A 的涨幅阈值（如 0.03 表示 3%）
        lookBack: 过滤器 B 的均量窗口
        volumeMultiplier: 过滤器 B 的倍数阈值
        minGrade: 最低返回等级 (weak/validTrend/validVolume/strong)
    """
    if minGrade not in _GRADES:
        raise ValueError(f"minGrade 必须是 {_GRADES}")
    return _findFractals(df, isBottom=True, merge=merge,
                         lookAhead=lookAhead, upThreshold=upThreshold,
                         lookBack=lookBack, volumeMultiplier=volumeMultiplier,
                         minGrade=minGrade)


def findTopFractal(df: pd.DataFrame,
                   merge: bool = True,
                   lookAhead: int = 10,
                   upThreshold: float = 0.03,
                   lookBack: int = 20,
                   volumeMultiplier: float = 2.0,
                   minGrade: str = "weak") -> pd.DataFrame:
    """查找顶分型。参数含义与底分型对称（upThreshold 改作跌幅阈值）。"""
    if minGrade not in _GRADES:
        raise ValueError(f"minGrade 必须是 {_GRADES}")
    return _findFractals(df, isBottom=False, merge=merge,
                         lookAhead=lookAhead, upThreshold=upThreshold,
                         lookBack=lookBack, volumeMultiplier=volumeMultiplier,
                         minGrade=minGrade)


def isCurrentBottomFractal(
    df: pd.DataFrame,
    maWindow: int = 20,
    volMaWindow: int = 120,
    dojiBodyRatio: float = 0.2,
    dojiShadowRatio: float = 0.6,
) -> dict | None:
    """检查最新 K 线是否构成课程体系底分型（三种反转组合 + 双前提）。

    三种形态（按优先级）：三过一 > 阳包阴 > 十字星底。
    两个硬性前提：close > MA20 且形态窗口内最大量 > MA120 当日值。
    """
    original = normalizeKline(df)
    n = len(original)
    if n < 1:
        return None

    _ma20 = original["close"].rolling(maWindow, min_periods=maWindow).mean()
    _volMa120 = original["volume"].rolling(volMaWindow, min_periods=volMaWindow).mean()

    lastClose = float(original["close"].iloc[-1])
    ma20Val = _ma20.iloc[-1]
    if pd.isna(ma20Val):
        return None

    _PATTERNS = [
        ("threeOverOne", "三过一", 3),
        ("engulfing", "阳包阴", 2),
        ("doji", "十字星底", 1),
    ]

    for patternKey, patternLabel, windowSize in _PATTERNS:
        if n < windowSize:
            continue

        window = original.iloc[-windowSize:]

        matched = False
        if patternKey == "threeOverOne":
            d1, d2, d3 = window.iloc[0], window.iloc[1], window.iloc[2]
            matched = (
                float(d3["close"]) > float(d1["high"])
                and float(d2["low"]) <= float(d1["low"])
            )
        elif patternKey == "engulfing":
            d1, d2 = window.iloc[0], window.iloc[1]
            d1IsYin = float(d1["close"]) < float(d1["open"])
            d2IsYang = float(d2["close"]) > float(d2["open"])
            matched = (
                d1IsYin and d2IsYang
                and float(d2["close"]) >= float(d1["open"])
                and float(d2["open"]) <= float(d1["close"])
            )
        elif patternKey == "doji":
            bar = window.iloc[0]
            amplitude = float(bar["high"]) - float(bar["low"])
            if amplitude > 0:
                bodyRatio = abs(float(bar["close"]) - float(bar["open"])) / amplitude
                lowerShadow = min(float(bar["open"]), float(bar["close"])) - float(bar["low"])
                matched = (
                    bodyRatio <= dojiBodyRatio
                    and lowerShadow >= dojiShadowRatio * amplitude
                )

        if not matched:
            continue

        if lastClose <= float(ma20Val):
            return None

        volMa120Val = _volMa120.iloc[-1]
        if pd.isna(volMa120Val):
            return None
        maxVol = float(window["volume"].max())
        if maxVol <= float(volMa120Val):
            return None

        lowestLow = float(window["low"].min())
        signalDate = pd.to_datetime(original["date"].iloc[-1])
        return {
            "pattern": patternKey,
            "patternLabel": patternLabel,
            "signalDate": signalDate,
            "signalPrice": lastClose,
            "lowestLow": lowestLow,
            "ma20": float(ma20Val),
            "volumeOk": True,
        }

    return None
