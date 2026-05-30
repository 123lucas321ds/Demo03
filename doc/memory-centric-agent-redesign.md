# SC2 Agent 重构：全面拥抱 nanobot 架构（项目原始文档）

> 2026-05-28

## 参考库本地路径

| 库 | 路径 |
|----|------|
| burnysc2（SC2 Python API） | `D:\Anaconda\anaconda\envs\LLM\Lib\site-packages\sc2\` |
| nanobot（Agent 框架参考） | `E:\Code\python\nanobot-main\` |
| nanobot 核心库 | `E:\Code\python\nanobot-main\nanobot\` |
| 本项目 | `E:\Code\python\scientific research\SC2\` |

> 游戏环境：星际争霸2 已在本机安装，不需要重新安装。使用已有的 `LLM` conda 环境（`D:\Anaconda\anaconda\envs\LLM\`），不要创建新环境。

> **执行模型：stop-the-world。** LLM 思考期间游戏完全暂停。Agent 通过 `ctrl.commit()` 休眠后游戏继续运行，`timer.monitor` 触发时游戏再次暂停并唤醒 Agent。不存在"LLM 边想边打"的并发场景。

---

## 1. 旧架构为什么必须抛弃

### 1.1 问题不是"设计得不够细"，而是"设计方向错了"

三层流水线（Strategy → Phase → Executor → Supervisor）的假设是：
- LLM 可以一次性理解 4000+ token 的全量观测
- 显式的分层审查能保证输出质量
- 每轮独立决策，通过"执行历史摘要"维持连续性

实际结果是：
- LLM 在全量观测面前输出安全默认值（连续10轮造补给站，从未训过坦克）
- Supervisor 导致角色混淆（Executor 输出审查报告格式，14次 parse_exhausted）
- 没有真正的记忆——"执行历史摘要"只是数据，不是理解

### 1.2 根本原因

**把 LLM 当成传统的程序模块来设计**——给它固定的输入格式、固定的输出格式、固定的审查流程。但 LLM 不是程序模块。LLM 擅长的是：在信息充分时做精准判断、在信息不足时主动探索、在迭代中逐步逼近正确方案。

三层架构剥夺了 LLM 的这三个能力：
- 把"主动探索"变成了"被动接受全量数据"
- 把"逐步逼近"变成了"一次性输出被审查后返工"
- 把"持续记忆"变成了"每轮从零推理"

---

## 2. 新架构：一个 Agent + 一组工具 + 一套记忆

不做三层。不做 Supervisor。不做策略池选择。不做显式阶段分解。

```
┌──────────────────────────────────────────────────┐
│  记忆系统                                         │
│  game_state.json ←── MemoryConsolidator(便宜LLM)    │
│  game_state.md   ←── 从 .json 派生（注入 prompt）    │
│  events.jsonl  ←── RoundRecorder(代码)            │
│  snapshots/     ←── SnapshotRecorder(代码, 三层)    │
└──────────────┬───────────────────────────────────┘
               │ 注入 system prompt    ↑ 每周期异步更新
┌──────────────▼──────────────────────────────────┐
│  AgentRunner（工具驱动循环，max N iterations）     │
│                                                  │
│  while not done:                                 │
│      response = LLM.chat(messages, tools)        │
│      if response.tool_calls:                     │
│          messages.append({role:"assistant",       │
│              tool_calls: response.tool_calls})    │
│          for each tool_call:                     │
│              result = execute(tool_call)          │
│              messages.append({role:"tool",        │
│                  tool_call_id, content: result})  │
│      else:                                       │
│          break  // 模型输出最终文本（非工具调用）    │
│                                                  │
│  最后一步必须是 ctrl.commit()                     │
│    → 提交命令时间线 → Timer Scheduler 接管         │
│    → Agent 休眠，等待下次唤醒                      │
│                                                  │
│  工具集：obs.* / query.* / cmd.* / build.*        │
│          econ.* / squad.* / timer.* / hist.*     │
│          ctrl.* / plan.* / review.*              │
│          (+ exec.* 待规划)                        │
│                                                  │
│  工具不分先后——Agent 在观察与思考的交织中按需调用：  │
│    粗看(obs.*) → 思考 → 深看(query.*) → 思考      │
│    → 自己推算时间线(plan.simulate + 数学思考)│
│    → 审查(调 review.plan subAgent) → 修正 → 提交   │
└──────────────────────┬───────────────────────────┘
                       │ 产出: timer.command[]
                       ▼
┌──────────────────────────────────────────────────┐
│  Timer Scheduler（游戏内定时器引擎）               │
│                                                  │
│  - 按 at_time 执行 timer.command                 │
│  - 每帧评估 timer.monitor 条件                    │
│  - 任一 timer.monitor 条件满足 → 唤醒 Agent       │
│  - 唤醒时附带原因上下文                            │
└──────────────────────────────────────────────────┘
```

**没有"策略层"**——策略是 game_state.md 里的一段持续判断，由记忆整合层在观察到重大事件时更新。

**没有"阶段层"**——"阶段"只是 game_state.md 里的几行当前优先级，随局势自然演变。

**没有"Supervisor"**——审查变成主 Agent 可主动调用的 `review.*` 工具（参数合法性由 `review.params` 纯代码检查，逻辑合理性由 `review.logic` spawn 审查 subAgent）。不是外部强制的审查流程。

### 2.1 多轮对话机制：结构化 messages，不拼接字符串

旧架构把观测信息、Supervisor 反馈全部拼成字符串塞进 user message——这是推理退化的直接原因。新架构使用标准的 OpenAI function calling 消息格式。AgentRunner 中每一轮工具调用追加的都是**结构化 message 对象**，对应 nanobot 的 `AgentRunner.run()` 第 134-140 行：

```python
# 模型调用工具后，AgentRunner 内部：
messages.append({"role": "assistant", "content": None, "tool_calls": [...]})
for tool_call, result in zip(tool_calls, results):
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "name": tool_call.name,
        "content": result,   # ← 工具返回值，结构化 JSON 字符串
    })
# 继续下一轮 LLM 调用，直到模型输出无 tool_calls 的最终文本
```

一轮完整的多轮对话示例：

```
messages = [
  {"role": "system", "content": "{game_state.md}\n\n{命名空间摘要}"},
  {"role": "user",   "content": "game_time=120s。唤醒原因: timer.monitor('game_time>=120', '检查 Factory')"},

  # Iteration 1
  {"role": "assistant", "content": None, "tool_calls": [
    {"id":"c1", "function":{"name":"obs.resources", "arguments":"{}"}}
  ]},
  {"role": "tool", "tool_call_id": "c1", "name": "obs.resources",
   "content": '{"minerals":820,"gas":45,"supply":"32/46","income_min":450,"income_gas":80}'},

  # Iteration 2
  {"role": "assistant", "content": None, "tool_calls": [
    {"id":"c2", "function":{"name":"obs.structures", "arguments":"{}"}},
    {"id":"c3", "function":{"name":"obs.enemy_visible", "arguments":"{}"}}
  ]},
  {"role": "tool", "tool_call_id": "c2", "content": "Factory(85%)..."},
  {"role": "tool", "tool_call_id": "c3", "content": "Marine×3, 无异常"},

  # Iteration 3~8 — 主 Agent 自己逐步构建命令时间线
  {"role": "assistant", "content": None, "tool_calls": [
    {"id":"c4", "function":{"name":"plan.build_time", "arguments": '{"type":"TechLab"}'}}
  ]},
  {"role": "tool", "tool_call_id": "c4", "content": '{"duration":18,"cost":{"minerals":50,"gas":50}}'},
  {"role": "assistant", "content": None, "tool_calls": [
    {"id":"c5", "function":{"name":"timer.command", "arguments": '{"at_time":127.0,"tool_name":"build.addon","arguments":{"structure_tag":42,"addon_type":"TechLab"}}'}}
  ]},
  {"role": "tool", "tool_call_id": "c5", "content": "OK"},
  ...（逐步推算，每步查 plan.build_time + plan.simulate + 调 timer.command）

  # Iteration 9 — 调用审查工具
  {"role": "assistant", "content": None, "tool_calls": [
    {"id":"c9", "function":{"name":"review.plan", "arguments": '{"staging_hash":"sha256:..."}'}}
  ]},
  {"role": "tool", "tool_call_id": "c9",
   "content": '{"verdict":"WARN","issues":[{"code":"IDLE_BARRACKS",...}]}'},

  # Iteration 10 — 模型决定提交
  {"role": "assistant", "content": None, "tool_calls": [
    {"id":"c10", "function":{"name":"ctrl.commit", "arguments":"{}"}}
  ]},
  {"role": "tool", "tool_call_id": "c10", "content": "OK — 25 commands scheduled, agent sleeping until t=300"},

  # 循环结束——ctrl.commit 返回后，Timer Scheduler 接管
]
```

**Sub-Agent 的返回方式**：与 nanobot 的异步消息注入不同，SC2 的 `review.logic` subAgent 在工具 handler 内部**同步等待**结果，返回值直接作为 tool message 的 `content` 写入主 Agent 的 messages 数组。主 Agent 在下一轮迭代中读到审查结果并决定如何修正。时间线规划不使用 subAgent——主 Agent 自己在工具调用循环中完成数学推理。

**跨周期上下文管理**——直接对应 nanobot 的 Session + MemoryConsolidator 模式：

nanobot 的核心机制（`Session` + `MemoryConsolidator`）：

```
Session.messages        ← 追加写入，永不删除（保证 LLM prompt cache 效率）
Session.last_consolidated ← 游标，标记"已被摘要归档"的消息位置

get_history():          只返回游标之后的消息（最近几轮原始对话）
build_system_prompt():  注入 MEMORY.md（旧消息的摘要，由 Consolidator 维护）

maybe_consolidate_by_tokens():
  if 当前 prompt token 数 > 预算:
      取游标之后最早的一批消息 → 发送给另一个 LLM 做摘要
      摘要写入 MEMORY.md + HISTORY.md
      游标前进（这些消息不再进入 get_history()，但仍在文件中）
