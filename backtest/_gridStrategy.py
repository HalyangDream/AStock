"""内部 GridStrategy：带初始底仓的双向等比网格交易。

撮合规则：
- 中心价：由外部传入（寻优器传首日 close）；0 = 首根 close
- 档位定义：level = round_or_floor(log(price/center) / log(1+spacing))
  - 浮点吸附：raw 距最近整数 < 1e-9 时取 round，否则 floor
- 每档最多持有 shareSize 股（_filledLevels 集合跟踪已占用档位）
- 初始化（首根 bar）：
  - 算出 initLevel = clamp(_level(close))
  - 对 initLevel-1 到 -gridLevels 每档各下 Market 单 shareSize 股
  - Market 单在 bar 1 开盘成交，模拟建仓
  - 资金不足时停止建仓
- 每根 bar（第 2 根起）：
  - 用 close 判断方向：closeLevel < lastLevel → 只处理 buy；closeLevel > lastLevel → 只处理 sell
  - buy：填充下穿到的目标档位 range(lastLevel-1, closeLevel-1, -1)，已持仓跳过
  - sell：按跨越格数，卖出最高 N 个已填充档位（N = closeLevel - lastLevel）
  - lastLevel 更新为 clamp(_level(close))
- 成交价 = 次日开盘（backtrader Market 默认行为，含佣金 + 印花税）
- 拒单回滚：notify_order 对 Canceled/Margin/Rejected 订单从 _filledLevels 恢复
- 交易配对：Level-aware —— 卖出 level L 时精确关闭 level L 的买入记录，
  不再 FIFO，确保每笔 trade 的成本和收益与档位对应。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set

import backtrader as bt

_LEVEL_EPS = 1e-9


class GridStrategy(bt.Strategy):
    """带底仓的双向等比网格策略。每档仅持一份仓位，买→卖→买 严格循环。"""

    params = (
        ("centerPrice", 0.0),
        ("gridSpacingPct", 0.02),
        ("gridLevels", 10),
        ("shareSize", 100),
        ("cashBuffer", 0.005),
    )

    def __init__(self) -> None:
        self._tradeLog: List[dict] = []
        self._eventLog: List[dict] = []
        self._openTrades: Dict[int, dict] = {}  # level -> entry
        self._centerPrice: float = 0.0
        self._lastLevel: int = 0
        self._initialized: bool = False
        self._filledLevels: Set[int] = set()
        self._orderLevelMap: Dict[int, int] = {}

    def _clampLevel(self, rawLevel: int) -> int:
        return max(-self.p.gridLevels, min(self.p.gridLevels, rawLevel))

    def _level(self, price: float) -> int:
        """价格 → 档位。精确落在网格线上时吸附到整数，避免 floor 误差。"""
        if price <= 0 or self._centerPrice <= 0:
            return 0
        ratio = price / self._centerPrice
        if ratio <= 0:
            return 0
        raw = math.log(ratio) / math.log(1 + self.p.gridSpacingPct)
        nearest = round(raw)
        if abs(raw - nearest) < _LEVEL_EPS:
            return nearest
        return int(math.floor(raw))

    def _gridLinePrice(self, level: int) -> float:
        return self._centerPrice * (1 + self.p.gridSpacingPct) ** level

    def _canBuy(self, refPrice: float) -> bool:
        cost = refPrice * self.p.shareSize * (1 + self.p.cashBuffer)
        return self.broker.getcash() >= cost

    def _initPosition(self) -> None:
        """首根 bar 建底仓：initLevel 以下到 -gridLevels 每格买入 shareSize（Market 单）。"""
        initLevel = self._clampLevel(
            self._level(float(self.data.close[0])))
        for lvl in range(initLevel - 1, -self.p.gridLevels - 1, -1):
            px = self._gridLinePrice(lvl)
            if not self._canBuy(px):
                break
            order = self.buy(size=self.p.shareSize)
            self._filledLevels.add(lvl)
            self._orderLevelMap[order.ref] = lvl

    def next(self) -> None:
        if not self._initialized:
            self._centerPrice = (self.p.centerPrice
                                 if self.p.centerPrice > 0
                                 else float(self.data.close[0]))
            self._initPosition()
            self._initialized = True
            self._lastLevel = self._clampLevel(
                self._level(float(self.data.close[0])))
            return

        closeLevel = self._clampLevel(
            self._level(float(self.data.close[0])))

        if closeLevel < self._lastLevel:
            for lvl in range(self._lastLevel - 1, closeLevel - 1, -1):
                if lvl in self._filledLevels:
                    continue
                px = self._gridLinePrice(lvl)
                if not self._canBuy(px):
                    break
                order = self.buy(size=self.p.shareSize)
                self._filledLevels.add(lvl)
                self._orderLevelMap[order.ref] = lvl

        elif closeLevel > self._lastLevel:
            sellCount = closeLevel - self._lastLevel
            pos = self.getposition(self.data).size
            currentClose = float(self.data.close[0])
            lossThreshold = currentClose * (1 + self.p.gridSpacingPct)
            candidates = sorted(self._filledLevels, reverse=True)
            toSell: List[int] = []
            for lvl in candidates:
                if len(toSell) >= sellCount:
                    break
                entry = self._openTrades.get(lvl)
                if entry and entry["entryPrice"] > lossThreshold:
                    continue
                toSell.append(lvl)
            for lvl in toSell:
                if pos <= 0:
                    break
                size = min(self.p.shareSize, pos)
                order = self.sell(size=size)
                self._filledLevels.discard(lvl)
                self._orderLevelMap[order.ref] = lvl
                pos -= size

        self._lastLevel = closeLevel

    def notify_order(self, order: bt.Order) -> None:
        if order.status in (order.Canceled, order.Margin, order.Rejected):
            lvl = self._orderLevelMap.pop(order.ref, None)
            if lvl is not None:
                if order.isbuy():
                    self._filledLevels.discard(lvl)
                else:
                    self._filledLevels.add(lvl)
            return

        if order.status != order.Completed:
            return

        lvl: Optional[int] = self._orderLevelMap.pop(order.ref, None)
        dtExec = bt.num2date(order.executed.dt).date()
        px = float(order.executed.price)
        size = abs(int(order.executed.size))
        comm = float(order.executed.comm)
        barIdx = len(self) - 1

        if order.isbuy():
            self._openTrades[lvl] = {
                "entryDate": dtExec,
                "entryPrice": px,
                "size": size,
                "entryComm": comm,
                "entryBar": barIdx,
                "level": lvl,
            }
            self._eventLog.append({
                "date": dtExec,
                "direction": "买入",
                "price": px,
                "size": size,
                "commission": comm,
                "pnl": None,
                "pnlNet": None,
            })
            return

        entry = self._openTrades.pop(lvl, None) if lvl is not None else None
        if entry is None:
            return
        matched = min(size, entry["size"])
        if matched <= 0:
            return
        entryCost = entry["entryPrice"] * matched
        commPro = (entry["entryComm"] * matched / entry["size"]
                   if entry["size"] else 0.0)
        sellCommPro = comm * matched / size if size else 0.0
        gross = (px - entry["entryPrice"]) * matched
        net = gross - commPro - sellCommPro
        self._tradeLog.append({
            "entryDate": entry["entryDate"],
            "exitDate": dtExec,
            "entryPrice": entry["entryPrice"],
            "exitPrice": px,
            "size": matched,
            "pnl": gross,
            "pnlNet": net,
            "pnlPct": (gross / entryCost) if entryCost else 0.0,
            "barsHeld": barIdx - entry["entryBar"],
        })
        self._eventLog.append({
            "date": dtExec,
            "direction": "卖出",
            "price": px,
            "size": matched,
            "commission": sellCommPro,
            "pnl": gross,
            "pnlNet": net,
        })
        remaining = entry["size"] - matched
        if remaining > 0:
            entry["size"] = remaining
            entry["entryComm"] -= commPro
            self._openTrades[lvl] = entry
