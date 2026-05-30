# 主 Agent 提示词体系设计方案

> 创建时间：2026-05-30
> 来源：四角度并行审查 + 设计文档 4.7 节 + skill 文件现状审计
> 状态：方案待审批，代码未修改

---

## 1. 问题诊断

### 1.1 当前 Agent 实际拿到的 System Prompt

Agent 在 `bot._run_agent_loop()` 中收到的 system message 由三段组成：

```
┌─ 第1段：身份与运行时（约80字）─────────────┐
│  你是 SC2 人族指挥官 AI。                    │
│  - 通过工具观察、推理和行动。                │
│  - 所有单位必须通过 unit_tag 引用...         │
│  - 所有带 at_time 的命令必须经过...           │
│  - 提交前必须调用 review.plan。              │
│  - 命令消耗不能超过预测资源。                │
│  - ctrl.commit 必须是最后一轮唯一的 tool_call │
├─ 第2段：当前局势（game_state.md）────────────┤
│  战略判断、优先级、已知事实、关键事件        │
├─ 第3段：可用工具（命名空间摘要）─────────────┤
│  build.* -- 9 tools: build.addon, ...        │
│  cmd.* -- 18 tools: cmd.move, ...            │
│  (11 行命名空间列表)                          │
└──────────────────────────────────────────────┘
```

**第4段（可用技能）为空** —— `bot.py` 没有调用 `skill_summary`，PromptBuilder 已有的 `skill_summary` 参数从未被传入。

### 1.2 缺失了什么

| 维度 | 设计文档要求 | 当前实现 |
|------|------------|---------|
| 决策流程指导 | 4.7 节 9 步详细流程 | 无——Agent 完全靠自己摸索 |
| 元认知自查 | 醒来先查 `hist.events` 频率 | 无 |
| 粗看→聚焦模式 | "粗看(obs.*) → 思考 → 深看(query.*) → 思考" | 无 |
| 时间线逐步推算 | "每步查 plan.build_time + plan.simulate" | 提示词只说了"必须经过数学推理"，没说怎么推理 |
| 审查迭代循环 | "规划→审查→修改→再审查" | 提示词只说"提交前必须审查" |
| WARN 不强制修改 | "最终决定权在主 Agent" | 未说明 |
| 时间线自适应 | 稳局 120-180s / 交战 15-30s | 无 |
| always skill 注入 | `main-flow` 标了 `always: true` | 从未注入到 prompt |

### 1.3 根因

设计文档定下的原则是"system prompt 只写'怎么用工具'，不写'应该怎么做'。工作流指南下沉到 skill"，设计方针完全正确，但**skill 注入机制从未实现**：
- `SkillLoader` 没有 `get_always_skills()` 方法和 `scan_skills()` 方法
- `bot.py` 没有调用 skill 加载逻辑
- `PromptBuilder.build_system_prompt()` 的 `skill_summary` 参数从未被传入

结果：Agent 既没有 workflow guide（应该在 skill 里），也没有 skill list（应该在 prompt 第4段里）。两头落空。

---

## 2. 技能体系审计

### 2.1 设计文档要求的 8 个 skill

| 编号 | skill | always | 使用者 | 当前状态 | 质量评估 |
|------|-------|:------:|--------|:------:|:--------:|
| 1 | main-flow | ✅ | 主 Agent | **需重写** | 仅7行，无元认知/粗看聚焦/审查迭代/反面示例 |
| 2 | production-math | | 主 Agent | **需重写** | 部分数据与 costs.py 不一致，缺少产能组合分析 |
| 3 | timeline-planning | | 主 Agent | **需重写** | 无逐步推算方法，无资源约束校验三要素 |
| 4 | standard-openings | | 主 Agent | 可用 | 内容偏薄但方向正确，需补充更多模板 |
| 5 | review-knowledge | | review.logic subAgent | 可用 | 5 维关注点清晰，无需大改 |
| 6 | review-dimensions | | review.logic subAgent | 可用 | 4 维审查流程清晰，无需大改 |
| 7 | consolidation-guide | | MemoryConsolidator | 可用 | 代码/LLM 职责分界清楚 |
| 8 | monitor-calibration | | 校准 subAgent | 可用 | 高频→校准的流程完整 |

