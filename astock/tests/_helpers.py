"""测试共享工具：仅供 astock/**/tests 使用。"""

from __future__ import annotations

import unittest
from typing import List

import pandas as pd


def assertDfCols(tc: unittest.TestCase, df: pd.DataFrame,
                 expected: List[str], anyOf: bool = False) -> None:
    """若 df 非空，断言预期列存在。

    Args:
        tc: 调用方 TestCase 实例
        df: 待检查 DataFrame
        expected: 期望列名
        anyOf: True 表示至少命中一个；False 表示全部命中
    """
    tc.assertIsInstance(df, pd.DataFrame)
    if df.empty:
        return
    cols = set(df.columns)
    if anyOf:
        tc.assertTrue(any(c in cols for c in expected),
                      f"期望至少一个列命中 {expected}, 实际 {list(cols)[:15]}")
    else:
        missing = [c for c in expected if c not in cols]
        tc.assertFalse(missing,
                       f"缺少预期列 {missing}, 实际 {list(cols)[:15]}")
