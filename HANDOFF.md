# AStock 项目交接文档

## 一、项目概述

A 股 / 基金多源数据采集、形态扫描、网格交易回测工具。四层架构：

- **数据层 `astock/`** — AKShare 封装，eastmoney / sina / tencent 三源分包 + 门面 fallback
- **策略层 `strategy/`** — 底分型、头肩底形态识别 + 全市场扫描 CLI
- **回测层 `backtest/`** — backtrader 薄封装 + 网格交易回测 + 步长寻优
- **网页层 `webapp/`** — Streamlit 多页应用（K 线查询 / 行业 / 资金流 / 财务摘要 + 网格交易测试）

**环境**：Python 3.9，`.venv` 虚拟环境，依赖见 `requirements.txt`。

**启动 Web 应用**：

```bash
.venv/bin/streamlit run webapp/app.py
```

**测试命令**（backtest 层 40 个用例全部通过）：

```bash
.venv/bin/python -m unittest discover -s backtest -t . -p 'test*.py' -v
.venv/bin/python -m unittest discover -s strategy -t . -p 'test*.py' -v
.venv/bin/python -m unittest discover -s webapp -t . -p 'test*.py' -v
.venv/bin/python -m unittest discover -s astock -t . -p 'test*.py' -v   # 联网，较慢
```

---

## 二、已完成的工作（按时间线）

### 2.1 数据层（稳定，无待改项）

- eastmoney / sina / tencent 三源分包，`astock/stock.py` + `astock/fund.py` 门面统一
- `source='auto'` fallback 优先级：sina > tencent > eastmoney（避开 DPI 拦截）
- `_common.safeCall` 装饰器统一异常处理
- 股票 13 个函数 + 基金 11 个函数全部实现
- BaoStock 暂未接入（不希望额外登录态）

### 2.2 策略层（稳定，无待改项）

- `strategy/patterns/fractal.py` — 底分型 / 顶分型（严格 3 bar + 包含合并 + 趋势/放量分级）
- `strategy/patterns/headShoulder.py` — 头肩底 / 头肩顶（3 摆动点 + 对称/跨度/颈线打分）
- `strategy/scan.py` — CLI 入口：`scanSingle` / `scanBatch` / `scanAll`（ThreadPoolExecutor 并发）

### 2.3 回测层 — 信号回测（稳定）

- `backtest/engine.py` — `runBacktest(kline, signals)`，T+1 开盘成交
- `backtest/_strategy.py` — `SignalStrategy` + `StampTaxCommission`（佣金 0.0003 + 印花税 0.001）+ `EquityAnalyzer`
- `backtest/adapters.py` — 形态结果 → 信号 DataFrame 转换器
- `backtest/results.py` — cerebro 输出 → 标准 DataFrame
- `backtest/metrics.py` — 绩效指标（winRate / avgPnlPct 优先用 `pnlNet` 净收益口径）

### 2.4 回测层 — 网格交易（最近主要工作，刚稳定）

**核心文件 `backtest/_gridStrategy.py`** 经历了多轮重构：

| 版本 | 关键变化 |
|---|---|
| v1 | 空仓低吸网格，close 判断，无底仓 |
| v2 | 加初始底仓（Market 单），改 high/low 触发 |
| v3 | 改 close 方向触发（消除日内顺序歧义），加 `_filledLevels` 每档单次持仓 |
| v4（当前） | 修 `_level()` 浮点精度（epsilon 吸附），卖出改为"最高 N 个已填充档位"（修复底仓上涨不卖），`_openTrades` 从 FIFO list 改为 per-level dict（level-aware 配对） |

**当前 `_gridStrategy.py` 设计要点**：

- **中心价**：外部传入（寻优器传首日 close），消除未来函数偏差
- **档位计算**：`_level(price)` = `floor(log(price/center)/log(1+spacing))`，精确网格线时 epsilon 吸附（`_LEVEL_EPS = 1e-9`）
- **每档仅持一份**：`_filledLevels: Set[int]` 跟踪，买→卖→买 严格循环
- **初始底仓**：首根 bar 对 initLevel-1 到 -gridLevels 下 Market 单，次日开盘成交
- **触发方向**：只看 close — closeLevel < lastLevel 只 buy，closeLevel > lastLevel 只 sell
- **买入范围**：`range(lastLevel-1, closeLevel-1, -1)`，跳过已填充档位
- **卖出范围**：`sorted(_filledLevels, reverse=True)[:sellCount]`，卖最高 N 个已填充档
- **拒单回滚**：`_orderLevelMap` 映射 orderRef→level，Canceled/Margin/Rejected 时恢复 `_filledLevels`
- **交易配对**：Level-aware（`_openTrades: Dict[int, dict]`），卖出 level L 精确关闭 level L 的买入记录

**`backtest/gridOptimizer.py`**：

- `centerPrice = sortedKline["close"].iloc[0]`（首日 close）
- `autoShareSize`：总资金 / (levels x 2)，下半底仓、上半补仓弹药
- 遍历 11 档 DEFAULT_SPACINGS，按 totalReturn 排序，返回 top 5

**`backtest/gridEngine.py`**：

- `runGridBacktest` 搭建 Cerebro，读取 `strat._tradeLog` 和 `list(strat._openTrades.values())`
- 返回 `{ equityCurve, trades, openPositions, metrics, summary }`

### 2.5 网页层（稳定）

- `webapp/pages/1_K线查询.py` — K 线查询 + 网格交易测试（层数 / 总金额输入 → Top5 候选 + 最优详情 + 净值曲线 + 交易明细 + 未平仓）
- `webapp/services.py` — 纯函数封装，文案已同步为"中心价 = 首日 close"
- 其他 3 个页面（行业板块 / 资金流 / 财务摘要）功能完整

