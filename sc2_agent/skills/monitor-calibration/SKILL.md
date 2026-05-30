---
name: monitor-calibration
description: monitor 校准 — 如何在高频唤醒时调整 monitor 条件阈值
always: false
---

# Monitor 校准

## 问题

当 Agent 被频繁唤醒时（例如 10 秒内被唤醒 3 次以上），说明 monitor 条件过于敏感。

## 处理方式

1. 检查 hist.events 中近期的唤醒事件。
2. 识别触发过于频繁的 monitor。
3. 调整该 monitor 的阈值：
   - 增加 value（如矿从 300 提到 500）
   - 增加 before_time（缩短有效期）
   - 或直接 timer.cancel 该 monitor

## 常用校准

- 资源 monitor：threshold 应为计划消耗量的 1.5-2 倍
- 敌方单位 monitor：应设置 before_time，避免一直等待
- 定时 monitor：间隔建议不低于 30 秒
