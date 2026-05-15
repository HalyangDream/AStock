# 头肩底 v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 v2 头肩底基础上新增量能递减硬性验证、买点三级标注、评分权重调整，并将头肩底战法写入主策略 skill。

**Architecture:** 在 `headShoulder.py` 内扩展 `_volumeDistScore` 返回值以同时输出 `volumeDecay: bool`；`_buildMatch` 写入 `volumeDecay` 和 `buyPoint` 两个新列；`_findHeadShoulder` 根据 `volumeDecayFilter` 参数控制硬性过滤。skill 文档独立更新。

**Tech Stack:** Python 3.9、pandas 2.x、numpy 2.0.2

---

## 共享契约区

### §A.1 `_volumeDistScore` 返回值变更

当前返回 `float`（评分），改为返回 `tuple[float, bool]`：

```
def _volumeDistScore(df, l1, l2, l3) -> tuple[float, bool]:
    # 返回 (score: float 0~1, volumeDecay: bool)
    # volumeDecay = avgLeft > avgHead and avgHead > avgRight
```

三段划分不变：左肩段 [L1, L2)、头部段 [L2-2, L2+3]（±2 根）、右肩段 (L2, L3]。

### §A.2 `_score` 权重调整（v3）

```
s1 = max(0.0, 1.0 - shoulderGap / 0.05) * 0.20   # 肩对称（v2: 0.25）
s2 = max(0.0, 1.0 - timeGap / 0.4)    * 0.15   # 时间对称
s3 = min(1.0, headDepth / 0.15)        * 0.20   # 头深
s4 = 0.10 if hasBreakout else 0.0               # 突破（v2: 0.15）
s5 = min(1.0, abs(trendSlope) / 0.005) * 0.10   # 趋势
s6 = volDistScore * 0.25                         # 成交量（v2: 0.15）
```

### §A.3 新增输出列

| 列名 | 类型 | 语义 |
|---|---|---|
| `volumeDecay` | `bool` | 三段量能严格递减（avgLeft > avgHead > avgRight） |
| `buyPoint` | `str \| None` | `rightShoulder` / `breakout` / `pullback` / `None` |

### §A.4 `findHeadShoulderBottom` 新增参数

```
volumeDecayFilter: bool = False
```

`_findHeadShoulder` 中 `if isBottom and volumeDecayFilter and not volumeDecay: continue`

---

## Task 1: 量能递减检测 + 评分权重 + 硬性过滤

**Files**
- Modify: `strategy/patterns/headShoulder.py`
- Test: `strategy/patterns/tests/testHeadShoulder.py`

**契约锚点**
- §A.1（`_volumeDistScore` 返回 `tuple[float, bool]`）
- §A.2（`_score` 权重调整）
- §A.4（`volumeDecayFilter` 参数 + 过滤逻辑）

**关键路径骨架**

```
# _volumeDistScore 末尾:
decay = avgLeft > avgHead and avgHead > avgRight
return min(1.0, score), decay

# _buildMatch 中:
volDistScore, volumeDecay = _volumeDistScore(df, l1, l2, l3)
# ... 写入 result dict: "volumeDecay": volumeDecay

# _findHeadShoulder 中, _buildMatch 调用前:
if isBottom and volumeDecayFilter:
    _, decay = _volumeDistScore(df, l1, l2, l3)
    if not decay: continue
```

**本 Task 专属约束**
- `_volumeDistScore` 调用方只有 `_buildMatch`（isBottom=True 时）和 `_findHeadShoulder`（volumeDecayFilter=True 时）
- `findHeadShoulderTop` 透传 `volumeDecayFilter` 但 isBottom=False 时不触发
- `_score` 权重调整只改系数，签名不变
- 为避免 `_findHeadShoulder` 中重复计算 `_volumeDistScore`（一次在过滤，一次在 `_buildMatch`），可将过滤逻辑移入 `_buildMatch` 内部，返回 `None` 表示被过滤；或接受双算（段均值计算开销极小）

**依赖前置 Task**
- 无

**验证**

```bash
.venv/bin/python -m unittest strategy.patterns.tests.testHeadShoulder -v
```

expected: 全部现有用例 PASS + 新增 `TestVolumeDecay` 用例 PASS

