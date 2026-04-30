"""metrics 模块单测。"""

from __future__ import annotations

import unittest

import pandas as pd

from backtest.metrics import computeMetrics, formatSummary


def _equity(values, startDate="2024-01-02"):
    dates = pd.bdate_range(start=startDate, periods=len(values))
    init = float(values[0])
    return pd.DataFrame({
        "date": dates,
        "value": values,
        "cash": [init] * len(values),
        "pnl": [v - init for v in values],
        "returnPct": [v / init - 1 for v in values],
    })


class TestComputeMetrics(unittest.TestCase):

    def test_emptyReturnsZeros(self) -> None:
        out = computeMetrics(pd.DataFrame(), pd.DataFrame())
        self.assertEqual(out["totalReturn"], 0.0)
        self.assertEqual(out["tradeCount"], 0)

    def test_monotonicGrowth(self) -> None:
        values = [100000 * (1.001 ** i) for i in range(252)]
        eq = _equity(values)
        out = computeMetrics(eq, pd.DataFrame())
        self.assertAlmostEqual(out["totalReturn"], values[-1] / values[0] - 1,
                               places=4)
        self.assertGreater(out["annualReturn"], 0.2)
        self.assertGreater(out["sharpe"], 5.0)
        self.assertAlmostEqual(out["maxDrawdown"], 0.0, places=6)

    def test_drawdown(self) -> None:
        values = [100, 120, 90, 110, 80, 100]
        out = computeMetrics(_equity(values), pd.DataFrame())
        # 最大回撤在 120 -> 80 = -33.33%
        self.assertAlmostEqual(out["maxDrawdown"], (80 - 120) / 120, places=4)

    def test_winRate(self) -> None:
        """winRate / avgPnlPct 均基于 pnlNet 口径。"""
        eq = _equity([100, 105, 100, 102])
        trades = pd.DataFrame([
            {"pnl": 5, "pnlNet": 4.5, "barsHeld": 3, "pnlPct": 0.05,
             "entryPrice": 10.0, "size": 10},
            {"pnl": -2, "pnlNet": -2.5, "barsHeld": 4, "pnlPct": -0.02,
             "entryPrice": 10.0, "size": 10},
            {"pnl": 1, "pnlNet": 0.5, "barsHeld": 2, "pnlPct": 0.01,
             "entryPrice": 10.0, "size": 10},
        ])
        out = computeMetrics(eq, trades)
        self.assertEqual(out["tradeCount"], 3)
        # pnlNet: 4.5 > 0, -2.5 < 0, 0.5 > 0 → 2/3
        self.assertAlmostEqual(out["winRate"], 2 / 3, places=4)
        self.assertAlmostEqual(out["avgHoldDays"], 3.0, places=4)
        # avgPnlPct = mean(pnlNet / (entryPrice * size))
        expectedAvg = (4.5 / 100 + (-2.5) / 100 + 0.5 / 100) / 3
        self.assertAlmostEqual(out["avgPnlPct"], expectedAvg, places=4)


class TestFormatSummary(unittest.TestCase):

    def test_summaryString(self) -> None:
        s = formatSummary({
            "tradeCount": 5,
            "totalReturn": 0.12,
            "annualReturn": 0.15,
            "sharpe": 1.3,
            "maxDrawdown": -0.08,
            "winRate": 0.6,
            "avgHoldDays": 7.0,
        })
        self.assertIn("trades=5", s)
        self.assertIn("12.00%", s)
        self.assertIn("sharpe=1.30", s)
        self.assertIn("avgHold=7.0d", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
