# 代码审查记录 · 第1轮：核心基础设施

> 审查时间：2026-05-29
> 对照文档：`doc/需求文档.md`、`doc/memory-centric-agent-redesign.md`、`docs/superpowers/plans/2026-05-29-phase-a-core-integration.md`

## 审查范围

| 文件 | 模块 |
|------|------|
| `sc2_agent/config/settings.py` | Settings 配置 |
| `sc2_agent/config/__init__.py` | 配置入口 |
| `sc2_agent/runtime/state.py` | Stop-the-world 状态机 |
| `sc2_agent/runtime/commit.py` | Commit 控制器 |
| `sc2_agent/models.py` | 通用数据模型 |
| `sc2_agent/exceptions.py` | 项目异常 |
| `sc2_agent/agent/runner.py` | AgentRunner 工具循环 |
| `sc2_agent/agent/session.py` | Session / JSONL 存储 |
| `sc2_agent/agent/prompt_builder.py` | System Prompt 构建 |
| `sc2_agent/tools/base.py` | 工具基类 |
| `sc2_agent/tools/registry.py` | 工具注册表 |
| `sc2_agent/llm/adapter.py` | LLM 适配器 |

---

## 1. Settings (`config/settings.py`)

### 与文档对照

| 文档要求 | 实现状态 | 说明 |
|----------|:--------:|------|
| `history_token_budget` 默认 12000 (Phase A Bot 设计) | ✅ 一致 | `history_token_budget: int = 12_000` |
| `max_agent_iterations` 默认 20 (需求 doc 无明确规定，Phase A 用 20) | ✅ 一致 | `max_agent_iterations: int = 20` |
| `subagent_max_iterations` 默认 10 (FR-09: Sub-Agent max_iterations=10) | ✅ 一致 | `subagent_max_iterations: int = 10` |
| `snapshot_decision_keep: 5` (FR-12: 决策级快照保留最近 5 份) | ✅ 一致 | |
| `snapshot_recent_keep: 5` (FR-12: 秒级快照保留最近 5 份) | ✅ 一致 | |
| 分钟级快照"无上限" (FR-12) | ⚠️ 未体现 | 无 `snapshot_minute_keep` 配置，但分钟级无上限=不需要裁剪参数，可接受 |

### 差异/问题

- **无严重差异。** 实现了 `from_env()` 工厂方法支持环境变量覆盖，额外的灵活性，与文档不冲突。
- 文档技术栈提到后续引入 `pydantic-settings`，当前 dataclass 为占位实现，符合 Phase A 范围。

---

## 2. Runtime State Machine (`runtime/state.py`)

### 与文档对照

| 文档要求 (FR-00) | 实现状态 | 说明 |
|----------|:--------:|------|
| PAUSED_THINKING / RUNNING_SLEEP 两个状态 | ✅ 一致 | `RuntimeState` 枚举精确包含这两个值 |
| `ctrl.commit()` 是唯一的 PAUSED→RUNNING 入口 | ✅ 一致 | `commit_to_sleep()` 校验前置状态 |
| `timer.monitor` 触发是唯一的 RUNNING→PAUSED 入口 | ✅ 一致 | `wake_to_thinking()` 校验前置状态 |
| 非法转换必须抛异常 (FR-00) | ✅ 一致 | `InvalidRuntimeTransition` 异常 |

### 差异/问题

- **无差异。** 状态机严格实现了 stop-the-world 不变量，与文档描述完全一致。
- 初始状态为 `PAUSED_THINKING`，bot.py 的首次 `on_step` 处理了冷启动 → 直接进入 Agent 循环，合理。

---

## 3. Commit Controller (`runtime/commit.py`)

### 与文档对照

| 文档要求 (FR-06, FR-08, 设计文档 4.0 节) | 实现状态 | 说明 |
|----------|:--------:|------|
| 校验 `staging_hash` 匹配 | ✅ 一致 | `staging_hash != current_hash` → 拒绝 |
| 校验已执行 `review.plan` | ✅ 一致 | `review_hash != current_hash` → 拒绝 |
| 提交顺序：快照→Session→game_state→Consolidator→render→Timer注册 | ✅ 一致 | `CommitServices` 7 个步骤按序执行 |
| commit 后状态转为 RUNNING_SLEEP | ✅ 一致 | `self.runtime.commit_to_sleep()` |
| commit 失败不抛异常，返回结构化失败 (FR-09) | ✅ 一致 | 返回 `Result.failure(...)` |
| `ctrl.abort()` 清理 staging | ✅ 一致 | `self.staging.clear()` |

### 差异/问题

