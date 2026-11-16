---
title: "常驻 Agent 不需要一直跑：拆解 Anthropic 的架构，做一个不会乱发消息的工程助手"
date: 2026-11-16T14:53:00+08:00
summary: "真正持续运行的是事件、状态和权限，不是模型。以 GitHub CI 观察员为例，给出能上线试点的状态机、失败恢复、预算和验收方案。"
section: explainer
label: "Agent 工程"
tags: [Agent, 事件驱动, 工程实践]
demo: false
sources:
  - title: "Anthropic / William Hu：Building always-on agents（2026-11-13）"
    url: "https://claude.com/resources/articles/building-always-on-agents"
  - title: "Anthropic：Claude Managed Agents（产品页）"
    url: "https://claude.com/platform/claude-managed-agents"
  - title: "Claude Code：延迟工具调用的适用条件"
    url: "https://code.claude.com/docs/en/hooks#defer-a-tool-call-for-later"
  - title: "Anthropic：提示缓存文档"
    url: "https://platform.claude.com/docs/en/build-with-claude/prompt-caching"
  - title: "GitHub Docs：Webhook 最佳实践"
    url: "https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks"
  - title: "GitHub Docs：Actions 工作流运行 API"
    url: "https://docs.github.com/en/rest/actions/workflow-runs"
  - title: "GitHub Docs：处理失败投递"
    url: "https://docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries"
---

一个 PR 刚跑红，过一分钟又绿了。你希望助手马上打断你，还是等它确认问题还在？再比如，它发通知时超时了：对方没收到，还是收到了、只是回执丢了？这两个问题，比“Agent 能不能 24 小时跑”更接近真正的难点。

