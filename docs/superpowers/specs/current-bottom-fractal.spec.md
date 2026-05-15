# Spec：底分型形态扫描（当前新形成）

**版本**：v1.0  
**日期**：2026-05-13  
**状态**：草稿，待确认

---

## 一、背景

`strategy/patterns/fractal.py` 已有 `findBottomFractal` 函数，能识别 K 线中**所有历史底分型**（缠论定义：连续 3 根合并 K 线，中间一根低点最低、高点最低）。`strategy/scan.py` 的 `scanSingle` 调用该函数后在 `_summaryRow` 中提取最近一个底分型的日期/等级/低点。

**缺失能力**：

| 缺失 | 现状 | 影响 |
|---|---|---|
| "当前刚好是底分型"判定 | 只有全量历史扫描 + 取最近一条 | 无法区分"历史上有过"和"现在刚形成" |
| 底分型独立展示入口 | webapp 形态扫描页仅支持头肩底 | 用户无法从 UI 筛选底分型 |
| 扫描一次、按形态切换查看 | 每次切换都要重新扫描 | 浪费时间 |

---

## 二、目标

1. 在 `fractal.py` 新增 `isCurrentBottomFractal` 函数，**仅检查最新 3 根合并 K 线**是否构成底分型（O(1)判定）
2. 在 `scanSingle` / `_summaryRow` 中集成该判定，输出 `isCurrentBottom` 等字段
3. webapp 形态扫描页改为**扫描一次**，结果缓存后按**按钮/tab 切换**底分型 / 头肩底两种展示视图

---

## 三、非目标

- 不修改 `findBottomFractal` 的现有行为（历史全量扫描保持不变）
- 不修改 `findHeadShoulderBottom` 及相关逻辑
- 不增加"前置下跌趋势"等额外过滤条件
- 不支持分钟级 K 线
- 不引入新的第三方库
- 不做分型"预判"（中心已出现但等待右侧确认的 forming 状态）——只识别已完成的分型
- 不在本次实现"点击个股查看 K 线详情"的跳转

---

## 四、决策表

| 决策点 | 方案 A | 方案 B | 选择 |
|---|---|---|---|
| 新增函数 vs 复用 `findBottomFractal` | 新增轻量 `isCurrentBottomFractal` 仅检查尾部 3 根 | 调用 `findBottomFractal` 全量扫描后过滤尾部 | **A**：全市场 5000 只时效率显著更优；尾部检查 O(1) vs 全量 O(n) |
| grade 分级方式 | 复用现有 4 级 (weak/validTrend/validVolume/strong) | 只输出 `volumeOk` 布尔标记 | **B**：当前分型无 look-ahead 数据，`validTrend`/`strong` 永远不可能满足，保留它们会造成误导；`volumeOk` 足够表达量能状态 |
| 服务层设计 | 新增独立扫描函数 `scanCurrentBottomFractal` | 复用 `scanAll` 全量结果 + 过滤函数 | **B**：`scanSingle` 已同时跑底分型和头肩底，新增 O(1) 检查无感知开销；一次扫描产出全部结果，按需过滤 |
| webapp 交互 | 选形态 → 点扫描（每次切换重新扫描） | 点扫描 → 缓存 → 按钮切换形态视图 | **B**：K 线获取是耗时瓶颈，扫描一次后切换形态无需重新拉数据 |

---

## 五、接口与方法签名

### 5.1 新增函数（`strategy/patterns/fractal.py`）

```python
def isCurrentBottomFractal(
    df: pd.DataFrame,
    merge: bool = True,
    lookBack: int = 20,
    volumeMultiplier: float = 2.0,
) -> dict | None
```

### 5.2 修改函数（`strategy/scan.py`）

`scanSingle` 签名不变；内部新增调用 `isCurrentBottomFractal(df)`。

`_summaryRow` 签名不变；输出 dict 新增字段（见 §六）。

### 5.3 新增过滤函数（`webapp/services.py`）

```python
def filterCurrentBottomFractal(scanResult: pd.DataFrame) -> pd.DataFrame
```

从 `scanAll` 的全量结果中筛选 `isCurrentBottom == True` 的行，重命名列为中文展示名，返回展示用 DataFrame。

### 5.4 `__init__.py` 导出

`strategy/patterns/__init__.py` 新增导出 `isCurrentBottomFractal`。

---

## 六、关键数据结构

### 6.1 `isCurrentBottomFractal` 返回值（非 None 时）

| 字段 | 类型 | 语义 |
|---|---|---|
| `centerDate` | `pd.Timestamp` | 分型中心 K 线日期 |
| `centerLow` | `float` | 分型中心低点（分型最低价） |
| `centerHigh` | `float` | 分型中心高点 |
| `leftDate` | `pd.Timestamp` | 左元素日期 |
| `rightDate` | `pd.Timestamp` | 右元素日期（= 最新合并 K 线日期） |
| `volumeOk` | `bool` | 分型窗口内最大成交量 ≥ 前 lookBack 均量 × volumeMultiplier |

返回 `None` 表示最新 K 线不构成底分型。

### 6.2 `_summaryRow` 新增字段

| 字段 | 类型 | 语义 |
|---|---|---|
| `isCurrentBottom` | `bool` | 最新 K 线是否构成底分型 |
| `currentBottomDate` | `str \| None` | 分型中心日期（YYYY-MM-DD）；非底分型时 None |
| `currentBottomLow` | `float \| None` | 分型最低价；非底分型时 None |
| `currentBottomVolumeOk` | `bool` | 量能是否确认；非底分型时 False |

