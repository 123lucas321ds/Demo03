# 代码审查记录 · 第3轮：记忆系统 + Timer引擎 + Bot集成

> 审查时间：2026-05-29
> 对照文档：`doc/需求文档.md`、`doc/memory-centric-agent-redesign.md`、`docs/superpowers/plans/2026-05-29-phase-a-core-integration.md`

## 审查范围

| 类别 | 文件 |
|------|------|
| 记忆模型 | `memory/models.py`、`memory/renderer.py` |
| 记忆存储 | `memory/store.py` |
| 记忆整合 | `memory/consolidator.py` |
| Timer 模型 | `timer/models.py` |
| Timer 暂存 | `timer/staging.py` |
| Timer 存储 | `timer/store.py` |
| Timer 调度 | `timer/scheduler.py` |
| Bot 集成 | `bot.py` |
| 入口 | `main.py` |

---

## 1. 记忆模型（`memory/models.py`）

### 与文档对照（FR-11）

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| 四段结构：战略判断、当前优先级、已知事实、关键事件 | ✅ | `GameState` 四个 `GameStateSection` 字段 |
| 每段标注游戏时间 (`updated_at`) | ✅ | `GameStateSection.updated_at: float` |
| `game_state.json` 是权威源 | ✅ | `to_dict()` / `from_dict()` 序列化 |
| 已知事实由代码覆盖（非追加） | ✅ | `with_known_facts()` 完全替换 |
| 关键事件由代码追加 | ✅ | `with_key_events()` 追加到现有列表 |
| 战略判断/优先级由整合 LLM 更新 | ✅ | `with_strategy_and_priorities()` 完全替换 |

### 差异/问题

- **无差异。** 数据模型与文档描述的四段式 `game_state.json` 结构完全一致。
- `initial()` 方法提供了正确的起始模板，包含默认的战略判断和优先级。

---

## 2. 记忆存储（`memory/store.py`）

### 与文档对照（FR-11）

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| `game_state.json` 由代码和 MemoryConsolidator 写入 | ✅ | `save_json()` 方法 |
| `game_state.md` 是派生视图 | ✅ | `render_markdown()` 从 `.json` 生成 `.md` |
| 原子写入避免损坏 | ✅ | 写入 `.tmp` 文件后 rename |
| 初始化时检查文件是否存在 | ✅ | `initialize()` 幂等 |

### 差异/问题

- **无严重差异。** 设计合理，原子写入策略保证了 `game_state.json` 的可靠性。
- ⚠️ `update_known_facts()` 和 `append_key_events()` 直接覆盖/追加后保存——这意味着如果调用顺序错误可能导致数据丢失。当前 commit 回调中的调用顺序正确。

---

## 3. 记忆渲染器（`memory/renderer.py`）

### 与文档对照（FR-11, 设计文档 5.3）

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| 四段 Markdown 标题 + 时间戳 | ✅ | `## 战略判断 (updated at 220s)` 格式 |
| 优先级用有序列表 | ✅ | `ordered=True` → `1. 2. 3.` |
| 战略判断/关键事件用无序列表 | ✅ | `ordered=False` → `- item` |
| 空内容显示占位符 | ✅ | `- 暂无` |
| 标题含 wake_id 和游戏时间 | ✅ | `# 当前局势 (wake #6, 220s)` |

### 差异/问题

- **无差异。** 渲染格式与设计文档 5.3 节的示例完全一致。

---

## 4. 记忆整合器（`memory/consolidator.py`）

