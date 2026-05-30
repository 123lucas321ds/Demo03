# 代码审查记录 · 第2轮：工具实现层

> 审查时间：2026-05-29
> 对照文档：`doc/需求文档.md`、`doc/memory-centric-agent-redesign.md`、`docs/superpowers/plans/2026-05-29-phase-a-core-integration.md`

## 审查范围

| 文件 | 对应需求 |
|------|---------|
| `sc2_agent/tools/obs.py` | FR-04 观测工具 |
| `sc2_agent/tools/query.py` | FR-04 查询工具 |
| `sc2_agent/tools/cmd.py` | FR-05 指令工具 |
| `sc2_agent/tools/build.py` | FR-05 建造与生产工具 |
| `sc2_agent/tools/econ.py` | FR-05 经济管理工具 |
| `sc2_agent/tools/timer.py` | FR-06 Timer Scheduler 工具 |
| `sc2_agent/tools/plan.py` | FR-07 时间线规划辅助 |
| `sc2_agent/tools/review.py` | FR-08 审查工具 |
| `sc2_agent/tools/ctrl.py` | FR-01/FR-03 流程控制工具 |
| `sc2_agent/tools/hist.py` | FR-10/FR-12 历史查询工具 |
| `sc2_agent/tools/squad.py` | FR-05 编队管理工具 |
| `sc2_agent/tools/skill.py` | FR-14 技能加载工具 |

---

## 1. obs.* 观测工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `obs.resources` | `ObsResourcesTool` | ✅ |
| `obs.units` | `ObsUnitsTool` | ✅ |
| `obs.unit` | `ObsUnitTool` | ✅ |
| `obs.structures` | `ObsStructuresTool` | ✅ |
| `obs.enemy_visible` | `ObsEnemyVisibleTool` | ✅ |
| `obs.enemy_inferred` | `ObsEnemyInferredTool` | ✅ |
| `obs.map` | `ObsMapTool` | ✅ |
| `obs.bases` | `ObsBasesTool` | ✅ |
| `obs.upgrades` | `ObsUpgradesTool` | ✅ |
| `obs.game_time` | `ObsGameTimeTool` | ✅ |
| `obs.controller` | `ObsControllerTool` | ✅ |
| `obs.scores` | `ObsScoresTool` | ✅ |
| **12个** | **12个** | **完全匹配** |

### 详细审查

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| 所有 obs 工具只读 | ✅ | 全部 `read_only = True`（默认值） |
| `obs.resources` 返回矿物/气体/人口/收入 | ⚠️ 部分 | 返回 `minerals, gas, supply`，但**缺少 `income_min` 和 `income_gas`**（设计文档示例中有） |
| `obs.unit` 返回单个单位完整属性 | ✅ | 按 tag 搜索 units + structures |
| `obs.enemy_visible` 按类型过滤 | ✅ | `unit_type` 可选参数 |
| `obs.enemy_inferred` 返回推测敌方信息 | ✅ | 包含 start_location 和 opponent_race |
| `obs.map` 返回地图尺寸 + playable area | ✅ | 可 snapshot 优先或 fallback 默认值 |
| `obs.bases` 返回基地归属 + 扩张点 | ✅ | 正确识别 CommandCenter/Nexus/Hatchery |

### 差异/问题

- **⚠️ `obs.resources` 缺少收入字段**：设计文档示例 `{"income_min":450,"income_gas":80}` 表明应返回资源收入。当前实现未包含 `income_min` 和 `income_gas`。

---

## 2. query.* 查询工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `query.find_units` | `QueryFindUnitsTool` | ✅ |
| `query.find_enemy` | `QueryFindEnemyTool` | ✅ |
| `query.find_structures` | `QueryFindStructuresTool` | ✅ |
| `query.find_workers` | `QueryFindWorkersTool` | ✅ |
| `query.find_idle` | `QueryFindIdleTool` | ✅ |
| `query.idle_producers` | `QueryIdleProducersTool` | ✅ |
| `query.in_region` | `QueryInRegionTool` | ✅ |
| `query.closest` | `QueryClosestTool` | ✅ |
| `query.placements` | `QueryPlacementsTool` | ✅ |
| `query.expansions` | `QueryExpansionsTool` | ✅ |
| `query.path` | `QueryPathTool` | ✅ |
| `query.can_afford` | `QueryCanAffordTool` | ✅ |
| `query.tech_requirement` | `QueryTechRequirementTool` | ✅ |
| **13个** | **13个** | **完全匹配** |

### 差异/问题