### 2.2 额外实现的 1 个 bonus skill

| 编号 | skill | always | 使用者 | 当前状态 |
|------|-------|:------:|--------|:------:|
| 9 | diff-analysis | | 差异分析 subAgent | 可用——JSON 输出格式定义清晰 |

### 2.3 总结

- **9/9 个 skill 文件全部存在**
- **3 个需要重写**（main-flow、production-math、timeline-planning）——内容太薄或数据不准确
- **1 个可增强**（standard-openings 模板偏少）
- **5 个基本可用**（review-knowledge、review-dimensions、consolidation-guide、monitor-calibration、diff-analysis）
- **注入机制完全缺失**——即使 skill 内容完美，Agent 也看不到它们

---

### 2.4 每个 Skill 的设计作用

#### 主 Agent 使用的（5 个）

| Skill | 一句话 | 作用详解 |
|-------|--------|---------|
| **main-flow** | 指挥官的"标准操作手册" | 教 Agent **怎么完成一个完整的决策周期**——从唤醒到提交的标准操作流程。包含元认知自查、粗看→聚焦的观察策略、时间线逐步推算方法、审查迭代循环、常见错误警示。`always: true`，每轮自动注入。 |
| **production-math** | 指挥官的"心算参考卡" | 提供建造耗时/成本、资源收入速率、产能组合消耗速率的**速查参考数据**。Agent 规划建造时先在脑内快速估算是否可行，再调用 `plan.build_time` 和 `plan.simulate` 精确验证。 |
| **timeline-planning** | "plan.simulate 的正确用法指南" | 教 Agent **怎么正确使用 plan 工具推算时间线**——五步循环（查→算→验→注→续）、资源约束校验三要素（资源/补给/生产者）、horizon 自适应选择表、以及常见推算错误的反面教材。 |
| **standard-openings** | 指挥官的"开局棋谱" | 提供人族标准开局模板参考（1-1-1、死神扩张等）。Agent 开局时加载，了解目标列表，但**仍需自己用 plan.build_time + plan.simulate 推算精确 at_time**。模板是目标列表，不是定时时间表。 |
| **diff-analysis** | "出了什么变化？"的分析框架 | 教 Agent 在被唤醒后**发现观测与记忆不一致时**，如何结构化地对比当前状态和历史快照，生成差异报告（资源、建筑、单位、补给四个维度的 before/after），并给出 keep_plan / adjust_plan / investigate 的行动建议。 |

#### Sub-Agent / 子系统使用的（4 个）

| Skill | 谁用 | 作用详解 |
|-------|------|---------|
| **review-knowledge** | `review.logic` 审查 Sub-Agent | 审查时的领域知识库：资源、生产、补给、军事、科技五个维度的常见问题类型和判断标准。告诉审查器"什么情况下应该报 WARN、什么情况报 REVISE"。 |
| **review-dimensions** | `review.logic` 审查 Sub-Agent | 审查的四个维度定义：**对抗合理性**（敌方有什么、我们有没有应对）、**资源合理性**（花费是否在预算内、有没有资源堆积）、**战略一致性**（命令是否服务于 game_state.md 中的战略方向）、**时间线合理性**（at_time 是否正确推算、有没有冲突）。 |
| **consolidation-guide** | MemoryConsolidator 整合 LLM | 记忆整合的规则：区分**代码自动维护**的部分（已知事实、关键事件——确定性覆盖/追加）和**LLM 维护**的部分（战略判断、当前优先级——token 超预算时触发）。告诉整合 LLM "怎么从事实变化推断战略演变"。 |
| **monitor-calibration** | 校准 Sub-Agent（高频唤醒时 spawn） | 当 Agent 发现自己 10 秒内被唤醒 ≥3 次时，教它怎么调整 monitor 阈值：扩大 trigger 值、缩短 before_time 窗口、或者直接 `timer.cancel` 该 monitor。目标是减少"狼来了"式的无效唤醒。 |

