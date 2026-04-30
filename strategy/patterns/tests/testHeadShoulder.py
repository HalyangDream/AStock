"""头肩底 / 头肩顶识别用例。"""

from __future__ import annotations

import unittest

import pandas as pd

from strategy.patterns.headShoulder import (
    findHeadShoulderBottom,
    findHeadShoulderTop,
)
from strategy.patterns.tests._helpers import interpolateKeypoints


def _buildHsbKline(withBreakout: bool = True) -> pd.DataFrame:
    """构造标准头肩底 K 线。

    Keypoints 设计（总 50 天）：
      D0  (20, 19) -- 初始段
      D10 (15, 14) -- 左肩 L1
      D16 (17, 16) -- 颈线 H1
      D25 (13, 12) -- 头部 L2（最低）
      D31 (17, 16) -- 颈线 H2（与 H1 等高，严格对称）
      D40 (15, 14) -- 右肩 L3（= L1）
      D44 (17.5, 16) -- 回抽
      D47 (19, 17.5) -- 确认突破上行
    """
    keypoints = [
        (0,  20.0, 19.0),
        (10, 15.0, 14.0),
        (16, 17.0, 16.0),
        (25, 13.0, 12.0),
        (31, 17.0, 16.0),
        (40, 15.0, 14.0),
    ]
    if withBreakout:
        keypoints += [
            (44, 17.5, 16.5),
            (47, 19.0, 17.5),
            (49, 19.5, 18.0),
        ]
    else:
        # 右肩形成后小幅回升但不突破颈线 17，维持 forming 状态
        keypoints += [
            (45, 15.8, 15.2),
            (50, 16.5, 15.5),
        ]
    return interpolateKeypoints(
        keypoints,
        baseVolume=1000,
        volumeSpikeAt=[47, 48] if withBreakout else [],
        volumeSpikeMul=4.0,
    )


class TestHeadShoulderBottom(unittest.TestCase):

    def test_detectConfirmedBreakout(self) -> None:
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5, conservativeTargetPct=0.05,
        )
        self.assertFalse(out.empty)
        top = out.iloc[0]
        self.assertIn(top["status"], ("breakout", "confirmed"))
        self.assertAlmostEqual(top["headPrice"], 12.0, places=1)
        self.assertAlmostEqual(top["leftShoulderPrice"], 14.0, places=1)
        self.assertAlmostEqual(top["rightShoulderPrice"], 14.0, places=1)
        self.assertAlmostEqual(top["necklinePrice"], 17.0, places=1)
        # 经典目标价 = 2×17 - 12 = 22
        self.assertAlmostEqual(top["targetPriceClassic"], 22.0, places=1)
        # 保守目标价 = 17 × 1.05
        self.assertAlmostEqual(top["targetPriceConservative"], 17.85, places=2)
        self.assertGreater(top["score"], 0.6)

    def test_detectForming(self) -> None:
        """未发生突破时 status=forming。"""
        df = _buildHsbKline(withBreakout=False)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
        )
        self.assertFalse(out.empty)
        self.assertEqual(out["status"].iloc[0], "forming")
        self.assertTrue(pd.isna(out["breakoutDate"].iloc[0]))

    def test_asymmetricShoulderRejected(self) -> None:
        """两肩高度差 30%，应被过滤。"""
        keypoints = [
            (0,  20.0, 19.0),
            (10, 15.0, 14.0),   # L1
            (16, 17.0, 16.0),   # H1
            (25, 13.0, 12.0),   # L2
            (31, 17.0, 16.0),   # H2
            (40, 12.0, 10.0),   # L3 明显低于 L1（不对称）
            (48, 19.0, 17.5),
        ]
        df = interpolateKeypoints(keypoints, baseVolume=1000)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.05,
        )
        self.assertTrue(out.empty)

    def test_shortDfReturnsEmpty(self) -> None:
        df = interpolateKeypoints([(0, 10, 9), (20, 12, 11)])
        out = findHeadShoulderBottom(df, minSpan=30)
        self.assertTrue(out.empty)


class TestHeadShoulderTop(unittest.TestCase):

    def test_detectTop(self) -> None:
        """对称：头在最高，两肩稍低，向下突破颈线。"""
        keypoints = [
            (0,  10.0,  9.0),
            (10, 15.0, 14.0),   # L1 左肩高点
            (16, 13.0, 12.0),   # H1 颈线谷
            (25, 17.0, 16.0),   # L2 头部最高
            (31, 13.0, 12.0),   # H2 颈线谷
            (40, 15.0, 14.0),   # L3 右肩
            (47,  9.0,  8.0),
            (49,  8.0,  7.0),
        ]
        df = interpolateKeypoints(
            keypoints, baseVolume=1000,
            volumeSpikeAt=[47, 48], volumeSpikeMul=4.0,
        )
        out = findHeadShoulderTop(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
        )
        self.assertFalse(out.empty)
        top = out.iloc[0]
        self.assertAlmostEqual(top["headPrice"], 17.0, places=1)
        self.assertIn(top["status"], ("breakout", "confirmed"))
        # 经典目标价 = 2×12 - 17 = 7
        self.assertAlmostEqual(top["targetPriceClassic"], 7.0, places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
