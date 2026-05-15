"""形态扫描页：一键扫全 A 股，tab 切换展示底分型 / 头肩底。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from webapp import services


def _renderHsbChart(symbol: str, days: int) -> None:
    """拉取 K 线和头肩底匹配数据，绘制 plotly 蜡烛图 + 形态标注。"""
    with st.spinner(f"加载 {symbol} K 线数据…"):
        data = services.fetchHsbChartData(symbol, days)

    kline = data["kline"]
    matches = data["matches"]
    name = data["name"]

    if kline.empty:
        st.warning(f"{symbol} K 线数据为空")
        return

    kline["date"] = pd.to_datetime(kline["date"])

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=kline["date"],
        open=kline["open"],
        high=kline["high"],
        low=kline["low"],
        close=kline["close"],
        name="K线",
        increasing_line_color="#ef5350",
        decreasing_line_color="#26a69a",
    ))

    if isinstance(matches, pd.DataFrame) and not matches.empty:
        best = matches.iloc[0]
        _annotateHsbPattern(fig, kline, best)

    fig.update_layout(
        title=f"{symbol} {name} — 头肩底形态",
        xaxis_title="日期",
        yaxis_title="价格",
        xaxis_rangeslider_visible=False,
        height=600,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)

    if isinstance(matches, pd.DataFrame) and not matches.empty:
        best = matches.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("状态", str(best.get("status", "")))
        c2.metric("评分", f"{best.get('score', 0):.4f}")
        c3.metric("颈线价", f"{best.get('necklinePrice', 0):.2f}")
        c4.metric("目标价(经典)", f"{best.get('targetPriceClassic', 0):.2f}")

        buyPt = best.get("buyPoint")
        if buyPt:
            _BUY_LABELS = {
                "rightShoulder": "第一买点（右肩企稳·激进）",
                "breakout": "第二买点（颈线突破·标准）",
                "pullback": "第三买点（回抽确认·保守）",
            }
            st.info(f"当前买点：**{_BUY_LABELS.get(buyPt, buyPt)}**")


def _annotateHsbPattern(fig: go.Figure, kline: pd.DataFrame,
                        match: pd.Series) -> None:
    """在 plotly figure 上标注一个头肩底形态。"""
    dates = kline["date"]

    lsIdx = match.get("leftShoulderIdx")
    headIdx = match.get("headIdx")
    rsIdx = match.get("rightShoulderIdx")
    h1Idx = match.get("leftNecklineIdx")
    h2Idx = match.get("rightNecklineIdx")

    if any(v is None or pd.isna(v) for v in (lsIdx, headIdx, rsIdx, h1Idx, h2Idx)):
        return

    lsIdx, headIdx, rsIdx = int(lsIdx), int(headIdx), int(rsIdx)
    h1Idx, h2Idx = int(h1Idx), int(h2Idx)

    lsDate = dates.iloc[lsIdx] if lsIdx < len(dates) else None
    headDate = dates.iloc[headIdx] if headIdx < len(dates) else None
    rsDate = dates.iloc[rsIdx] if rsIdx < len(dates) else None
    h1Date = dates.iloc[h1Idx] if h1Idx < len(dates) else None
    h2Date = dates.iloc[h2Idx] if h2Idx < len(dates) else None

    if any(d is None for d in (lsDate, headDate, rsDate, h1Date, h2Date)):
        return

    lsPrice = float(match.get("leftShoulderPrice", 0))
    headPrice = float(match.get("headPrice", 0))
    rsPrice = float(match.get("rightShoulderPrice", 0))
    h1Price = float(match.get("leftNecklinePrice", 0))
    h2Price = float(match.get("rightNecklinePrice", 0))

    priceRange = max(h1Price, h2Price) - headPrice
    labelOffset = priceRange * 0.08 if priceRange > 0 else 0.5

    fig.add_vrect(
        x0=lsDate, x1=rsDate,
        fillcolor="rgba(100, 149, 237, 0.08)",
        line_width=0,
        annotation_text="头肩底区间",
        annotation_position="top left",
        annotation_font_size=11,
        annotation_font_color="cornflowerblue",
    )

    neckSlope = float(match.get("necklineSlope", 0))
    neckExtendIdx = min(len(dates) - 1, rsIdx + 15)
    neckExtendDate = dates.iloc[neckExtendIdx]
    neckExtendPrice = h1Price + neckSlope * (neckExtendIdx - h1Idx)

    fig.add_trace(go.Scatter(
        x=[h1Date, h2Date, neckExtendDate],
        y=[h1Price, h2Price, neckExtendPrice],
        mode="lines+markers",
        line=dict(color="orange", width=2, dash="dash"),
        marker=dict(size=8, color="orange", symbol="circle"),
        name="颈线",
    ))
    fig.add_annotation(
        x=h1Date, y=h1Price + labelOffset * 0.5,
        text=f"H1 {h1Price:.2f}", showarrow=False,
        font=dict(size=10, color="orange"),
    )
    fig.add_annotation(
        x=h2Date, y=h2Price + labelOffset * 0.5,
        text=f"H2 {h2Price:.2f}", showarrow=False,
        font=dict(size=10, color="orange"),
    )

    fig.add_trace(go.Scatter(
        x=[lsDate, headDate, rsDate],
        y=[lsPrice - labelOffset, headPrice - labelOffset, rsPrice - labelOffset],
        mode="markers",
        marker=dict(size=10, color=["#1976D2", "#D32F2F", "#1976D2"],
                    symbol=["triangle-up", "triangle-up", "triangle-up"]),
        name="关键点",
        showlegend=True,
    ))

    for ptDate, ptPrice, ptLabel, ptColor in [
        (lsDate, lsPrice, "左肩", "#1976D2"),
        (headDate, headPrice, "头部", "#D32F2F"),
        (rsDate, rsPrice, "右肩", "#1976D2"),
    ]:
        fig.add_annotation(
            x=ptDate, y=ptPrice - labelOffset * 1.5,
            text=f"<b>{ptLabel}</b><br>{ptPrice:.2f}",
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
            arrowcolor=ptColor, ax=0, ay=30,
            font=dict(size=11, color=ptColor),
            bordercolor=ptColor, borderwidth=1, borderpad=3,
            bgcolor="rgba(255,255,255,0.85)",
        )

    fig.add_trace(go.Scatter(
        x=[lsDate, headDate, rsDate],
        y=[lsPrice, headPrice, rsPrice],
        mode="lines",
        line=dict(color="rgba(100, 100, 100, 0.4)", width=1.5, dash="dot"),
        showlegend=False,
    ))

    breakoutDate = match.get("breakoutDate")
    breakoutPrice = match.get("breakoutPrice")
    if breakoutDate is not None and not (isinstance(breakoutDate, float) and pd.isna(breakoutDate)):
        fig.add_trace(go.Scatter(
            x=[pd.to_datetime(breakoutDate)],
            y=[float(breakoutPrice)],
            mode="markers+text",
            marker=dict(size=14, color="#FF6F00", symbol="triangle-up"),
            text=["突破"],
            textposition="top center",
            textfont=dict(size=11, color="#FF6F00"),
            name="突破点",
        ))


st.set_page_config(page_title="形态扫描", page_icon="🔍", layout="wide")
st.title("形态扫描")

st.markdown(
    """
