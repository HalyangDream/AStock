"""网格交易二维寻优器（步长 × 层数）+ 持有收益基准。

策略：用户给定 totalAmount（总金额），系统遍历 spacings × levelsList 跑回测，
按 rankBy 指标排序，返回 top N + 最佳完整结果。每个候选额外计算同等资金 buy &
hold 的收益作为基准（holdReturn），以及 excessReturn = totalReturn - holdReturn。
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional

import pandas as pd

from .gridEngine import runGridBacktest

DEFAULT_SPACINGS = tuple(
    [round(i / 1000, 4) for i in range(10, 51)]        # 1.0%~5.0% 步进 0.1%
    + [round(i / 1000, 4) for i in range(55, 155, 5)]  # 5.5%~15.0% 步进 0.5%
)
DEFAULT_LEVELS_LIST = (3, 5, 8, 10, 15, 20, 30)

_RANK_KEYS = ("totalReturn", "annualReturn", "sharpe")
_CASH_BUFFER = 0.005


def autoShareSize(totalAmount: float, levels: int, refPrice: float) -> int:
    """每格资金 = totalAmount / (levels × 2)，扣 cashBuffer 后折成整百股。

    总资金分两半：下半用于买入加仓，上半用于持仓 + 盈利储备。
    最少 100 股。
    """
    if totalAmount <= 0 or levels <= 0 or refPrice <= 0:
        raise ValueError("totalAmount / levels / refPrice 必须 > 0")
    perGridAmount = totalAmount / (levels * 2) * (1 - _CASH_BUFFER)
    raw = int(perGridAmount // (refPrice * 100)) * 100
    return max(100, raw)


def _computeHoldReturn(kline: pd.DataFrame, totalAmount: float) -> float:
    """同等资金 buy & hold 收益（首日 close 全仓，末日 close 估值）。"""
    if kline is None or kline.empty:
        return 0.0
    sortedKline = kline.sort_values("date") if "date" in kline.columns else kline
    firstClose = float(sortedKline["close"].iloc[0])
    lastClose = float(sortedKline["close"].iloc[-1])
    if firstClose <= 0 or totalAmount <= 0:
        return 0.0
    rawShares = int(totalAmount * (1 - _CASH_BUFFER) // firstClose)
    shares = (rawShares // 100) * 100
    if shares <= 0:
        return 0.0
    cashLeft = totalAmount - shares * firstClose
    endValue = shares * lastClose + cashLeft
    return endValue / totalAmount - 1


def gridOptimize(kline: pd.DataFrame,
                 totalAmount: float,
                 spacings: Optional[List[float]] = None,
                 levelsList: Optional[List[int]] = None,
                 rankBy: str = "totalReturn",
                 topN: int = 5,
                 commission: float = 0.0003,
                 stampTax: float = 0.001,
                 progressCb: Optional[
                     Callable[[int, int, dict], None]] = None,
                 ) -> dict:
    """二维寻优：遍历 spacings × levelsList，返回 top N + 最佳完整结果。

    基准价 = K 线首日 close（避免未来函数偏差）。

    Args:
        kline: K 线 DataFrame
        totalAmount: 初始现金
        spacings: 候选步长列表，默认 DEFAULT_SPACINGS
        levelsList: 候选层数列表，默认 DEFAULT_LEVELS_LIST
        rankBy: 排序指标 (totalReturn / annualReturn / sharpe)
        topN: 返回前 N 个候选概要
        commission: 买卖双边佣金比例
        stampTax: 卖出印花税比例
        progressCb: 进度回调 (idx, total, summaryDict)

    Returns:
        {
          'candidates': List[dict],
          'top': List[dict],
          'best': dict  (含 spacing / levels / shareSize / centerPrice 元信息)
        }
    """
    if rankBy not in _RANK_KEYS:
        raise ValueError(f"rankBy 必须是 {_RANK_KEYS}")
    if totalAmount <= 0:
        raise ValueError("totalAmount 必须 > 0")
    if kline is None or kline.empty:
        raise ValueError("kline 不能为空")

    spacings = list(spacings) if spacings else list(DEFAULT_SPACINGS)
    levelsList = list(levelsList) if levelsList else list(DEFAULT_LEVELS_LIST)
    if not spacings or not levelsList:
        raise ValueError("spacings / levelsList 不能为空")
    for lv in levelsList:
        if lv <= 0:
            raise ValueError("levelsList 元素必须 > 0")

    sortedKline = kline.sort_values("date") if "date" in kline.columns else kline
    centerPrice = float(sortedKline["close"].iloc[0])
    holdReturn = _computeHoldReturn(sortedKline, totalAmount)

    candidates: List[dict] = []
    bestResult: Optional[dict] = None
    bestSpacing: Optional[float] = None
    bestLevels: Optional[int] = None
    bestShareSize: Optional[int] = None
    bestRank = -math.inf

    total = len(spacings) * len(levelsList)
    idx = 0
    for sp in spacings:
        for lv in levelsList:
            shareSize = autoShareSize(totalAmount, lv, centerPrice)
            result = runGridBacktest(
                kline,
                gridSpacingPct=sp,
                gridLevels=lv,
                shareSize=shareSize,
                centerPrice=centerPrice,
                initialCash=totalAmount,
                commission=commission,
                stampTax=stampTax,
            )
            m = result["metrics"]
            totalReturn = float(m.get("totalReturn", 0.0))
            row = {
                "spacing": sp,
                "levels": lv,
                "totalReturn": totalReturn,
                "annualReturn": float(m.get("annualReturn", 0.0)),
                "sharpe": float(m.get("sharpe", 0.0)),
                "maxDrawdown": float(m.get("maxDrawdown", 0.0)),
                "winRate": float(m.get("winRate", 0.0)),
                "tradeCount": int(m.get("tradeCount", 0)),
                "holdReturn": holdReturn,
                "excessReturn": totalReturn - holdReturn,
                "summary": result["summary"],
            }
            candidates.append(row)

            rankVal = row[rankBy]
            if rankVal > bestRank:
                bestRank = rankVal
                bestResult = result
                bestSpacing = sp
                bestLevels = lv
                bestShareSize = shareSize

            idx += 1
            if progressCb is not None:
                progressCb(idx, total, row)

    candidates.sort(key=lambda r: r[rankBy], reverse=True)
    top = candidates[:topN]

    bestPayload = dict(bestResult or {})
    bestPayload["spacing"] = bestSpacing
    bestPayload["levels"] = bestLevels
    bestPayload["shareSize"] = bestShareSize
    bestPayload["centerPrice"] = centerPrice
    bestPayload["holdReturn"] = holdReturn
    if bestResult is not None:
        bestTotalReturn = float(
            bestResult["metrics"].get("totalReturn", 0.0))
        bestPayload["excessReturn"] = bestTotalReturn - holdReturn
    else:
        bestPayload["excessReturn"] = 0.0

    return {
        "candidates": candidates,
        "top": top,
        "best": bestPayload,
    }