#### 加载关系图

```
主 Agent（always 注入）
  └─ main-flow ← 每轮自动可见，无需手动加载

主 Agent（按需加载，调 skill.load("名称")）
  ├─ production-math ← 开始规划时间线时加载，用于心算估算
  ├─ timeline-planning ← plan.simulate 返回意外结果时加载
  ├─ standard-openings ← 游戏开局前几轮或需要切换打法时加载
  └─ diff-analysis ← obs 数据与 game_state.md 明显不一致时加载

review.logic Sub-Agent（spawn 时框架自动注入）
  ├─ review-knowledge ← 告诉审查器"查什么问题"
  └─ review-dimensions ← 告诉审查器"从哪几个维度查"

MemoryConsolidator（系统内部自动注入）
  └─ consolidation-guide ← 告诉整合 LLM"怎么更新战略判断"

校准 Sub-Agent（高频唤醒时 spawn，框架自动注入）
  └─ monitor-calibration ← 告诉校准器"怎么调整阈值"
```

> **设计原则**：主 Agent 永远不需要手动加载 review-knowledge、review-dimensions、consolidation-guide——这些是给子系统和 Sub-Agent 用的。`_make_skill_summary()` 中不应列出它们，避免误导 Agent。

---

## 3. 设计方案

### 3.1 总体架构

```
┌─ System Prompt ─────────────────────────────┐
│ 1. 身份与运行时（角色 + 推荐流程 + 硬约束）    │  ← prompt_builder.py 改
│ 2. 当前局势（注入 game_state.md）            │  ← 不变
│ 3. 可用工具（命名空间摘要）                   │  ← 不变
│ 4. 可用技能                                   │  ← bot.py 新增 _make_skill_summary()
│    ├── 自动加载：[main-flow 全文]             │
│    └── 按需加载：[skill名 + 描述 + 场景指引]   │
└──────────────────────────────────────────────┘
                      │
                      ▼
┌─ Skill 文件（sc2_agent/skills/）────────────┐
│ main-flow/SKILL.md          ← always=true   │
│ production-math/SKILL.md    ← 按需           │
│ timeline-planning/SKILL.md  ← 按需           │
│ standard-openings/SKILL.md  ← 按需           │
│ ... (其余 5 个)                              │
└──────────────────────────────────────────────┘
```

### 3.2 第1段：身份与运行时（`prompt_builder.py` `_IDENTITY_RUNTIME` 常量）

当前 6 条孤立规则 → 改为"角色定位 + 决策周期推荐 + 硬约束"三段式：

