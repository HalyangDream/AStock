"""gridOptimize / autoShareSize 测试。"""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
import pandas as pd

from backtest import gridOptimize
from backtest.gridOptimizer import autoShareSize
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


class TestAutoShareSize(unittest.TestCase):

    def test_normalCase(self) -> None:
        # totalAmount=100000, levels=10, refPrice=10
        # perGrid = 100000 / 20 * 0.995 = 4975 → 4 手 = 400 股
        self.assertEqual(autoShareSize(100000, 10, 10.0), 400)

    def test_minimumOneHand(self) -> None:
        # 资金过小，按下取整为 0，需要兜底为 100 股
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
            gridOptimize(kline, levels=0, totalAmount=100000)
        with self.assertRaises(ValueError):
            gridOptimize(kline, levels=10, totalAmount=0)
        with self.assertRaises(ValueError):
            gridOptimize(pd.DataFrame(), levels=10, totalAmount=100000)
        with self.assertRaises(ValueError):
            gridOptimize(kline, levels=10, totalAmount=100000,
                         rankBy="bogus")

    def test_topSortedByRankKey(self) -> None:
        kline = _oscKline(days=60, amplitude=0.06, period=15)
        out = gridOptimize(kline, levels=5, totalAmount=100000,
                           spacings=[0.01, 0.02, 0.05])
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

    def test_progressCallback(self) -> None:
        kline = _oscKline(days=40, amplitude=0.04, period=10)
        calls: list = []
        gridOptimize(kline, levels=3, totalAmount=50000,
                     spacings=[0.01, 0.03, 0.05],
                     progressCb=lambda i, n, s: calls.append((i, n, s["spacing"])))
        self.assertEqual([c[0] for c in calls], [1, 2, 3])
        self.assertTrue(all(c[1] == 3 for c in calls))

    def test_centerPriceUsesFirstClose(self) -> None:
        """中心价自动取首日 close（避免未来函数偏差）。"""
        kline = buildLinearKline(days=20)
        expectedFirst = float(kline.sort_values("date")["close"].iloc[0])
        fake = {
            "equityCurve": pd.DataFrame(),
            "trades": pd.DataFrame(),
            "openPositions": pd.DataFrame(),
            "metrics": {"totalReturn": 0.0, "annualReturn": 0.0,
                        "sharpe": 0.0, "maxDrawdown": 0.0,
                        "winRate": 0.0, "tradeCount": 0},
            "summary": "mock",
        }
        with mock.patch("backtest.gridOptimizer.runGridBacktest",
                        return_value=fake) as m:
            out = gridOptimize(kline, levels=5, totalAmount=100000,
                               spacings=[0.01, 0.02])
        for call in m.call_args_list:
            self.assertAlmostEqual(call.kwargs["centerPrice"],
                                   expectedFirst, places=6)
        self.assertAlmostEqual(out["best"]["centerPrice"],
                               expectedFirst, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
