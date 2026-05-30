---
name: consolidation-guide
description: 记忆整合指南 — MemoryConsolidator 对战略判断和优先级的更新规则
always: false
---

# 记忆整合指南

MemoryConsolidator 在每轮 commit 后更新 game_state.json。

## 已知事实（代码自动维护）
- 资源数量变化
- 建筑和单位数量变化
- 科技完成情况
- 敌方可见信息

## 战略判断（LLM 在超预算时维护）
- 当前战略阶段（开局/中期/后期）
- 主要威胁方向
- 扩张策略

## 当前优先级（LLM 在超预算时维护）
- 排序列出 3-5 个当前最重要的目标
- 每个目标应有明确的完成条件
- 不应同时追求超过 5 个目标

Agent 应在每次唤醒时阅读 game_state.md 中的战略判断和当前优先级，确保本轮决策与长期战略一致。
