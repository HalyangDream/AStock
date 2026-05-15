# Spec：头肩底形态识别 v2（修复 + 对齐东财标准）

**版本**：v2.0  
**日期**：2026-05-12  
**状态**：草稿，待确认  
**参考**：[K线形态之头肩底（普通版本）- 东方财富](https://caifuhao.eastmoney.com/news/20260412154545236731410)

---

## 一、背景

v1 版头肩底已上线，实际使用发现 **2 个 bug** + 与主流技术分析标准（东财文章）对照存在 **4 个缺失要素**。

### 1.1 已确认 Bug

| # | 问题 | 原因 |
|---|---|---|
| B1 | **颈线价格不对**：`necklinePrice` 被写死为 `h2Price`（右颈线高点），而正确定义应为 H1/H2 两个反弹高点连线 | `_buildMatch` 第 153 行 `necklinePrice = h2Price`，丢弃了 H1 信息；当 H1 > H2 时颈线价偏低，导致突破判断偏早、目标价偏低 |
| B2 | **250 日含义歧义**：`lookbackDays` 在 `scanSingle` 里用 `df.tail(250)` 截取 — 取决于 `getDailyKline` 返回的是**交易日行**（每行 = 1 个交易日），实际确为交易日；但 UI 未标注清楚，且文档说"约 1 年"，实际 250 交易日 ≈ 365 自然日 | `scanSingle` L112 `df.tail(lookbackDays)` 无误，但 UI 的 help 文字和 spec 需明确 |

### 1.2 对照东财文章的缺失要素

东财文章定义的 6 大研判条件 vs 现有实现：

| 东财条件 | 现状 | 差距 |
|---|---|---|
| ①形态时间周期：头部→右肩 1~3 个月（20~65 交易日）| `minSpan=30, maxSpan=120` 约束的是 L1→L3 全跨度 | **头→右肩跨度未单独约束**，全跨度过宽 |
| ②成交量分布：左肩量 > 头部量 < 右肩量（右最大），突破放量，回抽缩量 | 仅检查突破日量 > 前5日均量 | **未验证"头部量最小"和"右肩量 > 左肩量"** |
| ③指标背离（加分项）：头部价格新低但 KD 未新低 | 未实现 | 非必要条件，**本次不实现**（标记为加分项，后续跟进） |
| ④波浪结构：右肩→颈线 = 1浪，回抽 = 2浪，再起 = 3浪主升 | 未实现 | 本次不实现 |
| ⑤目标价 = 颈线 + (颈线 - 头底)，即 1:1 等幅测距 | 现有 `targetPriceClassic = 2×颈线-头底`，**公式一致但颈线价不对导致目标价也不对**（Bug B1 连带） | 修颈线后自动修正 |
| ⑥突破颈线 3% 确认 | 现有仅检查"收盘 > 颈线 + 后 3 根不跌破" | **需增加 3% 幅度确认条件** |

---

## 二、目标

1. **修复 B1**：`necklinePrice` 改为真正的颈线价（H1→H2 连线在特定时刻的值），展示给用户的颈线价应为**右肩时刻的颈线外推价**（= H2Price），同时内部突破判断和目标价计算使用动态颈线
2. **修复 B2**：UI 标注明确"交易日"，help 文字改为"250 交易日 ≈ 1 年"
3. **新增成交量分布验证**：头部区间均量应为三段最小，右肩区间均量应 ≥ 左肩区间均量
4. **新增突破 3% 确认**：`confirmed` 状态要求收盘价 > 颈线价 × 1.03
5. 调整评分权重，纳入成交量分布维度

---

## 三、非目标

- 不实现 KD 指标背离（加分项，后续单独跟进）
- 不实现波浪结构划分
- 不修改 `findHeadShoulderTop`（isBottom 隔离原则不变）
- 不改变 `scanSingle / scanBatch / scanAll` 调用签名
- 不改变 webapp UI 布局（仅改 help 文字）

---

## 四、决策表

| 决策点 | 方案 A | 方案 B | 选择 |
|---|---|---|---|
| 颈线价展示 | 展示 `necklinePrice = H2Price`（右颈线端点价，用户直观）| 展示动态颈线在右肩日的值 | **A**：H2Price 与右颈线端等值，用户可在 K 线图上直接对照 |
| 成交量分布检验方式 | 三段区间均量对比（硬性过滤） | 三段区间均量对比（仅评分加分，不过滤） | **B**：东财文章说"不遵循不一定不是，只是概率小"，做软约束（评分）更合理 |
| 3% 突破确认 | 收盘 > 颈线 × 1.03 为 `confirmed` | 收盘 > 颈线 × 1.03 作为额外评分加分 | **A**：东财文章明确说 3% 是"形态最终定型的条件"，应作为硬性判定 |
| 头→右肩时间约束 | 新增参数 `headToRightShoulderMinSpan / MaxSpan` | 复用现有 `minSpan/maxSpan` 不单独约束 | **A**：东财明确"1~3 个月"指头→右肩，不是全跨度 |

---

## 五、接口与方法签名

### 5.1 `findHeadShoulderBottom` 新增参数

```python
def findHeadShoulderBottom(
    df,
    # ... 现有参数不变 ...
    # ── v2 新增 ──
    headToShoulderMinSpan: int = 20,   # 头(L2)→右肩(L3) 最小交易日
    headToShoulderMaxSpan: int = 65,   # 头(L2)→右肩(L3) 最大交易日
    breakoutConfirmPct: float = 0.03,  # 突破确认幅度（3%）
) -> pd.DataFrame
```

### 5.2 内部变更（无新公开函数）

- `_buildMatch`：修正 `necklinePrice` 的计算逻辑
- `_findBreakout`：在 confirmed 判定中增加 3% 幅度条件
- `_score`：新增成交量分布维度

---

## 六、关键数据结构

### 6.1 `necklinePrice` 定义修正

| 场景 | 旧值 | 新值 |
|---|---|---|
| `necklinePrice` 列 | `h2Price`（固定） | `max(h1Price, h2Price)`（颈线两端较高者，与经典技术分析定义一致）|
| 目标价计算 | `2 × h2Price - headLow` | `2 × necklinePrice - headLow`（颈线 + 等幅）|
| 突破判断 | 动态颈线外推（h1 + slope × Δ） | **不变**：内部仍用动态颈线外推判断突破点 |
| `necklinePriceAtBreakout` | 突破日外推价 | **不变** |

### 6.2 新增输出列

| 列名 | 类型 | 语义 |
|---|---|---|
| `volumeDistScore` | `float` | 成交量分布得分 0~1（头部量最小=1，左肩量<右肩量再加分）|

### 6.3 `confirmed` 状态定义修正

| 条件 | 旧版 | 新版 |
|---|---|---|
| 价格突破 | 收盘 > 动态颈线价 | 不变 |
| 量突破 | 突破日量 > 前5日均量 × multiplier | 不变 |
| 后续确认 | 后 3 根收盘不跌破颈线 | 后 3 根收盘不跌破颈线 **且** 突破日收盘 > `necklinePrice × (1 + breakoutConfirmPct)` |

未满足 3% 条件但满足原有条件的，状态为 `breakout`（而非 `confirmed`）。

### 6.4 评分权重（v2）

| 维度 | v1 权重 | v2 权重 | 说明 |
|---|---|---|---|
| 肩部价格对称 | 0.30 | 0.25 | 压缩 |
| 时间对称 | 0.20 | 0.15 | 压缩 |
| 头部深度 | 0.20 | 0.20 | 不变 |
| 突破加分 | 0.20 | 0.15 | 压缩 |
| 前置趋势强度 | 0.10 | 0.10 | 不变 |
| 成交量分布（新） | — | 0.15 | 头部量最小 + 右肩量≥左肩量 |
| **合计** | 1.00 | 1.00 | |

---

## 七、逻辑说明

### 7.1 颈线价修正（Bug B1）

- `necklinePrice` = `max(h1Price, h2Price)`，恢复为经典定义
- 目标价公式 `targetPriceClassic = 2 × necklinePrice - l2Price` 自动修正
- `necklinePriceAtBreakout`（动态颈线在突破日的外推值）计算逻辑不变

### 7.2 头→右肩时间约束（新增，仅 isBottom=True）

- 在三元组通过几何约束后，增加 `headToShoulderMinSpan ≤ (l3 - l2) ≤ headToShoulderMaxSpan` 检查
- 默认 20~65 交易日（约 1~3 个月）

### 7.3 成交量分布评分（新增，仅 isBottom=True）

- 将形态分为三段：左肩段 [L1, L2)、头部段 [L2 附近]、右肩段 (L2, L3]
- 计算各段均量：`avgVolLeft`、`avgVolHead`、`avgVolRight`
- 评分规则：
  - 头部均量是三段最小：+0.6
  - 右肩均量 ≥ 左肩均量：+0.4
  - 否则按比例衰减

### 7.4 突破 3% 确认（修改 `_findBreakout` 内部逻辑）

- 原 `confirmed` 条件：后 3 根不跌破颈线
- 新增：突破日收盘 ≥ `necklinePrice × (1 + breakoutConfirmPct)`
- 两者都满足 → `confirmed`；仅价格突破 + 量突破但未满足 3% → `breakout`

### 7.5 UI 标注修正（Bug B2）

- `webapp/pages/5_形态扫描.py` 的回溯天数 help 文字改为"回溯交易日数（250 交易日 ≈ 1 年）"

---

## 八、错误处理矩阵

| 异常场景 | 行为 |
|---|---|
| `headToShoulderMaxSpan < headToShoulderMinSpan` | 视为无效范围，跳过头→右肩约束（等同不启用）|
| 区间内 K 线不足以计算均量（如只有 1 根） | 该段均量 = 该根 volume，正常参与对比 |

---

## 九、影响范围

| 文件 | 改动类型 |
|---|---|
| `strategy/patterns/headShoulder.py` | B1 修复 + 3% 确认 + 成交量评分 + 头→右肩约束 + 评分权重 |
| `strategy/patterns/tests/testHeadShoulder.py` | 新增/修改对应测试用例 |
| `webapp/pages/5_形态扫描.py` | B2 help 文字修正（1 行） |

`scan.py`、`services.py`、`_utils.py` **无需修改**。

---

## 十、验收标准

1. `necklinePrice` = `max(h1Price, h2Price)`，当 H1 > H2 时不再错误地取 H2
2. `targetPriceClassic` = `2 × necklinePrice - headLow`，数值正确
3. `confirmed` 状态要求突破日收盘 ≥ 颈线 × 1.03；不满足 3% 但满足原有条件的为 `breakout`
4. 头→右肩跨度不在 [20, 65] 范围内的三元组被过滤
5. 评分权重之和 = 1.00，各维度独立验证
6. `volumeDistScore` 列存在且数值 ∈ [0, 1]
7. `findHeadShoulderTop` 结果与改动前完全一致（回归）
8. webapp help 文字包含"交易日"字样
9. 现有测试用例中因 `necklinePrice` 变化导致数值差异的，需更新期望值

---

## 十一、风险清单

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| `necklinePrice` 改为 `max(H1,H2)` 后，部分原来 `confirmed` 的变成 `breakout`（因为颈线抬高了） | 中 | 属预期行为（更严格）；用户可调低 `breakoutConfirmPct` |
| 头→右肩约束默认 20~65 过滤掉快速形态 | 中 | 参数可调；`headToShoulderMinSpan=0` 可关闭约束 |
| 成交量分布为软约束（评分），不排除量分布异常但仍高评分 | 低 | 东财文章本身说"不遵循不一定不是"，软约束合理 |
