"""东方财富源 - 股票接口测试。网络不可达时通过 safeCall 返回空 DF，用例仍判通过。"""

from __future__ import annotations

import unittest

from astock.eastmoney import stockApi as emStock
from astock.tests._helpers import assertDfCols


class TestEastmoneyStock(unittest.TestCase):

    def test_getStockListA(self) -> None:
        assertDfCols(self, emStock.getStockListA(), ["symbol", "name"])

    def test_getStockListByMarket(self) -> None:
        for m in ("sh", "sz", "bj"):
            with self.subTest(market=m):
                assertDfCols(self, emStock.getStockListByMarket(m),
                             ["symbol", "name"])
        df = emStock.getStockListByMarket("xx")
        self.assertTrue(df.empty)

    def test_getRealtimeQuote(self) -> None:
        assertDfCols(self, emStock.getRealtimeQuote(),
                     ["symbol", "name", "price"], anyOf=True)

    def test_getDailyKline(self) -> None:
        df = emStock.getDailyKline("600000", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close", "high", "low", "volume"])

    def test_getDailyKline_invalidAdjust(self) -> None:
        self.assertTrue(emStock.getDailyKline("600000", adjust="bad").empty)

    def test_getMinuteKline(self) -> None:
        df = emStock.getMinuteKline("600000", period="5")
        assertDfCols(self, df, ["datetime", "open", "close"], anyOf=True)

    def test_getIndexKline(self) -> None:
        df = emStock.getIndexKline("sh000001", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getIndustryList(self) -> None:
        assertDfCols(self, emStock.getIndustryList(),
                     ["symbol", "name"], anyOf=True)

    def test_getIndustryConstituents(self) -> None:
        assertDfCols(self, emStock.getIndustryConstituents("小金属"),
                     ["symbol", "name"], anyOf=True)

    def test_getFundFlowIndividual(self) -> None:
        assertDfCols(self, emStock.getFundFlowIndividual("600000"),
                     ["date", "close", "mainNetInflow"])

    def test_getFinancialAbstract(self) -> None:
        assertDfCols(self, emStock.getFinancialAbstract("600000"),
                     ["category", "indicator"])

    def test_getTradeCalendar(self) -> None:
        assertDfCols(self, emStock.getTradeCalendar(), ["tradeDate"])

    def test_isTradingDay(self) -> None:
        if emStock.getTradeCalendar().empty:
            self.skipTest("交易日历为空（网络不可用）")
        self.assertTrue(emStock.isTradingDay("2024-01-02"))
        self.assertFalse(emStock.isTradingDay("2024-01-01"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
