"""gridOptimize / autoShareSize 测试（二维寻优 + 持有收益基准）。"""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
import pandas as pd

from backtest import gridOptimize
from backtest.gridOptimizer import (DEFAULT_LEVELS_LIST, DEFAULT_SPACINGS,
                                    autoShareSize)
from backtest.tests._helpers import buildLinearKline


def _oscKline(days: int = 60, amplitude: float = 0.05,
              period: int = 20) -> pd.DataFrame:
    dates = pd.bdate_range(start="2024-01-02", periods=days)
    t = np.arange(days)
    closes = 10.0 * (1 + amplitude * np.sin(2 * np.pi * t / period))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens,
        "high": np.maximum(opens, closes) * 1.005,
        "low": np.minimum(opens, closes) * 0.995,
        "close": closes,
        "volume": np.full(days, 1000.0),
    })


def _fakeResult(totalReturn: float = 0.0) -> dict:
    return {
        "equityCurve": pd.DataFrame(),
        "trades": pd.DataFrame(),
        "tradeEvents": pd.DataFrame(),
        "openPositions": pd.DataFrame(),
        "metrics": {"totalReturn": totalReturn, "annualReturn": 0.0,
                    "sharpe": 0.0, "maxDrawdown": 0.0,
                    "winRate": 0.0, "tradeCount": 0},
        "summary": "mock",
    }


class TestAutoShareSize(unittest.TestCase):

    def test_normalCase(self) -> None:
        # totalAmount=100000, levels=10, refPrice=10
        # perGrid = 100000 / 20 * 0.995 = 4975 → 4 手 = 400 股
        self.assertEqual(autoShareSize(100000, 10, 10.0), 400)

    def test_minimumOneHand(self) -> None:
        self.assertEqual(autoShareSize(100, 10, 10.0), 100)

    def test_invalidRaises(self) -> None:
        with self.assertRaises(ValueError):
            autoShareSize(0, 10, 10)
        with self.assertRaises(ValueError):
            autoShareSize(1000, 0, 10)
        with self.assertRaises(ValueError):
            autoShareSize(1000, 10, 0)


class TestGridOptimize(unittest.TestCase):

    def test_invalidParamsRaise(self) -> None:
        kline = buildLinearKline(days=10)
        with self.assertRaises(ValueError):
            gridOptimize(kline, totalAmount=0)
        with self.assertRaises(ValueError):
            gridOptimize(pd.DataFrame(), totalAmount=100000)
        with self.assertRaises(ValueError):
            gridOptimize(kline, totalAmount=100000, rankBy="bogus")
        with self.assertRaises(ValueError):
            gridOptimize(kline, totalAmount=100000, levelsList=[0, 5])

    def test_topSortedByRankKey(self) -> None:
        kline = _oscKline(days=60, amplitude=0.06, period=15)
        out = gridOptimize(kline, totalAmount=100000,
                           spacings=[0.01, 0.02, 0.05],
                           levelsList=[5])
        self.assertEqual(len(out["candidates"]), 3)
        self.assertEqual(len(out["top"]), 3)
        rets = [c["totalReturn"] for c in out["top"]]
        self.assertEqual(rets, sorted(rets, reverse=True))
        self.assertEqual(out["best"]["spacing"], out["top"][0]["spacing"])
        self.assertIn("equityCurve", out["best"])
        self.assertIn("trades", out["best"])
        self.assertIn("metrics", out["best"])
        self.assertIn("shareSize", out["best"])
        self.assertIn("centerPrice", out["best"])
        self.assertIn("levels", out["best"])
        self.assertIn("holdReturn", out["best"])
        self.assertIn("excessReturn", out["best"])

    def test_progressCallback(self) -> None:
        kline = _oscKline(days=40, amplitude=0.04, period=10)
        calls: list = []
        gridOptimize(kline, totalAmount=50000,
                     spacings=[0.01, 0.03, 0.05],
                     levelsList=[3, 5],
                     progressCb=lambda i, n, s: calls.append(
                         (i, n, s["spacing"], s["levels"])))
        self.assertEqual([c[0] for c in calls], [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(c[1] == 6 for c in calls))

    def test_centerPriceUsesFirstClose(self) -> None:
        kline = buildLinearKline(days=20)
        expectedFirst = float(kline.sort_values("date")["close"].iloc[0])
        with mock.patch("backtest.gridOptimizer.runGridBacktest",
                        return_value=_fakeResult()) as m:
            out = gridOptimize(kline, totalAmount=100000,
                               spacings=[0.01, 0.02],
                               levelsList=[5])
        for call in m.call_args_list:
            self.assertAlmostEqual(call.kwargs["centerPrice"],
                                   expectedFirst, places=6)
        self.assertAlmostEqual(out["best"]["centerPrice"],
                               expectedFirst, places=6)

    def test_defaultGridIs66(self) -> None:
        """默认遍历 11 spacings × 6 levels = 66 组合。"""
        kline = buildLinearKline(days=10)
        with mock.patch("backtest.gridOptimizer.runGridBacktest",
                        return_value=_fakeResult()):
            out = gridOptimize(kline, totalAmount=100000)
        expected = len(DEFAULT_SPACINGS) * len(DEFAULT_LEVELS_LIST)
        self.assertEqual(len(out["candidates"]), expected)
        self.assertEqual(expected, 66)

    def test_levelsTraversed(self) -> None:
        """每个 spacing 都应遍历完整 levelsList。"""
        kline = buildLinearKline(days=10)
        with mock.patch("backtest.gridOptimizer.runGridBacktest",
                        return_value=_fakeResult()) as m:
            gridOptimize(kline, totalAmount=100000,
                         spacings=[0.02], levelsList=[3, 5, 8])
        seenLevels = sorted({c.kwargs["gridLevels"]
                             for c in m.call_args_list})
        self.assertEqual(seenLevels, [3, 5, 8])

    def test_holdReturnLinearUp(self) -> None:
        """线性上涨：holdReturn ≈ (lastClose / firstClose - 1)。"""
        kline = buildLinearKline(days=20, dailyReturn=0.005)
        sortedKline = kline.sort_values("date")
        firstClose = float(sortedKline["close"].iloc[0])
        lastClose = float(sortedKline["close"].iloc[-1])
        with mock.patch("backtest.gridOptimizer.runGridBacktest",
                        return_value=_fakeResult(totalReturn=0.0)):
            out = gridOptimize(kline, totalAmount=100000,
                               spacings=[0.02], levelsList=[5])
        priceReturn = lastClose / firstClose - 1
        self.assertAlmostEqual(out["candidates"][0]["holdReturn"],
                               priceReturn, delta=0.01)

    def test_excessReturnConsistent(self) -> None:
        """excessReturn = totalReturn - holdReturn。"""
        kline = buildLinearKline(days=15)
        with mock.patch("backtest.gridOptimizer.runGridBacktest",
                        return_value=_fakeResult(totalReturn=0.05)):
            out = gridOptimize(kline, totalAmount=100000,
                               spacings=[0.02], levelsList=[5])
        for row in out["candidates"]:
            self.assertAlmostEqual(
                row["excessReturn"],
                row["totalReturn"] - row["holdReturn"], places=8)
        self.assertAlmostEqual(
            out["best"]["excessReturn"],
            0.05 - out["best"]["holdReturn"], places=8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
