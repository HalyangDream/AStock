# Spec：头肩底 v3 — 量能递减验证 + 买点分级 + 战法入编

**版本**：v3.0  
**日期**：2026-05-13  
**状态**：待确认  
**前置**：v2 已实现颈线修正、3% 确认、成交量分布评分、头→右肩时间约束、回抽识别

---

## 一、背景

v2 上线后，对照知乎文章（zhuanlan/p/355092592）和课程体系，仍存在 3 个核心差距：

1. **量能递减只有软评分**：`_volumeDistScore` 做了"头部量最小 + 右肩量≥左肩量"评分，但文章定义的"下跌阶段量能递减（左肩量 > 头部量 > 右肩量）"没有硬性验证入口
2. **买点没有分级**：输出仅 `forming/breakout/confirmed`，无法区分文章明确的三个买点（右肩企稳/颈线突破/回抽确认）
3. **策略未入编**：主策略 skill 仍为 27 种战法 + P0-P13 / S0-S24，头肩底战法和对应 P/S 信号未写入

---

## 二、目标

1. 新增可选量能递减硬性过滤（参数控制），同时调高评分权重
2. 新增 `buyPoint` 列，三级标注买入时机
3. 将头肩底战法写入 `main-strategy/SKILL.md`，扩展 P14a/b/c + S25/26

---

## 三、非目标

- 不实现 KD 指标背离（加分项，后续单独跟进）
- 不实现波浪结构划分
- 不修改 `findHeadShoulderTop`（isBottom 隔离原则不变）
- 不改变 `scanSingle / scanBatch / scanAll` 调用签名（新列自动透传）
- 不改变 webapp 页面布局（新列由 services 自动透传）

---

## 四、决策表

| 决策点 | 方案 A | 方案 B | 方案 C | 选择 |
|---|---|---|---|---|
| 量能递减验证方式 | 纯软约束（只提权重到 0.25） | **可选硬性过滤 + 评分增强**（新参数 `volumeDecayFilter`） | 强制硬性过滤 | **B**：默认不过滤（向后兼容），用户可开启；评分权重从 0.15 提到 0.25 |
| 买点分级方式 | **新增 `buyPoint` 列** | 修改现有 `status` 列值域 | — | **A**：不破坏现有 `forming/breakout/confirmed` 契约 |
| 右肩企稳判定条件 | **forming + 右肩段量递减** | forming + score 阈值 | — | **A**：量递减是文章定义的右肩企稳核心标志 |

---

## 五、接口与方法签名

### 5.1 `findHeadShoulderBottom` 新增参数

```
volumeDecayFilter: bool = False
    是否强制要求量能递减（不满足则过滤掉三元组）
```

其余参数不变。

### 5.2 `_volumeDistScore` 返回值扩展

当前返回 `float`（0~1 评分），扩展为同时输出 `volumeDecay: bool`（三段量能是否严格递减）。

实现方式：内部检测后将 `volumeDecay` 写入返回 dict 或通过额外函数抽取；具体拆法由 plan 决定。

---

## 六、关键数据结构

### 6.1 新增输出列

| 列名 | 类型 | forming 时 | breakout/confirmed 时 |
|---|---|---|---|
| `buyPoint` | `str \| None` | `"rightShoulder"` 或 `None` | `"breakout"` 或 `"pullback"` |
| `volumeDecay` | `bool` | 照常计算 | 照常计算 |

### 6.2 `buyPoint` 判定规则

| buyPoint 值 | 条件 | 对应文章买点 |
|---|---|---|
| `"rightShoulder"` | `status == "forming"` 且 `volumeDecay == True` | 第一买点（激进） |
| `"breakout"` | `status in ("breakout", "confirmed")` | 第二买点（标准） |
| `"pullback"` | `status in ("breakout", "confirmed")` 且 `hasPullback == True` | 第三买点（保守） |
| `None` | `status == "forming"` 且 `volumeDecay == False` | 无明确买点信号 |

注意：`buyPoint` 取最高确认度的买点。当同时满足 breakout 和 pullback 条件时，标注为 `"pullback"`（确认度更高）。

### 6.3 评分权重（v3）