### 与文档对照（FR-13, 设计文档 6.2）

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| commit 后同步执行（stop-the-world） | ✅ | 在 `CommitServices` 回调中同步调用 |
| token 超预算时触发整合 LLM | ✅ | `trigger_tokens` 阈值判断 |
| 只更新战略判断和当前优先级 | ✅ | 输出类型为 `ConsolidationUpdate`（两个字段） |
| 推进 `last_consolidated` | ✅ | `session.last_consolidated = len(session.messages)` |
| 整合失败不抛异常，返回 degraded 状态 | ✅ | `try/except` → `Result.success(status="failed", degraded=True)` |
| 使用便宜 LLM（设计文档 6.3） | ⚠️ 有差异 | 见下文 |
| 使用 tiktoken 精确计数（技术栈 9.1） | ⚠️ 有差异 | 见下文 |

### 差异/问题

- **⚠️ 整合 LLM 选择**：设计文档明确说使用便宜 LLM（qwen-turbo）。实际 `bot.py` 中 `_LLMConsolidationProvider` 使用的是同一个 `SC2LLMAdapter`（主 LLM）。代码中注释为 `_LLMConsolidationProvider` 但实际上是 "用主 LLM 做整合"。成本会比文档预期高，**但不阻塞功能**。

- **⚠️ Token 估算粗糙**：`_estimate_tokens()` 使用 `len(text) // 4` 估算，非常粗略（英文每个 token ~4 字符，中文 ~1.5 字符）。文档技术栈建议使用 `tiktoken` 做精确计数。**建议后续替换**。

- **⚠️ 整合 Prompt 过于简单**：`_LLMConsolidationProvider._build_prompt()` 只是将 messages 数量和当前 state 打包成 JSON，没有提供文档 6.3 描述的"事实差异摘要"。这可能导致整合 LLM 缺乏足够的上下文来做高质量战略判断。

---

## 5. Timer 数据模型（`timer/models.py`）

### 与文档对照（FR-06）

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| `TimerCommand`: id, at_time, tool_name, arguments | ✅ | 精确匹配文档定义 |
| `TimerMonitor`: metric, op, value, reason, before_time, unit_type, building_type | ✅ | 精确匹配 |
| monitor metric 固定枚举 | ✅ | `MonitorMetric` Literal 类型 |
| monitor op 固定枚举 | ✅ | `MonitorOp` Literal 类型 |
| 执行记录 `TimerRunRecord` | ✅ | timer_id, game_time, status, error |

### 差异/问题

- **⚠️ MonitorMetric 枚举与 scheduler 实现不一致**：`timer/models.py` 的 `MonitorMetric` 类型包含了 9 个值（含 `unit_distance` 和 `unit_in_region`），但：
  1. `tools/timer.py` 的 `TimerMonitorTool` JSON Schema 只列出了 7 个（缺这两个）
  2. `timer/scheduler.py` 的 `_monitor_value()` 只实现了 7 个（这两个返回 None）
  - 说明类型定义比实现更完整，两个缺失的 metric 在这三层需保持一致。

---

## 6. Timer 暂存区（`timer/staging.py`）

### 与文档对照（FR-08）

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| 暂存本轮 commands + monitors | ✅ | `commands: list[TimerCommand]`、`monitors: list[TimerMonitor]` |
| 计算 staging_hash (SHA256) | ✅ | `hash()` 方法基于 JSON 排序的 SHA256 |
| review_hash 绑定审查 | ✅ | `mark_reviewed()` / `review_hash` 字段 |
| clear() 清空暂存 | ✅ | 三个字段全部重置 |

### 差异/问题

- **无差异。** staging_hash 机制与 FR-08 设计完全一致。

---

## 7. Timer 持久化存储（`timer/store.py`）

### 差异/问题

- **无差异。** 纯内存存储（`dataclass`），提供 register / cancel / update_status / deactivate_monitor / append_run 操作。
- 当前没有磁盘持久化——文档没说 timer store 必须持久化，因为 timer 在 commit 时注册、在当前 session 内执行。符合 Phase A 范围。

---

## 8. Timer 调度器（`timer/scheduler.py`）

