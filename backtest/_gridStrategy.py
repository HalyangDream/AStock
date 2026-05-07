"""静态网格策略（手动撮合）。

核心机制：
- 基准价 = 首日 close（或外部传入），全程固定
- 网格线：gridLinePrice(n) = basePrice × (1 + spacing)^n，n ∈ [-gridLevels, +gridLevels]
- 建仓：首根 bar 以 close 买入 1 份 @ Level 0
- 买入：Level L（L ≤ 0）未填充 且 low ≤ gridLinePrice(L) → 以 gridLinePrice(L) 成交
- 正档位（+1 ~ +gridLevels）仅作为卖出目标价，不可买入
- 卖出：Level L 已填充 且 high ≥ gridLinePrice(L+1) → 以 gridLinePrice(L+1) 成交
- 每笔闭合利润 = gridLinePrice(L+1) - gridLinePrice(L) - 手续费
- 同一 bar 内同一 Level 最多变化一次状态（防止 round-trip）
- 佣金：买入 = price × size × commission，卖出 = price × size × (commission + stampTax)
- backtrader 仅驱动 bar 循环，不使用其 broker / order 系统
"""

from __future__ import annotations

from typing import Dict, List, Set

import backtrader as bt


class GridStrategy(bt.Strategy):
    """静态网格策略。固定网格线，买 Level L → 卖 Level L+1，赚一格间距。"""

    params = (
        ("centerPrice", 0.0),
        ("gridSpacingPct", 0.02),
        ("gridLevels", 5),
        ("shareSize", 100),
        ("commission", 0.0003),
        ("stampTax", 0.001),
        ("initialCash", 100000.0),
    )

    def __init__(self) -> None:
        self._tradeLog: List[dict] = []
        self._eventLog: List[dict] = []
        self._openTrades: Dict[int, dict] = {}
        self._equityRecords: List[dict] = []

        self._centerPrice: float = 0.0
        self._filledLevels: Set[int] = set()
        self._cash: float = 0.0
        self._initialized: bool = False
        self._barIndex: int = 0

    # ------ 网格线 ------

    def _gridLinePrice(self, level: int) -> float:
        return self._centerPrice * (1 + self.p.gridSpacingPct) ** level

    # ------ 费用 ------

    def _buyComm(self, price: float, size: int) -> float:
        return price * size * self.p.commission

    def _sellComm(self, price: float, size: int) -> float:
        return price * size * (self.p.commission + self.p.stampTax)

    def _canBuy(self, price: float) -> bool:
        cost = price * self.p.shareSize + self._buyComm(price, self.p.shareSize)
        return self._cash >= cost

    # ------ 手动撮合 ------

    def _executeBuy(self, level: int, price: float,
                    dt: object, barIdx: int) -> bool:
        size = self.p.shareSize
        comm = self._buyComm(price, size)
        cost = price * size + comm
        if self._cash < cost:
            return False
        self._cash -= cost
        self._filledLevels.add(level)
        self._openTrades[level] = {
            "entryDate": dt,
            "entryPrice": price,
            "size": size,
            "entryComm": comm,
            "entryBar": barIdx,
            "level": level,
        }
        self._eventLog.append({
            "date": dt, "direction": "买入", "price": price,
            "size": size, "commission": comm,
            "pnl": None, "pnlNet": None,
        })
        return True

    def _executeSell(self, level: int, price: float,
                     dt: object, barIdx: int) -> bool:
        entry = self._openTrades.pop(level, None)
        if entry is None:
            return False
        size = entry["size"]
        comm = self._sellComm(price, size)
        self._cash += price * size - comm
        self._filledLevels.discard(level)

        gross = (price - entry["entryPrice"]) * size
        net = gross - entry["entryComm"] - comm
        entryCost = entry["entryPrice"] * size
        self._tradeLog.append({
            "entryDate": entry["entryDate"],
            "exitDate": dt,
            "entryPrice": entry["entryPrice"],
            "exitPrice": price,
            "size": size,
            "pnl": gross,
            "pnlNet": net,
            "pnlPct": (gross / entryCost) if entryCost > 0 else 0.0,
            "barsHeld": barIdx - entry["entryBar"],
        })
        self._eventLog.append({
            "date": dt, "direction": "卖出", "price": price,
            "size": size, "commission": comm,
            "pnl": gross, "pnlNet": net,
        })
        return True

    # ------ 权益记录 ------

    def _recordEquity(self, dt: object, close: float) -> None:
        posValue = sum(
            close * e["size"] for e in self._openTrades.values())
        self._equityRecords.append({
            "date": dt,
            "value": self._cash + posValue,
            "cash": self._cash,
        })

    # ------ bar 循环 ------

    def next(self) -> None:
        dt = self.data.datetime.date(0)
        close = float(self.data.close[0])
        low = float(self.data.low[0])
        high = float(self.data.high[0])

        if not self._initialized:
            self._cash = self.p.initialCash
            self._centerPrice = (self.p.centerPrice
                                 if self.p.centerPrice > 0
                                 else close)
            if self._canBuy(close):
                self._executeBuy(0, close, dt, self._barIndex)
            self._initialized = True
            self._recordEquity(dt, close)
            self._barIndex += 1
            return

        changedLevels: Set[int] = set()
        gl = self.p.gridLevels

        # 卖出：已填充的 Level L，high ≥ gridLinePrice(L+1) → 卖 @ gridLinePrice(L+1)
        for lvl in sorted(list(self._filledLevels), reverse=True):
            sellPrice = self._gridLinePrice(lvl + 1)
            if high >= sellPrice:
                if self._executeSell(lvl, sellPrice, dt, self._barIndex):
                    changedLevels.add(lvl)

        # 买入：未填充的 Level L（L ≤ 0，从高到低扫），low ≤ gridLinePrice(L) → 买 @ gridLinePrice(L)
        for lvl in range(0, -gl - 1, -1):
            if lvl in self._filledLevels:
                continue
            if lvl in changedLevels:
                continue
            buyPrice = self._gridLinePrice(lvl)
            if low <= buyPrice:
                if not self._canBuy(buyPrice):
                    continue
                self._executeBuy(lvl, buyPrice, dt, self._barIndex)

        self._recordEquity(dt, close)
        self._barIndex += 1