扫描全 A 股，识别**底分型**和**头肩底**形态。

- **底分型**：筛选当日新形成的底分型股票，辅助捕捉短期低点信号。
- **头肩底**：标记形态起始日、颈线价格与买点价格，辅助中期反转判断。

> 全市场约 5000 只股票，扫描耗时视网络和并发数而定（通常 5~15 分钟）。
    """
)

# ── 参数区 ────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    marketOpts = st.multiselect("市场", ["sh（沪市）", "sz（深市）", "bj（北交所）"],
                                default=["sh（沪市）", "sz（深市）"],
                                help="北交所数据覆盖差，建议不勾选")
with col2:
    days = st.number_input("回溯交易日", min_value=60, max_value=500,
                           value=250, step=10,
                           help="回溯交易日数（250 交易日 ≈ 1 年）")
with col3:
    workers = st.number_input("并发线程", min_value=1, max_value=32,
                              value=8, step=1,
                              help="线程越多速度越快，但过高可能触发限流")

runBtn = st.button("开始扫描", type="primary")

# ── 扫描逻辑（结果存入 session_state）─────────────────────────────────────
if runBtn:
    progressBar = st.progress(0.0, text="准备扫描全 A 股…")
    statusText = st.empty()

    def _progressCb(done: int, total: int) -> None:
        pct = done / total if total > 0 else 0.0
        progressBar.progress(pct, text=f"已扫描 {done} / {total} 只股票…")
        statusText.caption(f"进度 {pct * 100:.1f}%  |  已完成 {done} 只")

    markets = [m.split("（")[0] for m in marketOpts] if marketOpts else ["sh", "sz"]

    try:
        with st.spinner("扫描中，请耐心等待…"):
            scanResult: pd.DataFrame = services.runFullScan(
                days=int(days),
                workers=int(workers),
                markets=markets,
                progressCb=_progressCb,
            )
    except Exception as exc:
        progressBar.empty()
        statusText.empty()
        st.error(f"扫描失败：{exc}")
        st.stop()

    progressBar.progress(1.0, text="扫描完成")
    statusText.empty()

    st.session_state["scanResult"] = scanResult

# ── 结果展示（两个 tab）──────────────────────────────────────────────────
scanResult = st.session_state.get("scanResult")

if scanResult is None or (isinstance(scanResult, pd.DataFrame) and scanResult.empty):
    if runBtn:
        st.info("未扫描到任何形态。")
    st.stop()

if not isinstance(scanResult, pd.DataFrame) or scanResult.empty:
    st.stop()

tab1, tab2 = st.tabs(["底分型（当日新形成）", "头肩底"])

# ── tab1: 底分型 ─────────────────────────────────────────────────────────
with tab1:
    st.caption(
        "**形态**：阳包阴 / 十字星底 / 三过一　"
        "**信号日期**：形态确认日　"
        "**支撑位**：形态窗口最低价"
    )

    cbfDf = services.filterCurrentBottomFractal(scanResult)
    if cbfDf.empty:
        st.info("未找到当前刚形成底分型的股票。")
    else:
        st.success(f"共 **{len(cbfDf)}** 只股票当前形成底分型")
        st.dataframe(
            cbfDf,
            use_container_width=True,
            hide_index=True,
            column_config={
                "代码": st.column_config.TextColumn("代码", width=70),
                "名称": st.column_config.TextColumn("名称", width=90),
                "形态": st.column_config.TextColumn("形态", width=90),
                "信号日期": st.column_config.TextColumn("信号日期", width=100),
                "支撑位": st.column_config.NumberColumn("支撑位", format="%.2f"),
                "现价": st.column_config.NumberColumn("现价", format="%.2f"),
            },
        )
        csvData = cbfDf.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇ 下载 CSV", csvData,
                           file_name="current_bottom_fractal.csv", mime="text/csv")

# ── tab2: 头肩底 ─────────────────────────────────────────────────────────
with tab2:
    onlyBreakout = st.checkbox("仅显示已突破颈线", value=False,
                               help="勾选后只显示 breakout/confirmed 状态")

    hsbDf = services.scanHeadShoulderBottom(scanResult=scanResult,
                                            onlyBreakout=onlyBreakout)
    if hsbDf.empty:
        st.info("未找到符合条件的头肩底形态股票。")
    else:
        # ── 筛选区 ──────────────────────────────────────────────────────
        fCol1, fCol2, _fCol3 = st.columns([1, 1, 2])

        with fCol1:
            allStatuses = sorted(hsbDf["状态"].dropna().unique().tolist())
            statusFilter = st.multiselect(
                "状态筛选",
                options=allStatuses,
                default=allStatuses,
                help="选择要显示的形态状态",
            )

        with fCol2:
            scoreMin, scoreMax = 0.0, 1.0
            if "评分" in hsbDf.columns:
                validScores = hsbDf["评分"].dropna()
                if not validScores.empty:
                    scoreMin = float(validScores.min())
                    scoreMax = float(validScores.max())
            minScore = st.slider(
                "最低评分",
                min_value=0.0,
                max_value=1.0,
                value=max(scoreMin, 0.5),
                step=0.05,
                help="只显示评分 ≥ 此值的结果",
            )

        filtered = hsbDf.copy()
        if statusFilter:
            filtered = filtered[filtered["状态"].isin(statusFilter)]
        if "评分" in filtered.columns:
            filtered = filtered[filtered["评分"].fillna(0) >= minScore]
        filtered = filtered.reset_index(drop=True)

        # ── 结果展示 ────────────────────────────────────────────────────
        st.divider()
        st.success(f"共 **{len(hsbDf)}** 只命中，筛选后 **{len(filtered)}** 只（按评分降序）")

        st.caption(
            "**形态起始日**：左肩低点日期　"
            "**突破日**：收盘站上颈线且放量日（买入触发日）　"
            "**颈线价**：右肩反弹高点价格　"
            "**买点价**：突破日实际收盘价　"
            "**动态颈线价**：突破日颈线外推理论价　"
            "**目标价(经典)**：颈线 × 2 − 头部低点"
        )

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True,
            column_config={
                "代码": st.column_config.TextColumn("代码", width=70),
                "名称": st.column_config.TextColumn("名称", width=90),
                "形态起始日": st.column_config.TextColumn("形态起始日", width=100),
                "突破日": st.column_config.TextColumn("突破日", width=100),
                "颈线价": st.column_config.NumberColumn("颈线价", format="%.2f"),
                "买点价": st.column_config.NumberColumn("买点价", format="%.2f"),
                "动态颈线价": st.column_config.NumberColumn("动态颈线价", format="%.2f"),
                "目标价(经典)": st.column_config.NumberColumn("目标价(经典)", format="%.2f"),
                "评分": st.column_config.NumberColumn("评分", format="%.4f"),
                "状态": st.column_config.TextColumn("状态", width=80),
                "现价": st.column_config.NumberColumn("现价", format="%.2f"),
            },
        )

        csvData = filtered.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇ 下载 CSV", csvData,
                           file_name="head_shoulder_bottom.csv", mime="text/csv")

        # ── K 线图区 ────────────────────────────────────────────────────
        st.divider()
        st.subheader("头肩底 K 线图")

        symbolList = filtered["代码"].dropna().unique().tolist()
        if symbolList:
            selectedSymbol = st.selectbox(
                "选择股票查看 K 线",
                options=symbolList,
                format_func=lambda s: f"{s}  {filtered.loc[filtered['代码'] == s, '名称'].iloc[0]}"
                if not filtered.loc[filtered["代码"] == s, "名称"].empty else s,
            )
            if selectedSymbol:
                _renderHsbChart(selectedSymbol, int(days))