---

## 三、当前测试覆盖

`backtest/tests/` 共 5 个测试文件，约 40 个测试用例，全部通过：

- **testGridEngine.py**（16 个）：参数校验、震荡交易、V 形卖出、纯上涨卖底仓、小资金跳过、未平仓、底仓建立、单 bar、close 方向过滤、多 level 跳跃、极端偏离、不重复买、level-aware 配对、浮点精度
- **testGridOptimizer.py**（6 个）：autoShareSize + gridOptimize（中心价首日 close、排序、进度回调）
- **testMetrics.py**（5 个）：空输入、单调增长、回撤、胜率(pnlNet)、摘要格式
- **testEngine.py**（7 个）：信号回测基础
- **testAdapters.py**（5 个）：形态→信号转换
- **testServices.py**（1 个）：webapp 服务层

---

## 四、已修复的关键 Bug 记录

| Bug | 根因 | 修复方式 |
|---|---|---|
| `_level()` 浮点精度误判（floor 多减一档） | `math.floor(log(...))` 在价格精确落网格线时会低一档 | 加 `_LEVEL_EPS = 1e-9` epsilon 吸附，raw 距 nearest int < eps 时取 round |
| 纯上涨市场初始底仓不卖出（tradeCount=0） | 原 sell 逻辑用 `range(lastLevel, closeLevel)`，不覆盖低档位库存 | 改为卖出 `sorted(_filledLevels, reverse=True)[:sellCount]`（最高 N 个已填充档） |
| `_filledLevels` 按档位卖但 `_openTrades` FIFO 配对 | 卖 level -1 实际关闭的是最早买入（可能是 level -5） | `_openTrades` 从 `List[dict]` 改为 `Dict[int, dict]`，按 level 精确配对 |
| 网格交易 0 交易 + centerPrice 极低（0.01） | `_lastLevel` 不更新导致策略冻结 + centerPrice 用 median 引入未来函数 | `_lastLevel` 每次都更新；centerPrice 改为首日 close |
| `ImportError: relative import beyond top-level` | unittest discover 缺少 `-t .` 参数 | 命令改为 `.venv/bin/python -m unittest discover -s astock -t . -p 'test*.py'` |
| `ModuleNotFoundError: webapp` | Streamlit 把脚本目录设为 sys.path[0] | 各入口文件头部注入项目根到 sys.path |

---

## 五、已知限制 / 待改进方向

- **东财 DPI 拦截**：eastmoney 在部分 ISP 被拦，已通过 sina/tencent 优先回退；仅 eastmoney 覆盖的接口在该环境下返回空
- **BaoStock 未接入**：不希望额外登录态
- **分钟级网格**：当前只支持日 K 线
- **止损/止盈**：网格没有全局止损或单笔止损机制
- **动态中心价**：中心价固定首日 close，长周期回测中价格大幅偏移后网格可能失效
- **组合回测**：当前只支持单标的
- **形态识别**：仅底分型 + 头肩底，未做更多形态

---

## 六、代码规范

- 类名 UpperCamelCase，公开变量 lowerCamelCase，私有变量 _lowerCamelCase
- 所有函数返回 `pandas.DataFrame`，列名统一 lowerCamelCase
- 测试约定：包内 `tests/` 目录，文件名 `testXxx.py`，类名 `TestXxx`
- 不主动生成文档文件，不主动生成用例示例
- 修改前先分析方案让用户确认，再动代码
- 回复始终用中文简体，开头以"小磊"称呼

---

## 七、关键文件速查

| 文件 | 作用 |
|---|---|
| `backtest/_gridStrategy.py` | 网格策略核心（最近改动最多） |
| `backtest/gridEngine.py` | 网格回测入口，搭建 Cerebro |
| `backtest/gridOptimizer.py` | 步长寻优，遍历 11 档 spacing |
| `backtest/metrics.py` | 绩效指标（pnlNet 优先） |
| `backtest/results.py` | backtrader 输出 → DataFrame |
| `backtest/engine.py` | 信号回测入口 |
| `backtest/_strategy.py` | 信号策略 + 印花税佣金 |
| `backtest/adapters.py` | 形态→信号转换器 |
| `webapp/services.py` | UI 服务层 |
| `webapp/pages/1_K线查询.py` | K 线查询 + 网格交易 UI |
| `webapp/app.py` | Streamlit 首页入口 |
| `astock/stock.py` | 股票门面（13 个函数） |
| `astock/fund.py` | 基金门面（11 个函数） |
| `astock/_common.py` | 日期/代码归一、safeCall 装饰器 |
| `strategy/scan.py` | 全市场形态扫描 CLI |
| `strategy/patterns/fractal.py` | 底分型 / 顶分型 |
| `strategy/patterns/headShoulder.py` | 头肩底 / 头肩顶 |
| `README.md` | 项目说明文档 |
| `requirements.txt` | 依赖清单 |

---

## 八、目录结构

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
│   ├── _gridStrategy.py          内部网格 bt.Strategy
│   ├── _strategy.py              内部信号 bt.Strategy + 印花税佣金
│   ├── results.py                cerebro 结果 → 标准 DataFrame
│   ├── metrics.py                绩效指标
│   ├── adapters.py               形态输出 → 信号 DataFrame
│   └── tests/                    回测层测试
├── webapp/                       网页层（基于 Streamlit）
│   ├── app.py                    首页入口
│   ├── services.py               UI 与底层之间的纯函数封装
│   ├── pages/                    多页约定目录
│   └── tests/                    services 层测试
├── requirements.txt
├── README.md
└── HANDOFF.md                    本文档
```
