# 头肩底形态识别增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有 `findHeadShoulderBottom` 基础上补足前置趋势过滤、动态颈线、突破量基准修正、回抽识别四项缺失要素，提升识别精度。

**Architecture:** 在 `_utils.py` 新增 `calcTrendSlope` 工具函数；在 `headShoulder.py` 的共用函数链（`_findHeadShoulder → _buildMatch → _findBreakout`）中透传新参数，所有新增行为均通过 `if isBottom:` 隔离，确保头肩顶行为不变。

**Tech Stack:** Python 3.9、pandas 2.x、numpy 2.0.2（已为传递依赖，需显式固化）

---

## 共享契约区

### §A.1 `findHeadShoulderBottom` 对外签名（新增 5 个参数，均有默认值）

```python
def findHeadShoulderBottom(
    df, minSpan=30, maxSpan=120, pivotWindow=5,
    shoulderTolerance=0.05, timeSymmetry=0.4,
    volumeMultiplier=1.5, conservativeTargetPct=0.05,
    trendWindow=60, trendMinSlope=-0.0001,
    necklineSlopeMin=-0.002,
    pullbackWindow=10, pullbackTolerance=0.02,
) -> pd.DataFrame
```

### §A.2 `calcTrendSlope` 签名（新增到 `_utils.py`）

```python
def calcTrendSlope(series: pd.Series, window: int) -> float:
    """末尾 window 个点线性回归斜率，已按首值归一化（price/price/day）。
    数据不足 window 点时返回 0.0。"""
```

### §A.3 `_findHeadShoulder` 内部签名变更（新增参数透传链）

```python
def _findHeadShoulder(df, isBottom, minSpan, maxSpan, pivotWindow,
                      shoulderTolerance, timeSymmetry, volumeMultiplier,
                      conservativeTargetPct,
                      trendWindow, trendMinSlope, necklineSlopeMin,
                      pullbackWindow, pullbackTolerance) -> pd.DataFrame

def _buildMatch(df, l1, l2, l3, h1, h2, isBottom,
                volumeMultiplier, conservativeTargetPct,
                trendSlope,          # 新增：由 _findHeadShoulder 计算后传入
                pullbackWindow, pullbackTolerance) -> Optional[dict]

def _findBreakout(df, startIdx, necklinePrice, h1Idx, necklineSlope,
                  volumeMultiplier, maxLook, isBottom) -> Optional[dict]
# necklinePrice 改为在突破日做动态外推（仅 isBottom=True 时），h1Idx/necklineSlope 新增
# formWindowAvgVol 参数移除；改在函数内部取突破日前5日均量
```

### §A.4 新增输出列（由 `_buildMatch` 写入返回 dict）

| 列名 | 类型 | forming 时 |
|---|---|---|
| `necklineSlope` | `float` | 照常计算（斜率与突破状态无关） |
| `necklinePriceAtBreakout` | `float\|None` | `None` |
| `hasPullback` | `bool` | `False` |
| `pullbackDate` | `pd.Timestamp\|None` | `None` |
| `pullbackPrice` | `float\|None` | `None` |

### §A.5 评分权重（新，`_score` 函数签名同步更新）

```python
def _score(shoulderGap, timeGap, headDepth, hasBreakout, trendSlope) -> float:
    s1 = max(0.0, 1.0 - shoulderGap / 0.05) * 0.30   # 肩对称
    s2 = max(0.0, 1.0 - timeGap / 0.4)    * 0.20   # 时间对称
    s3 = min(1.0, headDepth / 0.15)        * 0.20   # 头深
    s4 = 0.20 if hasBreakout else 0.0               # 突破
    s5 = min(1.0, abs(trendSlope) / 0.005) * 0.10  # 趋势强度
    return round(s1 + s2 + s3 + s4 + s5, 4)
```

---

## Task 1: calcTrendSlope 工具函数

**Files**
- Modify: `strategy/patterns/_utils.py`
- Test: `strategy/patterns/tests/testUtils.py`

**契约锚点**
- 实现 §A.2 签名

**关键路径骨架**

```
if len(series) < 2 or window < 2: return 0.0
tail = series.iloc[-window:]
if len(tail) < 2: return 0.0
x = np.arange(len(tail), dtype=float)
coeffs = np.polyfit(x, tail.values.astype(float), 1)
base = float(tail.iloc[0]) or 1.0
return float(coeffs[0]) / base   # 归一化：斜率/首值
```

**验证**

```bash
.venv/bin/python -m unittest strategy.patterns.tests.testUtils.TestCalcTrendSlope -v
```

