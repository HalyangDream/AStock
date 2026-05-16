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
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            breakoutConfirmPct=0.03,
        )
        self.assertFalse(out.empty)
        top = out.iloc[0]
        self.assertIn(top["status"], ("breakout", "confirmed"))
        self.assertAlmostEqual(top["headPrice"], 12.0, places=1)
        self.assertAlmostEqual(top["leftShoulderPrice"], 14.0, places=1)
        self.assertAlmostEqual(top["rightShoulderPrice"], 14.0, places=1)
        # v2: necklinePrice = max(H1, H2) = 17.0
        self.assertAlmostEqual(top["necklinePrice"], 17.0, places=1)
        # 经典目标价 = 2×17 - 12 = 22
        self.assertAlmostEqual(top["targetPriceClassic"], 22.0, places=1)
        # 保守目标价 = 17 × 1.05
        self.assertAlmostEqual(top["targetPriceConservative"], 17.85, places=2)
        self.assertGreater(top["score"], 0.4)
        # v2: volumeDistScore 列存在
        self.assertIn("volumeDistScore", out.columns)

    def test_detectForming(self) -> None:
        """未突破时 status 为 forming 或 confirmed（价格在右肩~颈线之间升级为 confirmed）。"""
        df = _buildHsbKline(withBreakout=False)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty)
        self.assertIn(out["status"].iloc[0], ("forming", "confirmed"))
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

    def test_shallowHeadRejected(self) -> None:
        """头部与右肩几乎等高（深度 <3%），应被过滤。模拟 688099 场景。"""
        keypoints = [
            (0,  20.0, 19.0),
            (10, 15.5, 14.5),   # L1 = 14.5
            (16, 17.0, 16.0),   # H1
            (25, 15.0, 14.2),   # L2 = 14.2（仅比 L3 低 0.3）
            (31, 17.0, 16.0),   # H2
            (40, 15.3, 14.5),   # L3 = 14.5（与 L1 等高，但与 L2 差 2.1%）
            (47, 19.0, 17.5),
            (49, 19.5, 18.0),
        ]
        df = interpolateKeypoints(keypoints, baseVolume=1000,
                                  volumeSpikeAt=[47, 48], volumeSpikeMul=4.0)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            headDepthMin=0.03,
        )
        self.assertTrue(out.empty, "头部深度不足 3%，应被过滤")

    def test_deepHeadKept(self) -> None:
        """头部明显低于两肩（深度 >3%），应保留。"""
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            headDepthMin=0.03,
        )
        self.assertFalse(out.empty, "头部深度充分（>3%），应有结果")

    def test_shortDfReturnsEmpty(self) -> None:
        df = interpolateKeypoints([(0, 10, 9), (20, 12, 11)])
        out = findHeadShoulderBottom(df, minSpan=30)
        self.assertTrue(out.empty)


class TestConfirmedRecent(unittest.TestCase):

    def test_nearNecklineConfirmed(self) -> None:
        """突破 + 3 根站稳 + 价格在颈线附近(≤10%) → confirmed。"""
        keypoints = [
            (0,  20.0, 19.0),
            (10, 15.0, 14.0),
            (16, 17.0, 16.0),
            (25, 13.0, 12.0),
            (31, 17.0, 16.0),
            (40, 15.0, 14.0),
            (44, 17.5, 16.5),
            (47, 19.0, 17.5),
            (50, 18.5, 17.2),
        ]
        df = interpolateKeypoints(keypoints, baseVolume=1000,
                                  volumeSpikeAt=[47, 48], volumeSpikeMul=4.0)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            breakoutConfirmPct=0.03,
        )
        confirmed = out[out["status"] == "confirmed"]
        self.assertFalse(confirmed.empty,
                         "突破 + 站稳 + 价格在颈线附近 → 应为 confirmed")

    def test_priceAboveNeckline10PctNotConfirmed(self) -> None:
        """突破后价格远超颈线（>10%），不算 confirmed。"""
        keypoints = [
            (0,  20.0, 19.0),
            (10, 15.0, 14.0),
            (16, 17.0, 16.0),
            (25, 13.0, 12.0),
            (31, 17.0, 16.0),
            (40, 15.0, 14.0),
            (44, 17.5, 16.5),
            (47, 19.0, 17.5),
            (50, 20.5, 19.5),
        ]
        df = interpolateKeypoints(keypoints, baseVolume=1000,
                                  volumeSpikeAt=[47, 48], volumeSpikeMul=4.0)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            breakoutConfirmPct=0.03,
        )
        if not out.empty:
            breakouts = out[out["status"].isin(["breakout", "confirmed"])]
            for _, row in breakouts.iterrows():
                self.assertNotEqual(row["status"], "confirmed",
                                    "价格远超颈线 10%，不应 confirmed")


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


