# webapp 形态扫描页 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 webapp 新增「形态扫描」页，支持一键扫全 A 股头肩底、展示形态起始日 / 颈线价 / 买点价，带实时进度条。

**Architecture:** scan.py 补 4 个输出列 + progressCb 回调参数；services.py 封装扫描 service；新建 Streamlit 页面调用 service，通过回调驱动 st.progress。

**Tech Stack:** Python 3.9、pandas、Streamlit 1.40、strategy.scan（已有）

---

## 共享契约区

### §A.1 `_summaryRow` 新增列（scan.py）

在 `bestHsbTargetConservative` 之后追加（当 `hsb.empty` 时均为 `None`）：

```python
"bestHsbLeftShoulderDate": None,   # str YYYY-MM-DD
"bestHsbBreakoutDate":     None,   # str YYYY-MM-DD | None
"bestHsbBreakoutPrice":    None,   # float | None
"bestHsbNecklinePriceAtBreakout": None,  # float | None
```

赋值时：
```python
row["bestHsbLeftShoulderDate"] = pd.Timestamp(best["leftShoulderDate"]).strftime("%Y-%m-%d")
row["bestHsbBreakoutDate"]     = (pd.Timestamp(best["breakoutDate"]).strftime("%Y-%m-%d")
                                   if pd.notna(best.get("breakoutDate")) else None)
row["bestHsbBreakoutPrice"]    = (float(best["breakoutPrice"])
                                   if pd.notna(best.get("breakoutPrice")) else None)
row["bestHsbNecklinePriceAtBreakout"] = (float(best["necklinePriceAtBreakout"])
                                          if pd.notna(best.get("necklinePriceAtBreakout")) else None)
```

### §A.2 `scanAll` 新增参数

```python
def scanAll(..., progressCb: Optional[Callable[[int, int], None]] = None) -> pd.DataFrame
```

`progressCb(doneCount: int, total: int)` 在每只股票扫描完后调用（主线程，`as_completed` 循环内）。

### §A.3 `scanHeadShoulderBottom` 签名（services.py）

```python
def scanHeadShoulderBottom(
    days: int = 250,
    workers: int = 8,
    onlyBreakout: bool = True,
    progressCb: Optional[Callable[[int, int], None]] = None,
) -> pd.DataFrame
```

返回列（已整理，供 UI 直接展示）：

| 列名 | 来源 | 说明 |
|---|---|---|
| `代码` | symbol | 6 位股票代码 |
| `名称` | name | 股票名称 |
| `形态起始日` | bestHsbLeftShoulderDate | 左肩日期 |
| `突破日` | bestHsbBreakoutDate | 买入触发日（forming 为空）|
| `颈线价` | bestHsbNeckline | H2 端点价 |
| `买点价` | bestHsbBreakoutPrice | 突破日收盘（forming 为空）|
| `动态颈线价` | bestHsbNecklinePriceAtBreakout | 突破日颈线外推价 |
| `目标价(经典)` | bestHsbTargetClassic | 2×颈线-头部 |
| `评分` | bestHsbScore | 0~1 |
| `状态` | bestHsbStatus | forming/breakout/confirmed |
| `现价` | currentPrice | 扫描时最新价 |

---

## Task 1: scan.py 补输出列 + progressCb

**Files**
- Modify: `strategy/scan.py:L130-L162`（`_summaryRow`）
- Modify: `strategy/scan.py:L220-L290`（`scanAll` 签名 + 循环体）

**契约锚点**
- §A.1（新增4列）
- §A.2（progressCb 参数）

**关键路径骨架**

```
# _summaryRow: 在 hsb 赋值块末尾追加 §A.1 四列
# scanAll 签名: 新增 progressCb=None
# as_completed 循环末尾（紧跟 _printProgress）:
if progressCb is not None:
    progressCb(doneCount, total)
```

**验证**

```bash
.venv/bin/python -m unittest strategy.tests.testScan -v
```

expected: 全部 PASS（已有用例不受影响）

---

## Task 2: services.py 新增 scanHeadShoulderBottom

**Files**
- Modify: `webapp/services.py`（末尾追加函数）

**契约锚点**
- §A.3（函数签名 + 返回列映射）
- 依赖 Task 1（scan.py 已有 progressCb + 新列）

**关键路径骨架**

```
from strategy import scan as _scan

def scanHeadShoulderBottom(days, workers, onlyBreakout, progressCb):
    df = _scan.scanAll(lookbackDays=days, workers=workers,
                       hitOnly=True, progress=False,
                       progressCb=progressCb)
    if df.empty: return pd.DataFrame()
    hsb = df[df["bestHsbStatus"].notna()].copy()
    if onlyBreakout:
        hsb = hsb[hsb["bestHsbStatus"].isin(["breakout", "confirmed"])]
    # 重命名为 §A.3 展示列名
    return hsb.rename(columns={...})[列顺序]
```

**验证**

```bash
.venv/bin/python -m unittest webapp.tests.testServices.TestScanHsb -v
```

expected: PASS

---

## Task 3: 5_形态扫描.py 新建页面

**Files**
- Create: `webapp/pages/5_形态扫描.py`

**契约锚点**
- §A.3 返回 DataFrame 列名（直接展示，已是中文）

**UI 骨架**

```
st.title("形态扫描")

# 参数区
col1..col4: 类型(只有头肩底) / 回溯天数(250) / 并发(8) / 仅已突破(True)

if st.button("开始扫描"):
    progress_bar = st.progress(0)
    status_text = st.empty()

    def _cb(done, total):
        progress_bar.progress(done / total)
        status_text.text(f"已扫描 {done}/{total}...")

    with st.spinner("扫描全 A 股..."):
        df = services.scanHeadShoulderBottom(days, workers, onlyBreakout, _cb)

    progress_bar.progress(1.0)
    status_text.text(f"扫描完成，找到 {len(df)} 只")

    if df.empty:
        st.info("未找到符合条件的股票")
    else:
        st.dataframe(df, use_container_width=True)
        # CSV 下载按钮
```

**验证**

手动 `streamlit run webapp/app.py` 后在侧边栏看到「5 形态扫描」页即可（无自动化 UI 测试）。

---

## Task 4: testServices.py 新增 TestScanHsb

**Files**
- Modify: `webapp/tests/testServices.py`

**契约锚点**
- §A.3 返回列名

**关键测试点**

```
TestScanHsb:
  test_onlyBreakoutFiltersForming    # onlyBreakout=True 过滤 status=forming
  test_emptyReturnsEmptyDf           # scanAll 返回空 → 返回空 DataFrame
  test_columnNamesCorrect            # 返回 DataFrame 包含全部 §A.3 展示列
  test_progressCbCalledCorrectly     # progressCb 被调用且参数为 (done, total)
```

**验证**

```bash
.venv/bin/python -m unittest webapp.tests.testServices.TestScanHsb -v
```

expected: PASS
