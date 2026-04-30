"""财务摘要页。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from webapp import services

st.set_page_config(page_title="财务摘要", page_icon="📊", layout="wide")
st.title("财务摘要")

st.caption("数据源仅 eastmoney 覆盖。")

symbol = st.text_input("股票代码", value="600000")

if st.button("查询", type="primary"):
    with st.spinner(f"拉取 {symbol} 财务摘要 ..."):
        try:
            df = services.fetchFinancialAbstract(symbol)
        except Exception as exc:
            st.error(f"查询失败：{exc}")
            st.stop()

    if df is None or df.empty:
        st.warning("无数据")
        st.stop()

    st.success(f"共 {len(df)} 条记录")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "下载 CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"financial_{symbol}.csv",
        mime="text/csv",
    )
