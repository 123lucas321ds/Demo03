---
name: main-flow
description: 主流程指南 — Agent 每个 wake 周期的推荐思考模式
always: true
---

# 主流程指南

## 阶段一：定位

**元认知自查** — 醒来后先看自己，不看游戏。调 `hist.events(event_type="wake_up", since_game_time=N)`
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
| 开局 | 120-180s |
| 稳局 | 60-120s |
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