```
# 身份与运行时

你是星际争霸2人族指挥官 AI，运行在 burnysc2 环境中。
你不是流水线上的环节——你是完整的决策者：自己观察、自己规划、
自己调度、自己审查、自己提交。

**一切决策以实际观测为准。** 标准开局模板、建造耗时表、产能估算
都是参考工具，不是必须执行的教条。如果实际情况与模板不符——
资源被骚扰、建筑被摧毁、敌方打法出乎意料——以实际情况为准，
果断调整计划。模板可能不准确，也可能不适应当前局势。

## 决策周期

每轮唤醒后推荐按此模式操作（不强制，可跳过或重复某一步）：

① 自查 — 调 hist.events 检查近期唤醒频率。若频繁唤醒则加载
   monitor-calibration 技能调整阈值。
② 粗看 — obs.resources / obs.enemy_visible / obs.structures 并行调，
   30 秒内判断局势象限（稳局 / 备战 / 交战 / 不明），决定本次规划 horizon。
③ 聚焦 — 对关键对象调 obs.unit / query.* 深挖。若观测与 game_state.md
   不一致，加载 diff-analysis 技能或直接对比 hist.snapshot。
④ 时间线推理 — 逐步构建命令。循环：plan.build_time 查耗时 →
   plan.simulate 验证资源 → timer.command 注册 → 下一项。
⑤ 监测 — timer.monitor 设定时唤醒 + 偏差检测双保险。
   before_time 控制窗口，超时自动注销。
⑥ 审查 — review.plan 征求第二意见。正确节奏是：
   规划 → 审查 → 修改 → 再审查 → 直到满意。不是线性的"审完就交"。
   WARN 不等于必须改——最终决定权在你。
⑦ 提交 — ctrl.commit(staging_hash)，本轮结束。

## 并行工具调用

每一轮 LLM 响应中，你可以一次性发出多个 tool_calls，系统会批量执行：
- obs.* / query.* / plan.* / hist.* 等**只读工具可并发执行**，无数量限制。
- cmd.* / build.* / econ.* / timer.* / ctrl.* 等写入工具**按顺序串行执行**。
- 同一轮中混合读工具和写工具时，全部降级为串行以确保顺序正确。

**推荐做法**：
- 粗看阶段：obs.resources + obs.structures + obs.enemy_visible 三者并行，一次获取全局。
- 聚焦阶段：先并行 2-4 个 query.* / obs.unit 深入关键对象。
- plan.build_time + plan.simulate 可在同一轮并行查询。
- 时间线构建阶段：逐一调 timer.command（写工具，不可并行）。

**避免的做法**：
- 一次性发 12 个 obs.* 全部并行 → 信息过载，思考反而变慢。
- 在时间线构建阶段并行 5 个 timer.command → 它们会串行执行，不如逐个验证后逐个发出。

## 硬约束

- unit_tag 必须来自 obs.*/query.* 真实返回值，禁止编造。
- 每条 at_time 命令必须经 plan.simulate 数学验证——禁止手动估算。
- **plan.simulate 需要传入 mineral_income_rate 和 gas_income_rate。**
  若 simulate 返回 income_rate=0.0 或 first_failure，先检查参数是否完整，
  修正后重新模拟，不要放弃规划转向 monitor 兜底。
- 所有写操作（build.* / cmd.* / econ.* / squad.*）**必须通过
  timer.command 排期**，禁止在 PAUSED_THINKING 中直接调用。
  PAUSED_THINKING 中只允许只读工具 + timer.command/monitor。
- timer.monitor 仅负责"条件满足时唤醒你"——它不会自动执行任何命令。
  建造、训练、移动等执行动作必须通过 timer.command 排期。
- 提交前必须调 review.plan。WARN 可接受但必须看过。
- 提交前自查：staging 中是否包含了本轮计划的所有关键动作？
  对照模板或自己设定的目标列表逐一核对，确保没有遗漏。
- 命令总消耗不超预测资源收入。
- ctrl.commit 必须是最后一轮唯一的 tool_call。
```

字数约 370，符合 200-400 字目标。

### 3.3 第4段：可用技能（`bot._make_skill_summary()` 生成）

#### always skill 全文注入

`main-flow`（唯一 `always: true` 的 skill）全文注入，约 750 字。内容见下方第 4.1 节。

#### 按需 skill 清单

每行格式：`skill名 -- 一句话描述 -- 什么场景该用`

```
## 按需加载

使用 skill.load("名称") 按需加载。加载后内容在当前 wake 周期有效。

- production-math — 建造耗时/成本速查、收入速率、产能消耗 — 开始规划时间线时
- timeline-planning — 逐步推算方法、资源约束校验、常见错误 — plan.simulate 返回意外结果时
- standard-openings — 1-1-1/死神/两兵营等标准开局模板 — 游戏开局或切换打法时
- diff-analysis — 对比当前观测与历史快照的结构化差异 — 观测值与记忆不一致时
- monitor-calibration — 高频唤醒时的阈值校准方法 — 10 秒内被唤醒 ≥3 次时
```

以下 skill 由子系统自动加载，主 Agent 无需手动调用：
- review-knowledge / review-dimensions — review.logic 审查 Sub-Agent
- consolidation-guide — MemoryConsolidator

---

## 4. Skill 文件重写方案

### 4.1 main-flow/SKILL.md（需重写，always 注入）

