"""astock.fund 顶层门面测试。"""

from __future__ import annotations

import unittest

from astock import fund as facadeFund
from astock.tests._helpers import assertDfCols


class TestFundFacade(unittest.TestCase):

    def test_getFundList(self) -> None:
        assertDfCols(self, facadeFund.getFundList(),
                     ["symbol", "name", "fundType"])

    def test_getEtfList_auto(self) -> None:
        assertDfCols(self, facadeFund.getEtfList(), ["symbol", "name"])

    def test_getEtfKline_auto(self) -> None:
        df = facadeFund.getEtfKline("sh510050", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getEtfKline_sinaOnly(self) -> None:
        df = facadeFund.getEtfKline(
            "sh510050", "2024-01-02", "2024-01-10", source="sina")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
