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


class TestScanHsb(unittest.TestCase):
    """scanHeadShoulderBottom service 用例（全部离线 mock）。"""

    def _makeScanAllResult(self, statuses=("confirmed",)) -> pd.DataFrame:
        """构造 scanAll 返回的 DataFrame（含全部 bestHsb* 列）。"""
        rows = []
        for i, status in enumerate(statuses):
            rows.append({
                "symbol": f"60000{i}",
                "name": f"测试股{i}",
                "currentPrice": 20.0 + i,
                "asOfDate": "2024-03-01",
                "bottomCount": 1,
                "latestBottomDate": "2024-01-10",
                "latestBottomGrade": "validTrend",
                "latestBottomLow": 14.0,
                "hsbCount": 1,
                "bestHsbStatus": status,
                "bestHsbScore": 0.85 - i * 0.1,
                "bestHsbNeckline": 17.0,
                "bestHsbTargetClassic": 22.0,
                "bestHsbTargetConservative": 17.85,
                "bestHsbLeftShoulderDate": "2024-01-10",
                "bestHsbBreakoutDate": "2024-02-15" if status != "forming" else None,
                "bestHsbBreakoutPrice": 17.5 if status != "forming" else None,
                "bestHsbNecklinePriceAtBreakout": 17.1 if status != "forming" else None,
            })
        return pd.DataFrame(rows)

    def test_onlyBreakoutFiltersForming(self) -> None:
        """onlyBreakout=True 时 forming 状态的行应被过滤。"""
        fake = self._makeScanAllResult(["confirmed", "forming"])
        with mock.patch.object(services._scan, "scanAll", return_value=fake):
            out = services.scanHeadShoulderBottom(onlyBreakout=True)
        self.assertEqual(len(out), 1)
        self.assertNotIn("forming", out["状态"].tolist())

    def test_onlyBreakoutFalseIncludesForming(self) -> None:
        """onlyBreakout=False 时 forming 状态也应包含。"""
        fake = self._makeScanAllResult(["confirmed", "forming"])
        with mock.patch.object(services._scan, "scanAll", return_value=fake):
            out = services.scanHeadShoulderBottom(onlyBreakout=False)
        self.assertEqual(len(out), 2)

    def test_emptyReturnsEmptyDf(self) -> None:
        """scanAll 返回空 DataFrame 时 service 也返回空。"""
        with mock.patch.object(services._scan, "scanAll",
                               return_value=pd.DataFrame()):
            out = services.scanHeadShoulderBottom()
        self.assertTrue(out.empty)

    def test_columnNamesCorrect(self) -> None:
        """返回 DataFrame 应包含全部 §A.3 展示列（中文）。"""
        fake = self._makeScanAllResult(["confirmed"])
        with mock.patch.object(services._scan, "scanAll", return_value=fake):
            out = services.scanHeadShoulderBottom()
        expected_cols = {"代码", "名称", "形态起始日", "突破日", "颈线价",
                         "买点价", "动态颈线价", "目标价(经典)", "评分", "状态", "现价"}
        self.assertTrue(expected_cols.issubset(set(out.columns)),
                        f"缺少列: {expected_cols - set(out.columns)}")

    def test_progressCbCalled(self) -> None:
        """progressCb 应被 scanAll 调用（通过 mock 验证参数传递）。"""
        fake = self._makeScanAllResult(["confirmed"])
        calls = []

        def _cb(done, total):
            calls.append((done, total))

        with mock.patch.object(services._scan, "scanAll",
                               return_value=fake) as m:
            services.scanHeadShoulderBottom(progressCb=_cb)
        # progressCb 参数应透传给 scanAll
        _, kwargs = m.call_args
        self.assertIs(kwargs.get("progressCb"), _cb)

    def test_noHsbRowsReturnEmpty(self) -> None:
        """scanAll 结果中没有命中头肩底的行时返回空。"""
        fake = pd.DataFrame([{
            "symbol": "600000", "name": "test",
            "currentPrice": 10.0, "asOfDate": "2024-01-01",
            "bottomCount": 0, "latestBottomDate": None,
            "latestBottomGrade": None, "latestBottomLow": None,
            "hsbCount": 0,
            "bestHsbStatus": None, "bestHsbScore": None,
            "bestHsbNeckline": None, "bestHsbTargetClassic": None,
            "bestHsbTargetConservative": None,
            "bestHsbLeftShoulderDate": None, "bestHsbBreakoutDate": None,
            "bestHsbBreakoutPrice": None, "bestHsbNecklinePriceAtBreakout": None,
        }])
        with mock.patch.object(services._scan, "scanAll", return_value=fake):
            out = services.scanHeadShoulderBottom()
        self.assertTrue(out.empty)


