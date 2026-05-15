# Spec：头肩底形态识别增强

**版本**：v1.0  
**日期**：2026-05-12  
**状态**：草稿，待确认

---

## 一、背景

`strategy/patterns/headShoulder.py` 已有基础头肩底识别，核心逻辑为：枚举三摆动低点 → 验证几何约束（价格/时间对称）→ 检测颈线突破 → 综合评分。

但与标准技术分析定义相比，存在以下缺失：

| 缺失要素 | 现状 | 影响 |
|---|---|---|
| 前置下降趋势验证 | 未检查 | 横盘震荡末期的三低点也会被识别为头肩底，产生大量假信号 |
| 颈线实际斜率 | 固定取 max(H1,H2) 水平线 | 向右上倾斜颈线（更强信号）与水平颈线被同等对待；突破价判断偏差 |
| 突破量基准 | 形态区间均量 | 区间跨度 30~120 日，均量偏低，量能门槛过松 |
| 突破后回抽识别 | 未识别 | 用户无法感知二次买入机会 |

---

## 二、目标

在 `findHeadShoulderBottom` 现有接口基础上：

1. 增加**前置下降趋势过滤**，排除横盘/震荡结构中的假头肩底
2. 改用**动态颈线**（H1-H2 连线），记录斜率，修正突破价计算
3. 将**突破量基准**由形态区间均量改为突破前 5 日均量
4. 识别并输出**突破后回抽**信号（二次买入机会标记）
5. 调整**评分权重**，纳入前置趋势强度维度

---

## 三、非目标

- 不支持分钟级 K 线（仍仅支持日 K）
- 不修改 `findHeadShoulderTop` 的**外部行为**；新增逻辑仅在 `isBottom=True` 分支生效，顶形态完全不受影响（见 §7.0）
- 不改变 `scanSingle / scanBatch / scanAll` 调用签名（新增参数全部有默认值）
- 不引入新的第三方库；`calcTrendSlope` 使用 `numpy.polyfit`，numpy 已作为 pandas 的传递依赖存在于虚拟环境，但**需在 requirements.txt 中显式声明**（见 §九）
- 不改变 `DataFrame` 输出中已有列的**命名**；`necklinePrice` 语义有轻微调整（见 §6.2），并连带影响 `targetPriceClassic`（见 §十一 风险5）

---

## 四、决策表

| 决策点 | 方案 A | 方案 B | 选择 |
|---|---|---|---|
| 前置趋势检测方法 | 线性回归斜率（scipy/numpy） | 简单 N 日涨跌幅 | **A**：斜率对曲折下跌更稳定，numpy 已引入无额外依赖 |
| 颈线突破价 | 动态：颈线外推到突破日 | 固定：max(H1,H2) 兼容旧逻辑 | **A**：动态颈线更精确；旧结果通过参数控制兼容性 |
| 突破量基准 | 突破前 5 日均量 | 突破前 10 日均量 | **A（5日）**：贴近主流技术分析标准（知乎/零点财经等均引用5日） |
| 回抽判断方式 | 收盘价距颈线线段 ±pct | 收盘价距固定水平颈线 ±pct | **A**：与动态颈线保持一致 |
| 评分兼容旧版 | 新旧参数并行，旧版 score 另外存一列 | 直接覆盖 score | **B（直接覆盖）**：scan 已无外部依赖 score 旧值的调用方 |

---

## 五、接口与方法签名

### 5.1 对外接口（新增参数均有默认值，向后兼容）

```python
def findHeadShoulderBottom(
    df: pd.DataFrame,
    minSpan: int = 30,
    maxSpan: int = 120,
    pivotWindow: int = 5,
    shoulderTolerance: float = 0.05,
    timeSymmetry: float = 0.4,
    volumeMultiplier: float = 1.5,
    conservativeTargetPct: float = 0.05,
    # ── 新增 ──────────────────────────────────
    trendWindow: int = 60,
    trendMinSlope: float = -0.0001,
    necklineSlopeMin: float = -0.002,
    pullbackWindow: int = 10,
    pullbackTolerance: float = 0.02,
) -> pd.DataFrame
```

### 5.2 新增内部工具函数（_utils.py）

```python
def calcTrendSlope(series: pd.Series, window: int) -> float:
    """返回 series 末尾 window 个点的线性回归斜率（每日变化量，已按首值归一化）。
    series 不足 window 点时返回 0.0。
    """
```

---

## 六、关键数据结构

### 6.1 输出 DataFrame 新增列