```

SC2 的映射：

```
Session.messages        → 每轮 wake-up 周期的 messages 追加写入（JSONL 文件）
Session.last_consolidated → 已整合进 game_state.json 的消息位置

get_history():          只返回游标之后的消息 → 最近几轮的原始对话保留在上下文中
                       同 nanobot 的 `_find_legal_start()`：裁剪时必须保证 tool result
                       前面有匹配的 assistant tool_calls，避免 orphan tool result
build_system_prompt():  注入 game_state.md（旧周期的记忆摘要）

MemoryConsolidator:
  if prompt tokens 超预算:
      取最早的一批消息 → 调用整合 LLM（qwen-turbo）
      更新 game_state.md
      游标前进
```

为什么这样设计：Agent 被唤醒时，它看到的上下文是 `[system: game_state.md] + [最近几轮 raw messages] + [本轮 user message]`。Agent 可以回顾"我刚才做了什么"（raw messages），也可以通过 game_state.md 了解"前几分钟的整体局势"（摘要）。老消息不会被删除——它们留在 JSONL 文件中，`hist.*` 工具可以查询。但老消息不会进入 LLM 的上下文窗口——它们已被摘要替代，token 预算留给最近的决策。

### 2.2 System Prompt 设计

参考 nanobot 的 `ContextBuilder.build_system_prompt()`——身份 + 启动文件 + 记忆 + 技能摘要。SC2 对应为四段式结构：

```
┌──────────────────────────────────────────┐
│ 1. 身份与运行时（静态）                    │
│    你是谁、在什么环境运行、核心约束         │
├──────────────────────────────────────────┤
│ 2. 当前局势（动态——注入 game_state.md）    │
│    战况、优先级、已知事实、关键事件         │
├──────────────────────────────────────────┤
│ 3. 可用工具（半静态——命名空间摘要）          │
│    11个命名空间，每个一行描述               │
├──────────────────────────────────────────┤
│ 4. 可用技能（动态——skill 目录摘要）         │
│    引导 Agent 按需加载，非强制              │
└──────────────────────────────────────────┘
```

#### 第一部分：身份与运行时

```
你是星际争霸2人族指挥官 AI。运行在 burnysc2 环境中，通过工具与游戏交互。

你不是在"写 YAML"或"输出文本"——你通过调用工具来观察、推理和行动。
你是自己的规划师（plan.*）、审查者（review.*）和调度者（timer.*）。

核心约束：
- 所有带 at_time 的命令必须经过数学推理计算（查 plan.build_time + plan.simulate），禁止手动估算
- 提交前必须调用 review.plan 审查最终命令列表
- unit_tag 必须从 obs.* 获取，禁止编造
- 命令消耗不能超过预测资源收入
```

这里的关键：Agent 的身份是**会使用工具的指挥官**，不是"先输出策略、再输出阶段、再输出命令"的文本生成器。旧架构的指令（28 条具体规则、8 步强制流程）全部移除——那是在替模型思考。

#### 第二部分：当前局势

直接注入 `game_state.md`（5.3 节格式），每次唤醒时可能不同。

#### 第三部分：可用工具

命名空间摘要（3.6 节第一层），11 行：

```
可用工具分为 11 个命名空间：
  obs     — 读取当前游戏状态（12 个工具）
  query   — 按条件搜索实体（13 个工具）
  ...
```

具体参数由 OpenAI function calling schema 提供，不写在 system prompt 里。

#### 第四部分：可用技能

完全参考 nanobot 的 `SkillsLoader` 机制：

```
## Skills

以下技能文件包含领域知识和工作流指南。标记 always 的技能已自动加载到上下文中。
其他技能在需要时调用 skill.load(name) 按需加载。

<skills>
  <skill available="true">
    <name>main-flow</name>
    <description>决策周期工作流：从唤醒到提交的完整流程指南</description>
    <location>skills/main-flow/SKILL.md</location>
  </skill>
  <skill available="true">
    <name>production-math</name>
    <description>建造耗时表、训练耗时表、资源收入速率、科技树前置链</description>
    <location>skills/production-math/SKILL.md</location>
  </skill>
  ...
</skills>
```

每个 skill 是一个 `skills/{name}/SKILL.md` 文件，YAML frontmatter + Markdown 正文，与 nanobot 完全一致：

```markdown
---
name: production-math
description: 建造耗时表、训练耗时表、资源收入速率、科技树前置链
---

# 生产数学

## 建造耗时
| 建筑 | 耗时 | 矿物 | 气体 | 前置 |
|------|------|------|------|------|
| SupplyDepot | 21s | 100 | 0 | — |
| Barracks | 46s | 150 | 0 | — |
...
```

**加载机制**：

- `always: true` 的 skill（如 `main-flow`）在 system prompt 构建时自动注入，参考 nanobot 的 `get_always_skills()`
- 其他 skill 由 Agent 通过 `skill.load(name)` 工具按需加载——handler 读文件内容 → 追加到 messages 数组 → Agent 在下一轮迭代中读到知识
- workspace 优先于 builtin：`skills/` 目录下的 skill 覆盖同名的内置 skill，参考 nanobot 的 `list_skills()` 双目录扫描

**8 个 skill 清单**：

| skill | always | 使用者 | 内容 |
|-------|:------:|--------|------|
| main-flow | ✅ | 主 Agent | 决策周期完整工作流、审查与推理的交错指南、元认知自查流程 |
| production-math | | 主 Agent（规划时加载） | 建造/训练耗时表、资源收入基线、科技树前置链 |
| timeline-planning | | 主 Agent（规划时加载） | 逐步推算方法：怎么从目标列表推 at_time、资源约束怎么校验 |
| standard-openings | | 主 Agent（开局时加载） | 1-1-1、死神开局、两兵营压制等标准模板 |
| review-knowledge | | `review.logic` subAgent | 兵种克制速查、各阶段合理阈值、常见错误模式 |
| review-dimensions | | `review.logic` subAgent | 4 维审查流程、PASS/WARN/REVISE 判定标准 |
| consolidation-guide | | MemoryConsolidator 整合 LLM | 怎么从事实差异推断战略变化、怎么重新排列优先级 |
| monitor-calibration | | 校准 subAgent（高频唤醒时） | 各阶段合理阈值参考、调整幅度指南 |

#### 设计原则

**system prompt 只写"怎么用工具"，不写"应该怎么做"**。工作流指南、领域知识、流程模板全部下沉到 skill 文件中，由 Agent 按需加载。对比旧架构：

| | 旧架构 system prompt | 新架构 system prompt |
|---|---|---|
| 角色数 | 4 个（Strategy/Phase/Executor/Supervisor） | 1 个（指挥官） |
| 指令条数 | 28 条具体规则 + 8 步强制流程 | 4 条硬约束 |
| 观测 | 全量 JSON dump 拼在 prompt 里 | 只注入 game_state.md 摘要 |
| 领域知识 | 策略池 YAML 格式示例嵌在 prompt 中 | 下沉到 skill 文件，按需加载 |
| 输出格式 | "禁止输出 X""只能输出 Y" | 无——Agent 输出的是工具调用 |

---

## 3. 工具系统：全面原子化 + 命名空间分类

### 3.1 设计原则

**细粒度**：每个工具只做一件事，对应 burnysc2 的一个底层动作或查询。Agent 通过组合多个工具调用来完成复杂任务，而不是调用一个"高级 wrapper"。

**命名空间分层**：用 `namespace.action` 命名实现渐进式披露。Agent 看到名字就知道工具属于哪个类别，无需阅读全部描述。

**即时反馈**：每个执行类工具返回操作结果——成功/失败 + 原因。Agent 不再等 60 秒才知道上一轮指令是否生效。

### 3.2 工具命名空间总览

```
obs.*      观测 —— 读取当前游戏状态（只读）
query.*    查询 —— 按条件搜索特定实体
cmd.*      指令 —— 对单位/建筑下达即时命令（burnysc2 原生动作）
build.*    建造 —— 建造、训练、研发、挂件
econ.*     经济 —— 资源采集、工人分配、扩张
squad.*    编队 —— 小队管理、批量单位控制
timer.*    定时器 —— 定时唤醒、监测条件、定时命令
plan.*     规划 —— 资源预测 + 建造耗时数据（主 Agent 自己做数学推理）
review.*   审查 —— Sub-Agent 决策质量审查
hist.*     历史 —— 查询过去的游戏状态
ctrl.*     控制 —— 决策周期的起止、工具发现
```

### 3.3 各类别工具清单

#### obs — 观测（只读，读当前帧）

直接从 `botAI` 读取，不修改游戏状态。Agent 在决策开始时调用以了解局势。

```
obs.resources        → 矿物/气体/人口/收入/工人数
obs.units            → 我方所有单位的摘要列表[{tag,type,x,y,hp,status}]
obs.unit             → 单个单位的完整属性 (tag → 全部55个字段)
obs.structures       → 我方所有建筑的摘要列表
obs.enemy_visible    → 当前视野内的敌方单位
obs.enemy_inferred   → 曾见过但当前不可见的敌方单位（基于 enemy_tracker）
obs.map              → 地图信息（名称、尺寸、总矿基数）
obs.bases            → 基地拓扑（各基地归属、位置、资源量）
obs.upgrades         → 已完成/进行中的科技升级
obs.game_time        → 当前游戏时间（秒）和帧数
obs.controller       → 人口上限占用、空闲补给量、当前警报列表
obs.scores           → 双方分数统计
```

#### query — 查询（带条件检索实体）

在 `obs` 的基础上加过滤条件，返回精确匹配的结果。

```
query.find_units     → 按类型/区域/状态过滤我方单位
query.find_enemy     → 按类型/区域过滤敌方单位
query.find_structures→ 按类型/完成状态/基地过滤建筑
query.find_workers   → 按状态（采矿/采气/空闲/侦察中）过滤工人
query.find_idle      → 列出所有闲置单位（不限类型）
query.idle_producers → 列出空闲的生产建筑（兵营/重工/星港）
query.in_region      → 矩形区域内所有单位（含敌方）
query.closest        → 距离某点最近的 N 个单位
query.placements     → 在某基地附近找到可放置某建筑的位置
query.expansions     → 可扩张的矿点列表及状态
query.path            → 两点间的寻路距离估算
query.can_afford     → 当前资源能否负担指定单位/建筑/升级
query.tech_requirement→ 查询某单位的科技树前置条件
```

#### cmd — 指令（burnysc2 原生动作，即时执行）

每个工具对应一个底层游戏指令。Agent 每次调用指挥具体的单位做具体的动作。

```
cmd.move             → (tags[], x, y) 移动到坐标
cmd.attack_target    → (tags[], target_tag) 攻击指定单位
cmd.attack_move      → (tags[], x, y) A-move到位置
cmd.stop             → (tags[]) 停止当前指令
cmd.hold             → (tags[]) 原地驻守
cmd.patrol           → (tags[], x, y) 巡逻
cmd.use_ability      → (tags[], ability_id, target_tag?, x?, y?) 使用技能
cmd.load             → (tags[], transport_tag) 装载到运输船/地堡
cmd.unload           → (transport_tag, x?, y?) 卸载所有乘客
cmd.siege            → (tags[]) 攻城模式
cmd.unsiege          → (tags[]) 移动模式
cmd.cloak            → (tags[]) 隐身
cmd.decloak          → (tags[]) 显形
cmd.morph            → (tags[], morph_target) 变形（轨道指挥部/行星要塞等）
cmd.repair           → (worker_tags[], target_tag) SCV维修
cmd.return_cargo     → (tags[]) 工人返回资源
cmd.cancel_order     → (tag, order_index) 取消单位当前指令队列中的某一项
cmd.smart             → (tags[], target_tag|position) 右键智能指令
```

#### build — 建造与生产

```
build.structure      → (worker_tag, building_type, x, y) 工人建造
build.cancel         → (structure_tag) 取消建造中的建筑
build.land           → (structure_tag, x, y) 降落飞行建筑
build.lift           → (structure_tag) 起飞建筑
build.addon          → (structure_tag, addon_type) 建造挂件
build.train          → (structure_tag, unit_type, count?) 训练单位
build.cancel_train   → (structure_tag, queue_index) 取消训练队列项
build.research       → (structure_tag, upgrade_id) 研究升级
build.cancel_research→ (structure_tag) 取消研究
```

#### econ — 经济管理

```
econ.gather          → (worker_tags[], resource_tag?) 指派工人采集
econ.transfer        → (count, from_base_id, to_base_id) 跨基地转移工人
econ.set_mining      → (base_id, gas_count?) 调整某基地气矿工人数
econ.expand          → (near_base_id?) 扩张到新矿点
econ.build_refinery  → (base_id) 在某基地建造气矿（需要可用工人）
```

#### squad — 编队控制

在单个单位指令之上的编队抽象。并非替代 cmd.*，而是提供批量操作的便捷方式。

```
squad.list           → 当前所有小队的摘要
squad.create         → (name?) 创建新小队
squad.disband        → (squad_id) 解散小队
squad.add            → (squad_id, tags[]) 分配单位到小队
squad.remove         → (squad_id, tags[]) 从小队移除单位
squad.set_order      → (squad_id, action, params...) 设置小队状态
squad.set_count      → (n) 调整小队数量（自动均分兵力）
squad.auto_balance   → () 均分兵力到所有现有小队
```

#### hist — 历史查询

查询过去的游戏状态数据（由存储层持久化）。

```
hist.snapshot        → (kind?, index?) 返回某份快照（kind: minute/decision/5sec）
hist.trend           → (metric, lookback_n) 从分钟级快照中取最近 N 份做趋势
hist.events          → (type?, since_time?) 查询事件日志
hist.unit            → (tag, from_time, to_time) 从三层快照中重建某单位轨迹
hist.compare         → (kind, index_a, index_b) 同层两份快照的结构化 diff
```

#### ctrl — 流程控制

```
ctrl.commit(staging_hash) → 提交本轮命令时间线 + 监测条件（必须与审查 hash 匹配）
ctrl.abort           → 放弃本轮变更，保留现有命令和监测条件
ctrl.discover_tools  → (namespace?) 列出某命名空间下的工具详情
skill.load           → (name) 按需加载指定 skill 的完整 Markdown 内容
```

#### timer — 定时命令与唤醒条件

Agent 决策的产出是带精确时间戳的命令（`timer.command`）。唤醒也统一为条件判断（`timer.monitor`）——`game_time >= 180` 和 `minerals > 400` 本质上都是布尔条件，不需要两个工具。

```
timer.command         → (at_time, tool_name, arguments) 在精确游戏时间执行某个结构化工具调用
timer.monitor         → (metric, op, value, ...) 持续监测，条件满足时唤醒 Agent
timer.list            → 列出当前所有活跃的 timer
timer.cancel          → (id) 取消指定 timer
```

`timer.command` 示例——Agent 决策的产出，统一为结构化格式：

```
timer.command(at_time=3.21, tool_name="build.train", arguments={"structure_tag": 12, "unit_type": "SCV"})
timer.command(at_time=45.0, tool_name="cmd.move", arguments={"tags": [34], "x": 35.2, "y": 40.1})
```

字符串形式（`call="build.train(...)"`）仅用于日志展示，不作为 API 参数。

`timer.monitor` 示例——结构化参数，固定枚举，不需要表达式引擎：

```
# 定时唤醒（时间也是条件的一种）
timer.monitor(
    metric="game_time", op=">=", value=180,
    reason="时间线到期，检查执行结果"
)