expected: PASS（覆盖：下跌序列斜率 < 0，横盘序列斜率 ≈ 0，数据不足返回 0.0）

---

## Task 2: 参数透传 + isBottom 隔离 + 颈线斜率记录与过滤

**Files**
- Modify: `strategy/patterns/headShoulder.py`

**契约锚点**
- `findHeadShoulderBottom / findHeadShoulderTop`：按 §A.1 补全新参数，透传至 `_findHeadShoulder`
- `_findHeadShoulder`：按 §A.3 扩参；在三元组验证后计算 `necklineSlope`；`if isBottom: necklineSlope < necklineSlopeMin → continue`
- `_buildMatch`：按 §A.3 接收 `trendSlope`；`necklineSlope` 写入返回 dict（§A.4）；`necklinePrice` 改为 `h2Price`（颈线在 H2 端点的价格，与原 max(H1,H2) 在右上倾斜时一致）
- `_score`：按 §A.5 增加 `trendSlope` 参数

**本 Task 专属约束**
- `findHeadShoulderTop` 调用 `_findHeadShoulder` 时新参数传默认值，不影响其行为
- `_buildMatch` 此时仅写入 `necklineSlope`；其余新列（`necklinePriceAtBreakout` 等）在 Task 4 补入

**关键路径骨架**

```
# _findHeadShoulder 中，得到 h1/h2 后：
necklineSlope = (h2Price - h1Price) / (h2 - h1) if h2 != h1 else 0.0
if isBottom and necklineSlope < necklineSlopeMin:
    continue
match = _buildMatch(..., trendSlope=trendSlope, ...)
```

**依赖前置 Task**
- 无（Task 1 只加 `_utils.py`，本 Task 不调用 `calcTrendSlope`）

**验证**

```bash
.venv/bin/python -m unittest strategy.patterns.tests.testHeadShoulder -v
```

expected: 全部现有用例 PASS（参数透传不改变行为；`necklineSlope` 新列存在且为 float）

---

## Task 3: 前置趋势过滤 + 突破量基准修改 + 评分权重调整

**Files**
- Modify: `strategy/patterns/headShoulder.py`
- Test: `strategy/patterns/tests/testHeadShoulder.py`（新增用例）

**契约锚点**
- 依赖 §A.2（`calcTrendSlope`，Task 1 已实现）
- 依赖 §A.5（`_score` 新签名，Task 2 已扩参）

**本 Task 专属约束（趋势过滤，仅 isBottom=True）**

```
# _findHeadShoulder 中，三元组通过几何约束后：
trendSlope = 0.0
if isBottom:
    pre = df["close"].iloc[max(0, l1 - trendWindow) : l1]
    if len(pre) >= trendWindow:
        trendSlope = calcTrendSlope(pre, trendWindow)
        if trendSlope > trendMinSlope:
            continue   # 拒绝：趋势不满足
# 数据不足 trendWindow → trendSlope 保持 0.0，不拒绝
```

**本 Task 专属约束（量基准，`_findBreakout` 内）**

```
# 移除 formWindowAvgVol 参数，改为：
vol5 = float(df["volume"].iloc[max(0, i-5):i].mean())
volBreak = volume >= vol5 * volumeMultiplier
```

**验证**

```bash
# 现有用例
.venv/bin/python -m unittest strategy.patterns.tests.testHeadShoulder.TestHeadShoulderBottom -v
# 新增：趋势过滤 + 量基准
.venv/bin/python -m unittest strategy.patterns.tests.testHeadShoulder.TestTrendFilter -v
```

expected: 全部 PASS

新用例覆盖点（在 `TestTrendFilter` 类中）：
- 横盘 K 线（trendWindow 数据充足）→ 结果为空
- 下跌趋势 K 线（trendWindow 数据充足）→ 有结果
- L1 前数据不足 trendWindow → 不过滤，结果非空（与 Task 2 现有用例一致）

---

## Task 4: 动态颈线突破价 + 回抽识别 + 新输出列

**Files**
- Modify: `strategy/patterns/headShoulder.py`
- Test: `strategy/patterns/tests/testHeadShoulder.py`（新增用例）

**契约锚点**
- §A.3（`_buildMatch` 接收 `pullbackWindow, pullbackTolerance`）
- §A.4（新增 5 列输出）
- 依赖 §A.3 中 `_findBreakout` 返回 `breakoutIdx`（Task 2/3 已有）

**本 Task 专属约束**

