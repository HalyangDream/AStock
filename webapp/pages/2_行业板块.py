"""行业板块页：列表 + 成分股 双 Tab。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from webapp import services

st.set_page_config(page_title="行业板块", page_icon="🏷️", layout="wide")
st.title("行业板块")

st.caption("数据源仅 eastmoney 覆盖；DPI 拦截环境下可能返回空。")

tabList, tabConst = st.tabs(["行业列表", "行业成分股"])

with tabList:
    if st.button("加载行业列表", type="primary"):
        with st.spinner("拉取行业列表 ..."):
            try:
                df = services.fetchIndustryList()
            except Exception as exc:
                st.error(f"查询失败：{exc}")
                st.stop()
        if df is None or df.empty:
            st.warning("无数据（可能 eastmoney 不可达）")
        else:
            st.success(f"共 {len(df)} 个板块")

            keyword = st.text_input("搜索板块名（可空）", value="")
            shown = df
            if keyword:
                if "name" in df.columns:
                    shown = df[df["name"].astype(str).str.contains(
                        keyword, case=False, na=False)]
                else:
                    shown = df[df.apply(
                        lambda r: keyword in str(r.values), axis=1)]
            st.dataframe(shown, use_container_width=True, hide_index=True)

            st.download_button(
                "下载 CSV",
                data=df.to_csv(index=False).encode("utf-8-sig"),
                file_name="industry_list.csv",
                mime="text/csv",
            )

with tabConst:
    industry = st.text_input("行业名（精确）", value="",
                             help="例如：银行、白酒、半导体")
    if st.button("查询成分股", type="primary"):
        if not industry.strip():
            st.error("请输入行业名")
            st.stop()
        with st.spinner(f"拉取 {industry} 成分股 ..."):
            try:
                df = services.fetchIndustryConstituents(industry)
            except Exception as exc:
                st.error(f"查询失败：{exc}")
                st.stop()
        if df is None or df.empty:
            st.warning(f"未找到 {industry} 或当前不可达")
        else:
            st.success(f"共 {len(df)} 只成分股")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "下载 CSV",
                data=df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"industry_{industry}.csv",
                mime="text/csv",
            )