```
---
name: main-flow
description: 主流程指南 — Agent 每个 wake 周期的推荐思考模式
always: true
---

# 主流程指南

## 阶段一：定位

**元认知自查** — 醒来后先看自己，不看游戏。调 `hist.events(type="wake_up", since=N)`
检查唤醒频率。过去 10 秒被唤醒 3 次以上说明 monitor 太敏感或局势剧烈动荡，
必要时 spawn 校准 subAgent 调整阈值。

**粗看建立全局** — 三个 obs 调用在同一轮 tool_calls 中并行发出：`obs.resources`
（资源/人口）、`obs.structures`（关键建筑进度）、`obs.enemy_visible`（敌方可见单位）。
如果你能在一个响应中同时请求它们，系统会并发执行，效率远超逐个调用。
30 秒内判断局势象限（稳局/备战/交战/不明），决定本轮规划 horizon。

**聚焦深入** — 对上一步发现的关键对象并行 2-4 个 `obs.unit` 或 `query.*` 深挖细节。
注意控制数量——一次拿太多细节会导致信息过载，反而不利于思考。
如果需要理解睡着期间的变化，spawn diff-analysis subAgent 做结构化对比。

## 阶段二：规划

**逐步推算时间线** — 不要一次性列完整张命令表。每步：
0. 先调 `plan.initial_state` 获取含收入率的完整初始状态（勿手动拼接）。
1. `plan.build_time` 查耗时成本（可和其他只读工具并行）
2. 推算 at_time
3. `plan.simulate` 验证资源不超（同可并行）
4. `timer.command` 注册（写工具，需单独调用，不可和其他工具并行）
5. 回到第 1 步处理下一项

> simulate 返回 income_rate=0.0 或 first_failure 时，先检查 initial_state
> 是否包含了 mineral_income_rate 和 gas_income_rate。修正参数后重新模拟，
> 不要放弃规划转向 monitor 兜底。monitor 是安全网，不是规划替代品。

时间线长度由局势决定：

| 局势 | 推荐 horizon |
|------|:-----------:|
| 稳局/开局 | 120-180s |
| 备战/爆兵 | 45-90s |
| 交战/骚扰 | 15-30s |
| 不明 | 10-20s |

**规划本身就是推理** — 不需要也不应该 spawn subAgent 做规划。
所有数学计算在工具调用循环中自己完成。

## 阶段三：设定 monitor

定时唤醒 + 偏差检测两条腿走路：

- **定时唤醒**：`timer.monitor(metric="game_time", op=">=", value=horizon)` — 必设
- **偏差检测**：对关键预期值设 monitor（矿量超预期、兵力低于预期）。
  `before_time` 控制有效窗口，超时自动注销。

数量：稳局 2-3 个，交战 4-5 个。设宽了漏警不如设严了高频唤醒。

## 阶段四：审查迭代

不是"规划完审查一次就提交"。正确节奏：
1. 命令初稿 → `review.plan()`
2. **WARN 不等于必须改**——最终决定权在你。若有充分理由，保留意见并附理由提交
3. 决定修改 → 修改后 `review.plan()` 再来一轮
4. 重复直到满意 → `ctrl.commit(staging_hash)`

`ctrl.commit` 必须且只能是本轮最后一个 tool_call。

## 反面示例

- ❌ 一次性规划 20 条命令从不 simulate → 资源爆负
- ❌ simulate 返回 income_rate=0 或失败 → 不检查参数直接放弃，改用 monitor 兜底
- ❌ 用 timer.monitor 代替 timer.command 做建造——monitor 只唤醒不执行
- ❌ PAUSED_THINKING 中直接调 build.train / cmd.move 而不是通过 timer.command 排期
- ❌ 审查返回 WARN 后不修改也不附理由直接提交
- ❌ 提交前不自查 staging 内容——SupplyDepot 没排期但以为已经安排了
- ❌ 稳局设 15s horizon → 每 15 秒醒来无事发生，浪费 token
- ❌ 不设定时 monitor，只依赖偏差检测 → 无偏差时永远不醒来
- ❌ commit 同一轮还调 obs.* 或 cmd.* → commit 必须是唯一的 tool_call

## 提交后

代码自动完成持久化、记忆整合、game_state 更新、monitor 注册。Agent 休眠直到下次唤醒。
```

