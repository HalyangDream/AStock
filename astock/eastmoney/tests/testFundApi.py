"""东方财富源 - 基金接口测试。"""

from __future__ import annotations

import unittest

from astock.eastmoney import fundApi as emFund
from astock.tests._helpers import assertDfCols


class TestEastmoneyFund(unittest.TestCase):

    def test_getFundList(self) -> None:
        assertDfCols(self, emFund.getFundList(),
                     ["symbol", "name", "fundType"])

    def test_getFundListByType(self) -> None:
        df = emFund.getFundListByType("指数型")
        assertDfCols(self, df, ["symbol", "name", "fundType"])
        if not df.empty:
            self.assertTrue(df["fundType"].str.contains("指数型").all())

    def test_getFundNav(self) -> None:
        assertDfCols(self, emFund.getFundNav("000001"),
                     ["navDate", "unitNav"])

    def test_getFundRealtimeEstimate(self) -> None:
        assertDfCols(self, emFund.getFundRealtimeEstimate(),
                     ["symbol", "name"], anyOf=True)

    def test_getFundRank(self) -> None:
        assertDfCols(self, emFund.getFundRank("股票型"),
                     ["symbol", "name", "unitNav"])

    def test_getEtfList(self) -> None:
        assertDfCols(self, emFund.getEtfList(), ["symbol", "name"])

    def test_getEtfRealtimeQuote(self) -> None:
        assertDfCols(self, emFund.getEtfRealtimeQuote(),
                     ["symbol", "name"], anyOf=True)

    def test_getEtfKline(self) -> None:
        df = emFund.getEtfKline("159707", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getLofList(self) -> None:
        assertDfCols(self, emFund.getLofList(), ["symbol", "name"])

    def test_getLofKline(self) -> None:
        df = emFund.getLofKline("166009", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getFundHoldings(self) -> None:
        assertDfCols(self, emFund.getFundHoldings("000001", year=2024),
                     ["stockSymbol", "stockName", "navRatio"])

    def test_getFundManagers(self) -> None:
        assertDfCols(self, emFund.getFundManagers(),
                     ["name", "company", "currentFundSymbol", "currentFund"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
