"""底分型 / 顶分型识别用例。"""

from __future__ import annotations

import unittest

import pandas as pd

from strategy.patterns.fractal import findBottomFractal, findTopFractal
from strategy.patterns.tests._helpers import buildKline


def _row(open_, high, low, close, vol):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": vol}


class TestBottomFractal(unittest.TestCase):

    def test_basicBottom(self) -> None:
        """7 根 K：索引 2 处形成明显底分型，之后价格走高且不放量。"""
        rows = [
            _row(11, 12.0, 10.5, 11.5, 100),
            _row(11, 11.5, 10.0, 10.5, 110),
            _row(10, 10.0,  9.0,  9.5, 120),   # 底分型中心 idx=2
            _row(9,  11.5,  9.2, 11.0, 130),
            _row(11, 12.0, 10.5, 11.8, 140),
            _row(12, 12.5, 11.0, 12.2, 150),
            _row(12, 13.0, 11.5, 12.8, 160),
        ]
        df = buildKline(rows)
        out = findBottomFractal(df, merge=False, lookAhead=4,
                                upThreshold=0.03, lookBack=3,
                                volumeMultiplier=2.0, minGrade="weak")
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out["centerLow"].iloc[0], 9.0)
        self.assertTrue(out["trendOk"].iloc[0])
        self.assertFalse(out["volumeOk"].iloc[0])
        self.assertEqual(out["grade"].iloc[0], "validTrend")

    def test_strongGradeWithVolume(self) -> None:
        """放量底分型：volume 在中心附近显著高于均量。"""
        rows = [
            _row(11, 12.0, 10.5, 11.5, 100),
            _row(11, 11.5, 10.0, 10.5, 110),
            _row(10, 10.0,  9.0,  9.5, 500),   # 放量
            _row(9,  11.5,  9.2, 11.0, 130),
            _row(11, 12.0, 10.5, 11.8, 140),
            _row(12, 12.5, 11.0, 12.2, 150),
            _row(12, 13.0, 11.5, 12.8, 160),
        ]
        df = buildKline(rows)
        out = findBottomFractal(df, merge=False, lookAhead=4,
                                upThreshold=0.03, lookBack=3,
                                volumeMultiplier=2.0, minGrade="weak")
        self.assertEqual(out["grade"].iloc[0], "strong")
        self.assertTrue(out["volumeOk"].iloc[0])
        self.assertTrue(out["trendOk"].iloc[0])

    def test_filterByMinGrade(self) -> None:
        """minGrade=strong 时应过滤掉仅 weak/validTrend 的分型。"""
        rows = [
            _row(11, 12.0, 10.5, 11.5, 100),
            _row(11, 11.5, 10.0, 10.5, 110),
            _row(10, 10.0,  9.0,  9.5, 120),   # 普通底分型
            _row(9,   9.8,  9.2,  9.4, 115),
            _row(9.4, 9.5,  9.1,  9.3, 118),   # 后续不走高，trendOk 不成立
        ]
        df = buildKline(rows)
        out = findBottomFractal(df, merge=False, lookAhead=2,
                                upThreshold=0.03, lookBack=3,
                                volumeMultiplier=2.0, minGrade="strong")
        self.assertTrue(out.empty)

    def test_noBottomReturnsEmpty(self) -> None:
        rows = [
            _row(1, 2, 1, 1.5, 100),
            _row(2, 3, 2, 2.5, 100),
            _row(3, 4, 3, 3.5, 100),
        ]
        out = findBottomFractal(buildKline(rows), merge=False)
        self.assertTrue(out.empty)

    def test_invalidMinGrade(self) -> None:
        rows = [_row(1, 2, 1, 1.5, 100)] * 5
        with self.assertRaises(ValueError):
            findBottomFractal(buildKline(rows), minGrade="bad")


class TestTopFractal(unittest.TestCase):

    def test_basicTop(self) -> None:
        """对称用例：索引 2 处为顶分型，之后下跌。"""
        rows = [
            _row(10, 10.5,  9.5, 10.2, 100),
            _row(10, 11.0, 10.0, 10.8, 110),
            _row(10, 12.0, 11.0, 11.5, 500),  # 顶分型中心：high 最高、low 最高
            _row(11, 11.5, 10.2, 10.5, 130),
            _row(10, 10.5,  9.8, 10.0, 140),
            _row(10, 10.0,  9.5,  9.7, 150),
            _row(9.5, 9.8,  9.0,  9.2, 160),
        ]
        df = buildKline(rows)
        out = findTopFractal(df, merge=False, lookAhead=4,
                             upThreshold=0.03, lookBack=3,
                             volumeMultiplier=2.0, minGrade="weak")
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out["centerHigh"].iloc[0], 12.0)
        self.assertTrue(out["trendOk"].iloc[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
