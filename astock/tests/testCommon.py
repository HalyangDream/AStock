"""astock._common 纯逻辑单元测试，离线可跑。"""

from __future__ import annotations

import unittest
from datetime import datetime

import pandas as pd

from astock._common import (
    detectMarket,
    padCode,
    renameColumns,
    safeCall,
    splitSymbolAndMarket,
    toCompactDate,
    toDashDate,
    withMarketPrefix,
)


class TestCommon(unittest.TestCase):

    def test_padCode(self) -> None:
        self.assertEqual(padCode("1"), "000001")
        self.assertEqual(padCode("600000"), "600000")
        self.assertEqual(padCode(600000), "600000")
        self.assertEqual(padCode("abc"), "abc")

    def test_detectMarket(self) -> None:
        self.assertEqual(detectMarket("600000"), "sh")
        self.assertEqual(detectMarket("000001"), "sz")
        self.assertEqual(detectMarket("300750"), "sz")
        self.assertEqual(detectMarket("430047"), "bj")
        self.assertEqual(detectMarket("688001"), "sh")
        self.assertEqual(detectMarket("12345"), "sz")  # 自动补零
        with self.assertRaises(ValueError):
            detectMarket("1234567")
        with self.assertRaises(ValueError):
            detectMarket("abcdef")
        with self.assertRaises(ValueError):
            detectMarket("700000")

    def test_splitSymbolAndMarket(self) -> None:
        self.assertEqual(splitSymbolAndMarket("600000"), ("600000", "sh"))
        self.assertEqual(splitSymbolAndMarket("sh600000"), ("600000", "sh"))
        self.assertEqual(splitSymbolAndMarket("SH600000"), ("600000", "sh"))
        self.assertEqual(splitSymbolAndMarket("000001.SZ"), ("000001", "sz"))
        self.assertEqual(splitSymbolAndMarket("sz000001"), ("000001", "sz"))

    def test_withMarketPrefix(self) -> None:
        self.assertEqual(withMarketPrefix("600000"), "sh600000")
        self.assertEqual(withMarketPrefix("000001"), "sz000001")
        self.assertEqual(withMarketPrefix("sh600000"), "sh600000")

    def test_toCompactDate(self) -> None:
        self.assertEqual(toCompactDate("2024-01-02"), "20240102")
        self.assertEqual(toCompactDate("20240102"), "20240102")
        self.assertEqual(toCompactDate("2024/01/02"), "20240102")
        self.assertEqual(toCompactDate(datetime(2024, 1, 2)), "20240102")
        self.assertEqual(toCompactDate(None, default="19700101"), "19700101")
        with self.assertRaises(ValueError):
            toCompactDate("2024-1-2")

    def test_toDashDate(self) -> None:
        self.assertEqual(toDashDate("20240102"), "2024-01-02")
        self.assertEqual(toDashDate("2024-01-02"), "2024-01-02")

    def test_renameColumns(self) -> None:
        df = pd.DataFrame({"日期": [1], "收盘": [2], "其他": [3]})
        out = renameColumns(df, {"日期": "date", "收盘": "close"})
        self.assertEqual(list(out.columns), ["date", "close", "其他"])
        out2 = renameColumns(df, {"日期": "date", "收盘": "close"},
                             keepOnly=["date", "close"])
        self.assertEqual(list(out2.columns), ["date", "close"])
        empty = pd.DataFrame(columns=["日期", "收盘"])
        out3 = renameColumns(empty, {"日期": "date", "收盘": "close"})
        self.assertEqual(list(out3.columns), ["date", "close"])

    def test_safeCall(self) -> None:
        @safeCall(emptyColumns=["a", "b"])
        def boom() -> pd.DataFrame:
            raise RuntimeError("expected")

        df = boom()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertTrue(df.empty)
        self.assertEqual(list(df.columns), ["a", "b"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
