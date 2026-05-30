---
name: production-math
description: 人族单位/建筑成本速查、资源收入速率、产能组合消耗速率、补给管理
---

# 生产数学

此 skill 提供 plan.build_time 之外的高阶参考数据，用于评估收入与产能的匹配关系。
所有具体数值以 plan.build_time 返回为准，此表仅用于快速估算。

## 资源收入基线

| 配置 | 矿物/分钟 | 气体/分钟 |
|------|:--------:|:--------:|
| 1 SCV 采标准矿 | ~45 | — |
| 8 SCV 半饱和 | ~400 | — |
| 16 SCV 满饱和 | ~780 | — |
| 3 SCV 采一个气矿 | — | ~114 |
| 两个气矿满采 | — | ~228 |

## 关键单位/建筑速查

| 单位/建筑 | 矿物 | 气体 | 耗时(s) | 补给 | 生产者 |
|----------|:---:|:---:|:------:|:----:|--------|
| SCV | 50 | 0 | 12 | +1 | CommandCenter |
| Marine | 50 | 0 | 18 | +1 | Barracks |
| Marauder | 100 | 25 | 21 | +2 | Barracks+TechLab |
| Reaper | 50 | 50 | 32 | +1 | Barracks |
| Hellion | 100 | 0 | 21 | +2 | Factory |
| SiegeTank | 150 | 125 | 32 | +3 | Factory+TechLab |
| Medivac | 100 | 100 | 30 | +2 | Starport |
| SupplyDepot | 100 | 0 | 21 | +8 | SCV |
| Refinery | 75 | 0 | 21 | 0 | SCV |
| Barracks | 150 | 0 | 46 | 0 | SCV |
| Factory | 150 | 100 | 43 | 0 | Barracks |
| Starport | 150 | 100 | 36 | 0 | Factory |
| EngineeringBay | 125 | 0 | 35 | 0 | SCV |
| MissileTurret | 100 | 0 | 18 | 0 | SCV |
| TechLab | 50 | 25 | 18 | 0 | Barracks(addon) |
| Reactor | 50 | 50 | 36 | 0 | Barracks(addon) |

## 常见产能组合的资源消耗

持续生产时的每分钟资源消耗：

| 组合 | 矿物/分钟 | 气体/分钟 |
|------|:--------:|:--------:|
| 1 兵营连产 Marine | 167 | 0 |
| 1 兵营+Reactor 连产 Marine | 333 | 0 |
| 3 兵营+Reactor 暴 Marine | 1000 | 0 |
| 1 重工连产 SiegeTank | 281 | 234 |
| 1 星港连产 Medivac | 200 | 200 |

消耗速率公式：`成本 / duration × 60`

## 补给管理

- 开局 12/15 补给，第一个 SupplyDepot 应在人口到 13-14 前开建
- 每 8 个 Marine 约消耗一个 SupplyDepot
- 若 `supply_used > supply_cap - 4` 仍未造 Depot → 即将瓶颈，预留 21s 建造时间
