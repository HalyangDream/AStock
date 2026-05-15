# 头肩底 v3 测试点清单

对应 plan: `2026-05-13-head-shoulder-bottom-v3.md`

---

## Task 1: 量能递减检测 + 评分权重 + 硬性过滤

### 主路径

- **TP-1.1** `_volumeDistScore` 对标准头肩底 K 线返回 `(float, bool)` 元组，score ∈ [0, 1]
- **TP-1.2** 构造量能严格递减的 K 线（avgLeft > avgHead > avgRight），`volumeDecay` 为 `True`
- **TP-1.3** `volumeDecayFilter=False`（默认）时，量能不递减的三元组仍被保留（向后兼容）
- **TP-1.4** `_score` 各维度权重之和 = 1.00，成交量维度系数 = 0.25

### 边界

- **TP-1.5** 某段只有 1 根 K 线时，该段均量 = 该根 volume，`volumeDecay` 仍正确计算
- **TP-1.6** 三段均量完全相等时，`volumeDecay = False`（不满足严格递减）
- **TP-1.7** `volumeDecayFilter=True` 但所有三元组都不满足递减 → 返回空 DataFrame

### 异常

- **TP-1.8** `findHeadShoulderTop` 透传 `volumeDecayFilter=True`，不触发过滤，结果不变（isBottom=False 隔离回归）

---

## Task 2: 买点三级标注

### 主路径

- **TP-2.1** 输出 DataFrame 包含 `buyPoint` 列
- **TP-2.2** `status="forming"` + `volumeDecay=True` → `buyPoint="rightShoulder"`
- **TP-2.3** `status in ("breakout", "confirmed")` + `hasPullback=False` → `buyPoint="breakout"`
- **TP-2.4** `status in ("breakout", "confirmed")` + `hasPullback=True` → `buyPoint="pullback"`

### 边界

- **TP-2.5** `status="forming"` + `volumeDecay=False` → `buyPoint=None`
- **TP-2.6** `findHeadShoulderTop` 结果中 `buyPoint` 全部为 `None`（isBottom=False 不标注买点）

### 异常

- **TP-2.7** 空 DataFrame（无匹配）时不报错，`buyPoint` 列不存在是合法的（空表）

---

## Task 3: 主策略 skill 更新

### 主路径

- **TP-3.1** `main-strategy/SKILL.md` C 组中新增 `#### 28. 头肩底战法`，包含形态/量能/买点/止损/目标价定义
- **TP-3.2** 加分信号表中新增 P14a / P14b / P14c 三行，编号、条件、层级均填写完整
- **TP-3.3** 绝对卖出表中新增 S25 / S26 两行

### 边界

- **TP-3.4** P14b 层级为"高优先级"（非加分），P14a / P14c 为"加分"
- **TP-3.5** 现有 P0-P13 / S0-S24 定义未被修改