- **差异：步骤执行方式。** 设计文档 4.0 节规定 commit 内部步骤"严格按序执行，失败不重试，已写内容成为历史日志"。当前实现用 `for step in steps` 循环，异常即返回失败，符合"失败不重试"——但没有实现"已写内容成为历史日志"（即已完成步骤不回滚）。当前实现依赖各步骤自身的原子性，**不构成功能性缺陷**，但若后续某步骤可能部分成功，需要记录。
- **无严重差异。**

---

## 4. AgentRunner (`agent/runner.py`)

### 与文档对照

| 文档要求 (FR-01) | 实现状态 | 说明 |
|----------|:--------:|------|
| 多轮 function calling 循环 | ✅ 一致 | `for _ in range(spec.max_iterations)` |
| 每轮调 LLM → 如有 tool_calls 则执行 → 写回 tool message | ✅ 一致 | 标准 OpenAI tool calling 格式 |
| 无 tool_calls 时循环结束 | ✅ 一致 | `break` on `not response.has_tool_calls` |
| `ctrl.commit` 后进入休眠 | ✅ 一致 | 检测 commit 成功后 `break`，返回 `stop_reason="committed"` |
| `ctrl.commit` 必须在最后一轮 (FR-00) | ✅ 一致 | ToolRegistry 层面 + AgentRunner break 双重保证 |
| 未 commit 也未 abort → 自动 abort (FR-01) | ✅ 一致 | `auto_abort` 逻辑，包括 max_iterations 耗尽时 |
| 结构化 messages，不拼接字符串 | ✅ 一致 | `LLMResponse.to_assistant_message()` + `_tool_message()` |
| 工具失败不击穿循环 | ✅ 一致 | ToolRegistry 捕获异常返回 `Result.failure` |

### 差异/问题

- **差异：`_publish_pending_messages`。** 这是为了让 CommitController 的 services 能访问当前 messages 做 Session 追加。设计文档未明确描述此机制，但它解决了 commit 时需要拿到本轮完整 messages 的问题。**新增的内部机制，与文档无冲突。**
- **无严重差异。**

---

## 5. Session (`agent/session.py`)

### 与文档对照

| 文档要求 (FR-10) | 实现状态 | 说明 |
|----------|:--------:|------|
| JSONL 文件存储 messages | ✅ 一致 | JSONL 格式，一行一条消息 |
| 追加写入，不删除 (FR-10) | ⚠️ 有差异 | 见下文 |
| `last_consolidated` 游标 | ✅ 一致 | `Session.last_consolidated: int = 0` |
| `get_history()` 返回游标之后的消息 | ✅ 一致 | `self.messages[self.last_consolidated:]` |
| `_find_legal_start()` 避免 orphan tool result (FR-10) | ✅ 一致 | 实现了 nanobot 同名方法 |
| 仅保留最近 N 条消息的控制 | ✅ 一致 | `max_messages` 参数 |
| 从最近的 user message 开始 | ✅ 一致 | 裁剪逻辑 |

### 差异/问题

- **⚠️ 差异：写入方式。** 设计文档规定 JSONL"追加写入，永不删除"。当前 `SessionManager.save()` 使用 `mode="w"`，每次**完整覆写**整文件（元数据 + 全部 messages）。虽然最终结果等价（所有消息都保留），但这意味着：
  1. 大文件时每次全量写入效率低
  2. 如果进程在 `save()` 中途崩溃，整个 session 文件可能损坏
  3. 不满足"追加写入"的字面语义
  - **建议**：改为 `mode="a"` 追加单条消息，元数据单独存或每次覆写元数据行+追加消息行。**非阻塞性问题，但建议后续修复。**

---

## 6. PromptBuilder (`agent/prompt_builder.py`)

### 与文档对照

| 文档要求 (FR-02) | 实现状态 | 说明 |
|----------|:--------:|------|
| 四段式结构：身份与运行时 + 当前局势 + 可用工具 + 可用技能 | ✅ 一致 | 四个 section 分别构建 |
| "你是 SC2 人族指挥官 AI" 身份描述 | ✅ 一致 | |
| 5 条核心约束 (tag 获取、plan.simulate、review.plan、消耗≤收入、commit 最后) | ✅ 一致 | `_IDENTITY_RUNTIME` 包含全部 5 条 |
| 当前局势由 `game_state.md` 注入 | ✅ 一致 | `game_state_md` 参数直接注入 |
| 工具部分只放命名空间摘要 | ✅ 一致 | `tool_summary` 参数 |
| 技能部分列出可用 skill | ✅ 一致 | 可选的 `skill_summary` 参数 |
| System Prompt 不包含旧架构多角色指令 (FR-02) | ✅ 一致 | 无多角色、无 YAML 模板、无强制步骤 |

