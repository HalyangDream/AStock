"""底分型 / 顶分型识别用例。"""

from __future__ import annotations

import unittest

import pandas as pd

from strategy.patterns.fractal import (
    findBottomFractal, findTopFractal, isCurrentBottomFractal,
)
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


def _baseKline(n=130, baseClose=10.0, baseVol=1000.0):
    """构造 n 根平稳 K 线（close=baseClose, vol=baseVol）。"""
    dates = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({
        "date": dates,
        "open": [baseClose] * n,
        "high": [baseClose + 0.5] * n,
        "low": [baseClose - 0.5] * n,
        "close": [baseClose] * n,
        "volume": [baseVol] * n,
    })


class TestCurrentBottomFractal(unittest.TestCase):
    """isCurrentBottomFractal 新定义测试（课程体系三种形态 + 双前提）。"""

    # ── TP-1: 阳包阴 + 双前提满足 → pattern="engulfing" ──────────────
    def test_tp1_engulfing(self) -> None:
        df = _baseKline()
        # 确保 index[-3].high 足够高，使三过一不匹配
        df.loc[df.index[-3], "high"] = 12.0
        # Day1 阴线: close < open
        df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
            11.0, 11.5, 9.0, 9.5, 2000.0,
        ]
        # Day2 阳线: close > open, 实体包住 Day1
        df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
            9.0, 12.0, 8.8, 11.5, 2000.0,
        ]
        result = isCurrentBottomFractal(df)
        self.assertIsNotNone(result)
        self.assertEqual(result["pattern"], "engulfing")
        self.assertEqual(result["patternLabel"], "阳包阴")

    # ── TP-2: 十字星底 → pattern="doji" ──────────────────────────────
    def test_tp2_doji(self) -> None:
        df = _baseKline()
        # 十字星: 实体极小, 下影线长
        df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
            10.5, 10.6, 9.0, 10.5, 2000.0,
        ]
        result = isCurrentBottomFractal(df)
        self.assertIsNotNone(result)
        self.assertEqual(result["pattern"], "doji")
        self.assertEqual(result["patternLabel"], "十字星底")

    # ── TP-3: 三过一 → pattern="threeOverOne" ────────────────────────
    def test_tp3_threeOverOne(self) -> None:
        df = _baseKline()
        # Day1: high=10.5 (base)
        df.loc[df.index[-3], ["open", "high", "low", "close", "volume"]] = [
            10.0, 10.5, 9.5, 10.0, 2000.0,
        ]
        # Day2: low <= Day1.low (回调)
        df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
            10.0, 10.2, 9.2, 9.5, 2000.0,
        ]
        # Day3: close > Day1.high
        df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
            9.8, 11.5, 9.6, 11.0, 2000.0,
        ]
        result = isCurrentBottomFractal(df)
        self.assertIsNotNone(result)
        self.assertEqual(result["pattern"], "threeOverOne")
        self.assertEqual(result["patternLabel"], "三过一")

    # ── TP-4: 阳包阴但 close <= MA20 → None ─────────────────────────
    def test_tp4_engulfingButCloseUnderMa20(self) -> None:
        df = _baseKline()
        # 阻止三过一匹配
        df.loc[df.index[-3], "high"] = 12.0
        # Day1 阴线
        df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
            11.0, 11.5, 8.0, 8.5, 2000.0,
        ]
        # Day2 阳线包住 Day1, 但 close=9.0 < MA20≈10
        df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
            8.0, 9.5, 7.8, 9.0, 2000.0,
        ]
        result = isCurrentBottomFractal(df)
        self.assertIsNone(result)

    # ── TP-5: 阳包阴但 vol <= MA120 → None ──────────────────────────
    def test_tp5_engulfingButVolUnderMa120(self) -> None:
        df = _baseKline()
        # 阻止三过一匹配
        df.loc[df.index[-3], "high"] = 12.0
        # Day1 阴线
        df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
            11.0, 11.5, 9.0, 9.5, 500.0,
        ]
        # Day2 阳线包住 Day1, close>MA20, 但量能不达标 (vol<=MA120=1000)
        df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
            9.0, 12.0, 8.8, 11.5, 500.0,
        ]
        result = isCurrentBottomFractal(df)
        self.assertIsNone(result)

    # ── TP-6: 普通上涨 K 线（不匹配任何形态）→ None ──────────────────
    def test_tp6_noPatternMatch(self) -> None:
        df = _baseKline()
        # 最后一根普通阳线，不构成任何形态
        df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
            10.0, 10.8, 9.8, 10.5, 2000.0,
        ]
        result = isCurrentBottomFractal(df)
        self.assertIsNone(result)

    # ── TP-7: 空 DataFrame → None ────────────────────────────────────
    def test_tp7_emptyDf(self) -> None:
        df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        result = isCurrentBottomFractal(df)
        self.assertIsNone(result)

    # ── TP-8: K 线不足 → None ────────────────────────────────────────
    def test_tp8_insufficientBars(self) -> None:
        df = _baseKline(n=2)
        result = isCurrentBottomFractal(df)
        self.assertIsNone(result)

    # ── TP-9: 返回 dict 字段完整且类型正确 ───────────────────────────
    def test_tp9_returnFieldsAndTypes(self) -> None:
        df = _baseKline()
        df.loc[df.index[-3], "high"] = 12.0
        df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
            11.0, 11.5, 9.0, 9.5, 2000.0,
        ]
        df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
            9.0, 12.0, 8.8, 11.5, 2000.0,
        ]
        result = isCurrentBottomFractal(df)
        self.assertIsNotNone(result)
        self.assertIn("pattern", result)
        self.assertIn("patternLabel", result)
        self.assertIn("signalDate", result)
        self.assertIn("signalPrice", result)
        self.assertIn("lowestLow", result)
        self.assertIn("ma20", result)
        self.assertIn("volumeOk", result)
        self.assertIsInstance(result["pattern"], str)
        self.assertIsInstance(result["patternLabel"], str)
        self.assertIsInstance(result["signalDate"], pd.Timestamp)
        self.assertIsInstance(result["signalPrice"], float)
        self.assertIsInstance(result["lowestLow"], float)
        self.assertIsInstance(result["ma20"], float)
        self.assertIsInstance(result["volumeOk"], bool)
        self.assertTrue(result["volumeOk"])

    # ── TP-10: lowestLow = 形态窗口内最低价 ──────────────────────────
    def test_tp10_lowestLowIsWindowMin(self) -> None:
        df = _baseKline()
        df.loc[df.index[-3], "high"] = 12.0
        # 阳包阴 2 根窗口; Day1 low=9.0, Day2 low=8.8 → lowestLow=8.8
        df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
            11.0, 11.5, 9.0, 9.5, 2000.0,
        ]
        df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
            9.0, 12.0, 8.8, 11.5, 2000.0,
        ]
        result = isCurrentBottomFractal(df)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["lowestLow"], 8.8, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
