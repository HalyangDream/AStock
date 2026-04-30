"""腾讯源 - 股票接口测试。"""

from __future__ import annotations

import unittest

from astock.tencent import stockApi as txStock
from astock.tests._helpers import assertDfCols


class TestTencentStock(unittest.TestCase):

    def test_getDailyKline(self) -> None:
        df = txStock.getDailyKline("000001", "2024-01-02", "2024-01-10")
        assertDfCols(self, df, ["date", "open", "close"], anyOf=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