# 计划偏差检测——Agent 对自身推理准确性的兜底
timer.monitor(
    metric="minerals", op=">", value=400, before_time=100,
    reason="预期矿不应超过400，实际堆积→建造时间推算有偏差"
)

# 单位数量异常
timer.monitor(
    metric="unit_count", unit_type="Marine", op="<", value=8, before_time=160,
    reason="预期 Marine 数量稳定，减少→可能发生战斗"
)
```

**不需要表达式引擎**。可监测的对象是固定枚举：`game_time` / `minerals` / `gas` / `supply_available` / `unit_count` / `enemy_count` / `building_progress`。帧循环里就是一行 `if`：

```python
def _eval_metric(m, bot):
    if m.metric == "game_time":         return bot.time
    if m.metric == "minerals":          return bot.minerals
    if m.metric == "gas":               return bot.vespene
    if m.metric == "supply_available":  return bot.supply_cap - bot.supply_used
    if m.metric == "unit_count":        return bot.units.filter(lambda u: u.name == m.unit_type).amount
    if m.metric == "enemy_count":       return bot.enemy_units.amount
    if m.metric == "building_progress": return _get_building(bot, m.building_type).build_progress
    if m.metric == "unit_distance":     return _unit_by_tag(bot, m.unit_tag).distance_to(Point2((m.target_x, m.target_y)))
    if m.metric == "unit_in_region":    return _unit_in_rect(bot, m.unit_tag, m.x1, m.y1, m.x2, m.y2)  # 返回 bool
```

`before_time` 的作用：超过指定时间后条件自动注销。一个 `timer.monitor(metric="minerals", op=">", value=400, before_time=100)` 在 t=100 之后就不再评估——Agent 预设的"这个时间段内不该出问题"的时间窗口。

#### plan — 规划辅助

主 Agent 自己做数学推理，`plan.*` 提供纯计算的辅助工具（不调 LLM）：

```
plan.simulate         → (commands[], horizon) 确定性模拟器：输入命令序列，纳入 active timers、
                        当前生产队列、补给占用、建筑占用、工人分配，返回每步预测资源 + 失败点
plan.build_time       → (unit_or_building_type) 查询建造/训练耗时
plan.build_order      → (strategy_name) 从标准开局模板返回目标列表
```

主 Agent 反复调 `plan.simulate` 逐步逼近可行时间线——每次调参后重新模拟验证，直到所有命令通过资源校验。

#### review — Sub-Agent 审查

由主 Agent 在提交前主动调用，内部 spawn 审查 subAgent。详见 4.7 节。

```
review.plan           → 完整审查 = review.params + review.logic
review.params         → 纯代码检查（tag存在性、坐标合法性、科技树），不调 LLM
review.logic          → spawn 审查 subAgent，检查战术/战略/资源合理性
```

### 3.4 工具总数

| 命名空间 | 工具数 | 粒度 |
|----------|:-----:|------|
| obs | ~12 | burnysc2 BotAI 属性直接映射 |
| query | ~13 | burnysc2 unit/structure 过滤 + 寻路 + 科技树 |
| cmd | ~17 | burnysc2 UnitCommand / Ability 一对一映射 |
| build | ~9 | ProductionManager 任务拆解 |
| econ | ~5 | ResourceManager 操作拆解 |
| squad | ~8 | SquadManager 操作 |
| hist | ~5 | 历史存储层查询接口 |
| ctrl | ~4 | 决策轮控制 + skill 加载 |
| timer | ~4 | 定时命令 + 条件唤醒 |
| plan | ~3 | 纯计算辅助（资源曲线/建造耗时/开局模板） |
| review | ~3 | 审查 Sub-Agent（参数+逻辑） |
| **合计** | **~83** | |
| *(exec)* | *(2)* | *沙盒执行，待规划* |

~83 个工具。每个工具的 schema description 平均 ~80 字，总计 ~6500 字 ≈ 1600 token，在每次 LLM 请求中完全可承受。

### 3.5 扩展方向：`exec` 沙盒执行器（待规划）

#### 问题

`obs.*` 和 `query.*` 是"二级工具"——它们在 burnysc2 原生数据上做统计和批处理。但统计组合是无限的：

```
"我方空闲且血量<50%的单位有哪些？"
"找出所有正在攻击敌方建筑的我方单位"
"敌方在过去30秒内新出现的单位类型有哪些？"
"我方各基地的矿物饱和度分别是多少？"
```

不可能为每种统计组合都写一个工具。query.* 覆盖了最常见的情况，但 Agent 的想象力不应该被工具作者预设的查询模式限制。

#### 方案：沙盒化 `exec` 命名空间

参考 nanobot 的 `ExecTool`（bash 沙盒）和 Claude Code 的 `Bash` 工具——给 Agent 一个受控的代码执行环境。

```
exec.python           → (code: str) 在受限沙盒中执行 Python 代码，返回 stdout
exec.help             → 列出沙盒中可用的变量和函数
```

**沙盒提供的预绑定变量**（只读视图，不可修改游戏状态）：

```python
# Agent 在代码中可直接使用的变量（无需 import）
bot           # 当前 BotAI 的只读代理——所有属性可读，但写操作被拦截
units         # bot.units 的快捷方式
enemy         # bot.enemy_units + bot.enemy_structures
structures    # bot.structures

