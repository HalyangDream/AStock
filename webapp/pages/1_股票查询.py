"""股票查询页：股票 / ETF / LOF + 代码 + 日期 → 中文表格 + 网格交易测试。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import datetime as dt

import pandas as pd
import streamlit as st

from webapp import services

st.set_page_config(page_title="股票查询", page_icon="📈", layout="wide")
st.title("股票查询")

# 表单
col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
with col1:
    kind = st.selectbox("类型", services._KIND_OPTS, index=0)
with col2:
    symbol = st.text_input("代码", value="600000",
                           help="6 位代码，如 600000 / 510050")
with col3:
    startDate = st.date_input("开始日期",
                              value=dt.date.today() - dt.timedelta(days=180))
with col4:
    endDate = st.date_input("结束日期", value=dt.date.today())

run = st.button("查询", type="primary")

# 查询：拉数据并写入会话缓存
if run:
    if startDate > endDate:
        st.error("开始日期晚于结束日期")
        st.stop()
    with st.spinner(f"拉取 {kind} {symbol} {startDate}~{endDate} ..."):
        try:
            df = services.fetchKline(kind, symbol, startDate, endDate)
        except Exception as exc:
            st.error(f"查询失败：{exc}")
            st.stop()
    if df is None or df.empty:
        st.session_state.pop("klineCache", None)
        st.session_state.pop("gridResult", None)
        st.warning("无数据。可能原因：代码错误、日期区间内无交易、数据源不可达。")
        st.stop()
    name = ""
    try:
        name = services.lookupName(kind, symbol)
    except Exception:
        pass
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    st.session_state.klineCache = {
        "kind": kind, "symbol": symbol, "name": name,
        "startDate": startDate, "endDate": endDate, "df": df,
    }
    st.session_state.pop("gridResult", None)

cache = st.session_state.get("klineCache")
if not cache:
    st.info("点击「查询」获取数据。")
    st.stop()

df = cache["df"]
name = cache["name"]
displaySymbol = cache["symbol"]
displayKind = cache["kind"]

# 数据表
st.success(f"共 {len(df)} 条记录 · {displaySymbol}"
           f"{' ' + name if name else ''}")
st.subheader("数据表")
displayDf = df.copy()
nameForRow = name if name else "—"
insertPos = 1 if "date" in displayDf.columns else 0
displayDf.insert(insertPos, "name", nameForRow)
st.dataframe(services.labelKline(displayDf),
             use_container_width=True, hide_index=True)

st.download_button(
    "下载 CSV",
    data=displayDf.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"{displayKind}_{displaySymbol}_"
              f"{cache['startDate']}_{cache['endDate']}.csv",
    mime="text/csv",
)

# 网格交易参数 + 寻优按钮
st.divider()
st.subheader("网格交易测试")
gcol1, gcol2 = st.columns(2)
with gcol1:
    levels = st.number_input("层数（上下各 N 档）",
                             min_value=1, max_value=50, value=10, step=1)
with gcol2:
    totalAmount = st.number_input("总金额（元）",
                                  min_value=10000.0, value=100000.0,
                                  step=10000.0)

runGrid = st.button("网格交易测试", key="run_grid_test", type="secondary")

if runGrid:
    progress = st.progress(0.0, text="开始寻优 ...")

    def _onProgress(idx, total, summaryRow):
        progress.progress(
            idx / total,
            text=(f"[{idx}/{total}] 步长 {summaryRow['spacing']:.2%} · "
                  f"总收益 {summaryRow['totalReturn']:.2%}"),
        )

    try:
        result = services.runGridOptimize(df, int(levels),
                                          float(totalAmount),
                                          progressCb=_onProgress)
        st.session_state.gridResult = result
    except Exception as exc:
        st.error(f"寻优失败：{exc}")
        st.session_state.pop("gridResult", None)
    finally:
        progress.empty()

# 渲染寻优结果
if "gridResult" in st.session_state:
    result = st.session_state.gridResult
    top = pd.DataFrame(result["top"])
    best = result["best"]

    st.divider()
    st.subheader("Top 5 候选（按总收益排序）")
    if top.empty:
        st.info("无候选结果。")
    else:
        view = top.rename(columns={
            "spacing": "步长",
            "totalReturn": "总收益",
            "annualReturn": "年化",
            "sharpe": "夏普",
            "maxDrawdown": "最大回撤",
            "winRate": "胜率",
            "tradeCount": "交易次数",
            "summary": "摘要",
        }).copy()
        view["步长"] = view["步长"].apply(lambda x: f"{x:.2%}")
        for col in ("总收益", "年化", "最大回撤", "胜率"):
            view[col] = view[col].apply(lambda x: f"{x:.2%}")
        view["夏普"] = view["夏普"].apply(lambda x: f"{x:.2f}")
        view = view[["步长", "总收益", "年化", "夏普",
                     "最大回撤", "胜率", "交易次数", "摘要"]]
        st.dataframe(view, use_container_width=True, hide_index=True)

    if best and best.get("metrics"):
        m = best["metrics"]
        st.subheader(
            f"最优组合详情：步长 {best['spacing']:.2%} · "
            f"每格 {best['shareSize']} 股 · "
            f"中心 {best.get('centerPrice', 0):.2f}"
        )
        st.code(best["summary"], language="text")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总收益", f"{m.get('totalReturn', 0):.2%}")
        c2.metric("年化", f"{m.get('annualReturn', 0):.2%}")
        c3.metric("夏普", f"{m.get('sharpe', 0):.2f}")
        c4.metric("最大回撤", f"{m.get('maxDrawdown', 0):.2%}")

        c5, c6, c7 = st.columns(3)
        c5.metric("交易次数", int(m.get("tradeCount", 0)))
        c6.metric("胜率", f"{m.get('winRate', 0):.2%}")
        c7.metric("平均持有(日)", f"{m.get('avgHoldDays', 0):.1f}")

        eq = best.get("equityCurve")
        if eq is not None and not eq.empty and "date" in eq.columns:
            st.subheader("净值曲线")
            chart = eq.set_index("date")[["value"]]
            st.line_chart(chart)

        tradeEvents = best.get("tradeEvents")
        eventsColMap = {
            "date": "日期",
            "direction": "方向",
            "price": "价格",
            "size": "数量",
            "commission": "手续费",
            "pnl": "盈亏",
            "pnlNet": "净盈亏",
        }
        if tradeEvents is not None and not tradeEvents.empty:
            st.subheader(f"交易明细（{len(tradeEvents)} 笔）")
            eventsView = tradeEvents.rename(columns=eventsColMap)
            st.dataframe(eventsView, use_container_width=True,
                         hide_index=True)
            st.download_button(
                "下载交易明细 CSV",
                data=eventsView.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"grid_trades_{displaySymbol}.csv",
                mime="text/csv",
                key="dl_grid_trades",
            )
        else:
            st.info("无交易记录")

        openPos = best.get("openPositions")
        openColMap = {
            "entryDate": "买入日",
            "entryPrice": "买入价",
            "size": "数量",
            "lastPrice": "现价",
            "unrealizedPnl": "浮动盈亏",
            "unrealizedPnlPct": "浮动收益率",
        }
        if openPos is not None and not openPos.empty:
            st.subheader(f"未平仓持仓（{len(openPos)} 笔）")
            openView = openPos.rename(columns=openColMap)
            st.dataframe(openView, use_container_width=True,
                         hide_index=True)
        else:
            st.success("全部已平仓")
