"""webapp.services 单元测试。

使用 mock 替换 astock，所有用例离线运行。
"""

from __future__ import annotations

import datetime as dt
import unittest
from unittest import mock

import pandas as pd

from webapp import services


class TestFetchKline(unittest.TestCase):

    def setUp(self) -> None:
        self.df = pd.DataFrame({
            "date": pd.bdate_range("2024-03-01", periods=3),
            "open": [10, 10.1, 10.2],
            "high": [10.5, 10.6, 10.7],
            "low": [9.9, 10.0, 10.1],
            "close": [10.4, 10.5, 10.6],
            "volume": [1000, 1100, 1200],
        })

    def test_invalidKindRaises(self) -> None:
        with self.assertRaises(ValueError):
            services.fetchKline("foo", "600000")

    def test_emptySymbolRaises(self) -> None:
        with self.assertRaises(ValueError):
            services.fetchKline("股票", "")

    def test_stockDispatch(self) -> None:
        with mock.patch.object(services._stock, "getDailyKline",
                               return_value=self.df) as m:
            out = services.fetchKline("股票", "600000",
                                      dt.date(2024, 3, 1),
                                      dt.date(2024, 3, 5))
        m.assert_called_once_with("600000",
                                  startDate="2024-03-01",
                                  endDate="2024-03-05")
        self.assertEqual(len(out), 3)

    def test_etfDispatch(self) -> None:
        with mock.patch.object(services._fund, "getEtfKline",
                               return_value=self.df) as m:
            services.fetchKline("ETF", "510050", "2024-03-01", "2024-03-05")
        m.assert_called_once_with("510050",
                                  startDate="2024-03-01",
                                  endDate="2024-03-05")

    def test_lofDispatch(self) -> None:
        with mock.patch.object(services._fund, "getLofKline",
                               return_value=self.df) as m:
            services.fetchKline("LOF", "161725")
        m.assert_called_once_with("161725", startDate=None, endDate=None)

    def test_noneReturnNormalizedToEmpty(self) -> None:
        with mock.patch.object(services._stock, "getDailyKline",
                               return_value=None):
            out = services.fetchKline("股票", "600000")
        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(out.empty)


class TestFetchIndustry(unittest.TestCase):

    def test_listDelegates(self) -> None:
        df = pd.DataFrame({"name": ["银行", "白酒"]})
        with mock.patch.object(services._stock, "getIndustryList",
                               return_value=df) as m:
            out = services.fetchIndustryList()
        m.assert_called_once_with()
        self.assertEqual(len(out), 2)

    def test_constituentsDelegates(self) -> None:
        df = pd.DataFrame({"symbol": ["600000"], "name": ["浦发银行"]})
        with mock.patch.object(services._stock, "getIndustryConstituents",
                               return_value=df) as m:
            out = services.fetchIndustryConstituents("银行")
        m.assert_called_once_with("银行")
        self.assertEqual(out.iloc[0]["symbol"], "600000")

    def test_emptyIndustryRaises(self) -> None:
        with self.assertRaises(ValueError):
            services.fetchIndustryConstituents("")


class TestFetchFundFlow(unittest.TestCase):

    def test_delegates(self) -> None:
        df = pd.DataFrame({"date": ["2024-03-01"], "mainNet": [1234.5]})
        with mock.patch.object(services._stock, "getFundFlowIndividual",
                               return_value=df) as m:
            out = services.fetchFundFlow("600000")
        m.assert_called_once_with("600000")
        self.assertEqual(len(out), 1)

    def test_emptySymbolRaises(self) -> None:
        with self.assertRaises(ValueError):
            services.fetchFundFlow("   ")


class TestFetchFinancialAbstract(unittest.TestCase):

    def test_delegates(self) -> None:
        df = pd.DataFrame({"item": ["营业收入"], "value": [10_000_000]})
        with mock.patch.object(services._stock, "getFinancialAbstract",
                               return_value=df) as m:
            out = services.fetchFinancialAbstract("600000")
        m.assert_called_once_with("600000")
        self.assertEqual(len(out), 1)

    def test_emptySymbolRaises(self) -> None:
        with self.assertRaises(ValueError):
            services.fetchFinancialAbstract("")