# 辅助函数（预导入）
filter_by_type(units, "Marine")        # 按类型过滤
filter_by_region(units, x1, y1, x2, y2) # 按矩形区域过滤
filter_idle(units)                       # 过滤空闲单位
filter_by_health(units, min=0, max=100)  # 按血量百分比过滤
group_by_type(units)                     # 按类型分组
count_by_type(units)                     # 按类型计数
closest_n(units, x, y, n)               # 最近的N个
```

**Agent 使用示例**：

```
Agent → exec.python("""
low_hp_marines = [u for u in filter_by_type(units, "Marine")
                  if u.health_percentage < 0.5]
print(f"低血量枪兵: {len(low_hp_marines)}个")
for u in low_hp_marines:
    print(f"  tag={u.tag} hp={u.health:.0f}/{u.health_max:.0f} pos=({u.position.x:.1f},{u.position.y:.1f})")
""")
Tool → 低血量枪兵: 3个
         tag=1234 hp=18/45 pos=(35.2,40.1)
         tag=5678 hp=22/45 pos=(36.1,41.3)
         tag=9012 hp=31/45 pos=(34.8,39.7)
```

**安全边界**：
- 沙盒只暴露只读视图——任何修改 `bot` 状态的操作抛出 `PermissionError`
- 超时限制：5 秒，超时自动终止
- 内存限制：禁止 `import` 未在白名单中的模块，禁止文件 I/O，禁止网络
- 输出截断：stdout 超过 2000 字符自动截断

#### 与 query.* 的关系

`query.*` 不会被取代——它是高频查询的"预编译"版本：
- `query.idle_producers` = `exec.python("filter_idle(structures)")`，但更快（本地代码 vs Python 解释器开销）
- `query.can_afford` 有预计算的成本表，`exec` 中也可以做但不如专用工具高效

```
query.*  = 常用查询的高性能缓存版本
exec.*   = Agent 自由表达任意查询的通用出口
```

两者共存。`query.*` 覆盖 80% 的高频场景，`exec.*` 提供无限自由度。

#### 实施时机

Phase 2 不做 `exec.*`。先交付 `query.*` 内置的 13 个工具，在实战中观察 Agent 被哪些查询模式卡住的频率。收集足够的"Agent 想做但工具不支持"的案例后，再决定 `exec.*` 的沙盒边界和预绑定 API。过早实现会引入安全风险和性能开销，且 API 设计缺乏实战依据。

### 3.6 渐进式披露策略

**第一层：命名空间摘要**（在 system prompt 中）

```
可用工具分为 11 个命名空间（exec 待规划）：
  obs     — 读取当前游戏状态（12个工具）
  query   — 按条件搜索实体（13个工具）
  cmd     — 对单位下达即时指令（17个工具）
  build   — 建造/训练/研发（9个工具）
  econ    — 经济/资源/扩张管理（5个工具）
  squad   — 编队管理（8个工具）
  timer   — 定时命令 + 条件唤醒（4个工具）
  plan    — 规划辅助：资源曲线/建造耗时/开局模板（3个工具）
  review  — Sub-Agent 决策审查（3个工具）
  hist    — 查询历史状态（5个工具）
  ctrl    — 决策轮控制 + skill 加载（4个工具）
  exec    — 沙盒执行统计代码（2个工具，待规划）

如果你不确定某命名空间下有哪些具体工具，调用 ctrl.discover_tools("命名空间") 查看。
```

**第二层：工具 schema**（通过 OpenAI function calling 自动提供）

所有工具的完整 JSON Schema 传给模型。模型通过函数名（如 `cmd.siege`、`obs.resources`）自然分辨工具类别，无需阅读全部描述。

**第三层：按需发现**（`ctrl.discover_tools`）

当 Agent 不确定某个命名空间下有哪些具体参数时，主动调用 `ctrl.discover_tools("cmd")` 获取该空间下全部工具的详细描述。

这种三层设计确保：Agent 日常决策时只需通过名字识别工具（第一层），需要细节时阅读 schema（第二层），探索不熟悉的领域时主动查询（第三层）。

---

## 4. 执行模型：时间线 + 自设定时器 + 监测条件

### 4.0 核心不变量：stop-the-world 状态机

```
PAUSED_THINKING  ──ctrl.commit()──▶  RUNNING_SLEEP
       ▲                                  │
       │    timer.monitor 条件满足          │
       └──────────────────────────────────┘
              （游戏暂停）         （游戏运行）
```

**硬规则**：

- `PAUSED_THINKING`：游戏完全暂停。LLM、subAgent、`plan.*`、`obs.*`、所有工具调用**只在此状态执行**。
- `RUNNING_SLEEP`：游戏正常运行。Timer Scheduler 每帧执行 `timer.command` + 评估 `timer.monitor`。**禁止**任何 LLM 调用。
- 状态转换：`ctrl.commit()` 是唯一的 PAUSED→RUNNING 入口。`timer.monitor` 触发是唯一的 RUNNING→PAUSED 入口。
- `ctrl.commit()` 必须是每轮 AgentRunner 循环的**最后一个 tool_call**——commit 之后本轮不能再有任何工具调用。

### 4.1 核心理念：Agent 掌握"何时再思考"的主动权

三层架构的固定频率决策（每 30-60 秒触发一次）有两个致命缺陷：
- **不必要时也在决策**——局势稳定、命令顺利执行时也在浪费 LLM 调用
- **必要时不决策**——命令执行出现意外（矿物突然堆积、敌人突然出现）时，只能等下一轮

新方案：Agent 在每次决策周期的最后，自己设定"下次什么时候叫醒我"以及"什么意外情况下提前叫醒我"。

### 4.2 两种 Timer

`timer.schedule` 已合并到 `timer.monitor`——`game_time >= 180` 就是一个普通的布尔条件，没必要单独一个工具。

```
┌─────────────────────────────────────────────────┐
│                Timer Scheduler                   │
│                                                  │
│  ┌─ timer.command ───────────────────────────┐  │
│  │  "3.21s: CC训练SCV"                        │  │
│  │  "17.5s: SCV(tag=42)造SupplyDepot(35,40)" │  │
│  │  "45.0s: Marine(tag=34)移动到(35.2,40.1)" │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌─ timer.monitor ───────────────────────────┐  │
│  │  定时唤醒: metric="game_time", >=, 180     │  │
│  │  偏差检测: metric="minerals", >, 400       │  │
│  │  每个条件附带 reason（唤醒时的上下文）      │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

**`timer.command`**：Agent 决策的最终产出。每条命令带精确的 `at_time`，并以结构化 `{tool_name, arguments}` 表示实际要执行的工具调用。字符串形式只允许出现在日志和人类可读展示中，不进入执行路径。

**工具并发规则**：同一轮 LLM 可能返回多个 tool_calls。`obs.*` / `query.*` / `plan.*` / `hist.*` 等读工具可并发执行。`timer.*` / `build.*` / `cmd.*` / `econ.*` / `squad.*` / `ctrl.*` 等写工具按返回顺序串行执行。`ctrl.commit` 必须是最后一轮唯一的 tool_call——commit 所在响应中不能同时包含其他工具，commit 之后本轮循环立即结束。

**提交顺序**（`ctrl.commit` handler 内部，严格按序执行，失败不重试，已写内容成为历史日志）：

```
1. SnapshotRecorder.save("decision", bot) + events.flush()  ← 先持久化（可恢复）
2. Session 追加本轮 messages → JSONL                       ← 追加写入（不丢）
3. 代码更新 game_state.json "已知事实" + "关键事件"
4. MemoryConsolidator.maybe_consolidate()                   ← stop-the-world 下同步执行
5. 从 game_state.json 重新生成 game_state.md                 ← Markdown 仅派生、只读
6. Timer Scheduler 注册 timer.command[] + timer.monitor[]    ← 最后生效
7. 状态转换: PAUSED_THINKING → RUNNING_SLEEP
```

**`timer.monitor`**：统一的条件唤醒机制。结构化参数 + 固定枚举，不需要表达式引擎也不需要 subAgent：

```
# 定时唤醒
timer.monitor(metric="game_time", op=">=", value=180, reason="时间线到期")

# 计划偏差检测
timer.monitor(metric="minerals", op=">", value=400, before_time=100, reason="矿物异常堆积")
timer.monitor(metric="unit_count", unit_type="Marine", op="<", value=8, before_time=160, reason="兵力异常减少")
```

可监测对象：`game_time` / `minerals` / `gas` / `supply_available` / `unit_count(unit_type)` / `enemy_count` / `building_progress(building_type)` / `unit_distance` / `unit_in_region`。够用即可，不追求图灵完备。`before_time` 控制条件有效窗口——超时自动注销，避免过时条件残留在帧循环中。注意 `timer.monitor` 不检查"决策本身对不对"——那是 `review.*` 的职责。

**高频唤醒的元认知**：Agent 每次被唤醒时先通过 `hist.events(type="wake_up", since=最近N秒)` 检查唤醒频率。如果短时间内被频繁唤醒，说明两种情况之一：
1. 游戏内确实有紧急事件连续发生 → 正常处理
2. monitor 条件设得太敏感 → spawn subAgent 重新校准条件（扩大阈值、放宽时间窗口），避免狼来了

这不需要新的基础设施——Agent 只需在每轮开头做一个自查。