- **无严重差异。** 13 个工具全部实现，参数和功能与文档一致。
- `QueryPlacementsTool` 额外支持了真实 placement 查询（通过 `bot.find_placement`）+ grid fallback，比文档设计更实用。

---

## 3. cmd.* 指令工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `cmd.move` | `CmdMoveTool` | ✅ |
| `cmd.attack_target` | `CmdAttackTargetTool` | ✅ |
| `cmd.attack_move` | `CmdAttackMoveTool` | ✅ |
| `cmd.stop` | `CmdStopTool` | ✅ |
| `cmd.hold` | `CmdHoldTool` | ✅ |
| `cmd.patrol` | `CmdPatrolTool` | ✅ |
| `cmd.use_ability` | `CmdUseAbilityTool` | ✅ |
| `cmd.load` | `CmdLoadTool` | ✅ |
| `cmd.unload` | `CmdUnloadTool` | ✅ |
| `cmd.siege` | `CmdSiegeTool` | ✅ |
| `cmd.unsiege` | `CmdUnsiegeTool` | ✅ |
| `cmd.cloak` | `CmdCloakTool` | ✅ |
| `cmd.decloak` | `CmdDecloakTool` | ✅ |
| `cmd.morph` | `CmdMorphTool` | ✅ |
| `cmd.repair` | `CmdRepairTool` | ✅ |
| `cmd.return_cargo` | `CmdReturnCargoTool` | ✅ |
| `cmd.cancel_order` | `CmdCancelOrderTool` | ✅ |
| `cmd.smart` | `CmdSmartTool` | ✅ |
| **18个** | **18个** | **完全匹配** |

### 详细审查

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| tag 必须来自 obs.* (FR-05, 7.5) | ✅ | 所有工具通过 `find_by_tag()` 验证 |
| tag 不存在时返回 `TAG_NOT_FOUND` | ✅ | `_resolve_units()` 统一处理 |
| 返回 success_count + errors | ✅ | `_result()` 统一格式 |
| burnysc2 原生命令映射 (FR-05) | ✅ | 使用 `unit.move()`, `unit.attack()`, `unit.stop()` 等 |

### 差异/问题

- **无差异。** 18 个 cmd 工具全部实现，参数设计与文档一致，错误处理完整。

---

## 4. build.* 建造工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `build.structure` | `BuildStructureTool` | ✅ |
| `build.cancel` | `BuildCancelTool` | ✅ |
| `build.land` | `BuildLandTool` | ✅ |
| `build.lift` | `BuildLiftTool` | ✅ |
| `build.addon` | `BuildAddonTool` | ✅ |
| `build.train` | `BuildTrainTool` | ✅ |
| `build.cancel_train` | `BuildCancelTrainTool` | ✅ |
| `build.research` | `BuildResearchTool` | ✅ |
| `build.cancel_research` | `BuildCancelResearchTool` | ✅ |
| **9个** | **9个** | **完全匹配** |

### 差异/问题

- **无差异。** 9 个 build 工具全部实现，涵盖建造、训练、挂件、研发、起飞、降落和取消。

---

## 5. econ.* 经济工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `econ.gather` | `EconGatherTool` | ✅ |
| `econ.transfer` | `EconTransferWorkersTool` | ⚠️ |
| `econ.set_mining` | — | ❌ 缺失 |
| `econ.expand` | `EconExpandTool` | ✅ |
| `econ.build_refinery` | `EconBuildGasTool` | ✅ (名称不同) |
| **5个** | **4个** | **缺1个** |

### 差异/问题

- **❌ 缺失 `econ.set_mining`**：设计文档定义 `econ.set_mining(base_id, gas_count?)` 用于调整某基地气矿工人数。当前未实现。
- **⚠️ `econ.transfer` 语义偏差**：文档定义为 `econ.transfer(count, from_base_id, to_base_id)`——按数量跨基地转移工人，但实现是 `EconTransferWorkersTool(worker_tags[], resource_tag)`——按 tag 转移到特定资源。两者语义不同：文档是"从基地 A 转移 N 个工人到基地 B"的宏观操作，实现是"让指定工人采集指定资源"的微观操作。当前实现实际上更接近 `econ.gather`。
- **名称偏差**：文档的 `econ.build_refinery` 在实现中命名为 `econ.build_gas`。

---

## 6. timer.* 定时器工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `timer.command` | `TimerCommandTool` | ✅ |
| `timer.monitor` | `TimerMonitorTool` | ✅ |
| `timer.list` | `TimerListTool` | ✅ |
| `timer.cancel` | `TimerCancelTool` | ✅ |
| **4个** | **4个** | **完全匹配** |