### 4.2 timeline-planning/SKILL.md（需重写）

```
---
name: timeline-planning
description: 时间线逐步推算方法 — 从目标列表反推 at_time，资源约束校验，时间线长度选择
---

# 时间线规划

## 逐步推算方法（五步循环）

每个命令依次走完"查 → 算 → 验 → 注 → 续"：

1. **查耗时成本**：`plan.build_time("目标")` → 获取 duration、矿物/气体/补给成本、
   前置条件和生产者类型。**不要凭记忆估算**，每次重新查。

2. **推算 at_time**：`at_time = max(当前时间, 前置建筑完工时间, 生产者空闲时间,
   资源攒够时间)`。其中完成时间 = 开始时间 + duration。

3. **模拟验证**：`plan.simulate(commands=[全部命令+新命令], horizon=规划长度)`。
   **每次变更命令列表后必须重新模拟**——前序命令改变后续资源曲线。

4. **注册命令**：`timer.command(at_time=计算值, tool_name="...", arguments={...})`

5. **继续推算**：回到第 1 步处理下一个目标。

## 资源约束校验

plan.simulate 返回的每步预测中扫描三类异常：
- `minerals < 0` 或 `gas < 0` → 推迟该命令或在前序增加采矿时间
- `supply_used > supply_cap` → 补给瓶颈，提前造 SupplyDepot
- `producer_available = false` → 生产建筑被占用，错开或换建筑

## 时间线长度选择

| 局势 | 推荐长度 | 理由 |
|------|:------:|------|
| 开局 | 120-180s | 标准开局可预测 |
| 稳局 | 60-120s | 可预测但需防敌方动作 |
| 备战 | 45-90s | 资源波动大 |
| 交战 | 15-30s | 微操敏感，状态变化快 |
| 不明 | 10-20s | 信息不足，快速迭代 |

## 常见错误

- 全部命令堆完再 simulate → 失败点出现后整批重来
- 凭感觉设 at_time 不用 build_time → 偏差逐条积累
- 忽略生产者可用性 → 同一建筑安排冲突任务
- 只算资源不算补给 → 卡人口上限
- 交战期规划过长 → 15s 后局势剧变，前序作废
```

### 4.3 production-math/SKILL.md（需重写——数据对齐 costs.py）

```
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
| SiegeTank | 150 | 125 | 32 | +3 | Factory+TechLab |
| Medivac | 100 | 100 | 30 | +2 | Starport |
| SupplyDepot | 100 | 0 | 21 | +8 | SCV |
| Barracks | 150 | 0 | 46 | 0 | SCV |
| Factory | 150 | 100 | 43 | 0 | Barracks |
| Starport | 150 | 100 | 36 | 0 | Factory |
| TechLab | 50 | 25 | 18 | 0 | 挂件 |
| Reactor | 50 | 50 | 36 | 0 | 挂件 |

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
```

---

## 5. 代码改动方案

### 5.1 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `prompt_builder.py` | 修改 | `_IDENTITY_RUNTIME` 常量替换（6 条规则 → 角色+流程+约束三段式） |
| `skills/loader.py` | 新增方法 | `scan_skills()`、`get_always_skills()`、`_parse_frontmatter()` |
| `tools/skill.py` | 修改 | `description` 增强，指引 Agent 去 system prompt 找 skill 名 |
| `bot.py` | 新增 + 改参 | 新增 `_make_skill_summary()`；`_run_agent_loop()` 传入 `skill_summary` |
| `skills/main-flow/SKILL.md` | 重写 | 4 阶段详细流程 + 反面示例（见 4.1 节） |
| `skills/timeline-planning/SKILL.md` | 重写 | 5 步循环 + 资源校验 + 常见错误（见 4.2 节） |
| `skills/production-math/SKILL.md` | 重写 | 数据对齐 costs.py + 产能组合 + 补给管理（见 4.3 节） |

### 5.2 `SkillLoader` 新增方法

