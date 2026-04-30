"""astock.stock 顶层门面测试（自动源 + 指定源）。"""

from __future__ import annotations

import unittest

from astock import stock as facadeStock
from astock.tests._helpers import assertDfCols


class TestStockFacade(unittest.TestCase):

    def test_getDailyKline_auto(self) -> None:
        df = facadeStock.getDailyKline("600000", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getDailyKline_specificSource(self) -> None:
        for src in ("sina", "tencent", "eastmoney"):
            with self.subTest(source=src):
                df = facadeStock.getDailyKline(
                    "600000", "2024-01-02", "2024-01-10", source=src)
                assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getDailyKline_invalidSource(self) -> None:
        with self.assertRaises(ValueError):
            facadeStock.getDailyKline("600000", source="xxx")

    def test_getRealtimeQuote(self) -> None:
        assertDfCols(self, facadeStock.getRealtimeQuote(),
                     ["symbol", "name", "price"], anyOf=True)

    def test_getIndexKline(self) -> None:
        df = facadeStock.getIndexKline("sh000001", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getStockListA(self) -> None:
        assertDfCols(self, facadeStock.getStockListA(), ["symbol", "name"])

    def test_getTradeCalendar(self) -> None:
        assertDfCols(self, facadeStock.getTradeCalendar(), ["tradeDate"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
