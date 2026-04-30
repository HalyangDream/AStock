"""adapters 模块单测。"""

from __future__ import annotations

import unittest

import pandas as pd

from backtest.adapters import fromBottomFractal, fromHeadShoulderBottom
from backtest.tests._helpers import buildLinearKline


class TestFromBottomFractal(unittest.TestCase):

    def setUp(self) -> None:
        self.kline = buildLinearKline(days=30)

    def test_emptyInput(self) -> None:
        out = fromBottomFractal(pd.DataFrame(), self.kline)
        self.assertTrue(out.empty)
        self.assertEqual(list(out.columns), ["date", "signal"])

    def test_singleSignalProducesBuyAndSell(self) -> None:
        bottoms = pd.DataFrame([{
            "centerDate": pd.Timestamp(self.kline["date"].iloc[5]),
            "centerLow": 9.0, "centerHigh": 10.0,
            "grade": "validTrend",
        }])
        out = fromBottomFractal(bottoms, self.kline, holdDays=10)
        self.assertEqual(len(out), 2)
        self.assertEqual(out["signal"].tolist(), ["buy", "sell"])
        # buy 日 = kline 第 5 行
        self.assertEqual(out["date"].iloc[0],
                         pd.Timestamp(self.kline["date"].iloc[5]))
        # sell 日 = 5 + 10 = 15
        self.assertEqual(out["date"].iloc[1],
                         pd.Timestamp(self.kline["date"].iloc[15]))

    def test_holdExceedsKlineClampsToLast(self) -> None:
        bottoms = pd.DataFrame([{
            "centerDate": pd.Timestamp(self.kline["date"].iloc[25]),
            "centerLow": 9.0, "centerHigh": 10.0, "grade": "weak",
        }])
        out = fromBottomFractal(bottoms, self.kline, holdDays=100)
        self.assertEqual(out["date"].iloc[1],
                         pd.Timestamp(self.kline["date"].iloc[-1]))


class TestFromHeadShoulderBottom(unittest.TestCase):

    def setUp(self) -> None:
        self.kline = buildLinearKline(days=30)

    def test_skipsRowsWithoutBreakout(self) -> None:
        df = pd.DataFrame([
            {"breakoutDate": None, "score": 0.5},
            {"breakoutDate": pd.NaT, "score": 0.7},
        ])
        out = fromHeadShoulderBottom(df, self.kline)
        self.assertTrue(out.empty)

    def test_breakoutToBuySell(self) -> None:
        df = pd.DataFrame([{
            "breakoutDate": pd.Timestamp(self.kline["date"].iloc[10]),
            "score": 0.7,
        }])
        out = fromHeadShoulderBottom(df, self.kline, holdDays=5)
        self.assertEqual(len(out), 2)
        self.assertEqual(out["signal"].tolist(), ["buy", "sell"])
        self.assertEqual(out["date"].iloc[0],
                         pd.Timestamp(self.kline["date"].iloc[10]))
        self.assertEqual(out["date"].iloc[1],
                         pd.Timestamp(self.kline["date"].iloc[15]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
