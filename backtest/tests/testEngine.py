"""runBacktest 端到端测试。"""

from __future__ import annotations

import unittest

import pandas as pd

from backtest import runBacktest
from backtest.tests._helpers import buildFlatKline, buildLinearKline


class TestRunBacktest(unittest.TestCase):

    def test_emptySignalsNoTrades(self) -> None:
        kline = buildLinearKline(days=30)
        out = runBacktest(kline, pd.DataFrame(columns=["date", "signal"]))
        self.assertEqual(out["metrics"]["tradeCount"], 0)
        self.assertTrue(out["trades"].empty)
        self.assertEqual(len(out["equityCurve"]), 30)
        self.assertAlmostEqual(out["metrics"]["totalReturn"], 0.0, places=6)

    def test_buyHoldSellOnLinearTrend(self) -> None:
        kline = buildLinearKline(days=30, startPrice=10.0, dailyReturn=0.01)
        signals = pd.DataFrame([
            {"date": kline["date"].iloc[0], "signal": "buy"},
            {"date": kline["date"].iloc[-2], "signal": "sell"},
        ])
        out = runBacktest(kline, signals)
        self.assertEqual(out["metrics"]["tradeCount"], 1)
        trade = out["trades"].iloc[0]
        # T+1 开盘成交：buy 在 day1 open，sell 在 day -1 open
        self.assertGreater(trade["exitPrice"], trade["entryPrice"])
        self.assertGreater(trade["pnl"], 0)
        self.assertGreater(out["metrics"]["totalReturn"], 0)
        self.assertEqual(out["metrics"]["winRate"], 1.0)

    def test_flatMarketNearZeroReturn(self) -> None:
        kline = buildFlatKline(days=30, price=10.0)
        signals = pd.DataFrame([
            {"date": kline["date"].iloc[0], "signal": "buy"},
            {"date": kline["date"].iloc[-2], "signal": "sell"},
        ])
        out = runBacktest(kline, signals)
        self.assertEqual(out["metrics"]["tradeCount"], 1)
        trade = out["trades"].iloc[0]
        self.assertAlmostEqual(trade["entryPrice"], 10.0, places=6)
        self.assertAlmostEqual(trade["exitPrice"], 10.0, places=6)
        # 因佣金 + 印花税，pnlNet 为负
        self.assertLessEqual(trade["pnlNet"], 0.0)

    def test_commissionAffectsNet(self) -> None:
        kline = buildFlatKline(days=20, price=10.0)
        signals = pd.DataFrame([
            {"date": kline["date"].iloc[0], "signal": "buy"},
            {"date": kline["date"].iloc[-2], "signal": "sell"},
        ])
        outNoFee = runBacktest(kline, signals, commission=0.0, stampTax=0.0)
        outWithFee = runBacktest(kline, signals,
                                 commission=0.0003, stampTax=0.001)
        self.assertGreater(
            outNoFee["trades"].iloc[0]["pnlNet"],
            outWithFee["trades"].iloc[0]["pnlNet"],
        )

    def test_t1Execution(self) -> None:
        """信号在 T 日发出，应在 T+1 开盘价成交。"""
        kline = buildLinearKline(days=10, startPrice=10.0, dailyReturn=0.01)
        signals = pd.DataFrame([
            {"date": kline["date"].iloc[1], "signal": "buy"},
            {"date": kline["date"].iloc[5], "signal": "sell"},
        ])
        out = runBacktest(kline, signals, commission=0.0, stampTax=0.0)
        self.assertEqual(out["metrics"]["tradeCount"], 1)
        trade = out["trades"].iloc[0]
        self.assertAlmostEqual(
            trade["entryPrice"], float(kline["open"].iloc[2]), places=4)
        self.assertAlmostEqual(
            trade["exitPrice"], float(kline["open"].iloc[6]), places=4)

    def test_invalidSizing(self) -> None:
        with self.assertRaises(ValueError):
            runBacktest(buildFlatKline(days=10),
                        pd.DataFrame(columns=["date", "signal"]),
                        sizing="halfPosition")

    def test_missingKlineColumn(self) -> None:
        kline = buildFlatKline(days=10).drop(columns=["volume"])
        with self.assertRaises(ValueError):
            runBacktest(kline, pd.DataFrame(columns=["date", "signal"]))

    def test_summaryFormatNonEmpty(self) -> None:
        kline = buildLinearKline(days=20)
        signals = pd.DataFrame([
            {"date": kline["date"].iloc[0], "signal": "buy"},
            {"date": kline["date"].iloc[-2], "signal": "sell"},
        ])
        out = runBacktest(kline, signals)
        self.assertIn("trades=", out["summary"])
        self.assertIn("totalReturn=", out["summary"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