新用例覆盖点（`TestVolumeDecay` 类）：
- `test_volumeDecayColumnExists`: 输出包含 `volumeDecay` 列且为 bool
- `test_volumeDecayFilterTrue`: 构造量能不递减的 K 线，`volumeDecayFilter=True` 时结果为空
- `test_volumeDecayFilterFalse`: 同一 K 线，`volumeDecayFilter=False`（默认）时结果非空（向后兼容）
- `test_scoreWeightSumV3`: 理想形态 score 分项验证，成交量维度权重 = 0.25

---

## Task 2: 买点三级标注

**Files**
- Modify: `strategy/patterns/headShoulder.py`
- Test: `strategy/patterns/tests/testHeadShoulder.py`

**契约锚点**
- §A.3（`buyPoint` 列，值域 `{None, "rightShoulder", "breakout", "pullback"}`）
- 依赖 Task 1 产出的 `volumeDecay` 列

**关键路径骨架**

```
# _buildMatch 中, 已有 status / hasPullback / volumeDecay:
if status == _STATUS_FORMING:
    bp = "rightShoulder" if volumeDecay else None
elif hasPullback:
    bp = "pullback"
elif status in (_STATUS_BREAKOUT, _STATUS_CONFIRMED):
    bp = "breakout"
else:
    bp = None
# 写入 result dict: "buyPoint": bp
```

**依赖前置 Task**
- Task 1：`volumeDecay` 列已存在

**验证**

```bash
.venv/bin/python -m unittest strategy.patterns.tests.testHeadShoulder.TestBuyPoint -v
```

expected: PASS

新用例覆盖点（`TestBuyPoint` 类）：
- `test_buyPointColumnExists`: 输出包含 `buyPoint` 列
- `test_formingWithDecayIsRightShoulder`: forming + volumeDecay=True → buyPoint="rightShoulder"
- `test_formingWithoutDecayIsNone`: forming + volumeDecay=False → buyPoint=None
- `test_breakoutIsBuyPointBreakout`: breakout/confirmed → buyPoint="breakout"
- `test_pullbackIsBuyPointPullback`: hasPullback=True → buyPoint="pullback"
- `test_topHasNoBuyPoint`: findHeadShoulderTop → buyPoint=None（回归）

---

## Task 3: 主策略 skill 更新（第 28 条战法 + P14/S25-26）

**Files**
- Modify: `~/.cursor/skills/stock-course-strategy/main-strategy/SKILL.md`

**契约锚点**
- spec §七（P/S 信号定义 + 战法定位）

**改动说明**

1. 在 C 组（K 线形态战法）末尾、D 组之前新增 `#### 28. 头肩底战法`，内容按 spec §七.3 定义
2. 在「买入信号 → 第二层: 加分信号」表末尾新增 P14a / P14b / P14c 三行
3. 在「卖出信号 → 绝对卖出」表末尾新增 S25 / S26 两行
4. 不改动现有 P0-P13 / S0-S24 的定义

**依赖前置 Task**
- 无（与 Task 1/2 独立）

**验证**
- 人工检查：skill 文件中包含 "28. 头肩底战法"、"P14a"、"P14b"、"P14c"、"S25"、"S26"
- C 组战法编号连续（7→8→9→10→28）

---

## Self-Review

**Spec coverage 检查：**

| Spec 要点 | 覆盖 Task |
|---|---|
| §五.1 `volumeDecayFilter` 参数 | Task 1 |
| §五.2 `_volumeDistScore` 返回值变更 | Task 1 |
| §六.1 新增 volumeDecay / buyPoint 列 | Task 1 + Task 2 |
| §六.2 buyPoint 判定规则 | Task 2 |
| §六.3 评分权重 v3 | Task 1 |
| §七.1-7.3 P14/S25-26 + 28 战法 | Task 3 |
| §八 错误处理 | Task 1（volumeDecayFilter=True 全过滤 → 空 DataFrame） |
| §十.1-2 向后兼容 | Task 1 |
| §十.3-5 buyPoint 验收 | Task 2 |
| §十.6 评分权重 | Task 1 |
| §十.7 顶形态回归 | Task 2（test_topHasNoBuyPoint）+ Task 1（现有回归用例） |
| §十.8 skill 更新 | Task 3 |

**Placeholder 扫描：** 无 TBD / TODO / "类似 Task N"

**类型一致性：**
- `_volumeDistScore` 返回 `tuple[float, bool]` → Task 1 中 `_buildMatch` 解构接收 → Task 2 中 `buyPoint` 使用 `volumeDecay` 变量，链路一致
- `volumeDecayFilter: bool` 在 `findHeadShoulderBottom` → `_findHeadShoulder` → 过滤逻辑，链路一致
