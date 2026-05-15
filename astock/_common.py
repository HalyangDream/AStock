"""公共工具：日期/代码归一化、列名映射、异常封装。"""

from __future__ import annotations

import functools
import logging
from datetime import date, datetime
from typing import Callable, Dict, Iterable, Optional, Tuple, Union

import pandas as pd

logger = logging.getLogger(__name__)

DateLike = Union[str, date, datetime, None]


def toCompactDate(d: DateLike, default: Optional[str] = None) -> str:
    """归一化为 'YYYYMMDD'。None 时返回 default。"""
    if d is None:
        return default or ""
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y%m%d")
    s = str(d).strip().replace("-", "").replace("/", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"非法日期: {d}")
    return s


def toDashDate(d: DateLike, default: Optional[str] = None) -> str:
    """归一化为 'YYYY-MM-DD'。"""
    c = toCompactDate(d, default=default.replace("-", "") if default else None)
    if not c:
        return ""
    return f"{c[0:4]}-{c[4:6]}-{c[6:8]}"


def padCode(symbol: Union[str, int], width: int = 6) -> str:
    """将代码补零到指定位数（基金/股票/ETF 通用 6 位）。"""
    s = str(symbol).strip()
    if not s.isdigit():
        return s
    return s.zfill(width)


def detectMarket(symbol: Union[str, int]) -> str:
    """根据纯数字代码首位判断所属市场：sh / sz / bj。"""
    s = padCode(symbol)
    if not s.isdigit() or len(s) != 6:
        raise ValueError(f"非法 6 位代码: {symbol}")
    head2 = s[:2]
    head3 = s[:3]
    # 北交所：430xxx / 830xxx / 870xxx / 920xxx
    if head2 in ("43", "83", "87", "92"):
        return "bj"
    head = s[0]
    if head in ("5", "6", "9"):
        return "sh"
    if head in ("0", "1", "2", "3"):
        return "sz"
    if head in ("4", "8"):
        return "bj"
    raise ValueError(f"无法识别市场: {symbol}")


def splitSymbolAndMarket(symbol: Union[str, int]) -> Tuple[str, str]:
    """拆分出 (6 位纯代码, 'sh'/'sz'/'bj')。支持带前缀 'sh600000' / '600000.SH'。"""
    raw = str(symbol).strip().lower()
    for sep in (".", " "):
        if sep in raw:
            raw = raw.split(sep)[0] if raw.split(sep)[0].isdigit() else raw.split(sep)[-1]
    for prefix in ("sh", "sz", "bj"):
        if raw.startswith(prefix):
            return padCode(raw[len(prefix):]), prefix
    code = padCode(raw)
    return code, detectMarket(code)


def withMarketPrefix(symbol: Union[str, int]) -> str:
    """返回带市场前缀的代码，如 'sh600000'。已带前缀的原样返回（小写）。"""
    raw = str(symbol).strip().lower()
    if raw[:2] in ("sh", "sz", "bj"):
        return raw
    code, market = splitSymbolAndMarket(raw)
    return f"{market}{code}"


def renameColumns(df: pd.DataFrame, mapping: Dict[str, str],
                  keepOnly: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """重命名列；keepOnly 指定保留列名（重命名后）。未匹配列保留原名。"""
    if df is None:
        return pd.DataFrame()
    renamed = df.rename(columns=mapping)
    if keepOnly is not None:
        exists = [c for c in keepOnly if c in renamed.columns]
        renamed = renamed[exists]
    return renamed


def safeCall(emptyColumns: Optional[Iterable[str]] = None) -> Callable:
    """装饰器：异常时记录日志并返回空 DataFrame。"""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                result = fn(*args, **kwargs)
                if result is None:
                    return pd.DataFrame(columns=list(emptyColumns or []))
                return result
            except Exception as exc:  # noqa: BLE001
                logger.warning("akshare 调用失败 %s: %s", fn.__name__, exc)
                return pd.DataFrame(columns=list(emptyColumns or []))

        return wrapper

    return decorator
