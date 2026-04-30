"""内部 bt.Strategy：信号驱动 + 自定义佣金（含印花税）。

撮合规则：
- next() 在每根 bar 收盘后触发；buy() / close() 默认作为 Market 单
  → 在下一根 bar 开盘成交（T+1 开盘）。
- buy 时按现金估算可买股数，按 A 股 100 股最小单位向下取整。
- sell 信号统一用 close() 平掉全部持仓。
"""

from __future__ import annotations

from typing import Dict, List

import backtrader as bt


class StampTaxCommission(bt.CommInfoBase):
    """A 股佣金：买卖双边按 commission，sell 额外加 stampTax。"""

    params = (
        ("commission", 0.0003),
        ("stampTax", 0.001),
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
        ("percabs", True),
    )

    def _getcommission(self, size, price, pseudoexec):
        notional = abs(size) * price
        rate = self.p.commission
        if size < 0:  # sell
            rate += self.p.stampTax
        return notional * rate


class SignalStrategy(bt.Strategy):
    """信号驱动策略。

    params:
        signalMap: Dict[datetime.date, str]   # date -> 'buy'/'sell'
        sizing: str                           # 当前仅支持 'all'
        cashBuffer: float                     # 买入时预留比例（覆盖佣金/滑点）
    """

    params = (
        ("signalMap", None),
        ("sizing", "all"),
        ("cashBuffer", 0.005),
    )

    def __init__(self) -> None:
        self._tradeLog: List[dict] = []
        self._openTrade: Dict | None = None

    def _calcSize(self, priceEst: float) -> int:
        cash = self.broker.getcash()
        rawSize = int(cash * (1 - self.p.cashBuffer) // priceEst)
        return (rawSize // 100) * 100  # A 股 100 股一手

    def next(self) -> None:
        if self.p.signalMap is None:
            return
        currentDate = self.data.datetime.date(0)
        sig = self.p.signalMap.get(currentDate)
        if sig is None:
            return
        pos = self.getposition(self.data).size
        if sig == "buy" and pos == 0:
            size = self._calcSize(self.data.close[0])
            if size > 0:
                self.buy(size=size)
        elif sig == "sell" and pos > 0:
            self.close()

    def notify_order(self, order: bt.Order) -> None:
        if order.status != order.Completed:
            return
        dtExec = bt.num2date(order.executed.dt).date()
        px = float(order.executed.price)
        size = abs(int(order.executed.size))
        comm = float(order.executed.comm)
        barIdx = len(self) - 1

        if order.isbuy():
            self._openTrade = {
                "entryDate": dtExec,
                "entryPrice": px,
                "size": size,
                "entryComm": comm,
                "entryBar": barIdx,
            }
        elif order.issell() and self._openTrade is not None:
            entry = self._openTrade
            gross = (px - entry["entryPrice"]) * entry["size"]
            net = gross - entry["entryComm"] - comm
            self._tradeLog.append({
                "entryDate": entry["entryDate"],
                "exitDate": dtExec,
                "entryPrice": entry["entryPrice"],
                "exitPrice": px,
                "size": entry["size"],
                "pnl": gross,
                "pnlNet": net,
                "pnlPct": gross / (entry["entryPrice"] * entry["size"])
                          if entry["size"] else 0.0,
                "barsHeld": barIdx - entry["entryBar"],
            })
            self._openTrade = None


class EquityAnalyzer(bt.Analyzer):
    """每根 bar 记录账户净值与现金。"""

    def start(self) -> None:
        self.records: List[dict] = []

    def next(self) -> None:
        self.records.append({
            "date": self.strategy.datetime.date(0),
            "value": float(self.strategy.broker.getvalue()),
            "cash": float(self.strategy.broker.getcash()),
        })

    def get_analysis(self) -> List[dict]:
        return self.records