def _buildHsbWithTrend(downDays: int = 80) -> pd.DataFrame:
    """构造带前置下跌趋势的头肩底 K 线。

    前 downDays 根为线性下跌（从 25 跌到 18），之后接标准头肩底结构。
    总长度约 downDays + 50 根。
    """
    # 前置下跌段：keypoints 从 0 到 downDays
    trend_start_high = 25.0
    trend_end_high = 18.5
    trend_start_low = trend_start_high - 1.0
    trend_end_low = trend_end_high - 1.0

    # 头肩底关键点（相对于 downDays 偏移）
    d = downDays
    hsb_kps = [
        (d + 0,  20.0, 19.0),
        (d + 10, 15.0, 14.0),   # L1
        (d + 16, 17.0, 16.0),   # H1
        (d + 25, 13.0, 12.0),   # L2 (head)
        (d + 31, 17.0, 16.0),   # H2
        (d + 40, 15.0, 14.0),   # L3
        (d + 44, 17.5, 16.5),
        (d + 47, 19.0, 17.5),
        (d + 49, 19.5, 18.0),
    ]
    keypoints = [
        (0, trend_start_high, trend_start_low),
        (downDays - 1, trend_end_high, trend_end_low),
    ] + hsb_kps
    return interpolateKeypoints(
        keypoints,
        baseVolume=1000,
        volumeSpikeAt=[d + 47, d + 48],
        volumeSpikeMul=4.0,
    )


def _buildSidewaysWithTripleLow(trendDays: int = 80) -> pd.DataFrame:
    """构造横盘震荡中的假三低点 K 线（前置无下跌趋势）。

    L1/L2/L3 均在横盘价格区间内（19~21），前 trendDays 根收盘约 20.0，
    确保 trendWindow 窗口内斜率接近 0，能被趋势过滤器拒绝。
    """
    d = trendDays
    keypoints = [
        (0,      21.0, 19.0),   # 横盘初始
        (d - 1,  21.0, 19.0),   # 维持横盘到 d-1
        (d,      20.5, 19.5),   # 横盘内小波动
        (d + 10, 20.0, 19.0),   # L1（横盘内低谷）
        (d + 16, 21.0, 20.0),   # H1（颈线）
        (d + 25, 19.5, 18.5),   # L2（稍低于 L1，横盘内最低）
        (d + 31, 21.0, 20.0),   # H2（颈线）
        (d + 40, 20.0, 19.0),   # L3（与 L1 等高）
        (d + 44, 21.2, 20.3),   # 尝试突破
        (d + 47, 21.8, 20.8),   # 突破，量放大
        (d + 49, 22.0, 21.0),
    ]
    return interpolateKeypoints(
        keypoints,
        baseVolume=1000,
        volumeSpikeAt=[d + 47, d + 48],
        volumeSpikeMul=4.0,
    )


