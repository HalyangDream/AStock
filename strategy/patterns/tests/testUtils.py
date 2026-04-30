"""_utils.py 纯逻辑测试：包含处理 / 摆动高低点。"""

from __future__ import annotations

import unittest

import pandas as pd

from strategy.patterns._utils import (
    findSwingHighs,
    findSwingLows,
    highestBetween,
    lowestBetween,
    mergeContaining,
    normalizeKline,
)
from strategy.patterns.tests._helpers import buildKline


class TestNormalize(unittest.TestCase):

    def test_emptyDf(self) -> None:
        df = normalizeKline(pd.DataFrame())
        self.assertTrue(df.empty)
        self.assertIn("close", df.columns)

    def test_missingColumnRaises(self) -> None:
        df = pd.DataFrame({"date": ["2024-01-01"], "open": [1], "close": [1]})
        with self.assertRaises(ValueError):
            normalizeKline(df)

    def test_sortByDate(self) -> None:
        df = buildKline([
            {"date": "2024-01-03", "open": 2, "high": 2.5, "low": 1.8, "close": 2.2, "volume": 100},
            {"date": "2024-01-02", "open": 1, "high": 1.5, "low": 0.8, "close": 1.2, "volume": 50},
        ])
        out = normalizeKline(df)
        self.assertEqual(out["date"].iloc[0].strftime("%Y-%m-%d"), "2024-01-02")
        self.assertEqual(out["date"].iloc[-1].strftime("%Y-%m-%d"), "2024-01-03")


class TestMergeContaining(unittest.TestCase):

    def test_noContainment(self) -> None:
        df = buildKline([
            {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
            {"open": 1.5, "high": 3, "low": 2, "close": 2.5, "volume": 150},
            {"open": 2.5, "high": 4, "low": 3, "close": 3.5, "volume": 120},
        ])
        out = mergeContaining(df)
        self.assertEqual(len(out), 3)

    def test_upwardContainment(self) -> None:
        """先确立向上趋势，再出现被包含 K，合并后取较高的高/低。"""
        df = buildKline([
            {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
            {"open": 1.5, "high": 3, "low": 2, "close": 2.5, "volume": 120},
            {"open": 2.5, "high": 4, "low": 3, "close": 3.5, "volume": 130},
            {"open": 3.5, "high": 3.8, "low": 3.2, "close": 3.5, "volume": 80},
        ])
        out = mergeContaining(df)
        self.assertEqual(len(out), 3)
        # 最后一根合并后: high=max(4,3.8)=4, low=max(3,3.2)=3.2
        self.assertAlmostEqual(out["high"].iloc[-1], 4.0)
        self.assertAlmostEqual(out["low"].iloc[-1], 3.2)
        self.assertEqual(out["mergedCount"].iloc[-1], 2)

    def test_downwardContainment(self) -> None:
        df = buildKline([
            {"open": 5, "high": 6, "low": 5, "close": 5.5, "volume": 100},
            {"open": 5.5, "high": 5, "low": 4, "close": 4.5, "volume": 120},
            {"open": 4.5, "high": 4, "low": 3, "close": 3.5, "volume": 130},
            {"open": 3.5, "high": 3.8, "low": 3.2, "close": 3.5, "volume": 80},
        ])
        out = mergeContaining(df)
        self.assertEqual(len(out), 3)
        # 向下趋势：high=min(4,3.8)=3.8, low=min(3,3.2)=3.0
        self.assertAlmostEqual(out["high"].iloc[-1], 3.8)
        self.assertAlmostEqual(out["low"].iloc[-1], 3.0)


class TestSwingExtrema(unittest.TestCase):

    def _makeSeries(self, lows, highs):
        return buildKline([
            {"open": h - 0.1, "high": h, "low": l,
             "close": (h + l) / 2, "volume": 100}
            for l, h in zip(lows, highs)
        ])

    def test_swingLows(self) -> None:
        # 11 根 K：在索引 5 处形成谷底
        lows = [10, 9, 8, 7, 6, 4, 6, 7, 8, 9, 10]
        highs = [l + 1 for l in lows]
        df = self._makeSeries(lows, highs)
        self.assertEqual(findSwingLows(df, window=3), [5])

    def test_swingHighs(self) -> None:
        highs = [1, 2, 3, 4, 5, 7, 5, 4, 3, 2, 1]
        lows = [h - 1 for h in highs]
        df = self._makeSeries(lows, highs)
        self.assertEqual(findSwingHighs(df, window=3), [5])

    def test_shortSeriesReturnsEmpty(self) -> None:
        df = self._makeSeries([3, 2, 1], [4, 3, 2])
        self.assertEqual(findSwingLows(df, window=5), [])

    def test_highestLowestBetween(self) -> None:
        df = self._makeSeries([5, 3, 1, 2, 4], [6, 4, 2, 3, 5])
        self.assertEqual(highestBetween(df, 0, 4), 0)
        self.assertEqual(lowestBetween(df, 0, 4), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
