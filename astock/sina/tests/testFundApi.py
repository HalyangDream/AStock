"""新浪源 - 基金接口测试。"""

from __future__ import annotations

import unittest

from astock.sina import fundApi as sinaFund
from astock.tests._helpers import assertDfCols


class TestSinaFund(unittest.TestCase):

    def test_getEtfList(self) -> None:
        assertDfCols(self, sinaFund.getEtfList(), ["symbol", "name"])

    def test_getLofList(self) -> None:
        assertDfCols(self, sinaFund.getLofList(), ["symbol", "name"])

    def test_getEtfKline(self) -> None:
        df = sinaFund.getEtfKline("sh510050", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)

    def test_getLofKline(self) -> None:
        df = sinaFund.getLofKline("sh501050", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