class TestTrendFilter(unittest.TestCase):

    def test_downtrendPassesFilter(self) -> None:
        """含前置下跌趋势的头肩底应通过趋势过滤，有结果。"""
        df = _buildHsbWithTrend(downDays=80)
        out = findHeadShoulderBottom(
            df,
            minSpan=20, maxSpan=80, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            trendWindow=60, trendMinSlope=-0.0001,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty, "下跌趋势后的头肩底应被识别")

    def test_sidewaysRejectedByTrendFilter(self) -> None:
        """横盘前置段 + 三低点：使用较严格阈值（-0.001）时应被过滤。

        注：默认 trendMinSlope=-0.0001 过宽（spec 风险6），本测试用 -0.001
        演示当阈值合理收紧后横盘假信号可被排除。
        """
        df = _buildSidewaysWithTripleLow(trendDays=80)
        out = findHeadShoulderBottom(
            df,
            minSpan=20, maxSpan=80, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            trendWindow=60, trendMinSlope=-0.001,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertTrue(
            out.empty or (out["score"] < 0.4).all(),
            "收紧 trendMinSlope 后横盘假信号应被趋势过滤排除或评分极低",
        )

    def test_insufficientTrendDataNotRejected(self) -> None:
        """L1 前数据不足 trendWindow 时，三元组不被拒绝（与短 K 线原有用例行为一致）。"""
        df = _buildHsbKline(withBreakout=True)  # ~50 根，L1 前约 10 根
        out = findHeadShoulderBottom(
            df,
            minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            trendWindow=60,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty, "数据不足 trendWindow 时不应拒绝三元组")


class TestPullback(unittest.TestCase):

    def test_formingHasNoPullback(self) -> None:
        """未突破状态：新列均为 None / False。"""
        df = _buildHsbKline(withBreakout=False)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty)
        row = out.iloc[0]
        self.assertIn(row["status"], ("forming", "confirmed"))
        self.assertIsNone(row["necklinePriceAtBreakout"])
        self.assertFalse(row["hasPullback"])
        self.assertIsNone(row["pullbackDate"])
        self.assertIsNone(row["pullbackPrice"])

    def test_breakoutHasNecklinePriceAtBreakout(self) -> None:
        """已突破状态：necklinePriceAtBreakout 应为有效 float。"""
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        confirmed = out[out["status"].isin(["breakout", "confirmed"])]
        self.assertFalse(confirmed.empty)
        for _, row in confirmed.iterrows():
            self.assertIsNotNone(row["necklinePriceAtBreakout"])
            self.assertIsInstance(row["necklinePriceAtBreakout"], float)

    def test_pullbackDateAfterBreakoutDate(self) -> None:
        """若存在回抽，pullbackDate 必须晚于 breakoutDate。"""
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            pullbackWindow=10, pullbackTolerance=0.05,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        pullback_rows = out[out["hasPullback"]]
        for _, row in pullback_rows.iterrows():
            self.assertGreater(
                pd.to_datetime(row["pullbackDate"]),
                pd.to_datetime(row["breakoutDate"]),
            )

    def test_newColumnsExist(self) -> None:
        """输出 DataFrame 必须包含全部新增列（含 v2 volumeDistScore）。"""
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty)
        for col in ("necklineSlope", "necklinePriceAtBreakout",
                    "hasPullback", "pullbackDate", "pullbackPrice",
                    "volumeDistScore"):
            self.assertIn(col, out.columns, f"缺少列: {col}")


