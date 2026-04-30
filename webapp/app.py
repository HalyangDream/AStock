"""webapp 首页。

启动：
    streamlit run webapp/app.py

侧边栏会自动列出 webapp/pages/ 下的子页面。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

st.set_page_config(
    page_title="AStock 本地工具",
    page_icon="📈",
    layout="wide",
)

st.title("AStock 本地数据工具")

st.markdown(
    """
基于本项目 `astock` 数据层的本地查询界面。从左侧侧边栏选择功能：

- **K线查询**：股票 / ETF / LOF + 起止日期
- **行业板块**：板块列表与成分股
- **个股资金流**：单只股票的资金流向
- **财务摘要**：单只股票的财务摘要

> 数据源走 `auto` 自动 fallback（sina → tencent → eastmoney）。
> 仅 eastmoney 覆盖的接口（行业 / 资金流 / 财务）在 DPI 拦截环境下可能返回空。
    """
)