### 与文档对照（FR-06）

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| 每帧执行到期 `timer.command` | ✅ | `for command in sorted(...)` 按 at_time 执行 |
| 每帧评估活跃 `timer.monitor` | ✅ | `for monitor in list(...)` 评估条件 |
| `before_time` 超时自动注销 | ✅ | `game_time > monitor.before_time` → deactivate |
| monitor 触发后立即暂停游戏 + 唤醒 Agent | ✅ | `self.runtime.wake_to_thinking()` + `break()` |
| 仅在 RUNNING_SLEEP 状态执行 | ✅ | `tick()` 开头状态检查 |
| 执行记录写入 run_history | ✅ | `TimerRunRecord` 追加 |
| 命令执行失败标记 status="failed" | ✅ | `update_command_status(command.id, "failed")` |

### 差异/问题

- **⚠️ `unit_distance` 和 `unit_in_region` 未实现**：`_monitor_value()` 中这两个 metric 返回 `None`（条件不触发）。与第5节的枚举问题同源。
- **⚠️ monitor 触发后 break**：`_monitor_matches()` 触发后 `break` 意味着同一帧多个 monitor 条件下只有一个会触发。文档未明确要求多 trigger 同时处理，但按 stop-the-world 模型，一个 trigger 就会暂停游戏并唤醒 Agent，break 是合理的——Agent 醒来后会看到所有变化。

---

## 9. Bot 集成（`bot.py`）

### 与文档对照

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| 继承 `BotAI`（burnysc2） | ✅ | `class SC2AgentBot(BotAI)` |
| `__init__` 中初始化所有组件 | ✅ | 15 步初始化流程 |
| `on_step` 分三路：首次 / PAUSED_THINKING / RUNNING_SLEEP | ✅ | 清晰的路由逻辑 |
| 首次调用初始化 game_state → wake_to_thinking → agent loop | ✅ | `_game_initialized` 标志 |
| PAUSED_THINKING：运行 Agent 循环 | ✅ | `_run_agent_loop()` |
| RUNNING_SLEEP：tick Timer Scheduler | ✅ | `_tick_scheduler()` |
| `find_by_tag()` 实现 BotAI Protocol | ✅ | 遍历 7 个集合查找 tag |
| System Prompt 四段式（FR-02） | ✅ | game_state_md + tool_summary + skill_summary |
| 注册全部 80 个工具 | ✅ | `_register_all_tools()` |
| commit 步骤顺序正确（设计文档 4.0） | ✅ | 快照→Session→game_state→consolidate→render |
| 三层快照采集（FR-12） | ✅ | 决策级(commit时)+分钟级(每60s)+秒级(每5s) |
| LLM 配置缺失时优雅降级 | ✅ | `_UnavailableLLM` fallback |
| Session 管理（FR-10） | ✅ | `_append_session()` 回调 |

### 差异/问题

- **⚠️ LLM 配置文件路径**：Phase A 计划 `bot.py` 设计从 `E:/Code/python/scientific research/SC2/agent/llm_clients.json` 读取。实际实现改为 `sc2_agent/config/llm_clients.json`（相对于项目路径）。这是**更好的设计**——不依赖外部项目。

- **⚠️ Session 写入歧义**：`_run_agent_loop()` 和 `_append_session()` 都调用了 `self._session_manager.save(self._session)`。`_run_agent_loop()` 在 agent 运行完后追加 messages + 保存；`_append_session()` 在 commit 步骤中再次保存。两次保存之间的逻辑依赖 `_committed_run_message_count` 做去重。**逻辑正确但脆弱**，依赖 `_committed_run_message_count` 的精确管理。

- **⚠️ Squad 状态不持久化**：squad 状态（`dict[str, list[int]]`）只在内存中，Bot 重启或测试上下文重建后丢失。文档未要求持久化 squad 状态，但实际对局中 Agent 可能依赖它。

- **⚠️ ConsolidationProvider 用的是主 LLM 而非便宜 LLM**：`bot.py:282` 使用 `_LLMConsolidationProvider(self._llm_adapter)`，即主 LLM。