### 6.3 底分型展示 DataFrame 列（`filterCurrentBottomFractal` 输出）

| 展示列名 | 来源字段 | 格式 |
|---|---|---|
| 代码 | `symbol` | 文本 |
| 名称 | `name` | 文本 |
| 分型日期 | `currentBottomDate` | YYYY-MM-DD |
| 分型最低价 | `currentBottomLow` | 保留 2 位小数 |
| 量能确认 | `currentBottomVolumeOk` | 是/否 |
| 现价 | `currentPrice` | 保留 2 位小数 |

---

## 七、核心判定逻辑说明

### 7.1 "当前底分型"几何条件

经包含处理后的 K 线序列 `processed`，设长度为 `n`（n ≥ 3）。若同时满足：

- `lows[n-2] < lows[n-3]` 且 `lows[n-2] < lows[n-1]`
- `highs[n-2] < highs[n-3]` 且 `highs[n-2] < highs[n-1]`

则最新 K 线（`processed[n-1]`）恰好构成底分型的右元素，分型刚刚完成。

### 7.2 量能评估

在原始（未合并）K 线上评估，逻辑与现有 `_evaluateFractal` 的 filter B 一致：

- 取左/中/右对应原始索引范围内的最大成交量 `peakVol`
- 取左元素前一根的 rollingMean(volume, lookBack) 为基准 `refMa`
- `peakVol ≥ refMa × volumeMultiplier` → `volumeOk = True`

### 7.3 filter A（走高持续性）不适用

右元素 = 最新 K 线，无后续数据，不评估 filter A。

---

## 八、错误处理矩阵

| 异常场景 | 行为 |
|---|---|
| `df` 为空或 `None` | `isCurrentBottomFractal` 返回 `None` |
| 合并后 K 线不足 3 根 | 返回 `None` |
| 最新 3 根不满足几何条件 | 返回 `None` |
| `df` 缺少 OHLCV 必要列 | 沿用 `normalizeKline` 抛出 `ValueError` |
| volume 列全为 0 或 NaN | `volumeOk` 置 `False`，不报错 |
| lookBack 均量窗口数据不足 | `rollingMean` 已用 `min_periods=1` 兜底，正常计算 |
| 扫描中个别股票 K 线拉取失败 | 沿用 `scanAll` 现有 `try/except`，跳过该股票 |

---

## 九、影响范围

| 文件 | 改动类型 |
|---|---|
| `strategy/patterns/fractal.py` | 新增 `isCurrentBottomFractal` 函数 |
| `strategy/patterns/__init__.py` | 导出新函数 |
| `strategy/scan.py` | `scanSingle` 内部新增调用；`_summaryRow` 新增 4 个字段；`scanAll` 的 `isHit` 判断增加 `isCurrentBottom` |
| `webapp/services.py` | 新增 `filterCurrentBottomFractal` 过滤函数 + `_CBF_COL_MAP` 列映射 |
| `webapp/pages/5_形态扫描.py` | 移除形态类型 selectbox；扫描结果缓存后，增加 tab/按钮切换底分型 / 头肩底视图；底分型视图调用 `filterCurrentBottomFractal` |

**不受影响**：`findBottomFractal`、`findTopFractal`、`findHeadShoulderBottom`、`findHeadShoulderTop`、`headShoulder.py`、`_utils.py`、`requirements.txt`。

---

## 十、验收标准

1. 构造 K 线，最后 3 根（合并后）满足底分型几何条件 → `isCurrentBottomFractal` 返回非 None dict，字段完整且类型正确
2. 构造 K 线，最后 3 根不满足底分型 → 返回 `None`
3. 满足几何条件但不放量 → `volumeOk = False`
4. 满足几何条件且放量 → `volumeOk = True`
5. `scanSingle` 对满足底分型的 K 线返回 `isCurrentBottom = True`，反之 `False`
6. `filterCurrentBottomFractal` 从全量扫描结果中正确筛出 `isCurrentBottom == True` 的行，列名为中文
7. webapp 扫描一次后，切换"底分型"/"头肩底"tab 不触发重新扫描，数据来自 session_state 缓存
8. 现有 `findBottomFractal` / `findHeadShoulderBottom` / `scanHeadShoulderBottom` 行为不受影响
9. K 线不足 3 根时不抛异常

---

## 十一、风险清单

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| 包含处理后尾部 K 线可能"吞噬"多根原始 K 线，导致 `rightDate` 早于用户预期 | 中 | 返回值中包含 `rightDate` 供用户判断实际日期 |
| 全市场扫描数据源返回当日未完成 K 线，分型判定可能不稳定 | 中 | `getDailyKline` 标准行为返回已完成 K 线；盘中运行时分型可能在收盘后翻转，属预期行为 |
| 底分型信号密度较高（任何 V 形反弹底部都会产生），命中数可能较多 | 中 | 提供 `volumeOk` 列供用户过滤；后续可扩展前置趋势过滤（本次不做） |
| `scanSingle` 新增调用增加处理时间 | 低 | `isCurrentBottomFractal` 仅做 normalize + merge + 尾部 3 根比较，开销可忽略 |
| webapp 缓存全量扫描结果增加内存占用 | 低 | `_summaryRow` 每只股票仅 1 行扁平 dict，5000 只约 < 5MB |