class TestLabelKline(unittest.TestCase):

    def test_renamesKnownColumns(self) -> None:
        df = pd.DataFrame({
            "date": ["2024-03-01"],
            "open": [10.0], "high": [10.5], "low": [9.9], "close": [10.4],
            "volume": [1.5e7], "amount": [1.56e8],
            "preClose": [10.0], "changePct": [0.04],
        })
        out = services.labelKline(df)
        self.assertEqual(list(out.columns),
                         ["日期", "开盘", "最高", "最低", "收盘",
                          "成交量(千万)", "成交额(千万)", "昨收", "涨跌幅"])
        self.assertEqual(len(out), 1)

    def test_unknownColumnsKept(self) -> None:
        df = pd.DataFrame({"date": ["2024-03-01"], "weirdCol": [1]})
        out = services.labelKline(df)
        self.assertEqual(list(out.columns), ["日期", "weirdCol"])

    def test_emptyDfReturnedAsIs(self) -> None:
        out = services.labelKline(pd.DataFrame())
        self.assertTrue(out.empty)

    def test_volumeAndAmountConvertedToTenMillion(self) -> None:
        df = pd.DataFrame({
            "volume": [1_500_000.0, 25_000_000.0],
            "amount": [156_000_000.0, 1_234_500_000.0],
        })
        out = services.labelKline(df)
        self.assertAlmostEqual(out["成交量(千万)"].iloc[0], 0.15, places=2)
        self.assertAlmostEqual(out["成交量(千万)"].iloc[1], 2.5, places=2)
        self.assertAlmostEqual(out["成交额(千万)"].iloc[0], 15.6, places=2)
        self.assertAlmostEqual(out["成交额(千万)"].iloc[1], 123.45, places=2)

    def test_turnoverDecimalToPercent(self) -> None:
        df = pd.DataFrame({"turnover": [0.0234, 0.123, 0.0]})
        out = services.labelKline(df)
        self.assertAlmostEqual(out["换手率(%)"].iloc[0], 2.34, places=2)
        self.assertAlmostEqual(out["换手率(%)"].iloc[1], 12.3, places=2)
        self.assertAlmostEqual(out["换手率(%)"].iloc[2], 0.0, places=2)

    def test_preserveOriginalDf(self) -> None:
        df = pd.DataFrame({"volume": [1e7]})
        services.labelKline(df)
        self.assertAlmostEqual(df["volume"].iloc[0], 1e7, places=2)


class TestLookupName(unittest.TestCase):

    def setUp(self) -> None:
        services.clearNameCache()

    def tearDown(self) -> None:
        services.clearNameCache()

    def _stockSpot(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"symbol": "600000", "name": "浦发银行", "price": 12.34},
            {"symbol": "000001", "name": "平安银行", "price": 10.10},
        ])

    def test_stockHit(self) -> None:
        with mock.patch.object(services._stock, "getRealtimeQuote",
                               return_value=self._stockSpot()) as m:
            self.assertEqual(services.lookupName("股票", "600000"), "浦发银行")
            self.assertEqual(services.lookupName("股票", "000001"), "平安银行")
        m.assert_called_once()  # 缓存生效

    def test_stockMiss(self) -> None:
        with mock.patch.object(services._stock, "getRealtimeQuote",
                               return_value=self._stockSpot()):
            self.assertEqual(services.lookupName("股票", "999999"), "")

    def test_etfHit(self) -> None:
        df = pd.DataFrame([{"symbol": "510050", "name": "上证50ETF"}])
        with mock.patch.object(services._fund, "getEtfList",
                               return_value=df):
            self.assertEqual(services.lookupName("ETF", "510050"), "上证50ETF")

    def test_lofHit(self) -> None:
        df = pd.DataFrame([{"symbol": "161725", "name": "招商中证白酒"}])
        with mock.patch.object(services._fund, "getLofList",
                               return_value=df):
            self.assertEqual(services.lookupName("LOF", "161725"),
                             "招商中证白酒")

    def test_emptySymbolReturnsEmpty(self) -> None:
        self.assertEqual(services.lookupName("股票", ""), "")
        self.assertEqual(services.lookupName("股票", "   "), "")

    def test_invalidKindReturnsEmpty(self) -> None:
        self.assertEqual(services.lookupName("foo", "600000"), "")

    def test_emptyTableReturnsEmpty(self) -> None:
        with mock.patch.object(services._stock, "getRealtimeQuote",
                               return_value=pd.DataFrame()):
            self.assertEqual(services.lookupName("股票", "600000"), "")


class TestRunGridOptimize(unittest.TestCase):

    def _kline(self, days: int = 30) -> pd.DataFrame:
        idx = pd.bdate_range("2024-01-02", periods=days)
        closes = [10.0 * (1.005 ** i) for i in range(days)]
        opens = [closes[0]] + closes[:-1]
        return pd.DataFrame({
            "date": idx,
            "open": opens,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * days,
        })

    def test_invalidTotalAmountRaises(self) -> None:
        with self.assertRaises(ValueError):
            services.runGridOptimize(self._kline(), 0)

    def test_emptyKlineRaises(self) -> None:
        with self.assertRaises(ValueError):
            services.runGridOptimize(pd.DataFrame(), 100000)

    def test_delegatesToBacktestModule(self) -> None:
        fake = {
            "candidates": [{"spacing": 0.02, "levels": 5,
                            "totalReturn": 0.1, "holdReturn": 0.05,
                            "excessReturn": 0.05}],
            "top": [{"spacing": 0.02, "levels": 5,
                     "totalReturn": 0.1, "holdReturn": 0.05,
                     "excessReturn": 0.05}],
            "best": {"spacing": 0.02, "levels": 5,
                     "metrics": {"totalReturn": 0.1},
                     "holdReturn": 0.05, "excessReturn": 0.05,
                     "summary": "ok"},
        }
        with mock.patch("backtest.gridOptimize", return_value=fake) as m:
            out = services.runGridOptimize(self._kline(), 100000)
        m.assert_called_once()
        self.assertEqual(out, fake)


if __name__ == "__main__":
    unittest.main(verbosity=2)