```python
# skills/loader.py 新增

def scan_skills(self) -> list[dict[str, Any]]:
    """扫描所有 skill 目录，返回去重后的元数据列表。
    workspace skill 优先于 builtin。"""
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for root in self._roots():
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if name in seen:
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                continue
            meta = self._parse_frontmatter(
                skill_md.read_text(encoding="utf-8")
            )
            if meta is None:
                continue
            meta["path"] = str(skill_md)
            seen.add(name)
            results.append(meta)
    return results

def get_always_skills(self) -> list[dict[str, str]]:
    """返回所有 always:true 的 skill 的 name + 全文 content。"""
    always: list[dict[str, str]] = []
    for meta in self.scan_skills():
        if meta.get("always") is True:
            loaded = self.load(meta["name"])
            always.append({
                "name": meta["name"],
                "content": loaded["content"],
            })
    return always

@staticmethod
def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """简易 YAML frontmatter 解析（不依赖 PyYAML）。"""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    meta: dict[str, Any] = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v == "true": v = True
        elif v == "false": v = False
        meta[k] = v
    return meta if "name" in meta else None
```

### 5.3 `bot.py` 新增方法 + 改动点

```python
# bot.py — 在 _make_tool_summary() 方法后新增

def _make_skill_summary(self) -> str:
    parts: list[str] = []

    # always skill 全文注入
    always = self._skill_loader.get_always_skills()
    if always:
        parts.append("## 自动加载")
        for skill in always:
            parts.append(skill["content"])

    # 按需 skill 清单
    all_skills = self._skill_loader.scan_skills()
    # 只列出主 Agent 用的（排除 subAgent/subsystem 专用的）
    agent_skills = [
        s for s in all_skills
        if not s.get("always")
        and s["name"] not in {
            "review-knowledge", "review-dimensions",
            "consolidation-guide",
        }
    ]
    if agent_skills:
        parts.append("## 按需加载")
        parts.append("使用 skill.load(\"名称\") 按需加载：")
        for s in agent_skills:
            desc = s.get("description", "")
            parts.append(f"- {s['name']} — {desc}")

    # subsytem skill 说明
    parts.append("")
    parts.append("以下由子系统自动加载，无需手动调用：")
    parts.append("- review-knowledge / review-dimensions — review.logic 审查 Sub-Agent")
    parts.append("- consolidation-guide — MemoryConsolidator")

    return "\n".join(parts)

# bot.py — _run_agent_loop() 中修改（约第 728 行）
system_prompt = self._prompt_builder.build_system_prompt(
    game_state_md=game_state_md,
    tool_summary=tool_summary,
    skill_summary=self._make_skill_summary(),  # ← 新增
)
```

### 5.4 向后兼容

所有降级路径返回空/跳过，skills 目录缺失或 frontmatter 解析失败不崩溃：
- `scan_skills()` 中 `if not root.exists(): continue`
- `_parse_frontmatter()` 失败返回 `None` → scan_skills 跳过该目录
- `get_always_skills()` 无 always skill 时返回 `[]`
- `_make_skill_summary()` 全部为空时返回 `""`
- `PromptBuilder` 收到空 `skill_summary` 时跳过第 4 段

---

## 6. 实施计划

### 第一批：skill 文件重写（3 个文件，无代码依赖）

1. 重写 `skills/main-flow/SKILL.md`
2. 重写 `skills/timeline-planning/SKILL.md`
3. 重写 `skills/production-math/SKILL.md`

### 第二批：注入机制实现（4 个代码文件）

4. `skills/loader.py`：新增 `scan_skills()`、`get_always_skills()`、`_parse_frontmatter()`
5. `tools/skill.py`：增强 `description`
6. `bot.py`：新增 `_make_skill_summary()` + 传入 `skill_summary`
7. `prompt_builder.py`：替换 `_IDENTITY_RUNTIME` 常量

### 第三批：回归验证

8. 运行现有 195 个测试确保无回归
9. 新增测试：SkillLoader 新方法、PromptBuilder 第 4 段渲染

---

## 变更日志

| 时间 | 变更 |
|------|------|
| 2026-05-30 | 创建文档，汇总四角度审查 + skill 审计 + 完整设计方案 |
