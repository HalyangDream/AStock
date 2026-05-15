"""形态扫描入口：对单只 / 批量股票执行底分型 + 头肩底识别。

CLI:
    python -m strategy.scan 600000
    python -m strategy.scan 600000 000001 600519
    python -m strategy.scan 600000 --days 500 --realtime
    python -m strategy.scan 600000 --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List, Optional

import pandas as pd

from astock import stock as _stock
from astock._common import detectMarket, padCode

from .patterns import findBottomFractal, findHeadShoulderBottom, isCurrentBottomFractal

logger = logging.getLogger(__name__)

_MARKET_PREFIXES = ("sh", "sz", "bj")


def _extractCode(raw: str) -> Optional[str]:
    """从原始 symbol 提取 6 位纯数字代码。

    兼容两种格式：纯数字 '600000' 和带前缀 'sh600000' / 'bj920000'。
    """
    s = raw.strip().lower()
    for prefix in _MARKET_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.zfill(6)
    if len(s) == 6 and s.isdigit():
        return s
    return None


# 全 A 实时快照缓存（用于一次性获取 name + 实时价）
_spotCache: Optional[pd.DataFrame] = None


def _loadSpot() -> pd.DataFrame:
    """懒加载全 A 实时快照；失败返回空 DataFrame。"""
    global _spotCache
    if _spotCache is None:
        df = _stock.getRealtimeQuote()
        _spotCache = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    return _spotCache


def _spotLookup(symbol: str) -> dict:
    """按代码查名称 + 实时价。返回 {'name', 'price'}。"""
    code = padCode(symbol)
    spot = _loadSpot()
    if spot.empty or "symbol" not in spot.columns:
        return {"name": "", "price": None}
    hit = spot.loc[spot["symbol"].astype(str).apply(_extractCode) == code]
    if hit.empty:
        return {"name": "", "price": None}
    row = hit.iloc[0]
    name = str(row.get("name", "") or "")
    price = None
    if "price" in row and pd.notna(row["price"]):
        try:
            price = float(row["price"])
        except (TypeError, ValueError):
            price = None
    return {"name": name, "price": price}


def scanSingle(symbol: str,
               lookbackDays: int = 250,
               minFractalGrade: str = "validTrend",
               hsbMinSpan: int = 30,
               hsbMaxSpan: int = 120,
               realtime: bool = False,
               kline: Optional[pd.DataFrame] = None,
               hsbKwargs: Optional[dict] = None) -> dict:
    """单只股票形态扫描。

    Args:
        symbol: 6 位纯数字代码
        lookbackDays: 截取最近多少个交易日（<=0 表示不截取）
        minFractalGrade: 底分型返回的最低等级
        hsbMinSpan / hsbMaxSpan: 头肩底跨度范围（交易日）
        realtime: True 时现价取实时快照；否则用最后收盘
        kline: 预拉好的日 K 线（列 date/open/high/low/close/volume），
               提供时不再走网络
        hsbKwargs: 透传给 findHeadShoulderBottom 的额外参数

    Returns dict:
        symbol, name, currentPrice, asOfDate, lookbackDays,
        bottomFractals: DataFrame,
        headShoulderBottoms: DataFrame
    """
    code = padCode(symbol)

    if kline is None:
        df = _stock.getDailyKline(code)
    else:
        df = kline.copy()

    if isinstance(df, pd.DataFrame) and not df.empty and lookbackDays and lookbackDays > 0:
        df = df.tail(lookbackDays).reset_index(drop=True)

    lookup = _spotLookup(code)
    name = lookup["name"]

    if df is None or df.empty:
        return {
            "symbol": code,
            "name": name,
            "currentPrice": lookup["price"] if realtime else None,
            "asOfDate": None,
            "lookbackDays": lookbackDays,
            "bottomFractals": pd.DataFrame(),
            "headShoulderBottoms": pd.DataFrame(),
            "currentBottom": None,
        }

    if realtime and lookup["price"] is not None:
        currentPrice = lookup["price"]
    else:
        currentPrice = float(df["close"].iloc[-1])

    asOfDate = pd.Timestamp(df["date"].iloc[-1]).strftime("%Y-%m-%d")

    bottoms = findBottomFractal(df, minGrade=minFractalGrade)
    _extra = hsbKwargs or {}
    hsbs = findHeadShoulderBottom(df, minSpan=hsbMinSpan, maxSpan=hsbMaxSpan, **_extra)
    curBottom = isCurrentBottomFractal(df)

    return {
        "symbol": code,
        "name": name,
        "currentPrice": currentPrice,
        "asOfDate": asOfDate,
        "lookbackDays": lookbackDays,
        "bottomFractals": bottoms,
        "headShoulderBottoms": hsbs,
        "currentBottom": curBottom,
    }


def _summaryRow(res: dict) -> dict:
    """把 scanSingle 的结果压平为一行汇总。"""
    bf = res.get("bottomFractals")
    hsb = res.get("headShoulderBottoms")
    row = {
        "symbol": res.get("symbol"),
        "name": res.get("name"),
        "currentPrice": res.get("currentPrice"),
        "asOfDate": res.get("asOfDate"),
        "bottomCount": len(bf) if isinstance(bf, pd.DataFrame) else 0,
        "latestBottomDate": None,
        "latestBottomGrade": None,
        "latestBottomLow": None,
        "hsbCount": len(hsb) if isinstance(hsb, pd.DataFrame) else 0,
        "bestHsbStatus": None,
        "bestHsbScore": None,
        "bestHsbNeckline": None,
        "bestHsbTargetClassic": None,
        "bestHsbTargetConservative": None,
        "bestHsbLeftShoulderDate": None,
        "bestHsbBreakoutDate": None,
        "bestHsbBreakoutPrice": None,
        "bestHsbNecklinePriceAtBreakout": None,
    }
    if isinstance(bf, pd.DataFrame) and not bf.empty:
        latest = bf.sort_values("centerDate").iloc[-1]
        row["latestBottomDate"] = pd.Timestamp(latest["centerDate"]).strftime("%Y-%m-%d")
        row["latestBottomGrade"] = str(latest["grade"])
        row["latestBottomLow"] = float(latest["centerLow"])
    if isinstance(hsb, pd.DataFrame) and not hsb.empty:
        # 取距当前最近的头肩底（按右肩日期降序，最近的排首位）
        best = hsb.sort_values("rightShoulderDate", ascending=False).iloc[0]
        row["bestHsbStatus"] = str(best["status"])
        row["bestHsbScore"] = float(best["score"])
        row["bestHsbNeckline"] = float(best["necklinePrice"])
        row["bestHsbTargetClassic"] = float(best["targetPriceClassic"])
        row["bestHsbTargetConservative"] = float(best["targetPriceConservative"])
        row["bestHsbLeftShoulderDate"] = (
            pd.Timestamp(best["leftShoulderDate"]).strftime("%Y-%m-%d")
            if pd.notna(best.get("leftShoulderDate")) else None
        )
        row["bestHsbBreakoutDate"] = (
            pd.Timestamp(best["breakoutDate"]).strftime("%Y-%m-%d")
            if pd.notna(best.get("breakoutDate")) else None
        )
        row["bestHsbBreakoutPrice"] = (
            float(best["breakoutPrice"])
            if pd.notna(best.get("breakoutPrice")) else None
        )
        row["bestHsbNecklinePriceAtBreakout"] = (
            float(best["necklinePriceAtBreakout"])
            if pd.notna(best.get("necklinePriceAtBreakout")) else None
        )

    cb = res.get("currentBottom")
    row["isCurrentBottom"] = cb is not None
    row["currentBottomDate"] = (
        pd.Timestamp(cb["signalDate"]).strftime("%Y-%m-%d") if cb else None
    )
    row["currentBottomLow"] = float(cb["lowestLow"]) if cb else None
    row["currentBottomPattern"] = cb.get("patternLabel") if cb else None

    return row


def scanBatch(symbols: Iterable[str],
              lookbackDays: int = 250,
              minFractalGrade: str = "validTrend",
              hsbMinSpan: int = 30,
              hsbMaxSpan: int = 120,
              realtime: bool = False) -> pd.DataFrame:
    """批量扫描，返回每只股票的形态汇总 DataFrame（一行一只股票）。"""
    _loadSpot()
    rows: List[dict] = []
    for sym in symbols:
        res = scanSingle(sym,
                         lookbackDays=lookbackDays,
                         minFractalGrade=minFractalGrade,
                         hsbMinSpan=hsbMinSpan,
                         hsbMaxSpan=hsbMaxSpan,
                         realtime=realtime)
        rows.append(_summaryRow(res))
    return pd.DataFrame(rows)


# ================================================================
# 全市场扫描
# ================================================================
def getAllSymbols(markets: Optional[Iterable[str]] = None) -> List[str]:
    """从 sina 全 A 实时快照中取全部 6 位代码。

    Args:
        markets: 市场过滤（'sh' / 'sz' / 'bj'），None 表示全部
    """
    spot = _loadSpot()
    if spot.empty or "symbol" not in spot.columns:
        return []
    raw = spot["symbol"].astype(str).tolist()
    codes = [_extractCode(s) for s in raw]
    codes = [c for c in codes if c is not None]

    if markets:
        allowed = {m.strip().lower() for m in markets if m}
        kept: List[str] = []
        for c in codes:
            try:
                if detectMarket(c) in allowed:
                    kept.append(c)
            except ValueError:
                continue
        codes = kept

    seen = set()
    unique: List[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def scanAll(markets: Optional[Iterable[str]] = None,
            lookbackDays: int = 250,
            minFractalGrade: str = "validTrend",
            hsbMinSpan: int = 30,
            hsbMaxSpan: int = 120,
            workers: int = 8,
            limit: Optional[int] = None,
            hitOnly: bool = True,
            progress: bool = True,
            progressEvery: int = 200,
            progressCb=None) -> pd.DataFrame:
    """全市场扫描。并发拉每只股票的日 K 线并识别形态，汇总命中。

    Args:
        markets: 市场过滤（'sh'/'sz'/'bj'）
        workers: 并发线程数（IO 密集，默认 8）
        limit: 仅扫前 N 只（调试用，None 表示全部）
        hitOnly: True 时只返回 bottomCount>0 或 hsbCount>0 的行
        progress: True 时每 progressEvery 只往 stderr 打一行进度
    """
    symbols = getAllSymbols(markets=markets)
    if limit and limit > 0:
        symbols = symbols[:limit]
    if not symbols:
        return pd.DataFrame()

    total = len(symbols)
    startTime = time.time()
    rows: List[dict] = []
    hitCount = 0
    doneCount = 0

    def _scanOne(sym: str) -> Optional[dict]:
        try:
            res = scanSingle(sym,
                             lookbackDays=lookbackDays,
                             minFractalGrade=minFractalGrade,
                             hsbMinSpan=hsbMinSpan,
                             hsbMaxSpan=hsbMaxSpan,
                             realtime=False)
            return _summaryRow(res)
        except Exception as exc:  # noqa: BLE001
            logger.warning("扫描失败 %s: %s", sym, exc)
            return None

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_scanOne, s): s for s in symbols}
        for fut in as_completed(futures):
            doneCount += 1
            row = fut.result()
            if row is None:
                if progress and (doneCount % progressEvery == 0 or doneCount == total):
                    _printProgress(doneCount, total, hitCount, startTime)
                continue
            isHit = (
                (row.get("bottomCount") or 0) > 0
                or (row.get("hsbCount") or 0) > 0
                or row.get("isCurrentBottom", False)
            )
            if isHit:
                hitCount += 1
            if (not hitOnly) or isHit:
                rows.append(row)
            if progress and (doneCount % progressEvery == 0 or doneCount == total):
                _printProgress(doneCount, total, hitCount, startTime)
            if progressCb is not None:
                progressCb(doneCount, total)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["bestHsbLeftShoulderDate", "bestHsbScore", "bottomCount"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    return df


def _printProgress(done: int, total: int, hit: int, startTime: float) -> None:
    elapsed = time.time() - startTime
    print(f"[{done}/{total}] elapsed={elapsed:.1f}s hit={hit}",
          file=sys.stderr, flush=True)


# ================================================================
# 打印 / 序列化
# ================================================================
def _formatSingle(result: dict) -> str:
    """单只扫描结果的终端友好格式。"""
    lines = [
        "",
        f"========== {result['symbol']} {result['name']} ==========",
        f"现价: {result['currentPrice']}  |  截至: {result['asOfDate']}  "
        f"|  回溯: {result['lookbackDays']} 日",
        "",
        "-- 底分型 --",
    ]
    bf = result["bottomFractals"]
    if not isinstance(bf, pd.DataFrame) or bf.empty:
        lines.append("(无)")
    else:
        cols = ["centerDate", "centerLow", "centerHigh",
                "trendOk", "volumeOk", "grade"]
        show = bf[[c for c in cols if c in bf.columns]].copy()
        if "centerDate" in show.columns:
            show["centerDate"] = show["centerDate"].astype(str).str[:10]
        lines.append(show.tail(10).to_string(index=False))

    lines.append("")
    lines.append("-- 头肩底 --")
    hsb = result["headShoulderBottoms"]
    if not isinstance(hsb, pd.DataFrame) or hsb.empty:
        lines.append("(无)")
    else:
        cols = ["leftShoulderDate", "headDate", "rightShoulderDate",
                "necklinePrice", "status",
                "targetPriceClassic", "targetPriceConservative", "score"]
        show = hsb[[c for c in cols if c in hsb.columns]].copy()
        for c in ("leftShoulderDate", "headDate", "rightShoulderDate"):
            if c in show.columns:
                show[c] = show[c].astype(str).str[:10]
        lines.append(show.head(5).to_string(index=False))

    lines.append("")
    lines.append("-- 当前底分型 --")
    cb = result.get("currentBottom")
    if cb:
        lines.append(
            f"形态: {cb.get('patternLabel', '')}  "
            f"|  日期: {pd.Timestamp(cb['signalDate']).strftime('%Y-%m-%d')}  "
            f"|  支撑位: {cb['lowestLow']:.2f}"
        )
    else:
        lines.append("(无)")

    return "\n".join(lines)


def _resultToJsonable(result: dict) -> dict:
    """把 dict 中的 DataFrame 转成可 JSON 序列化的 list。"""
    out = dict(result)
    for key in ("bottomFractals", "headShoulderBottoms"):
        df = out.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.copy()
            for c in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    df[c] = df[c].astype(str).str[:10]
            out[key] = df.to_dict(orient="records")
        else:
            out[key] = []
    return out


# ================================================================
# CLI
# ================================================================
def _buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m strategy.scan",
        description="股票形态扫描：底分型 + 头肩底",
    )
    parser.add_argument("symbols", nargs="*",
                        help="股票代码（1 个或多个）；使用 --all 时可省略")
    parser.add_argument("--all", dest="scanAll", action="store_true",
                        help="扫描全市场 A 股")
    parser.add_argument("--days", type=int, default=250,
                        help="回溯交易日数（默认 250，0 表示全历史）")
    parser.add_argument("--minGrade", default="validTrend",
                        choices=["weak", "validTrend", "validVolume", "strong"],
                        help="底分型最低等级（默认 validTrend）")
    parser.add_argument("--hsbMinSpan", type=int, default=30,
                        help="头肩底最小跨度（默认 30）")
    parser.add_argument("--hsbMaxSpan", type=int, default=120,
                        help="头肩底最大跨度（默认 120）")
    parser.add_argument("--workers", type=int, default=8,
                        help="--all 模式并发线程数（默认 8）")
    parser.add_argument("--markets", default="",
                        help="--all 模式市场过滤，逗号分隔，如 sh,sz,bj；留空即全部")
    parser.add_argument("--limit", type=int, default=0,
                        help="--all 模式只扫前 N 只（0 表示不限）")
    parser.add_argument("--allRows", action="store_true",
                        help="--all 模式输出全部结果（默认只输出命中）")
    parser.add_argument("--out", default="",
                        help="CSV 输出路径；留空则打印到 stdout")
    parser.add_argument("--realtime", action="store_true",
                        help="现价使用实时快照（默认用最后收盘）")
    parser.add_argument("--json", action="store_true",
                        help="输出 JSON 而非表格")
    return parser


def _writeOrPrint(summary: pd.DataFrame, out: str, asJson: bool) -> None:
    if out:
        summary.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"已写出 {len(summary)} 行 → {out}",
              file=sys.stderr, flush=True)
        return
    if asJson:
        print(summary.to_json(orient="records",
                              force_ascii=False, indent=2))
    else:
        print(summary.to_string(index=False) if not summary.empty else "(无命中)")


def main(argv: Optional[List[str]] = None) -> int:
    parser = _buildParser()
    args = parser.parse_args(argv)

    if args.scanAll:
        markets = [m.strip() for m in args.markets.split(",") if m.strip()] or None
        summary = scanAll(
            markets=markets,
            lookbackDays=args.days,
            minFractalGrade=args.minGrade,
            hsbMinSpan=args.hsbMinSpan,
            hsbMaxSpan=args.hsbMaxSpan,
            workers=args.workers,
            limit=args.limit or None,
            hitOnly=not args.allRows,
        )
        _writeOrPrint(summary, args.out, args.json)
        return 0

    if not args.symbols:
        parser.error("请提供 symbols，或使用 --all 扫描全市场")

    if len(args.symbols) == 1:
        result = scanSingle(args.symbols[0],
                            lookbackDays=args.days,
                            minFractalGrade=args.minGrade,
                            hsbMinSpan=args.hsbMinSpan,
                            hsbMaxSpan=args.hsbMaxSpan,
                            realtime=args.realtime)
        if args.out:
            _summary = pd.DataFrame([_summaryRow(result)])
            _writeOrPrint(_summary, args.out, args.json)
        elif args.json:
            print(json.dumps(_resultToJsonable(result),
                             ensure_ascii=False, indent=2, default=str))
        else:
            print(_formatSingle(result))
    else:
        summary = scanBatch(args.symbols,
                            lookbackDays=args.days,
                            minFractalGrade=args.minGrade,
                            hsbMinSpan=args.hsbMinSpan,
                            hsbMaxSpan=args.hsbMaxSpan,
                            realtime=args.realtime)
        _writeOrPrint(summary, args.out, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