### 4.3 Sub-Agent 机制

参考 nanobot 的 `SubagentManager` + `SpawnTool` 模式。Sub-Agent 由主 Agent 通过工具调用创建，不是外部服务。主 Agent 调用 `review.logic(commands, context)` → 工具 handler 内部 spawn 一个审查 subAgent → subAgent 运行完毕后结果作为工具返回值交还给主 Agent。

注意：时间线规划不使用 subAgent——主 Agent 自己在工具调用循环中完成资源/时间的数学推理。subAgent 用于以下需要隔离上下文的场景：

- **审查**（`review.logic`）——独立纯净上下文做战术/战略质量检查
- **差异分析**——对比当前观测与上次决策时/最近 N 秒前的观测，返回结构化 diff
- **monitor 校准**——高频唤醒时重新调整监测条件阈值

```
主 Agent → review.logic(commands="...", context="...")
  │
  ▼
review.logic 工具 handler：
  ├─ 1. 构建 subAgent 专用的 system prompt
  │     "你是 SC2 决策审查器。从对抗合理性、资源合理性、战略一致性、
  │      时间线合理性四个维度审查命令列表。"
  │
  ├─ 2. 构建 subAgent 专用的 ToolRegistry（最小化工具集）
  │     包含：obs.*（当前状态）, hist.*（历史趋势）, query.tech_requirement
  │     禁止：cmd.*, build.*, timer.*, ctrl.*, spawn（防递归）
  │
  ├─ 3. 调用 AgentRunner.run(AgentRunSpec(
  │      messages=[subagent_system_prompt, user_task],
  │      tools=minimal_tools,
  │      max_iterations=10,
  │    ))
  │
  └─ 4. 返回给主 Agent：{verdict, issues: [...], suggestions: [...]}
```

subAgent 还用于差异分析：主 Agent 被唤醒后需要了解"我睡着期间发生了什么"，可以 spawn subAgent 做结构化对比——当前观测 vs 上次决策时 vs 最近 N 秒前——返回干净的 diff 而非让主 Agent 自己翻 `hist.*` 原始记录对比。

**subAgent 隔离规则**（直接对应 nanobot 的 `SubagentManager._run_subagent`）：

| 隔离项 | 规则 |
|--------|------|
| messages 数组 | 独立构建，与主 Agent 上下文完全隔离 |
| ToolRegistry | 最小化——仅包含完成该任务所需的工具 |
| 禁用工具 | `ctrl.*`, `timer.*`, `spawn`（防递归爆炸） |
| max_iterations | 审查/差异分析类 10 |
| 返回方式 | 作为工具调用的返回值，不是消息注入 |
| 容错 | 照搬 nanobot：`stop_reason` 分类（tool_error/error/max_iterations），失败时返回 `_format_partial_progress()`（已完成步骤 + 失败点）。handler 永远不抛异常 |

### 4.4 时间线规划：主 Agent 自己完成

不使用 subAgent。主 Agent 在工具调用循环中逐步构建命令时间线——观察、计算、输出 `timer.command`、验证、再观察、再计算。

`plan.*` 是纯计算的辅助工具（不调 LLM）：

```
plan.simulate         → (commands[], horizon) 确定性模拟器：纳入 active timers、当前生产队列、补给占用、
                        建筑占用和工人占用，返回每步预测资源与第一个失败点
plan.build_time       → (unit_or_building_type) 查询建造/训练耗时
plan.build_order      → (strategy_name) 从标准开局模板返回目标列表
```

主 Agent 的推理过程——所有计算在同一个工具调用循环中完成：

```
Agent: 我需要前 3 分钟完成补给站×2、兵营×1、气矿×1、枪兵×8、死神×1。

  第一步：模拟当前空时间线 → plan.simulate([], 180)
    → 每步预测资源：t=0 矿680气45, t=30 矿905气85, ...（已纳入 active timers + 生产队列）

  第二步：查建造耗时 → plan.build_time("SupplyDepot")
    → {duration: 21, cost: {minerals: 100}}
  思考: t=0 矿 680，造补给站消耗 100，21s 完工。收入 ~450/min，够。
  → timer.command(at_time=0.0, tool_name="build.structure",
                  arguments={"worker_tag": 42, "building_type": "SupplyDepot", "x": 35.2, "y": 40.1})
  矿 → 580

  第三步：继续 → plan.build_time("Barracks")
    → {duration: 46, cost: {minerals: 150}}
  查模拟结果 → t=21 时矿≈737。够。
  → timer.command(at_time=0.0, tool_name="build.structure",
                  arguments={"worker_tag": 43, "building_type": "Barracks", "x": 37.5, "y": 41.0})
  矿 → 430

  第四步：Barracks 完事才能训 Marine
    → plan.build_time("Marine") → {duration: 18, cost: {minerals: 50}}
  思考: Barracks t≈46s 完工，立刻开始训 Marine×2(t=46~82s)。
  每轮 Marine 消耗 50，t=46 时矿≈430+46×450/60≈775。够。
  → timer.command(at_time=46.0, tool_name="build.train",
                  arguments={"structure_tag": 88, "unit_type": "Marine", "count": 2})
  ...

  最后：检查总消耗 vs 预测收入 → plan.simulate 验证不存在负值 ✓
  → timer.monitor(metric="game_time", op=">=", value=180, reason="时间线到期")
  → timer.monitor(metric="minerals", op=">", value=600, before_time=200, reason="推算偏差")
  → 提交审查
```

subAgent 隔离表中的 `max_iterations: 规划类 20` 行移除——规划不使用 subAgent。

### 4.5 时间线长度的自适应

Agent 根据局势判断来决定规划多远：

| 局势 | 时间线长度 | 监测条件密度 | 理由 |
|------|:--------:|:----------:|------|
| 开局（前3分钟） | 长（120-180s） | 适中 | 局势稳定，标准开局，意外概率低 |
| 稳局（经济爬升期） | 中长（60-120s） | 适中 | 命令可预测，但敌方可能有动作 |
| 备战（爆兵/扩张） | 中（45-90s） | 较密 | 资源波动大，需要更频繁检查 |
| 交战/骚扰 | 短（15-30s） | 密集 | 微操敏感，状态变化快，沉默成本高 |
| 局势不明 | 极短（10-20s） | 密集 | 不确定敌方动向，快速迭代 |

Agent 自行判断——主 Agent 自己把握规划 horizon。局势明朗给 180s，敌方刚露头新科技给 30s。

### 4.6 审查：主 Agent 推理循环中的工具（`review.*`）

`timer.monitor` 解决的是"我的推理和现实有没有偏差"。还有一个独立的问题：**"我做出的决策本身对不对"**。

审查不是规划做完后才走的"最后一个检查站"——它是和主 Agent 推理交错往复的。主 Agent 构建命令初稿 → 调审查 → 根据反馈修改 → 再审查 → 再修改……直到主 Agent 自己判断"可以了"或被审查说服"必须改"。最终决定权在主 Agent：即使审查还有 `WARN` 级别问题，只要主 Agent 判断可接受，就可以跳过直接提交。

`review.*` 工具——`review.logic` 内部使用 subAgent（4.3 机制）：

```
review.plan(staging_hash) → 完整审查 = review.params + review.logic
review.params             → 纯代码检查，不调 LLM
review.logic              → spawn 审查 subAgent，检查战术/战略/资源合理性
```

**`staging_hash` 绑定**：Agent 调用 `review.plan` 时，当前命令列表被冻结并计算一个 hash。审查结果绑定此 hash。`ctrl.commit(staging_hash)` 只接受与审查相同的 hash——如果 Agent 在审查后又修改了命令列表，hash 不匹配，commit 被拒绝。这保证了"审查的就是提交的"。

审查 subAgent 专用工具集：`obs.*`（当前状态）, `hist.*`（历史趋势）, `query.tech_requirement`

#### 参数合理性审查（`review.params`）— 纯代码，不调 LLM

检查每一条命令的硬事实：

```
- 所有 unit_tag 是否真实存在？
- 所有坐标 (x, y) 是否在地图边界内？
- 建筑放置位置是否有效（非悬崖、非水域、不与其他建筑重叠）？
- 训练指令的生产建筑是否确实存在且已完成？
- 科技树前置是否满足？（没有 Factory 就训不了 SiegeTank）
- 资源预估是否合理？（总计划消耗 vs 预计总收入）
- 是否存在明显冗余？（同一 SCV 在同一秒被指派两个建造任务）
```

这些检查由代码在 1ms 内完成。返回 `issues` 列表，无 issues = PASS。

#### 逻辑合理性审查（`review.logic`）— 调 Sub-Agent

检查决策本身的战术和战略质量：

```
Sub-Agent 输入：
  - 当前 game_state.md（世界模型）
  - 敌方已知情报（兵种构成、科技水平、基地数量）
  - 本轮最终命令列表
  - 资源冗余说明（如果有意存钱，说明原因）

Sub-Agent 审查维度：
  1. 对抗合理性
     "敌方已有 Banshee(飞行+隐身)，但你只训了 Marine(无法对空)。
      需要补充 Viking 或 MissileTurret。"
     
  2. 资源合理性
     "矿物堆积 1200，但队列只有 3 个 Marine。
      有 2 个空闲兵营。如果不是故意存钱等科技，请增加训练量或补产能建筑。"
     如果 Agent 在命令列表中标注了原因（"存 400 矿等 Factory 落地后立刻挂 TechLab"），
     则 Sub-Agent 不应标记为问题。

  3. 战略一致性
     "game_state.md 中战略判断为'Bio-Tank 中期压制'，
      但当前命令列表中没有 SiegeTank 相关任务，也没有为 Factory 挂 TechLab。
      这与战略方向不一致。"

  4. 时间线合理性
     "第 15 条命令计划在 t=320s 建造 Starport，
      但此时总矿物预测为 200，不足以支付 Starport(150 矿)。
      建议推迟或调整前序命令。"

输出：
  verdict: PASS | WARN | REVISE
  issues:
    - code: NO_ANTI_AIR
      severity: error
      message: "敌方有飞行单位，我方无对空能力"
      suggestion: "在 build_queue 中加入 Viking×2 或 MissileTurret×1"
```

