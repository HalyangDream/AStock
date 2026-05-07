"""runGridBacktest 端到端测试（静态网格策略 v7）。"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backtest import runGridBacktest
from backtest.tests._helpers import buildLinearKline


# ---- 辅助 K 线生成 ----

def _oscKline(days: int = 60, center: float = 10.0,
              amplitude: float = 0.05, period: int = 20) -> pd.DataFrame:
    """正弦震荡 K 线。"""
    dates = pd.bdate_range(start="2024-01-02", periods=days)
    t = np.arange(days)
    closes = center * (1 + amplitude * np.sin(2 * np.pi * t / period))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.005
    lows = np.minimum(opens, closes) * 0.995
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": np.full(days, 1000.0),
    })


def _vShapeKline(days: int = 40, center: float = 10.0,
                 dipPct: float = 0.10) -> pd.DataFrame:
    """V 形走势：先跌再涨回。"""
    dates = pd.bdate_range(start="2024-01-02", periods=days)
    half = days // 2
    closes = []
    for i in range(half):
        closes.append(center * (1 - dipPct * i / (half - 1)))
    for i in range(days - half):
        pct = dipPct * i / (days - half - 1) if days - half > 1 else 0
        closes.append(center * (1 - dipPct) + center * pct)
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) * 1.003 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.997 for o, c in zip(opens, closes)]
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": np.full(days, 1000.0),
    })


def _steepDeclineKline(days: int = 60, startPrice: float = 10.0,
                       dailyReturn: float = -0.03) -> pd.DataFrame:
    """持续下跌 K 线。"""
    dates = pd.bdate_range(start="2024-01-02", periods=days)
    closes = [startPrice * ((1 + dailyReturn) ** i) for i in range(days)]
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) * 1.0005 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.9995 for o, c in zip(opens, closes)]
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens, "high": highs, "low": lows,
        "close": np.array(closes), "volume": np.full(days, 1000.0),
    })


class TestBasicParams(unittest.TestCase):
    """参数校验。"""

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


class TestStaticGridLines(unittest.TestCase):
    """静态网格线核心行为。"""

    def test_gridLinesAreGeometric(self) -> None:
        """网格线应是几何级数：gridLinePrice(n) = basePrice × (1+s)^n。"""
        from backtest._gridStrategy import GridStrategy
        strat = GridStrategy.__new__(GridStrategy)
        strat._centerPrice = 10.0
        strat.p = type("P", (), {"gridSpacingPct": 0.04})()

        self.assertAlmostEqual(strat._gridLinePrice(0), 10.0)
        self.assertAlmostEqual(strat._gridLinePrice(1), 10.4)
        self.assertAlmostEqual(strat._gridLinePrice(2), 10.816)
        self.assertAlmostEqual(strat._gridLinePrice(-1), 10.0 / 1.04)
        self.assertAlmostEqual(strat._gridLinePrice(-2), 10.0 / 1.04 ** 2)

    def test_initOnlyBuysLevel0(self) -> None:
        """建仓：首日仅在 Level 0（close 价）买入 1 份。"""
        kline = buildLinearKline(days=3, startPrice=10.0)
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        events = out["tradeEvents"]
        firstDate = events["date"].min()
        initBuys = events[(events["date"] == firstDate) &
                          (events["direction"] == "买入")]
        self.assertEqual(len(initBuys), 1,
                         "建仓应只有 1 笔买入（Level 0）")

    def test_gridLinesDoNotMove(self) -> None:
        """交易后网格线不移动：卖出价应固定等于对应 Level+1 网格线价。"""
        kline = _oscKline(days=100, center=10.0, amplitude=0.06, period=20)
        out = runGridBacktest(kline, gridSpacingPct=0.03,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        trades = out["trades"]
        if trades.empty:
            return
        basePrice = float(kline.sort_values("date")["close"].iloc[0])
        spacing = 0.03
        validPrices = {
            basePrice * (1 + spacing) ** n
            for n in range(-5, 7)
        }
        for _, row in trades.iterrows():
            exitP = float(row["exitPrice"])
            matched = any(abs(exitP - vp) < 1e-6 for vp in validPrices)
            self.assertTrue(
                matched,
                f"卖出价 {exitP:.6f} 不在固定网格线集合中")


class TestBuySellPairing(unittest.TestCase):
    """买 Level L → 卖 Level L+1 配对逻辑。"""

    def test_closedTradeEarnsOneSpacing(self) -> None:
        """每笔闭合交易 gross = gridLinePrice(L+1) - gridLinePrice(L)。"""
        kline = _vShapeKline(days=60, center=10.0, dipPct=0.12)
        spacing = 0.03
        out = runGridBacktest(kline, gridSpacingPct=spacing,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        trades = out["trades"]
        if trades.empty:
            self.skipTest("V 形未产生闭合交易")
        for _, row in trades.iterrows():
            entry = float(row["entryPrice"])
            exit_ = float(row["exitPrice"])
            expectedExit = entry * (1 + spacing)
            self.assertAlmostEqual(
                exit_, expectedExit, places=4,
                msg=f"卖出价 {exit_:.4f} 应 ≈ 买入价 {entry:.4f} × {1+spacing}")

    def test_closedTradeNetPositive(self) -> None:
        """spacing=5%（远大于费率）→ 每笔闭合交易 pnlNet > 0。"""
        kline = _vShapeKline(days=60, center=10.0, dipPct=0.20)
        out = runGridBacktest(kline, gridSpacingPct=0.05,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        trades = out["trades"]
        if trades.empty:
            self.skipTest("V 形未产生闭合交易")
        for _, row in trades.iterrows():
            self.assertGreater(
                float(row["pnlNet"]), 0,
                f"entry={row['entryPrice']:.4f} exit={row['exitPrice']:.4f} "
                f"pnlNet={row['pnlNet']:.4f} 应 > 0")


class TestCascadeTrades(unittest.TestCase):
    """单日跨多级联交易。"""

    def test_cascadeBuysOnBigDrop(self) -> None:
        """单日大跌：low 跨多条网格线 → 多笔买入。"""
        days = 3
        dates = pd.bdate_range(start="2024-01-02", periods=days)
        center = 10.0
        closes = [center, center * 0.90, center * 0.90]
        opens = [center, center, center * 0.90]
        highs = [center * 1.001, center * 1.001, center * 0.91]
        lows = [center * 0.999, center * 0.89, center * 0.89]
        kline = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": opens, "high": highs, "low": lows,
            "close": closes, "volume": [1000.0] * days,
        })
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        events = out["tradeEvents"]
        day2_buys = events[(events["direction"] == "买入") &
                           (events["date"] == pd.Timestamp("2024-01-03"))]
        self.assertGreater(len(day2_buys), 1,
                           "10% 跌幅 + 2% 间距应触发多笔级联买入")

    def test_cascadeSellsOnBigRise(self) -> None:
        """先跌买满多级，再大涨 → 多笔级联卖出。"""
        days = 4
        dates = pd.bdate_range(start="2024-01-02", periods=days)
        center = 10.0
        closes = [center, center * 0.88, center * 0.88, center * 1.02]
        opens = [center, center, center * 0.88, center * 0.88]
        highs = [center * 1.001, center * 1.001,
                 center * 0.89, center * 1.10]
        lows = [center * 0.999, center * 0.87,
                center * 0.87, center * 0.88]
        kline = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": opens, "high": highs, "low": lows,
            "close": closes, "volume": [1000.0] * days,
        })
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        events = out["tradeEvents"]
        day4_sells = events[(events["direction"] == "卖出") &
                            (events["date"] == pd.Timestamp("2024-01-05"))]
        self.assertGreater(len(day4_sells), 1,
                           "多级已填充 + 大涨应触发多笔级联卖出")


class TestPositionLimits(unittest.TestCase):
    """持仓上限。"""

    def test_maxFilledLevels(self) -> None:
        """填充 Levels 不超过 2 × gridLevels + 1（-5 到 +4 + Level 0）。"""
        kline = _steepDeclineKline(days=60, startPrice=10.0,
                                   dailyReturn=-0.03)
        gridLevels = 3
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=gridLevels, shareSize=100,
                              initialCash=100000)
        events = out["tradeEvents"]
        buyCount = int((events["direction"] == "买入").sum()) if not events.empty else 0
        sellCount = int((events["direction"] == "卖出").sum()) if not events.empty else 0
        maxHeld = buyCount - sellCount
        self.assertLessEqual(maxHeld, 2 * gridLevels + 1,
                             f"最大持仓 {maxHeld} 不应超过总格数")


class TestTradeQuality(unittest.TestCase):
    """交易质量：整体盈利、执行价。"""

    def test_vShapeOverallProfitable(self) -> None:
        """V 形走势整体应盈利（spacing=5% 远大于费率）。"""
        kline = _vShapeKline(days=80, center=10.0, dipPct=0.15)
        out = runGridBacktest(kline, gridSpacingPct=0.05,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        totalReturn = out["metrics"]["totalReturn"]
        self.assertGreater(totalReturn, -0.01,
                           f"V 形总收益不应大幅亏损，实际 {totalReturn:.4%}")

    def test_oscillationProducesTrades(self) -> None:
        """正弦震荡应产生买卖交易。"""
        kline = _oscKline(days=100, center=10.0, amplitude=0.06, period=20)
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        self.assertGreater(out["metrics"]["tradeCount"], 0,
                           "震荡行情应有闭合交易")

    def test_singleBarNoTrade(self) -> None:
        """只有 1 根 bar → 只建底仓，0 笔闭合交易。"""
        kline = buildLinearKline(days=1)
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        self.assertEqual(out["metrics"]["tradeCount"], 0)

    def test_tinyCashSkipsBuys(self) -> None:
        """现金极小：建仓和后续买入均因资金不足被跳过。"""
        kline = _oscKline(days=60, amplitude=0.05)
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=5, shareSize=100,
                              initialCash=100.0)
        self.assertEqual(out["metrics"]["tradeCount"], 0)

    def test_noRoundTripInSameBar(self) -> None:
        """同一 bar 内同一 Level 不应买了又卖（changedLevels 保护）。"""
        kline = _oscKline(days=80, center=10.0, amplitude=0.08, period=15)
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        trades = out["trades"]
        if trades.empty:
            return
        for _, row in trades.iterrows():
            self.assertGreater(
                int(row["barsHeld"]), 0,
                "闭合交易 barsHeld 应 > 0（不能同 bar round-trip）")

    def test_openPositionsOnDecline(self) -> None:
        """持续下跌应有 per-level 未平仓持仓。"""
        kline = _steepDeclineKline(days=30, startPrice=10.0,
                                   dailyReturn=-0.03)
        out = runGridBacktest(kline, gridSpacingPct=0.02,
                              gridLevels=5, shareSize=100,
                              initialCash=100000)
        op = out["openPositions"]
        self.assertGreater(len(op), 0, "持续下跌应有未平仓持仓")
        self.assertIn("entryPrice", op.columns)
        self.assertIn("unrealizedPnl", op.columns)


if __name__ == "__main__":
    unittest.main(verbosity=2)
