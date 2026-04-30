# AStock

A 股 / 基金多源数据采集与形态扫描工具。

- **数据层 `astock`**：封装 AKShare，按 `eastmoney / sina / tencent` 三源分包，顶层门面提供统一函数名与自动 fallback。
- **策略层 `strategy`**：基于日 K 线的形态识别（底分型、头肩底）以及单只 / 批量 / 全市场扫描入口。
- **回测层 `backtest`**：基于 backtrader 的薄封装，输入 K 线 + 信号 DataFrame，输出净值曲线 / 交易明细 / 绩效指标。
- **网页层 `webapp`**：基于 Streamlit 的本地多页应用，覆盖 K 线查询 / 行业板块 / 资金流 / 财务摘要。
- 所有函数返回 `pandas.DataFrame`，列名统一 `lowerCamelCase`。

## 目录结构

```
AStock/
├── astock/                       数据层（多源 + 门面）
│   ├── stock.py                  股票门面：getDailyKline 等
│   ├── fund.py                   基金门面：getEtfKline / getFundNav 等
│   ├── _common.py                日期 / 代码归一化、safeCall 装饰器
│   ├── eastmoney/                东方财富源（stockApi / fundApi）
│   ├── sina/                     新浪源
│   ├── tencent/                  腾讯源
│   └── tests/                    门面层测试
├── strategy/                     策略层
│   ├── patterns/                 形态识别
│   │   ├── fractal.py            底 / 顶分型
│   │   ├── headShoulder.py       头肩底 / 头肩顶
│   │   └── _utils.py             K 线归一 / 包含合并 / 摆动点
│   ├── scan.py                   扫描入口 + CLI
│   └── tests/                    策略层测试
├── backtest/                     回测层（基于 backtrader）
│   ├── engine.py                 入口 runBacktest(kline, signals, ...)
│   ├── gridEngine.py             网格交易入口 runGridBacktest(...)
│   ├── gridOptimizer.py          步长寻优 gridOptimize(...)
│   ├── _strategy.py              内部 bt.Strategy + 印花税佣金
│   ├── results.py                cerebro 结果 → 标准 DataFrame
│   ├── metrics.py                绩效指标
│   ├── adapters.py               形态输出 → 信号 DataFrame
│   └── tests/                    回测层测试
├── webapp/                       网页层（基于 Streamlit）
│   ├── app.py                    首页入口
│   ├── services.py               UI 与底层之间的纯函数封装（可测）
│   ├── pages/                    多页约定目录
│   └── tests/                    services 层测试
└── requirements.txt
```

## 环境与安装

- Python 3.9（项目使用 `.venv`）
- 依赖：`akshare==1.18.56`、`pandas==2.3.3`、`backtrader==1.9.78.123`、`streamlit==1.40.2`

```bash
python3.9 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 数据层 `astock`

### 设计要点

- **门面 + 多源 fallback**：`source='auto'` 时按 `_SOURCE_PRIORITY` 顺序尝试，首个非空结果即返回。
- **DPI 兜底**：东财公网接口在部分 ISP 被拦时，sina / tencent 自动接管。
- **统一异常**：`_common.safeCall` 装饰器把网络异常转为空 `DataFrame`，调用方无需 try/except。
- **代码归一**：`padCode / detectMarket / withMarketPrefix` 处理 6 位 / 带前缀代码差异。

### 股票门面 `astock.stock`

| 函数 | 说明 |
|---|---|
| `getDailyKline` | 日 K 线（sina → tencent → eastmoney） |
| `getMinuteKline` | 分钟 K 线（sina / eastmoney） |
| `getRealtimeQuote` | 全 A 实时快照 |
| `getIndexKline` | 指数日线 |
| `getIndexRealtimeQuote` | 指数实时快照 |
| `getStockListA` | 全 A 股票列表 |
| `getStockListByMarket` | 按市场（sh / sz / bj）拉列表 |
| `getIndustryList` | 行业板块列表 |
| `getIndustryConstituents` | 行业成分股 |
| `getFundFlowIndividual` | 个股资金流 |
| `getFinancialAbstract` | 财务摘要 |
| `getTradeCalendar` | 交易日历 |
| `isTradingDay` | 判断交易日 |

### 基金门面 `astock.fund`

| 函数 | 说明 |
|---|---|
| `getFundList` | 全量公募基金列表 |
| `getFundListByType` | 按类型筛选基金 |
| `getFundNav` | 单只基金净值历史 |
| `getFundRealtimeEstimate` | 实时净值估算 |
| `getFundRank` | 基金排名 |
| `getFundHoldings` | 持仓明细 |
| `getFundManagers` | 基金经理列表 |
| `getEtfList` | 全 ETF 列表 |
| `getEtfRealtimeQuote` | ETF 实时快照 |
| `getEtfKline` | ETF 日 K 线 |
| `getLofList` | LOF 列表 |
| `getLofKline` | LOF 日 K 线 |

最小调用：

```python
from astock import stock, fund