### 详细审查

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| `timer.command` 用结构化 `{tool_name, arguments}`，禁止字符串 (FR-06) | ✅ | 参数 `tool_name` + `arguments` object，无误 |
| `timer.monitor` 用固定枚举 metric (FR-06) | ⚠️ 部分 | 见下文 |
| `timer.monitor` 支持 `before_time` 自动过期 (FR-06) | ✅ | `before_time` 可选参数 |
| `timer.monitor` 附带 `reason` (FR-06) | ✅ | `reason` 必填参数 |
| monitor metric 枚举 (设计文档 3.3 `_eval_metric`) | ⚠️ 有差异 | 见下文 |

### 差异/问题

- **⚠️ `timer.monitor` metric 枚举少于文档设计**：

| 文档列出的 metric | 实现 schema enum | 状态 |
|----------|:--:|:--:|
| `game_time` | ✅ | |
| `minerals` | ✅ | |
| `gas` | ✅ | |
| `supply_available` | ✅ | |
| `unit_count` | ✅ | |
| `enemy_count` | ✅ | |
| `building_progress` | ✅ | |
| `unit_distance` | ❌ 缺失 | 设计文档 `_eval_metric` 函数中有 |
| `unit_in_region` | ❌ 缺失 | 设计文档 `_eval_metric` 函数中有 |

缺少 `unit_distance` 和 `unit_in_region` 两个 metric。设计文档的 `_eval_metric()` 函数包含这两个，但实现的 JSON Schema enum 中没有。**可能是 Phase A 范围裁剪，但建议后续补充。**

---

## 7. plan.* 规划辅助工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `plan.simulate` | `PlanSimulateTool` | ✅ |
| `plan.build_time` | `PlanBuildTimeTool` | ✅ |
| `plan.build_order` | `PlanBuildOrderTool` | ✅ |
| **3个** | **3个** | **完全匹配** |

### 差异/问题

- **无差异。** 三个 plan 工具均为纯计算/查表，不调 LLM，与文档要求一致。
- `PlanBuildOrderTool` 内置了两个标准开局模板（`terran_1rax_expand`、`terran_reaper_expand`），模板格式为 target list（非 timed schedule），符合文档"Agent must call plan.build_time and plan.simulate to produce exact at_time commands"的要求。

---

## 8. review.* 审查工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `review.plan` | `ReviewPlanTool` | ✅ |
| `review.params` | `ReviewParamsTool` | ✅ |
| `review.logic` | `ReviewLogicTool` | ✅ |
| **3个** | **3个** | **完全匹配** |

### 详细审查

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| 审查绑定 `staging_hash` (FR-08) | ✅ | `ReviewPlanTool` 和 `ReviewLogicTool` 都验证 hash |
| `review.params` 纯代码检查，不调 LLM | ✅ | `ReviewParamsTool.execute()` 无 LLM 调用 |
| `review.params` 检查坐标边界 (FR-08) | ✅ | 检查 x/y 在 0–map_width/map_height 内 |
| `review.params` 检查 tag 存在 | ⚠️ 仅检查是否有 tag key，不验证实际存在性 | `_has_producer_tag` 只检查 key 存在 |
| `review.logic` spawn 审查 Sub-Agent (FR-08) | ✅ | `SubAgentLogicReviewer` 实现 |
| 审查失败不抛异常 (FR-09) | ✅ | `DeterministicLogicReviewer` fallback |
| 审查结果 `verdict: PASS\|WARN\|REVISE` (FR-08) | ✅ | `LogicReview` 支持三种 verdict |
| `WARN` 不强制阻止提交 (FR-08) | ⚠️ 有差异 | 见下文 |

### 差异/问题

- **⚠️ `review.params` 不验证 tag 实际存在性**：`_has_producer_tag` 只检查 `structure_tag`/`worker_tag` key 是否在 arguments 中，但**不调用 `bot.find_by_tag()` 验证实际存在**。文档要求"所有 unit_tag 是否真实存在"。

- **⚠️ `review.plan` 中 `WARN` verdict 的行为**：`ReviewPlanTool.execute()` 在 `logic_review` 有 `severity="error"` 的 issue 时返回 failure。但如果 issue 全是 `warn` 级别，结果是 success（允许提交）。这与文档描述一致（"WARN 不应强制阻止提交"），**但 `review.plan` 返回 failure 意味着 `ctrl.commit` 校验 `review_hash` 可能会失败，从而阻止提交——这需要确认 commit 的具体行为**。

- `ReviewParamsTool` 目前是单个命令级别的检查，文档似乎预期它检查**全部**命令列表。`ReviewPlanTool.execute()` 中实际调用了 `plan.simulate` 做整体模拟（覆盖了资源合理性），部分代替了 params 的批量检查。