Anthropic 的 [《Building always-on agents》](https://claude.com/resources/articles/building-always-on-agents) 给出的思路是：**让模型按需醒来，把持续性放进模型之外。** 没有事就休眠；有事时短跑一次，写回进度，再退出。下面先拆原文的架构，再给一套具体的 GitHub CI 观察员方案。原文是设计指南，不是这些方案的可靠性保证；下文的指标、表结构和故障处理是本文建议，未部署或实测。

## 一、原文讲了什么？五个部件各管一件事

| 部件 | 解决的问题 | 工程上容易误解的地方 |
|---|---|---|
| **事件收件箱（Inbox）** | 用户消息、Webhook、定时任务统一入库，Worker 再取 | 推送是敲门铃，持久事件才是工作记录。一个队列的单活不是全系统单线程 |
| **定时器（Timers）** | 保存将来的回访和周期任务，到期投递事件 | 定时器不直接开模型；重复触发、停机补跑和取消都需要规则 |
| **记忆（Memory）** | 下次短跑知道前次进度、用户偏好和已经说过什么 | 会话记录不是业务账本。外部事实应留可查指针，权限更不能从记忆里推导 |
| **权限（Permissions）** | 区分可自动执行、明确禁止、需人确认 | 模型可以提议，执行层必须独立裁决；等审批时结束本次 run，不占 Worker |
| **发件箱（Outbox）** | 决定何时把结果送到用户，而不是直播每个步骤 | 原文允许简单场景直接发，正式发件箱用于节流和恢复；它本身并不保证只送一次 |

原文还区分 **run** 与 **session**：前者是一次有起止的执行，后者是承载消息和工具调用的对话记录。用户回复能续上已有 session，独立事件可以另开；真正要跨跑保留的状态，应另存。否则换会话、压缩长上下文或更换模型，任务就可能丢失。特别是三类信息不能混在一起：会话方便恢复对话，文字笔记记录偏好，结构化账本记录待处理事项和外部操作结果。笔记可以修订，但不能因为摘要改了就让“已发”变回“待发”。

这个设计的价值不是省掉一切成本，而是把**运行时长**和**服务持续性**分开。模型休眠不消耗连续推理 token，但数据库、轮询、日志、通知和待命 Worker 仍有开销。原文提到的模型成本改善是特定 benchmark 的对比，不等于任何常驻系统都能省同样比例。托管 Agent 也只是可替换的执行层；采用[托管方案](https://claude.com/platform/claude-managed-agents)还是自己跑，首先要查它替你持久化了哪层状态、审批和投递能否对账，再谈迁移。

## 二、先做一个窄任务：只读 GitHub CI 观察员

**试点设定：**一个公开仓库、一个固定私有通知目的地、只观察白名单里的 Actions 工作流。规则是：最新 PR head 的同一工作流最终失败且持续 2 分钟时，通知一次；已通知的失败在同一 head 上转绿，再通知一次恢复。新提交替换 head 时撤销旧候选，不把旧 SHA 的红灯当成当前阻塞。用户可以暂停并看状态。首版不改 PR、不重跑、不发评论、不合并，也不上传完整日志。

| 方案 | 首版选择 |
|---|---|
| 输入 | GitHub App Webhook；只订阅所需事件。另以定时对账修补漏投 |
| 服务 | 一个小型 HTTP 接收器、Postgres、API 查询 Worker 和通知派发 Worker；同一部署可分进程 |
| 事实判定 | 代码查 GitHub API，按 PR 当前 head、工作流和 run attempt 复核；只对明确的 PR 关联发通知。试点仅启用能一致绑定实际 PR head 的工作流 |
| 模型 | 可选：把已核实的失败步骤和来源链接压成两句。模型超时、输出不合规或预算用尽，就发模板 |
| 到达目的地 | 试点用自己的私有收件列表，按逻辑消息 ID 唯一显示；要接第三方通知，再逐个验证重试语义 |

这里最重要的取舍是：**“失败是否仍在、值不值得打扰”先写成规则，不要先做成模型提示词。** 模型只处理有价值的语言工作。若规则模板已经够用，就先不上模型；以后需要解释多个失败的共因，再加摘要能力做 A/B。

## 三、把流程写到可以实现的程度

```text
Webhook → 验签 → Inbox 落库 → 快速应答
定时扫描 / 对账 ──────────────┘
          ↓
Worker 取有效租约 → 查 PR 当前 head 与工作流结论
          ↓
同一事务：更新事件与状态；到时复查、生成通知意图或静默
          ↓
Outbox → 派发 / 对账 → 私有通知列表
```

1. **接收：HTTP 成功只表示事件已落库。** 按 [GitHub Webhook 规范](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks)用原始请求体验签，验证仓库安装与事件白名单；按 `(source, delivery_id)` 去重。通过验证才写入，落库成功才返回 2xx；模型不在接收路径上。GitHub [不会自动重投失败交付](https://docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries)，所以仍需周期性回查。可先每 5 分钟对账：分页核查当前 open PR 和其最新 head 的相关 runs（见 [Actions API](https://docs.github.com/en/rest/actions/workflow-runs)），每个已监控 run 单独复核 attempt。若以后用增量游标，留重叠窗口、处理完才推进，不假设 rerun 一定改变创建时间；超出回看窗或权限失效时，显式标记“观测有缺口”。
2. **领取：只允许一个有效提交者，而非假定永远只有一个进程。** 用短事务领取任务、设置租约和递增的代号，外部读和模型调用放到事务外。提交时在 SQL 里校验代号与业务状态版本；超时接管后，旧 Worker 即使恢复，也不能把旧结论写回。同一 PR 首版串行，不同 PR 可以并发；不要让一个正在解释日志的任务阻塞全仓。
3. **归并：传输去重不等于业务去重。** 收件箱去重只解决同一 delivery 多次到达；Webhook 与对账可能对同一故障提供不同 ID。业务状态按 `仓库 / PR / head SHA / workflow_id` 分组，用 API 复查 run attempt，不能按事件抵达顺序覆盖。发件箱再以 `业务键 / 故障轮次 / 通知类型` 去重。正在重跑不等于已经恢复；更新的 execution 未结束时暂停派发旧失败候选，等它有明确终态。一轮失败直到恢复只报警一次，恢复后若又红则开新轮次。不要给未报过红灯的短暂故障发送恢复提醒。
4. **定时：等两分钟必须是业务状态，不是让模型睡两分钟。** 初次确认红灯就写 `due_at`；调度器把到期复查写进 Inbox，并在同一事务更新定时器，事件用 `(timer_id, scheduled_for)` 去重。定期巡检停机补跑可合并为一次最新全量核对，不积攒几十个旧 tick；审批过期和即时失败复查则不能被旧事件覆盖。时间戳存 UTC；未来若有用户当地日程，另外存时区与补跑语义。
5. **发送：数据库事务保证的是“有意图”，不是对方“已收到”。** 业务状态与 outbox 同事务提交，避免“业务做完但忘了发”。试点内置私有收件列表，dispatcher 可在数据库事务里按消息 ID 插入通知、标记已写入。接第三方时优先用其官方幂等键；返回超时且无法查询是否接收，标记 `unknown` 并对账，不盲重发。发送前再检查当前状态版本、是否暂停、目的地授权；一旦外部已接收，不能靠回滚数据库撤回。已写入收件箱不等于用户已经阅读。

**最少的数据表：**`inbox(delivery_key, payload_ref, status, lease_until, lease_epoch, attempts)`、`timers(timer_id, due_at, schedule_rule, status)`、`subjects(domain_key, state, version, incident_generation, source_ref)`、`outbox(message_key, subject_version, recipient_ref, status, provider_ref)`。另留结构化运行审计：输入引用、规则版本、决策理由、模型预算与派发结果；原文日志不默认进记忆，不把密钥或用户授权凭证交给模型。首版的状态迁移可以这样写：

| 当前条件 | 动作与下一状态 |
|---|---|
| 最新 head 红灯，但还没满观察期 | `failure_pending`；登记到期复查，不发 |
| 到期仍红且观测新鲜 | 本轮失败通知入队；投递确认后标记已通知 |
| 满期前恢复或 head 变化 | 取消候选，按新事实更新，不补发旧告警 |
| 已通知的失败在同一 head 恢复 | 按本轮 ID 写一次 “恢复”；再失败开新轮 |
| API 不可达、事件关联不明 | 退避、对账，不把“不知道”当绿灯 |
| 重试超过阈值 | 进入死信供人工重放，保留原身份与审计 |

## 四、怎样试点：把权限、指标和成本一起验收

**第 1 阶段：回放与影子运行。** 第 1–2 天接一个公开仓库，只收集事实不推送。用历史和合成事件测试：重复投递、旧失败在新成功之后抵达、相同 workflow rerun、Webhook 漏投、租约过期旧 Worker 返回、写状态后派发器崩溃、通知回执丢失、暂停后队列里还留着通知。工具输出和日志当数据，不能变成指令。故障原因不明就写“不确定”，不要把模型概括当成证据。

**第 2 阶段：小流量真实通知。** 第 3–7 天启用私有通知、保留一键暂停与纯模板降级。试点建议门槛：重复/乱序回归包内零重复和零过时推送；每次推送能追到 head、run 和原始来源；人工标注的历史集里有效失败通知召回和精确率分别至少 95%，同时报告绝对分母及误报漏报；Webhook 正常时，审核失败窗口结束之后到私有收件箱的 P95 小于 60 秒；漏投场景单独测对账恢复，不混入正常路径的延迟。数据量小时，这些是试点验收条件，不是已证明的生产 SLA。

**成本也做上限。** 例如一天 300 条进入队列的原始事件，若规则合并后 30 条值得摘要，最多给其中 20 条模型调用，每条上限约 2,000 输入、300 输出 token，则这 20 次的摘要预算最多约 **4 万输入 + 6,000 输出 token/天**。这是假设预算，不是实测价格；还要分别统计 API 配额、入队与对账开销，以及每个有效提醒带来的阅读成本。每个任务的软超时、硬预算和熔断规则由服务层执行，不能靠提示词自报。没有证据表明摘要比模板更有用，就关闭模型。[Claude 提示缓存](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) 默认 5 分钟、另有 1 小时选项；跨小时醒来的任务不能把复用计为必然，预算按缓存未命中也能运行来设计。

**扩展路径先写清，不在试点打开写权限。** 以后如果要允许“重跑某次 CI”，把请求的具体命令、目标 run/head、调用方、时限和权限版本封成一条审批记录；用户回复只产生审批事件，恢复时重新确认目标和当前许可，不让会话文本本身授权。[Claude Code 的 defer](https://code.claude.com/docs/en/hooks#defer-a-tool-call-for-later) 有具体适用条件（非交互运行、该轮只有一次工具调用），不能假定所有会话或并行调用都能靠它暂停。即使不加这项功能，先把只读查询、模型生成和通知凭证隔离；日志中的命令、请求外发的文字或所谓审批都不具有授权效力。GitHub App 令牌仅由查询进程持有，按最小范围配置 Actions/PR 只读权限，模型只能收到简化字段和获准的链接。默认仅保留结构化观察，不落整份日志；若必须排查，另做短期、限制访问的留存。

核心判断：**常驻的是任务状态和授权边界，模型只是在该出力的时候出力。** 首版是否成功，就看三件事：没漏掉真正需要处理的问题、没为已消失的问题打扰人、遇到未知交付状态不会乱重试。做到这三点，再增加更聪明的判断或更广的权限。