class TestFilterCurrentBottomFractal(unittest.TestCase):
    """filterCurrentBottomFractal 过滤函数测试（TP-3.1 ~ TP-3.6）。"""

    @staticmethod
    def _makeScanResult(rows_spec) -> pd.DataFrame:
        """构造含 isCurrentBottom 等字段的 scanAll 结果。

        rows_spec: list[dict]，每个 dict 至少含 isCurrentBottom；
        其余字段自动补默认值。
        """
        defaults = {
            "symbol": "600000",
            "name": "测试股",
            "currentPrice": 20.123,
            "isCurrentBottom": False,
            "currentBottomDate": None,
            "currentBottomLow": None,
            "currentBottomPattern": None,
        }
        rows = []
        for i, spec in enumerate(rows_spec):
            row = {**defaults, **spec}
            if "symbol" not in spec:
                row["symbol"] = f"60000{i}"
            if "name" not in spec:
                row["name"] = f"测试股{i}"
            rows.append(row)
        return pd.DataFrame(rows)

    def test_tp31_filterByIsCurrentBottom(self) -> None:
        """TP-3.1 从含 isCurrentBottom=True 的行中正确筛选。"""
        fake = self._makeScanResult([
            {"isCurrentBottom": True, "currentBottomDate": "2024-03-01",
             "currentBottomLow": 9.567, "currentBottomPattern": "阳包阴"},
            {"isCurrentBottom": False},
            {"isCurrentBottom": True, "currentBottomDate": "2024-03-05",
             "currentBottomLow": 10.891, "currentBottomPattern": "十字星底"},
        ])
        out = services.filterCurrentBottomFractal(fake)
        self.assertEqual(len(out), 2)

    def test_tp32_outputColumnsAreChinese(self) -> None:
        """TP-3.2 输出列名为中文映射。"""
        fake = self._makeScanResult([
            {"isCurrentBottom": True, "currentBottomDate": "2024-03-01",
             "currentBottomLow": 9.5, "currentBottomPattern": "阳包阴"},
        ])
        out = services.filterCurrentBottomFractal(fake)
        expected = ["代码", "名称", "形态", "信号日期", "支撑位", "现价"]
        self.assertEqual(list(out.columns), expected)

    def test_tp33_noCurrentBottomReturnsEmpty(self) -> None:
        """TP-3.3 全量结果无 isCurrentBottom=True → 空 DataFrame。"""
        fake = self._makeScanResult([
            {"isCurrentBottom": False},
            {"isCurrentBottom": False},
        ])
        out = services.filterCurrentBottomFractal(fake)
        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(out.empty)

    def test_tp34_emptyInputReturnsEmpty(self) -> None:
        """TP-3.4 输入空 DataFrame → 空 DataFrame。"""
        out = services.filterCurrentBottomFractal(pd.DataFrame())
        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(out.empty)

    def test_tp35_noneInputReturnsEmpty(self) -> None:
        """TP-3.5 输入 None → 空 DataFrame。"""
        out = services.filterCurrentBottomFractal(None)
        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(out.empty)

    def test_tp36_numericColumnsRound2(self) -> None:
        """TP-3.6 支撑位 / 现价保留 2 位小数。"""
        fake = self._makeScanResult([
            {"isCurrentBottom": True, "currentBottomDate": "2024-03-01",
             "currentBottomLow": 9.56789, "currentBottomPattern": "阳包阴",
             "currentPrice": 20.12345},
        ])
        out = services.filterCurrentBottomFractal(fake)
        self.assertAlmostEqual(out["支撑位"].iloc[0], 9.57, places=2)
        self.assertAlmostEqual(out["现价"].iloc[0], 20.12, places=2)


class TestScanHsbWithScanResult(unittest.TestCase):
    """TP-3.7 scanHeadShoulderBottom 新增可选 scanResult 参数。"""

    def _makeScanAllResult(self, statuses=("confirmed",)) -> pd.DataFrame:
        rows = []
        for i, status in enumerate(statuses):
            rows.append({
                "symbol": f"60000{i}",
                "name": f"测试股{i}",
                "currentPrice": 20.0 + i,
                "asOfDate": "2024-03-01",
                "bottomCount": 1,
                "latestBottomDate": "2024-01-10",
                "latestBottomGrade": "validTrend",
                "latestBottomLow": 14.0,
                "hsbCount": 1,
                "bestHsbStatus": status,
                "bestHsbScore": 0.85 - i * 0.1,
                "bestHsbNeckline": 17.0,
                "bestHsbTargetClassic": 22.0,
                "bestHsbTargetConservative": 17.85,
                "bestHsbLeftShoulderDate": "2024-01-10",
                "bestHsbBreakoutDate": "2024-02-15" if status != "forming" else None,
                "bestHsbBreakoutPrice": 17.5 if status != "forming" else None,
                "bestHsbNecklinePriceAtBreakout": 17.1 if status != "forming" else None,
            })
        return pd.DataFrame(rows)

    def test_scanResultSkipsScanAll(self) -> None:
        """传入 scanResult 时不调用 scanAll，直接过滤。"""
        fake = self._makeScanAllResult(["confirmed", "breakout"])
        with mock.patch.object(services._scan, "scanAll") as m:
            out = services.scanHeadShoulderBottom(scanResult=fake)
        m.assert_not_called()
        self.assertEqual(len(out), 2)

    def test_scanResultNoneCallsScanAll(self) -> None:
        """scanResult=None（默认）时仍调用 scanAll。"""
        fake = self._makeScanAllResult(["confirmed"])
        with mock.patch.object(services._scan, "scanAll",
                               return_value=fake) as m:
            services.scanHeadShoulderBottom()
        m.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