#### 与旧 Supervisor 的本质区别

| | 旧 Supervisor | 新 `review.*` |
|---|---|---|
| 触发方式 | 强制——每轮必定调起 | 自愿——Agent 主动调用 |
| 定位 | 外部审查者，输出即指令 | 主 Agent 的工具，输出是建议 |
| 角色混淆 | 是——Executor 常模仿 Supervisor 格式 | 否——审查 Sub-Agent 独立运行 |
| 采纳决策 | 强制返工 | 主 Agent 决定是否修正 |
| 失败后果 | 整个计划被丢弃（REJECT） | issues 列表供主 Agent 参考 |

审查不是规划做完后的最后一个检查站，而是主 Agent 推理循环中的一个可复用工具。主 Agent 决定什么时候调、调几次、采纳哪些意见、什么时候停止：

```
主 Agent: 命令列表初稿完成 → review.plan()
  审查返回: verdict=WARN, issues=[IDLE_BARRACKS]

主 Agent: 有道理，插入训练命令 → 修改列表 → review.plan()
  审查返回: verdict=WARN, issues=[NO_ANTI_AIR_PREP]

主 Agent: 敌方未见星港，隐飞概率低。当前优先坦克线，这个风险可以接受。
         不再修了，commit 时附带理由。
         → ctrl.commit()
```

主 Agent 拥有最终决定权——即使审查还有 `WARN` 级别问题，只要主 Agent 判断可接受，就可以跳过直接提交。与旧 Supervisor 的本质区别：不是"不 PASS 就不能提交"，而是"审查给你信息，你来判断"。

### 4.7 一轮完整决策流程

```
Agent 睡着。游戏在跑。Timer Scheduler 每帧检查 timer.command 到没到点、
timer.monitor 条件满没满足。game_time 走到 127。

timer.monitor(metric="game_time", op=">=", value=127) 触发。


═══════════════════════════════════════════
1. 醒来
═══════════════════════════════════════════

Agent 拿到上下文：

  system:  game_state.md（世界模型：Factory 即将完工，优先级 TechLab）
          工具命名空间摘要（11 行）
          skills 入口（一行摘要）

  history: 游标之后最近几轮原始 messages（Agent 能看到上轮做了什么）

  user:   "game_time=127s。唤醒原因: timer.monitor(game_time>=127, 'Factory预计完工')"


═══════════════════════════════════════════
2. 元认知自查
═══════════════════════════════════════════

Agent 先不看游戏，先看自己 → hist.events(type="wake_up", since=60)
  → 过去 60 秒醒了 1 次。正常，继续。

（如果 10 秒醒了 3 次 → 判断：游戏真的出事了就接受；monitor 条件太敏感就
 spawn 校准 subAgent 调整阈值。）


═══════════════════════════════════════════
3. 粗看 —— 建立全局认知
═══════════════════════════════════════════

Agent → obs.resources()
  → {矿680, 气54, 人口32/46, 收入450/min}
思考：矿物充裕，气刚好 54——够挂 TechLab(50 气)了。和上轮 game_state 一致。

Agent → obs.enemy_visible()
  → Marine×3, Bunker×1, 无扩张
思考：敌方防守型，短期无进攻压力。

Agent → obs.structures()
  → Factory(100%)✅, Barracks×2✅, Refinery×1✅, Starport❌
思考：Factory 已完工。上轮预测 t≈127s 完工，实际吻合。


═══════════════════════════════════════════
4. 聚焦 —— 深入关键对象
═══════════════════════════════════════════

上一步发现 Factory 是关键。聚焦它：

Agent → obs.unit("Factory")
  → {tag:42, build_progress:1.0, is_ready:true, is_idle:true, has_addon:false}
思考：空闲、无挂件。立刻挂 TechLab——耗 50 气，气刚好 54。

Agent → query.idle_producers()
  → Barracks×2 均训练中（无闲置产能）
思考：产能饱和。

Agent → query.tech_requirement("SiegeTank")
  → {requires: ["Factory+TechLab"], cost: {minerals:150, gas:125}}
思考：TechLab 挂上后就能产坦克。挂件耗时 18s → t≈145 可用。坦克耗 125 气，
     气收入 80/min → 当前 54 气，挂件耗 50 → 余 4。
     (125-4)/(80/60) ≈ 91s → 最早 t≈218 才能开始产坦克。

（如果 Agent 想了解睡着期间的变化，spawn 差异分析 subAgent 做结构化对比。）


═══════════════════════════════════════════
5. 逐步构建命令时间线（主 Agent 自己推理，不 spawn subAgent）
═══════════════════════════════════════════

第一条：挂 TechLab
  Agent → plan.build_time("TechLab")
    → {duration:18, cost:{minerals:50, gas:50}, requires:["Factory"]}
  思考：t=127 立刻挂。
  → timer.command(at_time=127.0, tool_name="build.addon",
                  arguments={"structure_tag": 42, "addon_type": "TechLab"})

第二条：气用完了，先花矿——补 Marine
  思考：Barracks×2 在 t=127~145 空闲。训一轮 Marine×2，消耗 100 矿。
  Agent → plan.simulate(horizon=60) → t=127 矿 680。够。
  → timer.command(at_time=127.0, tool_name="build.train",
                  arguments={"structure_tag": 31, "unit_type": "Marine", "count": 2})

第三条：二矿扩张
  思考：上轮 SCV 已到二矿位置，造 CommandCenter。耗 400 矿。
  Agent → plan.simulate → t=127 矿 680-50-100=530。够。
  → timer.command(at_time=127.0, tool_name="build.structure",
                  arguments={"worker_tag": 77, "building_type": "CommandCenter", "x": 52.0, "y": 48.0})
  矿 → 130

第四条：等矿恢复
  思考：矿 130。Agent → plan.simulate → t=145 矿≈265。
  气不够产坦克（要 125），但矿够继续训 Marine。
  → timer.command(at_time=145.0, tool_name="build.train",
                  arguments={"structure_tag": 31, "unit_type": "Marine", "count": 2})

... 逐步推算到 horizon=300。每步核对 plan.simulate，确保不出现负资源。


═══════════════════════════════════════════
6. 设定监测条件
═══════════════════════════════════════════

→ timer.monitor(metric="game_time", op=">=", value=300, reason="时间线到期")
→ timer.monitor(metric="minerals", op=">", value=500, before_time=180,
                 reason="推算偏差：t=180前矿不应超500")
→ timer.monitor(metric="unit_count", unit_type="Marine", op="<", value=10,
                 before_time=160, reason="推算偏差：t=160前Marine不应减少")

before_time 控制窗口——超时自动注销。


═══════════════════════════════════════════
7. 审查 —— 与推理交错往复
═══════════════════════════════════════════

Agent: 初稿完成，征求第二意见 → review.plan(command_list)

  review.params（纯代码，1ms）：
    tag 有效性 ✓  坐标合法性 ✓  科技树前置 ✓  → PASS

  review.logic（spawn 审查 subAgent，独立 LLM）：
    subAgent 加载 review-knowledge + review-dimensions skill
    返回: verdict=WARN
          issues=[{code:"NO_ANTI_AIR_PREP", severity:"warn",
                   message:"敌方暂无空军，但长时间未侦察→不排除隐飞可能性"}]

Agent: 敌方未见星港，隐飞概率低。当前优先坦克+扩张线，这个风险可接受。
       不再修了。→ ctrl.commit(附理由:"敌方未见飞行单位，优先完成坦克产能线")

最终决定权在主 Agent。WARN ≠ 必须改。


═══════════════════════════════════════════
8. 提交 → 同步收尾（代码自动）
═══════════════════════════════════════════

Agent → ctrl.commit(staging_hash)
  → 校验 staging_hash 与最近一次 review.plan 结果一致
  → 按提交顺序完成持久化、记忆更新、同步整合
  → 最后注册全部 timer.command + timer.monitor
  → Agent 休眠，游戏恢复运行

ctrl.commit() 返回后，代码自动执行：

  1. RoundRecorder 写入快照 + 事件（先持久化，可恢复）
  2. Session 追加本轮全部 messages → JSONL 文件
  3. 代码更新 game_state.json：
     "已知事实"：矿 680→130, Factory→TechLab 挂载中, 二矿 CommandCenter 建造开始
     "关键事件"：追加 [127s] Factory 完工, [127s] TechLab 建造开始
  4. MemoryConsolidator 同步评估 token 预算：
     游标后消息 9200 token < 12000 预算 → 不触发整合 LLM
     "战略判断"和"当前优先级"保持旧值（Agent 下次醒来会看到旧时间戳）
  5. 从 game_state.json 重新生成 game_state.md（派生视图）
  6. Timer Scheduler 注册全部 timer.command + timer.monitor


═══════════════════════════════════════════
9. Agent 休眠，游戏继续
═══════════════════════════════════════════

Timer Scheduler 每帧:
  ├─ timer.command(at_time=127.0, tool_name="build.addon", arguments={...}) → 执行
  ├─ timer.command(at_time=127.0, tool_name="build.train", arguments={...}) → 执行
  ├─ timer.command(at_time=127.0, tool_name="build.structure", arguments={...}) → 执行
  └─ 评估 timer.monitor:
      minerals=130 < 500 ✗   Marine=12 ≥ 10 ✓   game_time=127 < 300 ✗
      → 无触发，继续休眠

  ... t=138: minerals 突然飙到 550！
  → timer.monitor(metric="minerals", op=">", value=500, before_time=180) 触发！
  → Agent 被唤醒，附带 reason: "推算偏差：t=180前矿不应超500"
  → Agent 醒来后调 obs.structures → CommandCenter 建造取消了？（SCV 被杀了？）
  → 这就是"我的推理和现实出现了偏差"
  → 重新规划，回到第 1 步
```

---

## 5. 记忆系统

记忆系统做一件事：**把 Agent 经历过的所有事情压缩成 Agent 下次醒来能快速理解的上下文。**