| 维度 | v2 权重 | v3 权重 | 变动说明 |
|---|---|---|---|
| 肩部价格对称 | 0.25 | 0.20 | 压缩 |
| 时间对称 | 0.15 | 0.15 | 不变 |
| 头部深度 | 0.20 | 0.20 | 不变 |
| 突破加分 | 0.15 | 0.10 | 压缩 |
| 前置趋势强度 | 0.10 | 0.10 | 不变 |
| 成交量分布 | 0.15 | **0.25** | 提升：量能是核心鉴别点 |
| **合计** | 1.00 | 1.00 | — |

---

## 七、P/S 信号定义（写入 skill）

### 7.1 买入信号扩展

| 编号 | 名称 | 条件 | 层级 | 出处 |
|---|---|---|---|---|
| P14a | 头肩底右肩企稳 | 右肩量萎缩（volumeDecay=True）+ 不破头 + 前置下跌趋势 | 加分 | 知乎文章 + 经典 TA |
| P14b | 头肩底颈线突破 | 放量突破颈线 + 量能递减确认 | **高优先级** | 知乎文章"突破放量" |
| P14c | 头肩底回抽确认 | 突破后回踩颈线（pullback）+ 不破颈线 | 加分 | 知乎文章"第三买点" |

### 7.2 卖出信号扩展

| 编号 | 名称 | 条件 | 层级 |
|---|---|---|---|
| S25 | 头肩底形态失败 | 跌破头部低点 L2 | 绝对卖出 |
| S26 | 头肩底假突破 | 突破颈线后回落到颈线以下 | 绝对卖出 |

### 7.3 战法定位

在主策略 27 种战法中新增 **第 28 条：头肩底战法**，归入 **C 组（K 线形态战法）**。

---

## 八、错误处理矩阵

| 异常场景 | 行为 |
|---|---|
| 某段区间只有 1 根 K 线 | 该段均量 = 该根 volume，正常参与递减对比 |
| `volumeDecayFilter=True` 但所有三元组都不满足递减 | 返回空 DataFrame（合法：没有满足条件的形态） |
| `findHeadShoulderTop` 接收到 `volumeDecayFilter` | 透传但不启用（isBottom=False 时跳过所有 v3 新逻辑） |

---

## 九、影响范围

| 文件 | 改动类型 |
|---|---|
| `strategy/patterns/headShoulder.py` | 量能递减验证 + 买点分级 + 评分权重调整 |
| `strategy/patterns/tests/testHeadShoulder.py` | 新增/修改测试用例 |
| `~/.cursor/skills/stock-course-strategy/main-strategy/SKILL.md` | 第 28 条战法 + P14a/b/c + S25/26 |

`_utils.py`、`scan.py`、`services.py`、`webapp/` **无需修改**。

---

## 十、验收标准

1. `volumeDecayFilter=True` 时，不满足量能递减（左肩量>头部量>右肩量）的三元组被过滤
2. `volumeDecayFilter=False`（默认）时，行为与 v2 完全一致（向后兼容）
3. `volumeDecay` 列存在且为 `bool`，数值正确反映三段量能递减关系
4. `buyPoint` 列存在，值域为 `{None, "rightShoulder", "breakout", "pullback"}`
5. `buyPoint` 判定逻辑：forming + volumeDecay → rightShoulder；breakout/confirmed → breakout；hasPullback → pullback
6. 评分权重之和 = 1.00，成交量分布维度权重 = 0.25
7. `findHeadShoulderTop` 结果与 v2 完全一致（回归）
8. `main-strategy/SKILL.md` 包含第 28 条战法定义和 P14a/b/c + S25/26 信号

---

## 十一、风险清单

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| `volumeDecayFilter=True` 可能过滤掉大量三元组（量能递减在 A 股不总是严格成立） | 中 | 默认 False，作为可选增强；用户自行评估是否开启 |
| 评分权重调整后原来高分形态可能降分 | 低 | 权重变化幅度可控（肩对称 -0.05，突破 -0.05，成交量 +0.10） |
| P14/S25-26 信号目前为 skill 文档级定义，代码层尚无 P/S 信号系统 | 低 | 本次仅写入 skill 文档供人工参考；代码层 P/S 系统建设为独立后续任务 |