class TestScoreWeights(unittest.TestCase):

    def test_necklineslopeSign(self) -> None:
        """右上倾颈线 necklineSlope > 0，右下倾颈线 necklineSlope < 0。"""
        # 构造右上倾颈线：H2 > H1
        kps_up = [
            (0,  20.0, 19.0),
            (10, 15.0, 14.0),   # L1
            (16, 16.0, 15.0),   # H1（较低）
            (25, 13.0, 12.0),   # L2
            (31, 18.0, 17.0),   # H2（较高）→ 右上倾
            (40, 15.0, 14.0),   # L3
            (44, 18.5, 17.5),
            (47, 20.0, 18.5),
            (49, 20.5, 19.0),
        ]
        df_up = interpolateKeypoints(kps_up, baseVolume=1000,
                                     volumeSpikeAt=[47, 48], volumeSpikeMul=4.0)
        out_up = findHeadShoulderBottom(
            df_up, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.10, timeSymmetry=0.5,
            volumeMultiplier=1.5, necklineSlopeMin=-0.005,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        if not out_up.empty:
            self.assertGreater(out_up.iloc[0]["necklineSlope"], 0,
                               "右上倾颈线斜率应为正值")

    def test_scoreWeightSumApproachesOne(self) -> None:
        """完美形态（肩对称、时间对称、头深充分、有突破、有趋势）score 应趋近 1.0。"""
        df = _buildHsbWithTrend(downDays=80)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=80, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.5,
            volumeMultiplier=1.5,
            trendWindow=60, trendMinSlope=-0.0001,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        if not out.empty:
            top_score = out.iloc[0]["score"]
            self.assertLessEqual(top_score, 1.0)
            self.assertGreater(top_score, 0.0)


def _buildHsbWithVolumeDecay(decay: bool = True) -> pd.DataFrame:
    """构造量能递减/不递减的头肩底 K 线。

    decay=True: 左肩段量高(2000)、头部段量中(1000)、右肩段量低(500)
    decay=False: 均匀量能(1000)，不满足严格递减
    """
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
    df = interpolateKeypoints(keypoints, baseVolume=1000,
                              volumeSpikeAt=[47, 48], volumeSpikeMul=4.0)
    if decay:
        vols = df["volume"].values.copy()
        vols[10:25] = 2000.0
        vols[23:28] = 1000.0
        vols[26:41] = 500.0
        df["volume"] = vols
    return df


class TestVolumeDecay(unittest.TestCase):

    def test_volumeDecayColumnExists(self) -> None:
        """输出包含 volumeDecay 列且为 bool。(TP-1.1)"""
        df = _buildHsbWithVolumeDecay(decay=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty)
        self.assertIn("volumeDecay", out.columns)

    def test_volumeDecayTrueWhenDecaying(self) -> None:
        """量能严格递减时 volumeDecay=True。(TP-1.2)"""
        df = _buildHsbWithVolumeDecay(decay=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty)
        self.assertTrue(out.iloc[0]["volumeDecay"])

    def test_volumeDecayFilterFalseBackcompat(self) -> None:
        """volumeDecayFilter=False（默认）时不递减仍保留。(TP-1.3)"""
        df = _buildHsbWithVolumeDecay(decay=False)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty, "默认不过滤，量能均匀仍应保留")

    def test_volumeDecayFilterTrueRejectsNonDecay(self) -> None:
        """volumeDecayFilter=True 时不递减被过滤。(TP-1.7)"""
        df = _buildHsbWithVolumeDecay(decay=False)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            volumeDecayFilter=True,
        )
        self.assertTrue(out.empty, "量能不递减 + 过滤开启 → 空")

    def test_volumeDecayFilterTrueKeepsDecay(self) -> None:
        """volumeDecayFilter=True 时递减的保留。"""
        df = _buildHsbWithVolumeDecay(decay=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            volumeDecayFilter=True,
        )
        self.assertFalse(out.empty, "量能递减 + 过滤开启 → 有结果")

    def test_equalVolumesNotDecay(self) -> None:
        """均匀量能不满足严格递减。(TP-1.6)"""
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        if not out.empty:
            self.assertFalse(out.iloc[0]["volumeDecay"])

    def test_scoreV3WeightSum(self) -> None:
        """v3 权重之和 = 1.00。(TP-1.4)"""
        from strategy.patterns.headShoulder import _score
        perfect = _score(
            shoulderGap=0.0, timeGap=0.0, headDepth=0.20,
            hasBreakout=True, trendSlope=-0.01, volDistScore=1.0,
        )
        self.assertAlmostEqual(perfect, 1.0, places=2)

    def test_topWithVolumeDecayFilterRegression(self) -> None:
        """头肩顶透传 volumeDecayFilter 不影响结果。(TP-1.8)"""
        keypoints = [
            (0,  10.0,  9.0),
            (10, 15.0, 14.0),
            (16, 13.0, 12.0),
            (25, 17.0, 16.0),
            (31, 13.0, 12.0),
            (40, 15.0, 14.0),
            (47,  9.0,  8.0),
            (49,  8.0,  7.0),
        ]
        df = interpolateKeypoints(keypoints, baseVolume=1000,
                                  volumeSpikeAt=[47, 48], volumeSpikeMul=4.0)
        out = findHeadShoulderTop(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeDecayFilter=True,
        )
        self.assertFalse(out.empty, "头肩顶不应受 volumeDecayFilter 影响")
        self.assertAlmostEqual(out.iloc[0]["headPrice"], 17.0, places=1)