### 5.1 三步机制

#### 第一步：记账（Session，JSONL 文件）

Agent 每次被唤醒后的整个工具调用过程——调了 `obs.resources`、调了 `plan.simulate`、调了 `ctrl.commit`——全部 messages 追加写入 JSONL 文件，一条不删。这是纯粹的**记账**，保证 `hist.*` 工具可以回溯"我刚才做了什么"。

#### 第二步：摘事实（代码，每周期必执行）

Agent 这轮调了 `obs.resources`，返回值是 `{"minerals": 680, "gas": 24}`——结构化 JSON。代码直接从工具返回值中提取变化，更新 `game_state.md` 里的两段纯数据：

- **已知事实**：覆盖旧数字（矿 820→680，Factory 15%→85%）
- **关键事件**：追加新事件（"[220s] Factory 建造开始"）

这一步不调 LLM。就是字符串替换和追加——确定性操作，1ms 完成。

#### 第三步：做判断（整合 LLM，token 超预算时触发）

当 Agent 积累了太多轮原始 messages，上下文快爆了（token 超预算），就把这些旧 messages 所代表的"事实变化"发给一个便宜 LLM（qwen-turbo），让它更新 `game_state.md` 里的两段定性文字：

- **战略判断**："敌方 VeryEasy，单矿超过5分钟，防守型。我方 1-1-1 推进顺利 → 可以加速 Bio-Tank 成型"
- **当前优先级**："1. Factory 即将完工 → 准备挂 TechLab；2. 气已攒到80 → 资源就绪；3. 敌方无压力"

LLM 更新完毕后，游标前移——这些旧 messages 不再出现在 Agent 的上下文中，但它们的"意义"被保留在 `game_state.md` 里。旧 messages 本身仍在 JSONL 文件中，`hist.*` 工具仍可查询。

### 5.2 每次 Agent 醒来的上下文

```
system prompt {
    game_state.md          ← 旧消息的提炼（战略 + 优先级 + 最新事实 + 事件）
    工具命名空间摘要
}
+ 最近几轮原始 messages（游标之后的未整合部分）
+ 本轮 user message（"game_time=220s，唤醒原因: timer.monitor('game_time>=220')"）
```

这就是全部。没有数据库，没有查询引擎——两个 JSONL 文件（session + events）+ 一对 game_state 文件。

**`game_state.json` 是权威源**（结构化，代码可靠读写），**`game_state.md` 是派生视图**（Markdown，注入 system prompt 供 LLM 阅读）。代码只写 `.json`，构建 system prompt 时从 `.json` 生成 `.md`。两者始终一致，`.json` 是真相源。

### 5.3 game_state.md 格式

每个部分都标注**最后一次更新的游戏时间**，避免 Agent 被过时信息误导：

```markdown
# 当前局势 (wake #6, 220s)

## 战略判断 (updated at 220s)                     ← 整合 LLM 维护
- 敌方: VeryEasy Terran, 单矿, 未见扩张, 未见AOE
- 我方: 1-1-1开局 → Bio-Tank压制, 已连续确认3个周期

## 当前优先级 (updated at 220s)                   ← 整合 LLM 维护
1. Factory 建造进度确认（SCV是否到达？）
2. 气体不足(12), 等 Refinery 积累到50气后立刻挂 TechLab
3. 暂无战斗压力, 继续经济扩张

## 已知事实 (updated at 220s)                     ← 代码维护
- 基地: 主矿(1)✅, 二矿(SCV赶路中)
- 建筑: Barracks×2✅, Refinery×1✅, Factory(15%), Starport❌
- 兵力: Marine×10, Reaper×2, SCV×18
- 资源: 矿680 气24, 趋势: 矿↑(+200/周期), 气缓慢积累
- 产能: Barracks×2均生产中

## 关键事件 (updated at 220s)                     ← 代码维护
- [47s] 1-1-1开局
- [157s] Refinery建成
- [180s] 二矿扩张开始
```

四段内容，两种更新方式：

| 部分 | 维护者 | 更新方式 | 触发时机 |
|------|--------|----------|----------|
| 已知事实 + 更新时间 | 代码 | 从本轮 `obs.*` 返回值提取结构化数据，覆盖旧值 | 每周期结束后必定执行 |
| 关键事件 + 更新时间 | 代码 | 从事件日志取新增条目，追加到末尾 | 每周期结束后必定执行 |
| 战略判断 + 更新时间 | 整合 LLM | 读旧判断 + 代码生成的事实差异摘要，决定是否修改 | token 超预算时触发 |
| 当前优先级 + 更新时间 | 整合 LLM | 同上，根据最新事实调整排序 | token 超预算时触发 |

Agent 读到 `(updated at 220s)` 就知道这条信息的时效性——如果当前是 500s 而某条更新于 50s，Agent 就知道它已经过时 450 秒了。

### 5.4 更新流程示例

**初始**（游戏开始 wake #0）——代码从策略池模板 + 初始观测填充：

```markdown
# 当前局势 (wake #0, 0s)

## 战略判断 (updated at 0s)
- 敌方: 未知
- 我方: 1-1-1万能开局（标准人族开局，兼顾经济与科技）

## 当前优先级 (updated at 0s)
1. 按标准开局流程推进
2. 死神侦察获取敌方情报

## 已知事实 (updated at 0s)
- 地图: {map_name}
- 基地: 主矿(1)✅, 总计{total_bases}个矿点
- 建筑: CommandCenter×1✅
- 兵力: SCV×12
- 资源: 矿50 气0

## 关键事件 (updated at 0s)
- [0s] 游戏开始，选定 1-1-1 开局
```

**wake #6 结束后**（代码更新已执行，token 超预算触发整合 LLM）：

```
1. 代码：更新"已知事实"
   对比 game_state.md 旧值 + 本轮 obs.* 返回值：
     - 矿: 820→680, 气: 12→24, Factory: 15%→85%
   → 覆盖"已知事实"，时间戳更新为 (updated at 220s)

2. 代码：追加"关键事件"
   本轮事件: [200s] Factory 建造开始, [200s] Marine×2 完成
   → 追加到列表中，时间戳更新为 (updated at 220s)

3. 代码：评估 token 预算
   get_history() token = 13500 > 12000（预算）
   → 触发整合 LLM

4. 整合 LLM（qwen-turbo, ~500 token prompt）：
   输入：旧战略判断 + 旧优先级 + 代码生成的事实差异摘要
     "资源: 矿趋稳(600-800), 气持续积累(12→24→48→80)
      Factory 15%→45%→85%, 即将完工
      Marine 8→10→14(+6), 新增 Reaper×2
      二矿 SCV 赶路中→已到达→CommandCenter(25%)
      敌方持续未见扩张, Marine×3 未变化"
   
   调用 save_game_state → 输出：
     "战略判断 (updated at 220s):
        敌方: VeryEasy Terran, 单矿超过5分钟未扩张, 防守型
        我方: 1-1-1 推进顺利 → 加速 Bio-Tank 成型
      当前优先级 (updated at 220s):
        1. Factory 即将完工(85%) → 准备挂 TechLab
        2. 气已达80 → 资源就绪
        3. 二矿建造中 → 预计30s后可转移工人
        4. 敌方无压力 → 暂不需防守"

5. game_state.json 四段全部更新完毕，并重新生成 game_state.md → last_consolidated 游标前进
```

如果 token 预算未超（步骤3），则跳过步骤4——"已知事实"和"关键事件"被代码更新，"战略判断"和"当前优先级"保持旧值（但 Agent 可以通过时间戳知道它们可能过时）。

### 5.5 botAI 快照（三层周期） + 事件日志

botAI 全量快照，三种采集周期、不同保留策略：

| 层级 | 采集频率 | 保留策略 | 20分钟游戏 | 用途 |
|------|----------|----------|:---------:|------|
| 分钟级 | 每 60s 游戏时间 | 无上限 | ~20 份 | 长期趋势：`hist.trend`、`hist.compare` |
| 决策级 | 每次 `ctrl.commit()` | 最近 5 份 | 5 份 | 跨周期对比：`hist.snapshot`、差异分析 subAgent |
| 秒级 | 每 5s 游戏时间 | 最近 5 份（滑动窗口） | 5 份 | 近期细节：`hist.unit` 查单位轨迹 |

每份快照 ~15KB（全量 botAI 状态）。30 份 × 15KB = **~450KB**，无内存压力。

采集逻辑（在游戏帧循环中，纯代码，不调 LLM）：

```python
def on_step(bot, game_time):
    if game_time % 60 < last_dt:      # 跨分钟边界
        SnapshotRecorder.save("minute", bot)
    if game_time % 5 < last_dt:       # 跨5s边界
        SnapshotRecorder.save("5sec", bot, max_keep=5)
    # 决策级在 ctrl.commit() 后触发，不在帧循环中

def after_commit(bot):
    SnapshotRecorder.save("decision", bot, max_keep=5)
```

事件日志保持不变：

| 存储层 | 格式 | 写入者 | 单条大小 | 查询工具 |
|--------|------|--------|----------|----------|
| 事件日志 | JSONL | 各处回调触发 | ~100B | `hist.events` |

---

## 6. 记忆整合层 (MemoryConsolidator)

直接对应 nanobot 的 `MemoryConsolidator` + `Session.last_consolidated` 游标机制。

### 6.1 核心机制

```
Session.messages（JSONL 文件，追加写入，永不删除）
     │
     ├── last_consolidated 游标之前 ── 已整合进 game_state.json
     │    这些消息不再进入 get_history()，但保留在文件中供 hist.* 查询
     │
     └── last_consolidated 游标之后 ── 未整合的最近消息
          这些消息直接出现在 Agent 的下一次上下文中
```

### 6.2 职责

MemoryConsolidator 本身是一个**编排器**，协调代码和 LLM 两种更新方式：

- **代码更新（每周期必执行）**：
  - 从本轮 `obs.*` 工具返回值中提取事实变化 → 更新"已知事实"
  - 从事件日志取新增条目 → 追加到"关键事件"
  - 不需要 LLM，确定性操作，1ms 完成