### 差异/问题

- **无差异。** 与 Phase A Task 2 的设计完全一致，比设计文档更精简——遵循了"只写怎么用工具，不写应该怎么做"的原则。

---

## 7. Tool 基类 (`tools/base.py`)

### 与文档对照

| 文档要求 (FR-03) | 实现状态 | 说明 |
|----------|:--------:|------|
| 工具名称 `namespace.action` 形式 | ✅ 一致 | `name` 抽象属性，由子类返回 `"cmd.move"` 等 |
| JSON Schema 参数声明 | ✅ 一致 | `parameters` 属性 + `to_schema()` 生成 OpenAI 格式 |
| 只读/写入属性 | ✅ 一致 | `read_only: bool = True` |
| 参数类型转换 (cast) | ✅ 一致 | `cast_params()` 方法 |
| 参数校验 (validate) | ✅ 一致 | `validate_params()` 方法 |
| 执行 handler | ✅ 一致 | `async def execute(**kwargs)` |

### 差异/问题

- **无差异。** 是文档工具系统设计的直接翻译。

---

## 8. ToolRegistry (`tools/registry.py`)

### 与文档对照

| 文档要求 (FR-03, FR-00) | 实现状态 | 说明 |
|----------|:--------:|------|
| 注册/查询工具 | ✅ 一致 | `register()`, `get()`, `has()` |
| 工具 schema 列表导出 | ✅ 一致 | `schemas()` → OpenAI format |
| 执行前参数校验 | ✅ 一致 | cast → validate → execute |
| 读工具可并发，写工具串行 | ✅ 一致 | `execute_calls()` 中的并发/串行策略 |
| `ctrl.commit` 必须是所在响应中唯一的 tool_call (FR-00) | ✅ 一致 | `execute_calls()` 中显式检查并拒绝 |
| 工具执行异常不击穿 | ✅ 一致 | `try/except` 返回 `Result.failure` |

### 差异/问题

- **无差异。** 完美实现了文档中的工具执行策略。
- **细节**：`execute()` 返回 `Result` 统一包装，同时兼容工具直接返回 `dict(ok=..., ...)` 的简化格式——这是对文档的合理补充。

---

## 9. LLM Adapter (`llm/adapter.py`)

### 与文档对照

| 文档要求 (技术栈 9.1) | 实现状态 | 说明 |
|----------|:--------:|------|
| 使用 `openai` SDK (≥2.8) | ✅ 一致 | `import openai`，使用 `openai.OpenAI` |
| 实现 `LLMClient` Protocol | ✅ 一致 | `async def chat()` 签名匹配 |
| 多供应商 sticky 路由 | ✅ 一致 | `sticky_client_name` + `_find_sticky_spec()` |
| 返回归一化 `LLMResponse` | ✅ 一致 | 包含 content, tool_calls, usage, finish_reason |
| 从 `llm_clients.json` 读取配置 (Phase A Bot 设计) | ✅ 一致 | 在 `bot._init_llm()` 中加载 |
| API Key 环境变量解析 (`env:`) | ✅ 一致 | `_resolve_api_key()` |
| 错误不击穿，返回 finish_reason="error" | ✅ 一致 | try/except → `LLMResponse(finish_reason="error")` |

### 差异/问题

- **与 Phase A 计划差异：** Phase A Task 1 计划从 SC2 项目导入 `UnifiedLLMClient` 做薄包装。实际实现**直接使用 `openai` SDK**，不再依赖 SC2 项目的旧 LLM 客户端。这是**更好的实现**——避免了跨项目路径 hack，与文档技术栈建议"引入 `openai` SDK 替换 `UnifiedLLMClient`"一致。
- **无严重差异。**

---

## 第1轮审查总结

### 一致性评估

| 类别 | 数量 |
|------|:----:|
| 完全匹配文档 | 8 个模块 |
| 有轻微差异 | 1 个 (Session 写入方式) |
| 有严重差异 | 0 |

### 关键发现

1. **Session 写入方式** (`session.py:97`)：使用 `mode="w"` 覆写而非 `mode="a"` 追加，与文档"JSONL 追加写入"要求不一致。建议修复，但不阻塞当前进度。

2. **整体架构对齐度极高。** 核心基础设施（状态机、AgentRunner、ToolRegistry、PromptBuilder、CommitController）与三份文档的设计描述完全一致。

### 下一步审查

第2轮：工具实现层（`obs.*`, `query.*`, `cmd.*`, `build.*`, `econ.*`, `timer.*`, `plan.*`, `review.*`, `ctrl.*`）
