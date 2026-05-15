"""webapp 首页。

启动：
    streamlit run webapp/app.py

侧边栏会自动列出 webapp/pages/ 下的子页面。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 国内数据源（eastmoney/sina/tencent）需要直连，禁用代理
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

import requests as _requests
_OrigSession = _requests.Session
class _NoProxySession(_OrigSession):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.trust_env = False
_requests.Session = _NoProxySession

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