| 列名 | 类型 | 语义 |
|---|---|---|
| `necklineSlope` | `float` | 颈线每日斜率（正=右上倾斜，负=右下倾斜），单位：价格/日 |
| `necklinePriceAtBreakout` | `float \| None` | 突破日颈线外推价；`status='forming'` 时为 `None` |
| `hasPullback` | `bool` | 突破后是否出现回抽颈线机会 |
| `pullbackDate` | `pd.Timestamp \| None` | 回抽日期；无回抽时 `None` |
| `pullbackPrice` | `float \| None` | 回抽日收盘价；无回抽时 `None` |

### 6.2 已有列语义变更说明

| 列名 | 原语义 | 新语义 |
|---|---|---|
| `necklinePrice` | max(H1,H2) 水平颈线价 | **语义微调**：改为颈线直线在 H2 时刻的价格（= H2Price）。当颈线水平或右上倾斜时与原值相同；右下倾斜时两者存在差异，但均为 H2 端点价，不影响 `fromHeadShoulderBottom` adapter 的信号生成逻辑 |
| `score` | 四维评分（权重见下） | 五维评分（新增前置趋势维度），数值域仍 [0, 1] |

### 6.3 评分权重（新）

| 维度 | 权重 | 计算说明 |
|---|---|---|
| 肩部价格对称 | 0.30 | `max(0, 1 - shoulderGap/0.05)` |
| 时间对称 | 0.20 | `max(0, 1 - timeGap/0.4)` |
| 头部深度 | 0.20 | `min(1, headDepth/0.15)` |
| 突破加分 | 0.20 | `0.20 if hasBreakout else 0.0` |
| 前置趋势强度 | 0.10 | `min(1, abs(trendSlope) / 0.005)`（斜率归一至 0.5% / 日封顶） |

---

## 七、过滤逻辑说明

### 7.0 顶/底共用函数隔离原则（重要）

`_findHeadShoulder`、`_buildMatch`、`_findBreakout` 为顶底共用函数。所有新增参数（`trendWindow`、`trendMinSlope`、`necklineSlopeMin`、`pullbackWindow`、`pullbackTolerance`）**必须透传至这些函数**，但：
- 趋势过滤（§7.1）、颈线斜率过滤（§7.2）、突破价修改（§7.4）、回抽识别（§7.5）**只在 `isBottom=True` 时执行**
- `isBottom=False`（头肩顶）时，上述逻辑完全跳过，行为与改动前一致

### 7.1 前置趋势过滤（新增，仅 `isBottom=True`，在三元组枚举阶段执行）

- 取 `df["close"]` 在 L1 前 `trendWindow` 个交易日的序列
- **若该序列长度 < `trendWindow`（数据不足）**：趋势过滤跳过（不拒绝该三元组），趋势评分计 0
- 若数据充足：调用 `calcTrendSlope(series, trendWindow)` 计算归一化斜率
  - `slope > trendMinSlope`（默认 -0.0001）→ 拒绝；否则通过

### 7.2 颈线斜率过滤（新增）

- `necklineSlope = (H2Price - H1Price) / (H2Idx - H1Idx)`
- `necklineSlope < necklineSlopeMin`（默认 -0.002）→ 跳过（颈线过于向右下倾斜）

### 7.3 突破量基准改动

- 突破检测时，取 `df["volume"].iloc[breakoutIdx-5 : breakoutIdx]` 均值作为基准
- 若突破日前可用数据不足 5 根，取实际可用数根均值（`min_periods=1`）

### 7.4 动态颈线突破价

- 突破日的颈线判断价应基于颈线在该日期的外推值（线性插值），而非固定的水平线
- `necklinePriceAtBreakout` 输出该外推值，供上层业务判断使用

### 7.5 回抽识别（突破后执行）

- 仅在 `status in ('breakout', 'confirmed')` 时执行，`status='forming'` 时 `hasPullback=False`
- 在突破日之后的 `pullbackWindow` 个交易日内，若收盘价回落至当日颈线外推价附近（偏差 ≤ `pullbackTolerance`），则视为回抽
- 取首次满足条件的日期为 `pullbackDate`

---

## 八、错误处理矩阵

