"""网格交易步长寻优器。

策略：用户给定 levels（上下档位数）+ totalAmount（总金额），系统遍历
DEFAULT_SPACINGS（11 档）跑回测，按 rankBy 指标排序，返回 top N + 最佳完整结果。
"""

from __future__ import annotations

from typing import Callable, List, Optional

import pandas as pd

from .gridEngine import runGridBacktest

DEFAULT_SPACINGS = (0.005, 0.01, 0.015, 0.02, 0.025,
                    0.03, 0.04, 0.05, 0.07, 0.10, 0.15)

_RANK_KEYS = ("totalReturn", "annualReturn", "sharpe")
_CASH_BUFFER = 0.005  # 与 GridStrategy 默认一致


def autoShareSize(totalAmount: float, levels: int, refPrice: float) -> int:
    """每格资金 = totalAmount / (levels × 2)，扣 cashBuffer 后折成整百股。

    总资金分两半：下半用于初始底仓（最多 levels 档），上半用于后续下跌补仓弹药。
    最少 100 股；若用户金额过小，由 GridStrategy 内现金检查兜底跳过 buy。
    """
    if totalAmount <= 0 or levels <= 0 or refPrice <= 0:
        raise ValueError("totalAmount / levels / refPrice 必须 > 0")
    perGridAmount = totalAmount / (levels * 2) * (1 - _CASH_BUFFER)
    raw = int(perGridAmount // (refPrice * 100)) * 100
    return max(100, raw)


def gridOptimize(kline: pd.DataFrame,
                 levels: int,
                 totalAmount: float,
                 spacings: Optional[List[float]] = None,
                 rankBy: str = "totalReturn",
                 topN: int = 5,
                 progressCb: Optional[
                     Callable[[int, int, dict], None]] = None,
                 ) -> dict:
    """对每个步长跑一次 grid 回测，返回 top N + 最佳完整结果。

    中心价 = K 线首日 close（策略启动时唯一已知价格，避免未来函数偏差）。

    Args:
        kline: K 线 DataFrame
        levels: 上下各档位数
        totalAmount: 初始现金
        spacings: 候选步长列表，默认 DEFAULT_SPACINGS
        rankBy: 排序指标 (totalReturn / annualReturn / sharpe)
        topN: 返回前 N 个候选概要
        progressCb: 进度回调 (idx, total, summaryDict)

    Returns:
        {
          'candidates': List[dict],
          'top': List[dict],
          'best': dict  (含 spacing / shareSize / centerPrice 元信息)
        }
    """
    if rankBy not in _RANK_KEYS:
        raise ValueError(f"rankBy 必须是 {_RANK_KEYS}")
    if levels <= 0:
        raise ValueError("levels 必须 > 0")
    if totalAmount <= 0:
        raise ValueError("totalAmount 必须 > 0")
    if kline is None or kline.empty:
        raise ValueError("kline 不能为空")

    spacings = list(spacings) if spacings else list(DEFAULT_SPACINGS)
    sortedKline = kline.sort_values("date") if "date" in kline.columns else kline
    centerPrice = float(sortedKline["close"].iloc[0])
    shareSize = autoShareSize(totalAmount, levels, centerPrice)

    candidates: List[dict] = []
    bestResult: Optional[dict] = None
    bestSpacing: Optional[float] = None
    bestRank = -float("inf")

    for idx, sp in enumerate(spacings):
        result = runGridBacktest(
            kline,
            gridSpacingPct=sp,
            gridLevels=levels,
            shareSize=shareSize,
            centerPrice=centerPrice,
            initialCash=totalAmount,
        )
        m = result["metrics"]
        row = {
            "spacing": sp,
            "totalReturn": float(m.get("totalReturn", 0.0)),
            "annualReturn": float(m.get("annualReturn", 0.0)),
            "sharpe": float(m.get("sharpe", 0.0)),
            "maxDrawdown": float(m.get("maxDrawdown", 0.0)),
            "winRate": float(m.get("winRate", 0.0)),
            "tradeCount": int(m.get("tradeCount", 0)),
            "summary": result["summary"],
        }
        candidates.append(row)

        rankVal = row[rankBy]
        if rankVal > bestRank:
            bestRank = rankVal
            bestResult = result
            bestSpacing = sp

        if progressCb is not None:
            progressCb(idx + 1, len(spacings), row)

    candidates.sort(key=lambda r: r[rankBy], reverse=True)
    top = candidates[:topN]

    bestPayload = dict(bestResult or {})
    bestPayload["spacing"] = bestSpacing
    bestPayload["shareSize"] = shareSize
    bestPayload["centerPrice"] = centerPrice

    return {
        "candidates": candidates,
        "top": top,
        "best": bestPayload,
    }
