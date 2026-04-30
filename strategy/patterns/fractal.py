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

from ._utils import mergeContaining, normalizeKline, rollingMean

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