---

## 9. ctrl.* 流程控制工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `ctrl.commit(staging_hash)` | `CommitTool` | ✅ |
| `ctrl.abort` | `AbortTool` | ✅ |
| `ctrl.discover_tools` | `DiscoverToolsTool` | ✅ |
| `skill.load` | `SkillLoadTool` (在 skill.py) | ✅ |
| **4个** | **4个** | **完全匹配** |

### 差异/问题

- **无差异。** 4 个 ctrl 工具全部实现，参数正确。
- `DiscoverToolsTool` 支持 `include_schemas` 参数做按需展开，与文档"第三层：按需发现"的设计一致。

---

## 10. hist.* 历史工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `hist.snapshot` | `HistSnapshotTool` | ✅ |
| `hist.trend` | `HistTrendTool` | ✅ |
| `hist.events` | `HistEventsTool` | ✅ |
| `hist.unit` | `HistUnitTool` | ✅ |
| `hist.compare` | `HistCompareTool` | ✅ |
| **5个** | **5个** | **完全匹配** |

### 差异/问题

- **无差异。** 5 个 hist 工具全部实现。

---

## 11. squad.* 编队工具

### 工具数量对照

| 设计文档 (3.3) | 实现 | 状态 |
|----------|------|:--:|
| `squad.list` | — | ❌ 缺失 |
| `squad.create` | `SquadCreateTool` | ✅ |
| `squad.disband` | `SquadDisbandTool` | ✅ |
| `squad.add` | `SquadAddTool` | ✅ |
| `squad.remove` | `SquadRemoveTool` | ✅ |
| `squad.set_order` | `SquadOrderTool` | ✅ (名称不同) |
| `squad.set_count` | — | ❌ 缺失 |
| `squad.auto_balance` | — | ❌ 缺失 |
| **8个** | **5个** | **缺3个** |

### 差异/问题

- **❌ 缺失 3 个 squad 工具**：
  - `squad.list`：列出当前所有小队摘要
  - `squad.set_count(n)`：调整小队数量（自动均分兵力）
  - `squad.auto_balance()`：均分兵力到所有现有小队

- Squad 工具存在一个**架构问题**：当前所有 squad 工具共享一个 `dict[str, list[int]]`（通过依赖注入），但文档暗示 squad 状态应由 SquadManager 持有。当前实现将状态分散在工具实例中，如果工具被重新创建则状态丢失。

---

## 12. skill.load 技能工具

### 差异/问题

- **无差异。** `SkillLoadTool` 实现了 `skill.load(name)`，支持 workspace 优先于 builtin（由 `SkillLoader` 内部处理）。

---

## 第2轮审查总结

### 工具数量统计

| 命名空间 | 文档数量 | 实现数量 | 匹配 |
|----------|:------:|:------:|:--:|
| obs | 12 | 12 | ✅ |
| query | 13 | 13 | ✅ |
| cmd | 18 | 18 | ✅ |
| build | 9 | 9 | ✅ |
| econ | 5 | 4 | ⚠️ 缺1 (set_mining) |
| timer | 4 | 4 | ✅ |
| plan | 3 | 3 | ✅ |
| review | 3 | 3 | ✅ |
| hist | 5 | 5 | ✅ |
| ctrl | 4 | 4 | ✅ (skill 在 skill.py) |
| squad | 8 | 5 | ❌ 缺3 |
| **合计** | **~83** | **80** | **缺3** |

### 关键发现

1. **❌ 缺失 `econ.set_mining`**（FR-05）：影响气矿工人精细管理，建议补充。
2. **❌ 缺失 `squad.list`、`squad.set_count`、`squad.auto_balance`**（FR-05）：影响编队批量操作，其中 `squad.list` 最重要——Agent 需要知道自己创建了哪些小队。
3. **⚠️ `econ.transfer` 语义偏差**：实现的是"按 tag 到具体资源"而非文档"按数量跨基地转移"。
4. **⚠️ `timer.monitor` 缺少 `unit_distance` 和 `unit_in_region` metric**：限制了条件唤醒的灵活性。
5. **⚠️ `obs.resources` 缺少 `income_min`/`income_gas`**：影响经济规划精度。
6. **⚠️ `review.params` 不验证 tag 真实存在**：仅检查参数中有没有 tag key，不查 BotAI。

### 下一步审查

第3轮：记忆系统 + Timer 引擎 + Bot 集成 + Main（`memory/`, `timer/`, `bot.py`, `main.py`）