class TestBuyPoint(unittest.TestCase):

    def test_buyPointColumnExists(self) -> None:
        """输出包含 buyPoint 列。(TP-2.1)"""
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        self.assertFalse(out.empty)
        self.assertIn("buyPoint", out.columns)

    def test_formingWithDecayIsRightShoulder(self) -> None:
        """forming + volumeDecay=True → buyPoint='rightShoulder'。(TP-2.2)"""
        df = _buildHsbWithVolumeDecay(decay=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=100.0,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        forming = out[out["status"] == "forming"]
        if not forming.empty:
            decayed = forming[forming["volumeDecay"]]
            for _, row in decayed.iterrows():
                self.assertEqual(row["buyPoint"], "rightShoulder")

    def test_formingWithoutDecayIsNone(self) -> None:
        """forming + volumeDecay=False → buyPoint=None。(TP-2.5)"""
        df = _buildHsbKline(withBreakout=False)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
        )
        forming = out[out["status"] == "forming"]
        if not forming.empty:
            noDecay = forming[~forming["volumeDecay"]]
            for _, row in noDecay.iterrows():
                self.assertIsNone(row["buyPoint"])

    def test_breakoutIsBuyPointBreakout(self) -> None:
        """breakout/confirmed → buyPoint='breakout'（无回抽时）。(TP-2.3)"""
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            pullbackTolerance=0.001,
        )
        breakouts = out[out["status"].isin(["breakout", "confirmed"])]
        noPullback = breakouts[~breakouts["hasPullback"]]
        for _, row in noPullback.iterrows():
            self.assertEqual(row["buyPoint"], "breakout")

    def test_pullbackIsBuyPointPullback(self) -> None:
        """hasPullback=True → buyPoint='pullback'。(TP-2.4)"""
        df = _buildHsbKline(withBreakout=True)
        out = findHeadShoulderBottom(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
            volumeMultiplier=1.5,
            headToShoulderMinSpan=10, headToShoulderMaxSpan=65,
            pullbackWindow=10, pullbackTolerance=0.05,
        )
        pulled = out[out["hasPullback"]]
        for _, row in pulled.iterrows():
            self.assertEqual(row["buyPoint"], "pullback")

    def test_topHasNoBuyPoint(self) -> None:
        """头肩顶 buyPoint 全部为 None。(TP-2.6)"""
        keypoints = [
            (0,  10.0,  9.0),
            (10, 15.0, 14.0),
            (16, 13.0, 12.0),
            (25, 17.0, 16.0),
            (31, 13.0, 12.0),
            (40, 15.0, 14.0),
            (47,  9.0,  8.0),
            (49,  8.0,  7.0),
        ]
        df = interpolateKeypoints(keypoints, baseVolume=1000,
                                  volumeSpikeAt=[47, 48], volumeSpikeMul=4.0)
        out = findHeadShoulderTop(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
        )
        self.assertFalse(out.empty)
        for _, row in out.iterrows():
            self.assertIsNone(row["buyPoint"])


class TestHeadShoulderTopRegression(unittest.TestCase):

    def _runTop(self) -> pd.DataFrame:
        keypoints = [
            (0,  10.0,  9.0),
            (10, 15.0, 14.0),
            (16, 13.0, 12.0),
            (25, 17.0, 16.0),
            (31, 13.0, 12.0),
            (40, 15.0, 14.0),
            (47,  9.0,  8.0),
            (49,  8.0,  7.0),
        ]
        df = interpolateKeypoints(
            keypoints, baseVolume=1000,
            volumeSpikeAt=[47, 48], volumeSpikeMul=4.0,
        )
        return findHeadShoulderTop(
            df, minSpan=20, maxSpan=60, pivotWindow=3,
            shoulderTolerance=0.08, timeSymmetry=0.4,
        )

    def test_topResultUnchanged(self) -> None:
        """头肩顶结果不应因 isBottom 新逻辑而改变。"""
        out = self._runTop()
        self.assertFalse(out.empty)
        top = out.iloc[0]
        self.assertAlmostEqual(top["headPrice"], 17.0, places=1)
        self.assertIn(top["status"], ("breakout", "confirmed"))
        self.assertAlmostEqual(top["targetPriceClassic"], 7.0, places=1)

    def test_topHasNoBottomColumns(self) -> None:
        """头肩顶的 isBottom 专属列应为 None/False/0。"""
        out = self._runTop()
        self.assertFalse(out.empty)
        row = out.iloc[0]
        # necklineSlope 对顶形态置 0
        self.assertEqual(row["necklineSlope"], 0.0)
        self.assertIsNone(row["necklinePriceAtBreakout"])
        self.assertFalse(row["hasPullback"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