| 异常场景 | 行为 |
|---|---|
| `trendWindow` 前数据不足（L1 之前 < trendWindow 根） | 趋势过滤跳过（不拒绝三元组），趋势评分计 0；不报错 |
| 突破前可用 K 线不足 5 根 | 用实际可用根数均值，不报错 |
| H1Idx == H2Idx（颈线零跨度） | `necklineSlope` 置 0.0，通过斜率过滤 |
| `df` 为空（`df.empty=True`） | 返回空 DataFrame（沿用 `normalizeKline` 现有行为），不抛错 |
| `df` 非空但缺必要列 | 沿用 `normalizeKline` 抛出 `ValueError` |
| `pullbackWindow` 超出 df 范围 | 截断到 df 末尾，若无满足条件的回抽则 `hasPullback=False` |
| `status='forming'`（无突破） | `hasPullback=False`，`pullbackDate=None`，`pullbackPrice=None` |

---

## 九、影响范围

| 文件 | 改动类型 |
|---|---|
| `strategy/patterns/headShoulder.py` | 主逻辑：新增隔离判断（§7.0）+ 5处 bottom 专属改动（趋势过滤、斜率记录、量基准、突破价、回抽） |
| `strategy/patterns/_utils.py` | 新增 `calcTrendSlope` 函数 |
| `strategy/patterns/tests/testHeadShoulder.py` | 新增测试用例；现有 bottom 用例需传 `trendWindow` 适配短 K 线（见注①） |
| `requirements.txt` | 新增 `numpy` 显式声明（当前版本由 pandas 传递依赖提供，建议固化） |

`scan.py`、`backtest/adapters.py`、`webapp/` 均**无需修改**。

> **注①**：现有测试使用约 50 根 K 线、L1 位于第 10 根附近，前置数据远不足默认 `trendWindow=60`。按 §7.1 规则，数据不足时趋势过滤跳过，现有测试结果**不应**因此变为空——实现时需确认此行为正确。新用例若测试趋势过滤逻辑，需单独构造含足够前置下跌段的 K 线。

---

## 十、验收标准

1. `findHeadShoulderBottom(df)` 零参调用不抛出异常；与旧版相比，`score`、`necklinePriceAtBreakout` 列为新增或变更，`breakoutPrice` 可能因量基准改变而减少（属预期行为），其余已有列语义不变
2. `status='forming'` 的结果中 `necklinePriceAtBreakout / pullbackDate / pullbackPrice` 均为 `None`
3. `hasPullback=True` 的记录中 `pullbackDate > breakoutDate` 必须成立
4. 给定一组已知头肩底形态的测试 K 线（含前置下跌趋势）：`score ≥ 0.7` 且 `status='confirmed'`
5. 给定一组横盘震荡中的假三低点 K 线：前置趋势过滤后结果为空 DataFrame
6. 评分之和权重 = `0.30 + 0.20 + 0.20 + 0.20 + 0.10 = 1.00`，各维度独立验证
7. `necklineSlope` 在颈线右上倾斜时为正值、右下倾斜时为负值
8. 给定一组弱横盘 K 线（价格波动 <3%、60日内无明显下跌趋势、人工构造三低点）：当 `trendWindow` 数据充足时，前置趋势过滤后结果为空 DataFrame 或 `score < 0.4`
9. `findHeadShoulderTop` 在改动前后输出结果**完全一致**（回归验证共用函数隔离正确）

---

## 十一、风险清单

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| `_findHeadShoulder` 为顶底共用，新增逻辑若未做 `isBottom` 隔离将悄然影响头肩顶 | **高** | 实现时必须在每处新增逻辑前加 `if isBottom:` 判断；测试须包含"头肩顶在改动后结果不变"的回归用例 |
| 前置趋势过滤过严，漏掉 V 形反弹型头肩底 | 中 | `trendMinSlope` 默认值宽松（-0.0001）；用户可调整 |
| `necklinePrice` 从 max(H1,H2) 改为 H2Price，连带导致 `targetPriceClassic`（= 2×颈线 - 头部价）和 scan 输出的 `bestHsbNeckline`、`bestHsbTargetClassic` 同步变化 | 中 | 影响范围已知且可控（仅颈线右下倾斜时有差异，且该情形被 `necklineSlopeMin` 大量过滤）；需在验收中对比旧版数值 |
| 前5日量基准使部分原来通过的突破不再通过（结果变少） | 低 | 属预期行为（过滤伪突破）；如需还原可调高 `volumeMultiplier` |
| `trendMinSlope=-0.0001` 等效于 60 日跌幅仅 ~0.6%，对弱震荡假信号抑制有限 | 中 | 验收须补"弱横盘"样本（价格波动 <3%、无明显趋势）：期望该样本被过滤或评分显著低于真实头肩底 |
| numpy 未在 requirements.txt 显式声明，当前由 pandas 传递提供；若环境变动可能丢失 | 低 | 在 requirements.txt 中显式固化 numpy 版本 |
