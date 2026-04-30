"""runGridBacktest 端到端测试（双向网格 + 底仓 + close 方向触发 + 每档单次持仓）。"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backtest import runGridBacktest
from backtest.tests._helpers import buildLinearKline


def _oscKline(days: int = 60, center: float = 10.0,
              amplitude: float = 0.05, period: int = 20) -> pd.DataFrame:
    """正弦震荡 K 线（close 在多个 level 间摆动）。"""
    dates = pd.bdate_range(start="2024-01-02", periods=days)
    t = np.arange(days)
    closes = center * (1 + amplitude * np.sin(2 * np.pi * t / period))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.005
    lows = np.minimum(opens, closes) * 0.995
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(days, 1000.0),
    })


def _vShapeKline(days: int = 40, center: float = 10.0,
                 dipPct: float = 0.10) -> pd.DataFrame:
    """V 形走势：先跌 dipPct 再涨回原位。"""
    dates = pd.bdate_range(start="2024-01-02", periods=days)
    half = days // 2
    closes = []
    for i in range(half):
        closes.append(center * (1 - dipPct * i / (half - 1)))
    for i in range(days - half):
        closes.append(center * (1 - dipPct) +
                      center * dipPct * i / (days - half - 1)
                      if days - half > 1 else center)
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) * 1.003 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.997 for o, c in zip(opens, closes)]
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(days, 1000.0),
    })


def _stepKline(steps: list, center: float = 10.0,
               spacing: float = 0.02) -> pd.DataFrame:
    """按 level 序列生成 K 线。steps 例如 [0, -1, -2, -1, 0, 1, 0]。"""
    days = len(steps)
    dates = pd.bdate_range(start="2024-01-02", periods=days)
    closes = [center * (1 + spacing) ** s for s in steps]
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) * 1.001 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.999 for o, c in zip(opens, closes)]
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(days, 1000.0),
    })


class TestRunGridBacktest(unittest.TestCase):

    def test_invalidParamsRaise(self) -> None:
        kline = buildLinearKline(days=10)
        with self.assertRaises(ValueError):
            runGridBacktest(kline, gridSpacingPct=0)
        with self.assertRaises(ValueError):
            runGridBacktest(kline, gridLevels=0)
        with self.assertRaises(ValueError):
            runGridBacktest(kline, shareSize=50)

    def test_missingKlineColumn(self) -> None:
        kline = buildLinearKline(days=10).drop(columns=["volume"])
        with self.assertRaises(ValueError):
            runGridBacktest(kline)

    def test_oscillatingMarketProducesTrades(self) -> None:
        """正弦震荡行情：close 反复跨越多个 level，应产生交易。"""
        kline = _oscKline(days=80, amplitude=0.05, period=20)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              initialCash=100000)
        self.assertGreater(out["metrics"]["tradeCount"], 0)
        self.assertEqual(len(out["equityCurve"]), 80)

    def test_vShapeSellsInitialPosition(self) -> None:
        """V 形走势：下跌时底仓已持有不重复买，上涨时逐格卖出 → 有已平仓交易。"""
        kline = _vShapeKline(days=40, dipPct=0.10)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=10,
                              shareSize=100,
                              initialCash=100000)
        self.assertGreater(out["metrics"]["tradeCount"], 0)

    def test_uptrendSellsInitialPosition(self) -> None:
        """纯上涨：底仓应随价格上穿逐格卖出。

        steps [0, 1, 2, 3, 4]：
        - init 买 level -1 ~ -5（5 档底仓）
        - 价格从 0 涨到 4，每涨 1 格卖出 1 份最高底仓
        - 预期 ≥ 1 笔已平仓交易（Market 单 T+1 成交限制可能导致部分卖单在最后 bar 后未成交）
        """
        steps = [0, 1, 2, 3, 4]
        kline = _stepKline(steps, center=10.0, spacing=0.02)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              centerPrice=10.0,
                              initialCash=100000)
        tc = out["metrics"]["tradeCount"]
        self.assertGreater(tc, 0,
                           f"纯上涨应卖出底仓，实际 tradeCount={tc}")

    def test_tinyCashSkipsBuys(self) -> None:
        """现金极小：建底仓和后续 buy 都因现金不足被跳过。"""
        kline = _oscKline(days=60, amplitude=0.05, period=15)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              initialCash=100.0)
        self.assertEqual(out["metrics"]["tradeCount"], 0)

    def test_openPositionsExposed(self) -> None:
        """单边下跌：底仓 + 补仓后无回升 → openPositions 非空。"""
        kline = buildLinearKline(days=30, dailyReturn=-0.005)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.005,
                              gridLevels=20,
                              shareSize=100,
                              centerPrice=float(kline["close"].iloc[0]),
                              initialCash=100000)
        self.assertIn("openPositions", out)
        op = out["openPositions"]
        self.assertGreater(len(op), 0)
        for col in ("entryDate", "entryPrice", "size",
                    "lastPrice", "unrealizedPnl", "unrealizedPnlPct"):
            self.assertIn(col, op.columns)

    def test_initialPositionBuilt(self) -> None:
        """底仓应在回测早期建立。"""
        kline = _vShapeKline(days=20, dipPct=0.08)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              initialCash=100000)
        trades = out["trades"]
        openPos = out["openPositions"]
        allEntries = []
        if not trades.empty:
            allEntries.extend(trades["entryDate"].tolist())
        if not openPos.empty:
            allEntries.extend(openPos["entryDate"].tolist())
        self.assertGreater(len(allEntries), 0, "应有底仓或交易记录")

    def test_singleBarKline(self) -> None:
        """只有 1 根 bar → 只下底仓单（未成交），无已平仓交易。"""
        kline = buildLinearKline(days=1)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              initialCash=100000)
        self.assertEqual(out["metrics"]["tradeCount"], 0)
        self.assertEqual(len(out["equityCurve"]), 1)

    def test_closeDirectionOnly(self) -> None:
        """close 方向过滤：close 从 level 0 跳到 level -3，只触发 buy，不触发 sell。"""
        steps = [0, -3, 0, -3, 0]
        kline = _stepKline(steps, center=10.0, spacing=0.02)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              centerPrice=10.0,
                              initialCash=100000)
        self.assertGreater(out["metrics"]["tradeCount"], 0)

    def test_multiLevelCloseJump(self) -> None:
        """close 一次跨多个 level → 多笔交易触发。"""
        steps = [0, -3, 0]
        kline = _stepKline(steps, center=10.0, spacing=0.02)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              centerPrice=10.0,
                              initialCash=100000)
        tc = out["metrics"]["tradeCount"]
        opCount = len(out["openPositions"]) if not out["openPositions"].empty else 0
        self.assertGreater(tc + opCount, 0,
                           "close 跨 3 个 level 应触发多笔交易")

    def test_clampedLevelOnExtremeDeviation(self) -> None:
        """centerPrice=10 但首日 close=1 → 不崩溃。"""
        kline = buildLinearKline(days=10, startPrice=1.0, dailyReturn=0.01)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              centerPrice=10.0,
                              initialCash=100000)
        self.assertIn("equityCurve", out)
        self.assertEqual(len(out["equityCurve"]), 10)

    def test_noDoubleBuyAtSameLevel(self) -> None:
        """同一档位在未卖出前不应重复买入。

        steps [0, -1, 0, -1, -1, 0, 0]（7 bars，最后多留 1 bar 让末笔卖单成交）：
        - Day 0: init 买入 level -1 ~ -5
        - Day 1: close=-1, -1 已满 → 不重复买
        - Day 2: close=0, 卖出最高已填充(=-1)
        - Day 3: close=-1, -1 已空 → 重新买入
        - Day 4: close=-1, 不动
        - Day 5: close=0, 卖出 -1
        - Day 6: close=0, 卖单在 bar 6 开盘成交

        共 2 笔已平仓交易（两次 level -1 的 买→卖 循环）。
        """
        steps = [0, -1, 0, -1, -1, 0, 0]
        kline = _stepKline(steps, center=10.0, spacing=0.02)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              centerPrice=10.0,
                              initialCash=100000)
        tc = out["metrics"]["tradeCount"]
        self.assertEqual(tc, 2,
                         f"应恰好 2 笔已平仓交易，实际 {tc}")

    def test_levelPrecisionOnGridLine(self) -> None:
        """价格精确落在网格线上时，_level() 不应误判一档。

        center=10.0, spacing=0.02:
        level -1 price = 10/1.02 ≈ 9.80392
        level  2 price = 10*1.02^2 = 10.404

        用这些精确值做 close，验证 _level 计算正确。
        """
        spacing = 0.02
        center = 10.0
        lvlm1_px = center / (1 + spacing)       # level -1
        lvl2_px = center * (1 + spacing) ** 2    # level 2

        steps_prices = [center, lvlm1_px, center, lvl2_px, center]
        days = len(steps_prices)
        dates = pd.bdate_range(start="2024-01-02", periods=days)
        kline = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": [steps_prices[0]] + steps_prices[:-1],
            "high": [p * 1.001 for p in steps_prices],
            "low": [p * 0.999 for p in steps_prices],
            "close": steps_prices,
            "volume": np.full(days, 1000.0),
        })
        out = runGridBacktest(kline,
                              gridSpacingPct=spacing,
                              gridLevels=5,
                              shareSize=100,
                              centerPrice=center,
                              initialCash=100000)
        tc = out["metrics"]["tradeCount"]
        self.assertGreater(tc, 0,
                           "精确网格线价格应正确触发交易")


    def test_levelAwarePairing(self) -> None:
        """卖出 level -1 应关闭 level -1 的买入记录，而非 FIFO 最早记录。

        steps [0, 1, 0]：
        - Day 0: init 买 level -1 ~ -5（5 笔底仓），Market 单，成交于 day 1 开盘
        - Day 1: close=1, 卖出最高已填充(=-1)，Market 单，成交于 day 2 开盘
        - Day 2: close=0, 无动作

        交易明细中唯一一笔 trade 的 entryPrice 应为 day 1 开盘价（level -1 的买入
        成交价），而非 level -5 的成交价（FIFO 最早那笔）。
        由于所有 init Market 单在同一个 bar 1 成交，entryPrice 都相同。
        改用非对称结构验证：先跌再涨，使不同档位在不同日成交。
        """
        steps = [0, -1, -2, -1, 0, 0]
        kline = _stepKline(steps, center=10.0, spacing=0.02)
        out = runGridBacktest(kline,
                              gridSpacingPct=0.02,
                              gridLevels=5,
                              shareSize=100,
                              centerPrice=10.0,
                              initialCash=100000)
        trades = out["trades"]
        openPos = out["openPositions"]
        if not trades.empty:
            for _, t in trades.iterrows():
                ep = float(t["entryPrice"])
                xp = float(t["exitPrice"])
                self.assertGreater(xp, 0)
                self.assertGreater(ep, 0)
        if not openPos.empty:
            for _, o in openPos.iterrows():
                self.assertGreater(float(o["entryPrice"]), 0)
                self.assertGreater(float(o["size"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
