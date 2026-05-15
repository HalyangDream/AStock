# 底分型形态扫描 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 全市场扫描"当前刚好形成底分型"的股票，webapp 扫描一次后按 tab 切换底分型/头肩底视图。

**Architecture:** `fractal.py` 新增 `isCurrentBottomFractal`（O(1) 尾部检查） → `scan.py` 集成到 `scanSingle`/`_summaryRow` → `services.py` 过滤函数 → webapp tab 切换展示。

**Tech Stack:** Python / pandas / Streamlit（均为已有依赖）

---

## 共享契约区

### §A.1 `isCurrentBottomFractal` 签名与返回结构

```python
def isCurrentBottomFractal(
    df: pd.DataFrame,
    merge: bool = True,
    lookBack: int = 20,
    volumeMultiplier: float = 2.0,
) -> dict | None
```

返回 dict（非 None 时）：

| 字段 | 类型 |
|---|---|
| `centerDate` | `pd.Timestamp` |
| `centerLow` | `float` |
| `centerHigh` | `float` |
| `leftDate` | `pd.Timestamp` |
| `rightDate` | `pd.Timestamp` |
| `volumeOk` | `bool` |

### §A.2 `_summaryRow` 新增字段

| 字段 | 类型 | 默认值（无底分型时） |
|---|---|---|
| `isCurrentBottom` | `bool` | `False` |
| `currentBottomDate` | `str \| None` | `None` |
| `currentBottomLow` | `float \| None` | `None` |
| `currentBottomVolumeOk` | `bool` | `False` |

### §A.3 `filterCurrentBottomFractal` 签名

```python
def filterCurrentBottomFractal(scanResult: pd.DataFrame) -> pd.DataFrame
```

### §A.4 底分型列映射

```python
_CBF_COL_MAP = {
    "symbol":                "代码",
    "name":                  "名称",
    "currentBottomDate":     "分型日期",
    "currentBottomLow":      "分型最低价",
    "currentBottomVolumeOk": "量能确认",
    "currentPrice":          "现价",
}
```

---

### Task 1: `isCurrentBottomFractal` 函数

**Files**
- Modify: `strategy/patterns/fractal.py`（文件末尾追加函数）
- Modify: `strategy/patterns/__init__.py`（新增导出）
- Test: `strategy/patterns/tests/testFractal.py`

**契约锚点**
- 依赖 §A.1（函数签名与返回结构）

**关键路径骨架**

```
original = normalizeKline(df)
processed = mergeContaining(original) if merge else original
if len(processed) < 3: return None
n = len(processed)
if not (lows[n-2] < lows[n-3] and lows[n-2] < lows[n-1]
    and highs[n-2] < highs[n-3] and highs[n-2] < highs[n-1]):
    return None
# 评估 volumeOk（映射回原始索引，取 peakVol vs refMa）
return {centerDate, centerLow, centerHigh, leftDate, rightDate, volumeOk}
```

**依赖前置 Task**
- 无

**验证**
- `python -m pytest strategy/patterns/tests/testFractal.py -v -k "current"` — expected: PASS

---

### Task 2: `scan.py` 集成

**Files**
- Modify: `strategy/scan.py`（`scanSingle` 内部 + `_summaryRow` + `scanAll` isHit + `_formatSingle`）
- Test: `strategy/tests/testScan.py`

**契约锚点**
- 依赖 §A.1（调用 `isCurrentBottomFractal`）
- 依赖 §A.2（`_summaryRow` 新增字段）

**关键路径骨架**

```
# scanSingle 内部（在现有 bottoms/hsbs 之后）
from .patterns import isCurrentBottomFractal
curBottom = isCurrentBottomFractal(df)
# 加入返回 dict

# _summaryRow 内部
cb = res.get("currentBottom")
row["isCurrentBottom"] = cb is not None
row["currentBottomDate"] = fmt(cb["centerDate"]) if cb else None
row["currentBottomLow"] = cb["centerLow"] if cb else None
row["currentBottomVolumeOk"] = cb.get("volumeOk", False) if cb else False

# scanAll 的 isHit 判断
isHit = ... or row.get("isCurrentBottom", False)
```

**依赖前置 Task**
- Task 1：`isCurrentBottomFractal` 已实现

**验证**
- `python -m pytest strategy/tests/testScan.py -v -k "current"` — expected: PASS
- `python -m pytest strategy/tests/testScan.py -v` — expected: 全部 PASS（回归）

---

### Task 3: `services.py` 过滤函数

**Files**
- Modify: `webapp/services.py`（新增 `filterCurrentBottomFractal` + `_CBF_COL_MAP`）
- Test: `webapp/tests/testServices.py`

**契约锚点**
- 依赖 §A.3（函数签名）
- 依赖 §A.4（列映射）
- 依赖 §A.2（输入 DataFrame 包含的字段）

**关键路径骨架**

```
def filterCurrentBottomFractal(scanResult: pd.DataFrame) -> pd.DataFrame:
    if scanResult is None or scanResult.empty:
        return pd.DataFrame()
    df = scanResult[scanResult["isCurrentBottom"] == True].copy()
    if df.empty:
        return pd.DataFrame()
    df = df.reindex(columns=list(_CBF_COL_MAP.keys()))
    df = df.rename(columns=_CBF_COL_MAP)
    # 数值列 round(2)，量能确认列映射为 是/否
    return df.reset_index(drop=True)
```

**依赖前置 Task**
- Task 2：`_summaryRow` 已输出 `isCurrentBottom` 等字段

**验证**
- `python -m pytest webapp/tests/testServices.py -v -k "currentBottom"` — expected: PASS

---

### Task 4: webapp 形态扫描页改造

**Files**
- Modify: `webapp/pages/5_形态扫描.py`（tab 切换 + 底分型展示）

**契约锚点**
- 依赖 §A.3（`filterCurrentBottomFractal`）
- 依赖 §A.4（展示列名）
- 现有 `services.scanHeadShoulderBottom` 不变，但改为从缓存全量结果过滤

**关键路径骨架**

```
# 扫描按钮 → scanAll 全量结果存入 session_state["scanResult"]
# 扫描完成后显示两个 tab
tab1, tab2 = st.tabs(["底分型（当日新形成）", "头肩底"])
with tab1:
    cbfDf = services.filterCurrentBottomFractal(scanResult)
    # 展示 + 下载
with tab2:
    hsbDf = services.scanHeadShoulderBottom(...)  # 改为从 scanResult 过滤
    # 保持现有展示逻辑
```

**依赖前置 Task**
- Task 3：`filterCurrentBottomFractal` 已实现

**验证**
- 手动：启动 webapp，扫描后切换 tab 无报错，底分型 tab 正确展示命中结果
- 手动：切换 tab 不触发重新扫描

---

## 注意事项

1. `services.scanHeadShoulderBottom` 当前内部调用 `_scan.scanAll` 再过滤。改造后 webapp 页面应直接调用 `_scan.scanAll` 拿全量结果存缓存，再分别用 `filterCurrentBottomFractal` 和 `scanHeadShoulderBottom`（改为接受已有结果作为输入）过滤。需要给 `scanHeadShoulderBottom` 增加一个可选的 `scanResult` 参数，有值时跳过 `scanAll` 调用直接过滤。
2. 现有测试中使用 mock/构造 K 线的模式，新测试沿用同样模式。
