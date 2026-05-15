"""scan.scanSingle / scanBatch / CLI 单元测试。

网络完全不触达：
- scanSingle 通过 kline= 传入预构造 K 线
- 名称 / 实时价通过直接写 scan._spotCache 注入
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

import pandas as pd

from strategy import scan
from strategy.patterns.tests._helpers import interpolateKeypoints


def _buildHsbKline() -> pd.DataFrame:
    """含头肩底 + 底分型的合成 K 线（复用 headShoulder 测试同款）。"""
    keypoints = [
        (0,  20.0, 19.0),
        (10, 15.0, 14.0),   # L1
        (16, 17.0, 16.0),   # H1
        (25, 13.0, 12.0),   # L2 (head)
        (31, 17.0, 16.0),   # H2
        (40, 15.0, 14.0),   # L3
        (44, 17.5, 16.5),
        (47, 19.0, 17.5),
        (49, 19.5, 18.0),
    ]
    return interpolateKeypoints(
        keypoints,
        baseVolume=1000,
        volumeSpikeAt=[47, 48],
        volumeSpikeMul=4.0,
    )


def _buildSpotDf() -> pd.DataFrame:
    """构造 sina 风格的全 A 实时快照。"""
    return pd.DataFrame([
        {"symbol": "600000", "name": "浦发银行", "price": 12.34},
        {"symbol": "000001", "name": "平安银行", "price": 10.10},
        {"symbol": "300001", "name": "特锐德", "price": 20.00},
        {"symbol": "830799", "name": "艾融软件", "price": 8.50},
    ])


class TestScanSingle(unittest.TestCase):

    def setUp(self) -> None:
        scan._spotCache = _buildSpotDf()

    def tearDown(self) -> None:
        scan._spotCache = None

    def test_resultShape(self) -> None:
        df = _buildHsbKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0,
                              hsbMinSpan=20, hsbMaxSpan=60,
                              hsbKwargs={"headToShoulderMinSpan": 10})
        self.assertEqual(res["symbol"], "600000")
        self.assertEqual(res["name"], "浦发银行")
        self.assertIsNotNone(res["currentPrice"])
        self.assertIsInstance(res["bottomFractals"], pd.DataFrame)
        self.assertIsInstance(res["headShoulderBottoms"], pd.DataFrame)
        self.assertFalse(res["headShoulderBottoms"].empty)
        self.assertEqual(res["asOfDate"],
                         pd.Timestamp(df["date"].iloc[-1]).strftime("%Y-%m-%d"))

    def test_currentPriceFromCloseByDefault(self) -> None:
        df = _buildHsbKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0,
                              realtime=False, hsbMinSpan=20, hsbMaxSpan=60,
                              hsbKwargs={"headToShoulderMinSpan": 10})
        self.assertAlmostEqual(res["currentPrice"],
                               float(df["close"].iloc[-1]), places=4)

    def test_currentPriceFromRealtime(self) -> None:
        df = _buildHsbKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0,
                              realtime=True, hsbMinSpan=20, hsbMaxSpan=60,
                              hsbKwargs={"headToShoulderMinSpan": 10})
        self.assertAlmostEqual(res["currentPrice"], 12.34, places=4)

    def test_emptyKlineGracefullyReturns(self) -> None:
        res = scan.scanSingle("600000", kline=pd.DataFrame(), lookbackDays=0)
        self.assertEqual(res["symbol"], "600000")
        self.assertEqual(res["name"], "浦发银行")
        self.assertIsNone(res["currentPrice"])
        self.assertIsNone(res["asOfDate"])
        self.assertTrue(res["bottomFractals"].empty)
        self.assertTrue(res["headShoulderBottoms"].empty)

    def test_unknownSymbolHasEmptyName(self) -> None:
        df = _buildHsbKline()
        res = scan.scanSingle("999999", kline=df, lookbackDays=0,
                              hsbMinSpan=20, hsbMaxSpan=60)
        self.assertEqual(res["symbol"], "999999")
        self.assertEqual(res["name"], "")

    def test_lookbackDaysTrims(self) -> None:
        df = _buildHsbKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=10,
                              hsbMinSpan=20, hsbMaxSpan=60)
        self.assertEqual(res["asOfDate"],
                         pd.Timestamp(df["date"].iloc[-1]).strftime("%Y-%m-%d"))


class TestScanBatch(unittest.TestCase):

    def setUp(self) -> None:
        scan._spotCache = _buildSpotDf()

    def tearDown(self) -> None:
        scan._spotCache = None

    def test_batchSummaryColumns(self) -> None:
        df = _buildHsbKline()
        # 通过 monkeypatch scanSingle 避免拉 K 线
        origSingle = scan.scanSingle

        def fakeSingle(symbol, **kwargs):
            return origSingle(symbol, kline=df, lookbackDays=0,
                              hsbMinSpan=20, hsbMaxSpan=60,
                              minFractalGrade=kwargs.get("minFractalGrade",
                                                        "validTrend"),
                              realtime=kwargs.get("realtime", False),
                              hsbKwargs={"headToShoulderMinSpan": 10})

        with mock.patch.object(scan, "scanSingle", side_effect=fakeSingle):
            out = scan.scanBatch(["600000", "000001"], lookbackDays=0)

        self.assertEqual(len(out), 2)
        expectedCols = {
            "symbol", "name", "currentPrice", "asOfDate",
            "bottomCount", "latestBottomDate", "latestBottomGrade",
            "latestBottomLow",
            "hsbCount", "bestHsbStatus", "bestHsbScore",
            "bestHsbNeckline",
            "bestHsbTargetClassic", "bestHsbTargetConservative",
            "bestHsbLeftShoulderDate", "bestHsbBreakoutDate",
            "bestHsbBreakoutPrice", "bestHsbNecklinePriceAtBreakout",
        }
        self.assertTrue(expectedCols.issubset(set(out.columns)))
        self.assertEqual(list(out["name"]), ["浦发银行", "平安银行"])
        self.assertTrue((out["hsbCount"] > 0).any())


class TestFormatters(unittest.TestCase):

    def setUp(self) -> None:
        scan._spotCache = _buildSpotDf()

    def tearDown(self) -> None:
        scan._spotCache = None

    def test_formatSingleContainsHeader(self) -> None:
        df = _buildHsbKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0,
                              hsbMinSpan=20, hsbMaxSpan=60)
        txt = scan._formatSingle(res)
        self.assertIn("600000", txt)
        self.assertIn("浦发银行", txt)
        self.assertIn("底分型", txt)
        self.assertIn("头肩底", txt)

    def test_jsonableResult(self) -> None:
        df = _buildHsbKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0,
                              hsbMinSpan=20, hsbMaxSpan=60)
        payload = scan._resultToJsonable(res)
        s = json.dumps(payload, ensure_ascii=False, default=str)
        self.assertIn("600000", s)
        self.assertIsInstance(payload["bottomFractals"], list)
        self.assertIsInstance(payload["headShoulderBottoms"], list)


class TestCli(unittest.TestCase):

    def setUp(self) -> None:
        scan._spotCache = _buildSpotDf()

    def tearDown(self) -> None:
        scan._spotCache = None

    def test_singleCliTable(self) -> None:
        df = _buildHsbKline()

        def fakeSingle(symbol, **kwargs):
            return {
                "symbol": symbol,
                "name": "浦发银行",
                "currentPrice": 12.34,
                "asOfDate": "2024-03-01",
                "lookbackDays": kwargs.get("lookbackDays", 250),
                "bottomFractals": pd.DataFrame(),
                "headShoulderBottoms": pd.DataFrame(),
            }

        with mock.patch.object(scan, "scanSingle", side_effect=fakeSingle):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = scan.main(["600000", "--days", "30"])
        self.assertEqual(rc, 0)
        self.assertIn("600000", buf.getvalue())
        self.assertIn("浦发银行", buf.getvalue())

    def test_batchCliJson(self) -> None:
        summary = pd.DataFrame([
            {"symbol": "600000", "name": "浦发银行",
             "currentPrice": 12.34, "asOfDate": "2024-03-01",
             "bottomCount": 1, "latestBottomDate": "2024-02-01",
             "latestBottomGrade": "validTrend", "latestBottomLow": 9.5,
             "hsbCount": 1, "bestHsbStatus": "confirmed",
             "bestHsbScore": 0.72, "bestHsbNeckline": 17.0,
             "bestHsbTargetClassic": 22.0,
             "bestHsbTargetConservative": 17.85},
            {"symbol": "000001", "name": "平安银行",
             "currentPrice": 10.10, "asOfDate": "2024-03-01",
             "bottomCount": 0, "latestBottomDate": None,
             "latestBottomGrade": None, "latestBottomLow": None,
             "hsbCount": 0, "bestHsbStatus": None,
             "bestHsbScore": None, "bestHsbNeckline": None,
             "bestHsbTargetClassic": None,
             "bestHsbTargetConservative": None},
        ])
        with mock.patch.object(scan, "scanBatch", return_value=summary):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = scan.main(["600000", "000001", "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["symbol"], "600000")


class TestGetAllSymbols(unittest.TestCase):

    def setUp(self) -> None:
        scan._spotCache = _buildSpotDf()

    def tearDown(self) -> None:
        scan._spotCache = None

    def test_returnsAllWhenNoMarketFilter(self) -> None:
        codes = scan.getAllSymbols()
        self.assertEqual(set(codes), {"600000", "000001", "300001", "830799"})

    def test_marketFilterSh(self) -> None:
        codes = scan.getAllSymbols(markets=["sh"])
        self.assertEqual(codes, ["600000"])

    def test_marketFilterMultiple(self) -> None:
        codes = scan.getAllSymbols(markets=["sh", "sz"])
        self.assertEqual(set(codes), {"600000", "000001", "300001"})

    def test_emptyCacheReturnsEmpty(self) -> None:
        scan._spotCache = pd.DataFrame()
        self.assertEqual(scan.getAllSymbols(), [])


class TestScanAll(unittest.TestCase):

    def setUp(self) -> None:
        scan._spotCache = _buildSpotDf()

    def tearDown(self) -> None:
        scan._spotCache = None

    def _fakeScanSingle(self, symbol, **_kwargs):
        """按代码造出不同命中情况的假结果。"""
        hsbDf = pd.DataFrame([{
            "status": "confirmed",
            "score": 0.8,
            "necklinePrice": 17.0,
            "targetPriceClassic": 22.0,
            "targetPriceConservative": 17.85,
            "leftShoulderDate": pd.Timestamp("2024-01-10"),
            "rightShoulderDate": pd.Timestamp("2024-02-20"),
            "breakoutDate": pd.Timestamp("2024-02-25"),
            "breakoutPrice": 17.5,
            "necklinePriceAtBreakout": 17.1,
        }])
        bottomDf = pd.DataFrame([{
            "centerDate": pd.Timestamp("2024-03-01"),
            "centerLow": 10.0,
            "centerHigh": 11.0,
            "grade": "validTrend",
        }])
        base = {"symbol": symbol, "name": f"名{symbol}",
                "currentPrice": 1.0, "asOfDate": "2024-03-01",
                "lookbackDays": 250,
                "bottomFractals": pd.DataFrame(),
                "headShoulderBottoms": pd.DataFrame()}
        if symbol == "600000":
            base["headShoulderBottoms"] = hsbDf
            base["bottomFractals"] = bottomDf
        elif symbol == "000001":
            base["bottomFractals"] = bottomDf
        elif symbol == "300001":
            low = hsbDf.copy()
            low.loc[0, "score"] = 0.4
            low.loc[0, "leftShoulderDate"] = pd.Timestamp("2024-02-01")
            low.loc[0, "rightShoulderDate"] = pd.Timestamp("2024-03-01")
            base["headShoulderBottoms"] = low
        return base

    def test_hitOnlyFiltersNoSignalRows(self) -> None:
        with mock.patch.object(scan, "scanSingle",
                               side_effect=self._fakeScanSingle):
            out = scan.scanAll(workers=2, hitOnly=True, progress=False)
        self.assertEqual(set(out["symbol"]), {"600000", "000001", "300001"})
        self.assertNotIn("830799", set(out["symbol"]))

    def test_sortByRecentThenScore(self) -> None:
        """结果按最近日期优先，同日期按评分降序。"""
        with mock.patch.object(scan, "scanSingle",
                               side_effect=self._fakeScanSingle):
            out = scan.scanAll(workers=2, hitOnly=True, progress=False)
        hsb_rows = out[out["bestHsbStatus"].notna()]
        if len(hsb_rows) >= 2:
            self.assertEqual(hsb_rows.iloc[0]["symbol"], "300001")
            self.assertEqual(hsb_rows.iloc[1]["symbol"], "600000")

    def test_allRowsIncludesMisses(self) -> None:
        with mock.patch.object(scan, "scanSingle",
                               side_effect=self._fakeScanSingle):
            out = scan.scanAll(workers=2, hitOnly=False, progress=False)
        self.assertEqual(len(out), 4)

    def test_limitTrims(self) -> None:
        with mock.patch.object(scan, "scanSingle",
                               side_effect=self._fakeScanSingle):
            out = scan.scanAll(workers=2, limit=2,
                               hitOnly=False, progress=False)
        self.assertLessEqual(len(out), 2)

    def test_marketFilterPassedThrough(self) -> None:
        with mock.patch.object(scan, "scanSingle",
                               side_effect=self._fakeScanSingle):
            out = scan.scanAll(markets=["sh"], workers=1,
                               hitOnly=False, progress=False)
        self.assertEqual(out["symbol"].tolist(), ["600000"])


def _buildCurrentBottomKline():
    """130 根 K 线，尾部构成阳包阴 + 双前提满足。"""
    n = 130
    dates = pd.bdate_range("2024-01-01", periods=n)
    baseClose = 10.0
    baseVol = 1000.0
    df = pd.DataFrame({
        "date": dates,
        "open": [baseClose] * n,
        "high": [baseClose + 0.5] * n,
        "low": [baseClose - 0.5] * n,
        "close": [baseClose] * n,
        "volume": [baseVol] * n,
    })
    # Day1 阴线
    df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
        11.0, 11.5, 9.0, 9.5, 2000.0,
    ]
    # Day2 阳包阴, close>MA20, vol>MA120
    df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
        9.0, 12.0, 8.8, 11.5, 2000.0,
    ]
    return df


def _buildNoBottomKline():
    """尾部不构成底分型的 K 线（持续上行）。"""
    rows = [
        {"open": 10, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100},
        {"open": 10.5, "high": 11.5, "low": 10.0, "close": 11.0, "volume": 110},
        {"open": 11, "high": 12.0, "low": 10.5, "close": 11.5, "volume": 120},
        {"open": 11.5, "high": 12.5, "low": 11.0, "close": 12.0, "volume": 130},
    ]
    dates = pd.bdate_range("2024-01-01", periods=len(rows))
    for i, r in enumerate(rows):
        r["date"] = dates[i].strftime("%Y-%m-%d")
    return pd.DataFrame(rows)


class TestCurrentBottomIntegration(unittest.TestCase):
    """TP-2.1 ~ TP-2.8: 当前底分型在 scan 模块的集成。"""

    def setUp(self) -> None:
        scan._spotCache = _buildSpotDf()

    def tearDown(self) -> None:
        scan._spotCache = None

    # TP-2.1
    def test_scanSingleWithBottomFractal(self) -> None:
        df = _buildCurrentBottomKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0)
        self.assertIsNotNone(res.get("currentBottom"))

    # TP-2.3
    def test_scanSingleWithoutBottomFractal(self) -> None:
        df = _buildNoBottomKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0)
        self.assertIsNone(res.get("currentBottom"))

    # TP-2.5
    def test_scanSingleEmptyKline(self) -> None:
        res = scan.scanSingle("600000", kline=pd.DataFrame(), lookbackDays=0)
        self.assertIsNone(res.get("currentBottom"))

    # TP-2.2
    def test_summaryRowWithCurrentBottom(self) -> None:
        df = _buildCurrentBottomKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0)
        row = scan._summaryRow(res)
        self.assertTrue(row["isCurrentBottom"])
        self.assertIsNotNone(row["currentBottomDate"])
        self.assertIsNotNone(row["currentBottomLow"])
        self.assertIsInstance(row["currentBottomPattern"], str)

    # TP-2.4
    def test_summaryRowWithoutCurrentBottom(self) -> None:
        df = _buildNoBottomKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0)
        row = scan._summaryRow(res)
        self.assertFalse(row["isCurrentBottom"])
        self.assertIsNone(row["currentBottomDate"])
        self.assertIsNone(row["currentBottomLow"])
        self.assertIsNone(row["currentBottomPattern"])

    # TP-2.7
    def test_summaryRowExistingFieldsUnchanged(self) -> None:
        df = _buildHsbKline()
        res = scan.scanSingle("600000", kline=df, lookbackDays=0,
                              hsbMinSpan=20, hsbMaxSpan=60,
                              hsbKwargs={"headToShoulderMinSpan": 10})
        row = scan._summaryRow(res)
        self.assertIn("bottomCount", row)
        self.assertIn("latestBottomDate", row)
        self.assertIn("hsbCount", row)
        self.assertIn("bestHsbStatus", row)
        self.assertGreater(row["hsbCount"], 0)

    # TP-2.6
    def test_scanAllHitOnlyIncludesCurrentBottomOnly(self) -> None:
        """仅有 isCurrentBottom=True（无 hsb / 无历史 bottom）的股票应被 hitOnly 保留。"""
        bottomKline = _buildCurrentBottomKline()
        noBottomKline = _buildNoBottomKline()

        def _fakeScanSingle(symbol, **_kwargs):
            base = {
                "symbol": symbol, "name": f"名{symbol}",
                "currentPrice": 1.0, "asOfDate": "2024-03-01",
                "lookbackDays": 250,
                "bottomFractals": pd.DataFrame(),
                "headShoulderBottoms": pd.DataFrame(),
                "currentBottom": None,
            }
            if symbol == "600000":
                from strategy.patterns import isCurrentBottomFractal
                base["currentBottom"] = isCurrentBottomFractal(bottomKline)
            return base

        with mock.patch.object(scan, "scanSingle",
                               side_effect=_fakeScanSingle):
            out = scan.scanAll(workers=1, hitOnly=True, progress=False)
        self.assertIn("600000", set(out["symbol"]))
        self.assertNotIn("000001", set(out["symbol"]))

    # TP-2.8
    def test_scanBatchContainsCurrentBottomColumn(self) -> None:
        df = _buildCurrentBottomKline()
        origSingle = scan.scanSingle

        def fakeSingle(symbol, **kwargs):
            return origSingle(symbol, kline=df, lookbackDays=0)

        with mock.patch.object(scan, "scanSingle", side_effect=fakeSingle):
            out = scan.scanBatch(["600000"])
        self.assertIn("isCurrentBottom", out.columns)


class TestScanAllCli(unittest.TestCase):

    def setUp(self) -> None:
        scan._spotCache = _buildSpotDf()

    def tearDown(self) -> None:
        scan._spotCache = None

    def test_allFlagCallsScanAll(self) -> None:
        fake = pd.DataFrame([
            {"symbol": "600000", "name": "浦发银行",
             "currentPrice": 12.34, "asOfDate": "2024-03-01",
             "bottomCount": 1, "latestBottomDate": "2024-03-01",
             "latestBottomGrade": "validTrend", "latestBottomLow": 10.0,
             "hsbCount": 1, "bestHsbStatus": "confirmed",
             "bestHsbScore": 0.8, "bestHsbNeckline": 17.0,
             "bestHsbTargetClassic": 22.0,
             "bestHsbTargetConservative": 17.85},
        ])
        with mock.patch.object(scan, "scanAll", return_value=fake) as m:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = scan.main(["--all", "--workers", "4",
                                "--markets", "sh,sz"])
        self.assertEqual(rc, 0)
        m.assert_called_once()
        _, kwargs = m.call_args
        self.assertEqual(kwargs["markets"], ["sh", "sz"])
        self.assertEqual(kwargs["workers"], 4)
        self.assertTrue(kwargs["hitOnly"])
        self.assertIn("600000", buf.getvalue())

    def test_csvOutput(self) -> None:
        import os
        import tempfile

        fake = pd.DataFrame([
            {"symbol": "600000", "name": "浦发银行",
             "currentPrice": 12.34, "asOfDate": "2024-03-01",
             "bottomCount": 1, "latestBottomDate": "2024-03-01",
             "latestBottomGrade": "validTrend", "latestBottomLow": 10.0,
             "hsbCount": 1, "bestHsbStatus": "confirmed",
             "bestHsbScore": 0.8, "bestHsbNeckline": 17.0,
             "bestHsbTargetClassic": 22.0,
             "bestHsbTargetConservative": 17.85},
        ])
        tmp = tempfile.NamedTemporaryFile(suffix=".csv",
                                          delete=False, mode="w")
        tmp.close()
        try:
            with mock.patch.object(scan, "scanAll", return_value=fake):
                rc = scan.main(["--all", "--out", tmp.name])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.getsize(tmp.name) > 0)
            with open(tmp.name, encoding="utf-8-sig") as f:
                text = f.read()
            self.assertIn("浦发银行", text)
            self.assertIn("symbol", text)
        finally:
            os.unlink(tmp.name)

    def test_missingSymbolsWithoutAllErrors(self) -> None:
        with mock.patch.object(scan, "scanAll") as m:
            with self.assertRaises(SystemExit):
                scan.main([])
        m.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
