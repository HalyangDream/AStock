"""把 backtrader 跑完的结果转成项目标准 DataFrame。"""

from __future__ import annotations

from typing import List

import pandas as pd

_EQUITY_COLS = ["date", "value", "cash", "pnl", "returnPct"]
_TRADE_COLS = ["entryDate", "exitDate", "entryPrice", "exitPrice",
               "size", "pnl", "pnlNet", "pnlPct", "barsHeld"]
_EVENT_COLS = ["date", "direction", "price", "size",
               "commission", "pnl", "pnlNet"]
_OPEN_COLS = ["entryDate", "entryPrice", "size",
              "lastPrice", "unrealizedPnl", "unrealizedPnlPct"]


def buildEquityCurve(records: List[dict],
                     initialCash: float) -> pd.DataFrame:
    """analyzer 记录 → 净值曲线 DataFrame。"""
    if not records:
        return pd.DataFrame(columns=_EQUITY_COLS)
    df = pd.DataFrame(records).copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["pnl"] = df["value"] - initialCash
    df["returnPct"] = df["value"] / initialCash - 1
    return df[_EQUITY_COLS]


def buildTrades(tradeLog: List[dict]) -> pd.DataFrame:
    """策略内部 _tradeLog → 交易明细 DataFrame。"""
    if not tradeLog:
        return pd.DataFrame(columns=_TRADE_COLS)
    df = pd.DataFrame(tradeLog).copy()
    df["entryDate"] = pd.to_datetime(df["entryDate"])
    df["exitDate"] = pd.to_datetime(df["exitDate"])
    df = df.sort_values("entryDate").reset_index(drop=True)
    return df[_TRADE_COLS]


def buildTradeEvents(eventLog: List[dict]) -> pd.DataFrame:
    """策略内部 _eventLog → 逐笔买卖事件 DataFrame。"""
    if not eventLog:
        return pd.DataFrame(columns=_EVENT_COLS)
    df = pd.DataFrame(eventLog).copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[_EVENT_COLS]


def buildOpenPositions(openTrades: List[dict],
                       lastPrice: float) -> pd.DataFrame:
    """策略内部 _openTrades + 末根 close → 未平仓持仓 DataFrame。

    每行一笔仍未配对的买入：含买入日 / 买入价 / 当前数量 / 现价 / 浮盈。
    """
    if not openTrades:
        return pd.DataFrame(columns=_OPEN_COLS)
    rows = []
    for entry in openTrades:
        size = int(entry.get("size", 0))
        if size <= 0:
            continue
        entryPrice = float(entry.get("entryPrice", 0.0))
        cost = entryPrice * size
        unreal = (lastPrice - entryPrice) * size
        rows.append({
            "entryDate": entry.get("entryDate"),
            "entryPrice": entryPrice,
            "size": size,
            "lastPrice": float(lastPrice),
            "unrealizedPnl": unreal,
            "unrealizedPnlPct": (unreal / cost) if cost else 0.0,
        })
    if not rows:
        return pd.DataFrame(columns=_OPEN_COLS)
    df = pd.DataFrame(rows)
    df["entryDate"] = pd.to_datetime(df["entryDate"])
    df = df.sort_values("entryDate").reset_index(drop=True)
    return df[_OPEN_COLS]


_OPEN_SUMMARY_COLS = ["avgCost", "totalShares", "lastPrice",
                      "unrealizedPnl", "unrealizedPnlPct"]


def buildOpenPositionsSummary(totalShares: int, avgCost: float,
                              lastPrice: float) -> pd.DataFrame:
    """动态基准价策略的汇总持仓（单行）。"""
    if totalShares <= 0:
        return pd.DataFrame(columns=_OPEN_SUMMARY_COLS)
    cost = avgCost * totalShares
    unreal = (lastPrice - avgCost) * totalShares
    return pd.DataFrame([{
        "avgCost": avgCost,
        "totalShares": totalShares,
        "lastPrice": lastPrice,
        "unrealizedPnl": unreal,
        "unrealizedPnlPct": (unreal / cost) if cost > 0 else 0.0,
    }])