- **LLM 更新（token 预算触发）**：
  - 输入：旧 game_state.json（战略判断 + 当前优先级部分）+ 代码生成的"事实差异摘要"
  - 调用整合 LLM（qwen-turbo）→ 更新 game_state.json 的"战略判断"和"当前优先级"
  - 代码从更新后的 .json 重新生成 .md（派生视图）
  - ~500 token prompt，1-2s 延迟
- **维护游标**：`last_consolidated` 记录已整合进 game_state.json 的消息位置
- **不修改原始 messages**：JSONL 文件追加写入，永不修改

### 6.3 工作流

```
ctrl.commit() 执行完毕 → Timer Scheduler 写入命令和监测条件
  → RoundRecorder 写入快照 + 事件
  → Session 追加本轮全部 messages（追加写入 JSONL）
  
  → [代码] 从 obs.* 返回值提取事实变化 → 覆盖 game_state.json "已知事实"
  → [代码] 从事件日志追加新事件 → game_state.json "关键事件"
  → [代码] 从 game_state.json 重新生成 game_state.md（派生视图）
  
  → MemoryConsolidator.maybe_consolidate():
      if estimate_tokens(get_history()) > budget:
          取游标之后最早的一批消息（到周期边界为止）
          → 代码生成事实差异摘要（从已更新的 game_state.md 中提取）
          → 整合 LLM（qwen-turbo）调用 save_game_state 工具
              输入: 旧战略判断 + 旧优先级 + 事实差异摘要
              输出: 新战略判断 + 新优先级
          → 更新 game_state.json 的战略判断和优先级部分
          → 从 .json 重新生成 game_state.md（派生视图）
          → last_consolidated 游标前进
```

### 6.4 与 nanobot 的差异

| | nanobot | SC2 |
|---|---|---|
| 消息持久化 | JSONL 文件，追加写入 | 相同 |
| 游标 | `Session.last_consolidated` | 相同 |
| 摘要存于 | MEMORY.md | game_state.md |
| 整合触发 | token 超预算时 | 相同 |
| 整合粒度 | 取到 user-turn 边界 | 取到 wake-up 周期边界 |
| 整合方式 | 调整合 LLM → save_memory 工具 | 调整合 LLM → save_game_state 工具 |
| 整合运行 | 后台异步（nanobot 无 stop-the-world） | 同步（commit 内执行，sleep 前完成） |

---

## 7. 与旧架构的彻底决裂

| | 旧架构 | 新架构 |
|---|---|---|
| 组织方式 | 3层流水线 + Supervisor | 1个Agent + 11个命名空间 + 记忆 + Sub-Agent |
| 策略来源 | 每轮从策略池选择 | game_state.md 持续演化 |
| 决策频率 | 固定8-60s间隔 | Agent 自设 timer.monitor（含定时+偏差检测） |
| 执行方式 | 一次性YAML输出 → 替换队列 | 带精确时间戳的命令时间线 (timer.command) |
| 规划长度 | 固定：一轮一个queue | 自适应：稳局3min / 乱局30s |
| 观测 | 4000+ token 全量注入 | Agent 按需调 obs.*/query.* |
| 偏差检测 | 无——等下一轮才知道结果 | timer.monitor：对自身推理准确性的运行时兜底 |
| 决策审查 | Supervisor 强制审查，角色混淆 | review.* Sub-Agent，主 Agent 主动调用的工具 |
| 指令粒度 | 高级wrapper (queue_building) | 原子命令 (cmd.move / build.structure / train) |
| 层级 | 显式、强制、不可跳过 | 无显式层级——策略从记忆涌现，时间线由数学推理驱动，审查是可选工具 |

---

## 8. 实施路径（更新）

### Phase 1: 工具基础设施 + AgentRunner
- 创建 `agent/tools/` 目录，参考 nanobot 的 `Tool` 基类
- 创建 `agent/tools/registry.py` — 工具注册表
- 改造 `AgentRunner`（基于现有的 `generate_with_tools()`，抽取为独立循环）

### Phase 2: 核心工具实现
- `obs.*` + `query.*` — 观测和查询（25个工具，最高优先级）
- `cmd.*` + `build.*` — 指令和建造（26个工具）
- `timer.*` — 定时器引擎（4个工具，核心基础设施）
- `econ.*` + `squad.*` — 经济和编队（13个工具）
- `hist.*` + `ctrl.*` — 历史和流程控制（9个工具）

### Phase 3: Timer Scheduler 引擎
- 游戏帧循环中的定时器评估逻辑
- `timer.monitor` 条件表达式解析和执行
- `timer.command` 的按时分发
- 唤醒时附带原因的上下文注入

### Phase 4: 记忆系统
- `MemoryStore` — game_state.json 读写 + game_state.md 派生视图生成
- `RoundRecorder` — 快照 + 事件日志采集
- `MemoryConsolidator` — stop-the-world 下同步整合 LLM

### Phase 5: plan.* 辅助工具
- `plan.simulate` — 纯计算资源曲线预测
- `plan.build_time` — 建造/训练耗时查询
- `plan.build_order` — 标准开局模板数据

### Phase 6: 集成
- 重建 system prompt（注入 game_state.md + 命名空间摘要）
- 简化 user message（唤醒原因 + 上下文）
- 移除旧的 TriggerScheduler（被 timer.* 取代）

### Phase 7: 清理
- 删除 StrategyLayer / PhaseLayer / ExecutionLayer
- 删除 Supervisor 相关所有文件
- 删除旧 prompt 文件
- 删除旧 TriggerScheduler
- 保留 LLMClient / ProductionManager / SquadManager 等基础设施
- 保留 observation 模块（obs.* 工具的数据来源）

### Phase 8: 扩展（后续）
- `exec.*` 沙盒执行器（依实战反馈决定）

---

## 9. 技术栈

### 9.1 参考 nanobot 的技术选型

nanobot 的核心依赖及 SC2 项目的适用性：

#### 建议引入（替换现有自研组件）

| 技术 | 用途 | 替换你的 |
|------|------|----------|
| `openai` (>=2.8) | LLM SDK，原生 function calling 支持 | `UnifiedLLMClient._OpenAICompatibleSingleClient` 手写 HTTP |
| `pydantic` + `pydantic-settings` | 类型化配置、schema 校验、环境变量加载 | `llm_clients.json` 手动解析 |
| `loguru` | 结构化日志 | 现有 `print()` + `DecisionLogger` 混合使用 |
| `tiktoken` | 精确 token 计数 | 现有的粗略估算 |

**为什么换 `UnifiedLLMClient`**：你当前的 LLM 客户端是手写的 HTTP + 重试 + 多供应商路由层，约 1200 行。引入 `openai` SDK 后，function calling 的 message 格式处理（tool_calls、tool role 等）由 SDK 处理，不再需要手动维护 `_normalize_message_for_tool_loop` 这种脆弱的格式转换。nanobot 的 `openai_compat_provider.py`（~200 行）是直接参考——它包装 `AsyncOpenAI`，只做 chat + stream + retry，不做路由。

**供应商路由怎么办**：你现有的多供应商路由逻辑可以保留为一个薄层——创建多个 `AsyncOpenAI` 实例（不同 base_url/api_key），失败时切换到下一个。路由逻辑 ~100 行，远小于当前的 1200 行。

#### 建议引入（新增能力）

| 技术 | 用途 |
|------|------|
| `json-repair` | LLM 输出的 YAML/JSON 格式修复——你日志中的 parse_exhausted 问题可直接减少 |
| `msgpack` | 轮次快照 + 事件日志的高效序列化（比 JSON 小 40-60%） |

#### 不需要引入（仅 nanobot 需要）

| 技术 | 原因 |
|------|------|
| `anthropic` SDK | 你的供应商池里没有 Anthropic 原生 API（只有 OpenAI-compatible 的 DeepSeek/Qwen/MiniMax） |
| `typer` / `rich` / `prompt-toolkit` / `questionary` | CLI/TUI——SC2 无交互终端 |
| `python-telegram-bot` / `slack-sdk` 等 6 个通道 SDK | 聊天网关——SC2 不需要 |
| `websockets` / `python-socketio` | WebSocket 自定义通道——SC2 不需要 |
| `ddgs` / `readability-lxml` | Web 搜索/正文提取——SC2 不需要 |
| `croniter` | cron 解析——你的 `timer.*` 使用游戏内时间，非系统时间 |
| `mcp` | Model Context Protocol——可后续考虑（用于工具热加载），初期不需要 |
| `httpx` | nanobot 用于异步 HTTP（非 OpenAI SDK 路径），引入 `openai` SDK 后不需要单独依赖 |

### 9.2 保留的现有基础设施

| 模块 | 理由 |
|------|------|
| `LLMClient.py` 的路由/重试逻辑 | 多供应商切换是核心需求，提取为 ~100 行的薄路由层 |
| `CommandParser.py` | 不再用于解析 `timer.command` 字符串；如保留，仅作为旧日志/旧配置迁移工具 |
| `ProductionManager` / `SquadManager` / `TacticManager` | 游戏引擎接口——不可替代 |
| `observation/` 模块 | `obs.*` 工具的数据采集来源 |
| `DecisionLogger.py` | JSONL 日志系统——已工作良好 |
| `strategy_pool.py` | 开局模板数据——`plan.build_order` 和 `game_state.json` 初始化的参考数据 |

### 9.3 依赖清单（新项目）

```
# 核心（必须）
openai>=2.8              # LLM SDK
pydantic>=2.12           # 配置 schema
pydantic-settings>=2.12  # 环境变量加载
loguru>=0.7              # 日志
tiktoken>=0.12           # Token 计数

# 博弈层（新增能力）
json-repair>=0.57        # LLM 输出修复
msgpack>=1.1             # 高效序列化（快照/事件日志）

# 游戏层（已有，不变）
burnysc2                 # SC2 Python API
```

总计引入 6 个新依赖（3 个替换、3 个新增），均为纯 Python，无系统依赖。