stock.getDailyKline("600000")         # auto fallback
stock.getDailyKline("600000", source="sina")
fund.getEtfKline("510050")
```

## 策略层 `strategy`

### 形态识别 `strategy.patterns`

| 函数 | 说明 |
|---|---|
| `findBottomFractal` | 底分型：3 根 K 中心严格最低 + 趋势 / 放量过滤，输出 grade |
| `findTopFractal` | 顶分型，与底对称 |
| `findHeadShoulderBottom` | 头肩底：枚举三摆动低点，按对称 / 跨度 / 颈线突破打分 |
| `findHeadShoulderTop` | 头肩顶，与底对称 |

### 扫描入口 `strategy.scan`

| 函数 | 说明 |
|---|---|
| `scanSingle` | 单只扫描，返回 dict（含底分型 + 头肩底两个 DataFrame） |
| `scanBatch` | 给定代码集合的批量扫描，返回汇总 DataFrame |
| `scanAll` | 全市场扫描；并发拉 K 线，默认只输出命中、按 `bestHsbScore` 排序 |
| `getAllSymbols` | 从 sina 全 A 快照取所有 6 位代码（可按市场过滤） |

最小调用：

```python
from strategy import scan

scan.scanSingle("600000")                   # 单只
scan.scanBatch(["600000", "000001"])        # 批量
scan.scanAll(markets=["sh", "sz"], workers=16)  # 全市场
```

## 回测层 `backtest`

### 设计要点

- **薄封装 backtrader**：用户只看 K 线 / 信号两个 DataFrame；引擎内部搭 `Cerebro + Strategy + Analyzer`。
- **撮合规则**：T+1 开盘成交、双边佣金 0.0003、卖出印花税 0.001、A 股 100 股一手、默认全仓进出。
- **输出**：`equityCurve` / `trades` / `metrics` / `summary` 一站式返回。

### 信号 DataFrame schema

| 列 | 类型 | 说明 |
|---|---|---|
| `date` | `pd.Timestamp` | 信号日；引擎在 T+1 开盘成交 |
| `signal` | `'buy'` / `'sell'` | 同一日多条取最后一条 |

### 接口

| 函数 | 说明 |
|---|---|
| `runBacktest` | 主入口，输入 K 线 + 信号，返回 dict |
| `runGridBacktest` | 等比网格回测：支持初始底仓 + close 方向触发双向交易（每档仅持一份仓位），参数：步长 / 档位数 / 每格股数；返回 dict 中含 `openPositions`（未平仓持仓） |
| `gridOptimize` | 步长寻优：固定档位 + 总金额，遍历多种步长返回 top N；中心价 = 首日 close（避免未来函数偏差） |
| `adapters.fromBottomFractal` | 底分型结果 → 信号 DataFrame（持有 holdDays 个交易日） |
| `adapters.fromHeadShoulderBottom` | 头肩底结果 → 信号 DataFrame（突破日买入） |
| `metrics.computeMetrics` | 由 equity + trades 算 sharpe / maxDD / 胜率等 |

### `runBacktest` 默认参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `initialCash` | 100000 | 初始现金 |
| `commission` | 0.0003 | 双边佣金率 |
| `stampTax` | 0.001 | 卖出印花税率 |
| `slippage` | 0.0 | 滑点比例（0 = 关闭） |
| `sizing` | `'all'` | 全仓进出，目前仅此一种 |

### 返回 dict

| key | 类型 | 内容 |
|---|---|---|
| `equityCurve` | DataFrame | `date / value / cash / pnl / returnPct` |
| `trades` | DataFrame | `entryDate / exitDate / entryPrice / exitPrice / size / pnl / pnlNet / pnlPct / barsHeld` |
| `metrics` | dict | `totalReturn / annualReturn / sharpe / maxDrawdown / winRate / tradeCount / avgHoldDays / avgPnlPct` |
| `summary` | str | 单行人类可读摘要 |

最小调用：

```python
from astock import stock
from strategy.patterns import findBottomFractal
from backtest import runBacktest, adapters

