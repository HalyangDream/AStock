# Spec：底分型重构 — 课程体系定义

**版本**：v2.0  
**日期**：2026-05-13  
**状态**：草稿，待确认  
**来源**：`stock-course-strategy` skill 主策略第 8 条「顶底分型战法」+ P7 信号

---

## 一、背景

当前 `isCurrentBottomFractal` 采用**缠论几何定义**（3 根 K 线中心 low/high 最低）。实际扫描中发现：
- 上涨趋势中的小回调频繁触发，产生大量假信号
- 与课程体系中"底分型"的定义不一致

课程体系中的底分型是**具体的 K 线反转组合**，而非缠论的抽象几何条件。本次重构将底分型定义完全对齐课程体系。

---

## 二、底分型构造定义

### 2.1 三种 K 线组合（满足任一即为底分型形态）

#### 形态 A：阳包阴（Bullish Engulfing）

```
  ┃         ┃
 ┃█┃      ┌───┐
 ┃█┃  →   │   │
 ┃█┃      │   │
  ┃       └───┘
 Day1      Day2
(阴线)    (阳线)
```

条件：
- Day1 为阴线（close < open）
- Day2 为阳线（close > open）
- Day2 实体完全包住 Day1 实体：`Day2.close ≥ Day1.open` 且 `Day2.open ≤ Day1.close`

#### 形态 B：十字星底（Doji / Hammer Bottom）

```
  ┃
  ╋  ←  十字星（实体极小）
  ┃
  ┃  ←  下影线长
```

条件：
- 实体极小：`abs(close - open) / (high - low) ≤ 0.2`（实体占振幅不超过 20%）
- 下影线明显：`min(open, close) - low ≥ 0.6 × (high - low)`（下影线占振幅 ≥ 60%）
- 出现在下跌或回调末端（由 MA20 前提隐式保证）

#### 形态 C：三过一（Third-Over-First）

```
 ┃          ┃         ┌───┐
┃█┃       ┃█┃        │   │
┃█┃       ┃█┃        │   │ close > Day1.high
 ┃          ┃         └───┘
Day1      Day2       Day3
```

条件：
- 连续 3 根 K 线
- Day3 收盘价 > Day1 最高价：`Day3.close > Day1.high`
- Day2 低点 ≤ Day1 低点（有回调过程）：`Day2.low ≤ Day1.low`

### 2.2 硬性前提（缺一不可）

| 前提 | 条件 | 含义 |
|---|---|---|
| **价格前提** | 分型最后一根 K 线 `close > MA20` | 处于中期上升趋势或刚突破 |
| **量能前提** | 分型窗口内最大成交量 > MA120 均量 | 有真实资金参与 |

两个前提必须**同时满足**，否则即使 K 线组合匹配也不算有效底分型。

### 2.3 完整判定流程

```
1. 取最新 2-3 根 K 线（阳包阴/十字星看 1-2 根，三过一看 3 根）
2. 检查是否匹配三种形态之一
3. 若匹配 → 检查价格前提（close > MA20）
4. 若通过 → 检查量能前提（maxVol > MA120 均量）
5. 全部通过 → 返回底分型信息
```

---

## 三、与旧定义的对照

| 维度 | 旧（缠论几何） | 新（课程体系） |
|---|---|---|
| 几何条件 | 3 根 K 线中心 low/high 最低 | 阳包阴 / 十字星底 / 三过一 |
| 趋势前提 | 前 20 根斜率 ≤ 0 | close > MA20 |
| 量能前提 | 可选（volumeOk 标记） | **硬性**（不满足则不算） |
| 信号定位 | 独立形态 | P7 加分信号 |
| 观察窗口 | 3 根合并 K 线 | 2-3 根原始 K 线（不做包含处理） |

**重要变更**：不再做缠论的 K 线包含处理（`mergeContaining`），直接在原始日 K 上识别。

---

## 四、接口变更

### 4.1 `isCurrentBottomFractal` 签名更新

```python
def isCurrentBottomFractal(
    df: pd.DataFrame,
    maWindow: int = 20,
    volMaWindow: int = 120,
    dojiBodyRatio: float = 0.2,
    dojiShadowRatio: float = 0.6,
) -> dict | None
```

移除旧参数：`merge` / `lookBack` / `volumeMultiplier` / `trendWindow` / `trendMaxSlope`

### 4.2 返回 dict 结构更新

| 字段 | 类型 | 语义 |
|---|---|---|
| `pattern` | `str` | 形态类型：`"engulfing"` / `"doji"` / `"threeOverOne"` |
| `patternLabel` | `str` | 中文标签：`"阳包阴"` / `"十字星底"` / `"三过一"` |
| `signalDate` | `pd.Timestamp` | 信号确认日（最后一根 K 线日期） |
| `signalPrice` | `float` | 信号确认价（最后一根 K 线收盘价） |
| `lowestLow` | `float` | 形态窗口内最低价（支撑位参考） |
| `ma20` | `float` | 当日 MA20 值 |
| `volumeOk` | `bool` | 量能前提是否满足（本版本恒为 True，不满足不返回） |

---

## 五、展示列更新

| 展示列名 | 来源字段 | 说明 |
|---|---|---|
| 代码 | `symbol` | |
| 名称 | `name` | |
| 形态 | `currentBottomPattern` | 阳包阴 / 十字星底 / 三过一 |
| 信号日期 | `currentBottomDate` | |
| 信号价 | `currentBottomPrice` | 收盘价 |
| 支撑位 | `currentBottomLow` | 形态窗口最低价 |
| 现价 | `currentPrice` | |

---

## 六、影响范围

| 文件 | 改动 |
|---|---|
| `strategy/patterns/fractal.py` | 重写 `isCurrentBottomFractal` |
| `strategy/scan.py` | `_summaryRow` 字段调整（`currentBottomVolumeOk` → `currentBottomPattern`） |
| `webapp/services.py` | `_CBF_COL_MAP` 列映射更新 |
| `webapp/pages/5_形态扫描.py` | 底分型 tab 的 column_config 更新 |
| `strategy/patterns/tests/testFractal.py` | 重写 `TestCurrentBottomFractal` |
| `strategy/tests/testScan.py` | 调整相关测试 |
| `webapp/tests/testServices.py` | 调整列名相关测试 |

---

## 七、验收标准

1. 构造阳包阴 K 线 + close > MA20 + vol > MA120 → 返回 `pattern="engulfing"`
2. 构造十字星底 K 线 + 前提满足 → 返回 `pattern="doji"`
3. 构造三过一 K 线 + 前提满足 → 返回 `pattern="threeOverOne"`
4. 形态匹配但 close ≤ MA20 → 返回 None
5. 形态匹配但量能不足 → 返回 None
6. 上涨趋势中的普通小回调（不匹配三种形态）→ 返回 None
7. 现有 `findBottomFractal`（历史全量扫描）不受影响
8. webapp 底分型 tab 展示形态列（阳包阴/十字星底/三过一）