---

## 10. Main 入口（`main.py`）

### 与文档对照

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| SC2 游戏入口 | ✅ | 使用 `sc2.main.run_game` |
| Terran Bot + Computer 对手 | ✅ | `Bot(Race.Terran, SC2AgentBot())` + `Computer(Race.Random, Difficulty.VeryEasy)` |
| `realtime=False`（stop-the-world） | ✅ | 步进模式 |
| 异常处理不崩溃 | ✅ | `try/except` → return 1 |

### 差异/问题

- **⚠️ 地图不同**：Phase A 计划指定 `AbyssalReefLE`，实际使用 `Simple64`。这不影响功能，Simple64 更适合测试。

---

## 第3轮审查总结

### 一致性评估

| 模块 | 状态 | 关键发现 |
|------|:--:|------|
| 记忆模型 (models.py) | ✅ | 四段式结构完美匹配文档 |
| 记忆存储 (store.py) | ✅ | 原子写入 + .json→.md 派生 |
| 记忆渲染器 (renderer.py) | ✅ | Markdown 格式精确匹配 5.3 节 |
| 记忆整合器 (consolidator.py) | ⚠️ | 用主LLM而非便宜LLM；token估算粗糙 |
| Timer 模型 (models.py) | ⚠️ | 类型枚举比实现多2个metric |
| Timer 暂存 (staging.py) | ✅ | staging_hash 绑定机制正确 |
| Timer 存储 (store.py) | ✅ | 功能完整 |
| Timer 调度器 (scheduler.py) | ⚠️ | unit_distance/unit_in_region 未实现 |
| Bot 集成 (bot.py) | ✅ | 15步初始化 + 正确路由 + 三层快照 |
| Main 入口 (main.py) | ✅ | 基本正确 |

### 关键发现汇总

1. **⛔ 中等：`unit_distance` / `unit_in_region` monitor metric 三处不一致**：models.py 的类型定义有，但 tools/timer.py 的 Schema 没有，scheduler 的实现也返回 None。

2. **⚠️ 中等：整合 LLM 使用了主 LLM**：不符合文档"便宜 LLM (qwen-turbo)"的设计意图，成本可能偏高。

3. **⚠️ 轻微：Token 估算简陋**：`len(text) // 4` 没有用 tiktoken，对中文场景偏差大。

4. **✅ Bot 集成本身架构优秀**：15步清晰的初始化、正确的状态机路由、三层快照采集、LLM 缺失优雅降级、工具注册完整——整体质量很高。

### 三轮审查总体评估

| 轮次 | 模块数 | 完全匹配 | 有轻微差异 | 有明显缺失 |
|------|:-----:|:------:|:--------:|:--------:|
| 第1轮：核心基础设施 | 9 | 8 | 1 | 0 |
| 第2轮：工具实现 | 12 | 9 | 2 | 1 (3个缺失工具) |
| 第3轮：记忆+Timer+Bot | 10 | 7 | 3 | 0 |
| **合计** | **31** | **24** | **6** | **1** |

### 优先修复建议

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0 | `econ.set_mining` 工具缺失 | 无法调整气矿工人数 |
| P0 | `squad.list` 工具缺失 | Agent 无法查询自己创建的小队 |
| P1 | `unit_distance` / `unit_in_region` metric 未实现 | 限制条件唤醒灵活性 |
| P1 | `obs.resources` 缺少 income 字段 | 影响经济规划精度 |
| P1 | `review.params` 不验证 tag 实际存在 | 假阳性审查结果 |
| P2 | Session 覆写而非追加写入 | 崩溃可能损坏文件 |
| P2 | 整合 LLM 用主 LLM 而非便宜 LLM | 成本偏高 |
| P2 | Token 估算粗糙 | 整合触发时机不准 |
| P3 | `squad.set_count` / `squad.auto_balance` 缺失 | 编队批量操作不便 |