kline = stock.getDailyKline("600000")
bottoms = findBottomFractal(kline, minGrade="validTrend")
signals = adapters.fromBottomFractal(bottoms, kline, holdDays=10)
result = runBacktest(kline, signals)
print(result["summary"])
```

## 网页层 `webapp`

基于 Streamlit 的本地工具，启动一行命令：

```bash
.venv/bin/streamlit run webapp/app.py
```

打开 `http://localhost:8501`，左侧侧边栏列出 4 个子页：

| 页面 | 功能 |
|---|---|
| K线查询 | 选择股票 / ETF / LOF + 代码 + 起止日期；展示中文表格（成交量 / 成交额单位千万、换手率百分比），支持 CSV 下载，并提供网格交易步长寻优 |
| 行业板块 | Tab1 行业列表（支持名字搜索）；Tab2 输入行业名查成分股 |
| 个股资金流 | 输入股票代码查询资金流向 |
| 财务摘要 | 输入股票代码查询财务摘要 |

> 网页层不直接调底层；UI 文件只调用 `webapp/services.py` 中的纯函数，便于单测。

## CLI 参考

```bash
python -m strategy.scan [SYMBOLS...] [选项]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `SYMBOLS` | — | 1 个或多个 6 位代码；使用 `--all` 时可省略 |
| `--all` | False | 扫描全市场 A 股 |
| `--days` | 250 | 回溯交易日数（0 表示全历史） |
| `--minGrade` | validTrend | 底分型最低等级：`weak / validTrend / validVolume / strong` |
| `--hsbMinSpan` | 30 | 头肩底最小跨度（交易日） |
| `--hsbMaxSpan` | 120 | 头肩底最大跨度（交易日） |
| `--workers` | 8 | `--all` 模式并发线程数 |
| `--markets` | 全部 | `--all` 模式市场过滤，逗号分隔，如 `sh,sz,bj` |
| `--limit` | 0 | `--all` 模式只扫前 N 只（0 表示不限） |
| `--allRows` | False | `--all` 模式输出全部结果（默认仅命中） |
| `--out` | — | CSV 输出路径；留空打印到 stdout |
| `--realtime` | False | 现价使用实时快照（默认用最后收盘） |
| `--json` | False | 输出 JSON 而非表格 |

## 测试

按层运行（`astock` 走真实网络较慢，建议单独跑）：

```bash
# 离线层（策略 / 回测 / 网页 services）
.venv/bin/python -m unittest discover -s strategy -t . -p 'test*.py'
.venv/bin/python -m unittest discover -s backtest -t . -p 'test*.py'
.venv/bin/python -m unittest discover -s webapp -t . -p 'test*.py'

# 数据层（联网）
.venv/bin/python -m unittest discover -s astock -t . -p 'test*.py'
```

约定：每个包同级 `tests/` 目录，文件名 `testXxx.py`，类名 `TestXxx`。

## 已知限制

- 东财（eastmoney）部分接口在国内某些 ISP 被 DPI 拦截，已通过 sina / tencent 优先回退；但仅 eastmoney 覆盖的接口（如 `getStockListA`、行业 / 资金流 / 财务）在该环境下会返回空。
- BaoStock 暂未接入（不希望额外登录态）。
- 策略层目前只覆盖底分型与头肩底，未做信号回测、组合优化等。
- 形态识别基于日 K，分钟级未支持。
- `scanAll` 每只单独走网络拉 K 线，5000+ 只全量耗时与并发数和源稳定性强相关。