动态颈线外推价（仅 isBottom=True）：
```
# _buildMatch 中，得到 breakoutIdx 后：
if isBottom and breakoutIdx is not None:
    necklinePriceAtBreakout = h1Price + necklineSlope * (breakoutIdx - h1)
else:
    necklinePriceAtBreakout = None
```

回抽识别（仅 isBottom=True，status != forming）：
```
hasPullback, pullbackDate, pullbackPrice = False, None, None
if isBottom and breakoutIdx is not None:
    end = min(len(df), breakoutIdx + 1 + pullbackWindow)
    for i in range(breakoutIdx + 1, end):
        dynNeck = h1Price + necklineSlope * (i - h1)
        close = float(df["close"].iloc[i])
        if dynNeck > 0 and abs(close - dynNeck) / dynNeck <= pullbackTolerance:
            hasPullback = True
            pullbackDate = df["date"].iloc[i]
            pullbackPrice = close
            break
```

**验证**

```bash
.venv/bin/python -m unittest strategy.patterns.tests.testHeadShoulder.TestPullback -v
.venv/bin/python -m unittest strategy.patterns.tests.testHeadShoulder.TestHeadShoulderTop -v
```

expected: 全部 PASS

新用例覆盖点（`TestPullback` 类）：
- `status='confirmed'` 的记录中 `necklinePriceAtBreakout` 为 float
- `status='forming'` 的记录中 `necklinePriceAtBreakout` 为 None、`hasPullback=False`
- 构造含回抽段的 K 线：`hasPullback=True` 且 `pullbackDate > breakoutDate`

`TestHeadShoulderTop`（回归）：
- `findHeadShoulderTop` 结果与 Task 1 前完全一致（不含新列，或新列均为默认 None/False）

---

## Task 5: 测试套件收口 + requirements.txt

**Files**
- Modify: `strategy/patterns/tests/testHeadShoulder.py`（补充验收标准用例）
- Modify: `requirements.txt`

**契约锚点**
- §A.5 评分权重数值（用例验证权重之和 = 1.00）
- Spec §十 验收标准 1-9

**本 Task 专属**

`requirements.txt` 增加一行：
```
numpy==2.0.2
```

补充测试用例（可放在 `TestHeadShoulderBottom` 内）：
- `test_newColumnsExist`：任意命中结果中包含 `necklineSlope / necklinePriceAtBreakout / hasPullback / pullbackDate / pullbackPrice`
- `test_scoreWeightSum`：构造极端理想形态，验证 `score` 近似 0.30+0.20+0.20+0.20+0.10=1.00（或分项可加得 1.0）
- `test_necklineslopeSign`：右上倾颈线 → `necklineSlope > 0`；右下倾颈线 → `necklineSlope < 0`
- `test_weakSideways`：弱横盘样本（价格波动 <3%，60日前置数据充足）→ 结果为空或 score < 0.4

**验证**

```bash
# 全策略层
.venv/bin/python -m unittest discover -s strategy -t . -p 'test*.py' -v
```

expected: 全部 PASS，0 个错误

---

## Self-Review

**Spec coverage 检查：**

| Spec 要点 | 覆盖 Task |
|---|---|
| §5.1 对外签名新增5参数 | Task 2 |
| §5.2 `calcTrendSlope` | Task 1 |
| §6.1 新增5列输出 | Task 4 |
| §6.2 `necklinePrice` 语义（→H2Price）| Task 2 |
| §6.3 评分权重 | Task 2（_score 签名）+ Task 3（trendSlope 传入） |
| §7.0 isBottom 隔离 | Task 2 |
| §7.1 前置趋势过滤 | Task 3 |
| §7.2 颈线斜率过滤 | Task 2 |
| §7.3 突破量基准改动 | Task 3 |
| §7.4 动态颈线突破价 | Task 4 |
| §7.5 回抽识别 | Task 4 |
| §八 错误处理矩阵 | Task 3（数据不足）+ Task 4（pullback边界）|
| §九 requirements.txt | Task 5 |
| §十 验收标准 1-9 | Task 5（收口测试） |
| §十一 风险1（顶底隔离回归） | Task 4（TestHeadShoulderTop 回归） |

**Placeholder 扫描：** 无 TBD / TODO / "类似Task N"

**类型一致性：**
- `trendSlope: float` 在 Task 1（calcTrendSlope 返回值）→ Task 3（传给 _buildMatch）→ Task 2（_score 入参）链路一致
- `necklineSlope: float` 在 Task 2 计算并写入 dict → Task 4 用于外推价，一致
- `h1Idx`（即变量 `h1: int`）在 Task 4 外推公式中直接使用 `h1`（已有变量），无命名冲突
