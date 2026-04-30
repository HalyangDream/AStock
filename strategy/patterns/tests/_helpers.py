"""测试数据构造工具。"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


def buildKline(rows: List[dict], startDate: str = "2024-01-01") -> pd.DataFrame:
    """从 dict 列表构造 K 线 DataFrame。

    每项必需键: open, high, low, close, volume；date 可省略（自动按交易日递增）。
    """
    dates = pd.bdate_range(start=startDate, periods=len(rows)).strftime("%Y-%m-%d")
    out = []
    for i, row in enumerate(rows):
        out.append({
            "date": row.get("date", dates[i]),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        })
    return pd.DataFrame(out)


def interpolateKeypoints(keypoints: List[Tuple[int, float, float]],
                         noise: float = 0.0,
                         baseVolume: float = 1000.0,
                         volumeSpikeAt: List[int] = None,
                         volumeSpikeMul: float = 3.0,
                         startDate: str = "2024-01-01") -> pd.DataFrame:
    """在关键点之间线性插值生成 K 线。

    keypoints: [(dayIndex, high, low), ...]；dayIndex 必须递增且从 0 起。
    插值后每日 close = (high+low)/2，open 取上一日 close（首日取当日 close）。
    volumeSpikeAt: 放量的 dayIndex 列表。
    """
    volumeSpikeAt = volumeSpikeAt or []
    keypoints = sorted(keypoints, key=lambda x: x[0])
    totalDays = keypoints[-1][0] + 1

    highs = np.zeros(totalDays)
    lows = np.zeros(totalDays)
    for (d0, h0, l0), (d1, h1, l1) in zip(keypoints[:-1], keypoints[1:]):
        seg = d1 - d0
        for k in range(seg + 1):
            idx = d0 + k
            t = k / seg if seg else 0
            highs[idx] = h0 + (h1 - h0) * t
            lows[idx] = l0 + (l1 - l0) * t

    if noise > 0:
        rng = np.random.default_rng(42)
        highs += rng.normal(0, noise, totalDays)
        lows -= np.abs(rng.normal(0, noise, totalDays))

    closes = (highs + lows) / 2
    opens = np.concatenate([[closes[0]], closes[:-1]])
    volumes = np.full(totalDays, baseVolume, dtype=float)
    for d in volumeSpikeAt:
        if 0 <= d < totalDays:
            volumes[d] *= volumeSpikeMul

    dates = pd.bdate_range(start=startDate, periods=totalDays).strftime("%Y-%m-%d")
    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
