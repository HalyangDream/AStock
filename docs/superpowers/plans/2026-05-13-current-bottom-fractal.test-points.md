# 底分型形态扫描 — 测试点清单

对应 plan: `2026-05-13-current-bottom-fractal.md`

---

## Task 1: `isCurrentBottomFractal` 函数

### 主路径

- **TP-1.1** 最后 3 根 K 线（merge=False）满足底分型几何条件 → 返回非 None dict
- **TP-1.2** 返回 dict 包含全部 §A.1 字段（centerDate / centerLow / centerHigh / leftDate / rightDate / volumeOk），类型正确

### 边界

- **TP-1.3** 最后 3 根不满足几何条件（中心 low 不是最低）→ 返回 None
- **TP-1.4** K 线仅 2 根 → 返回 None
- **TP-1.5** 空 DataFrame → 返回 None
- **TP-1.6** merge=True，原始 K 线中存在包含关系，合并后尾部 3 根满足底分型 → 返回非 None
- **TP-1.7** merge=True，合并后 K 线不足 3 根 → 返回 None
- **TP-1.8** 满足几何但中间有底分型、最后 3 根不满足 → 返回 None（只看尾部）

### 异常 / 质量

- **TP-1.9** 满足几何条件但不放量（peakVol < refMa × multiplier）→ `volumeOk = False`
- **TP-1.10** 满足几何条件且放量 → `volumeOk = True`
- **TP-1.11** rightDate = 最新 K 线日期（验证是尾部分型，不是中间的）

---

## Task 2: `scan.py` 集成

### 主路径

- **TP-2.1** `scanSingle` 传入尾部是底分型的 K 线 → 返回 dict 中 `currentBottom` 非 None
- **TP-2.2** `_summaryRow` 输出包含 `isCurrentBottom=True` + `currentBottomDate` / `currentBottomLow` / `currentBottomVolumeOk` 字段正确

### 边界

- **TP-2.3** `scanSingle` 传入非底分型 K 线 → `currentBottom` 为 None
- **TP-2.4** `_summaryRow` 当 `currentBottom=None` 时：`isCurrentBottom=False`，其余 3 个字段为 None/False
- **TP-2.5** 空 K 线时 `isCurrentBottom=False`
- **TP-2.6** `scanAll(hitOnly=True)` 包含仅有 `isCurrentBottom=True`（无 hsb 也无历史 bottom）的股票

### 回归

- **TP-2.7** `_summaryRow` 已有字段（bottomCount / latestBottomDate / hsbCount / bestHsbStatus 等）不受影响
- **TP-2.8** `scanBatch` 输出 DataFrame 包含新增的 `isCurrentBottom` 列

---

## Task 3: `services.py` 过滤函数

### 主路径

- **TP-3.1** `filterCurrentBottomFractal` 从含 `isCurrentBottom=True` 的行中正确筛选
- **TP-3.2** 输出 DataFrame 列名为中文（§A.4 映射：代码 / 名称 / 分型日期 / 分型最低价 / 量能确认 / 现价）

### 边界

- **TP-3.3** 全量结果无 `isCurrentBottom=True` → 返回空 DataFrame
- **TP-3.4** 输入空 DataFrame → 返回空 DataFrame
- **TP-3.5** 输入 None → 返回空 DataFrame

### 质量

- **TP-3.6** 数值列（分型最低价 / 现价）保留 2 位小数
- **TP-3.7** `scanHeadShoulderBottom` 新增可选 `scanResult` 参数：传入时不调用 `scanAll`，直接过滤

---

## Task 4: webapp 页面改造

> 以下为手动验证点（UI 层不写自动化测试）

- **TP-4.1** 点击「开始扫描」后，全量扫描结果存入 `session_state["scanResult"]`
- **TP-4.2** 扫描完成后出现两个 tab：「底分型（当日新形成）」和「头肩底」
- **TP-4.3** 切换 tab 不触发重新扫描（观察：无进度条重新出现）
- **TP-4.4** 底分型 tab 展示 `filterCurrentBottomFractal` 的结果，列名 / 格式正确
- **TP-4.5** 头肩底 tab 保持原有筛选 + 展示逻辑不变
- **TP-4.6** 两个 tab 各自有独立的 CSV 下载按钮
