"""新浪源 - 股票接口测试。"""

from __future__ import annotations

import unittest

from astock.sina import stockApi as sinaStock
from astock.tests._helpers import assertDfCols


class TestSinaStock(unittest.TestCase):

    def test_getDailyKline(self) -> None:
        df = sinaStock.getDailyKline("600000", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "high", "low", "close"])

    def test_getMinuteKline(self) -> None:
        df = sinaStock.getMinuteKline("600000", period="5")
        assertDfCols(self, df, ["datetime", "open", "close"], anyOf=True)

    def test_getRealtimeQuote(self) -> None:
        df = sinaStock.getRealtimeQuote()
        assertDfCols(self, df, ["symbol", "name", "price"], anyOf=True)

    def test_getIndexKline(self) -> None:
        df = sinaStock.getIndexKline("sh000001", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getIndexRealtimeQuote(self) -> None:
        assertDfCols(self, sinaStock.getIndexRealtimeQuote(),
                     ["symbol", "name"], anyOf=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
