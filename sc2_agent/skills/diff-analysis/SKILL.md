---
name: diff-analysis
description: 差异分析 — 对比当前观测与历史快照，生成结构化变化报告
always: false
---

# 差异分析

## 触发场景

Agent 被唤醒后，如果怀疑局势发生了意外变化（资源异常、敌方突然出现、建筑被毁等），应执行差异分析。

## 操作步骤

1. 使用 `hist.snapshot(kind="decision", index=-1)` 获取最近一次决策快照。
2. 使用 `obs.resources`、`obs.units`、`obs.structures` 获取当前观测。
3. 逐项对比：
   - 资源：矿/气的变化是否在预期范围内？
   - 建筑：是否有新建筑完成？是否有建筑被摧毁？
   - 单位：我方兵力变化？敌方可见单位变化？
   - 补给：是否被卡？差值是否正常？
4. 如果有异常，记录具体差异并评估是否需要调整当前计划。

## 输出格式

```json
{
  "has_diff": true/false,
  "changes": [
    {"category": "resources/buildings/units/supply", "field": "...", "before": ..., "after": ..., "assessment": "expected/unexpected"}
  ],
  "recommendation": "keep_plan / adjust_plan / investigate"
}
```

## 工具使用

- `hist.snapshot` / `hist.compare` — 获取历史快照和对比
- `obs.resources` / `obs.units` / `obs.structures` — 获取当前观测
- 禁止使用 cmd.* / build.* / econ.* / timer.* / ctrl.*
