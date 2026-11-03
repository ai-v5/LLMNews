---
title: "DeepSeek Super-agent 源码深读：从事件流到有边界的自主协作"
date: 2026-11-03T20:40:00+08:00
summary: "从事件流、工单授权、并发调度与恢复机制读懂 DeepSeek 的研究原型，结合实验和社区评论分析长期 Agent 的价值、成本与边界。"
section: explainer
label: "源码深读"
tags: [DeepSeek, 智能体, 开源]
demo: false
sources:
  - title: "项目理念"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/000-philosophy.md"
  - title: "固定版本"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/tree/8c32a9dc5d72c033816c6a8110b37f40cf94fba4"
  - title: "设计文章镜像"
    url: "https://xitter.cf/DeepSeekHarness/article/2116857257245987236"
  - title: "README 第 3 至 9 行"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/README.md#L3-L9"
  - title: "角色模型实现"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/role-models.ts#L8-L43"
  - title: "领域模型"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/001-domain.md"
  - title: "Engine 入口"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/engine.ts#L19-L48"
  - title: "Trigger 接收与扇出"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/intake.ts#L19-L60"
  - title: "准入与权限代码"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L167-L240"
  - title: "授权文档"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/002-authorization.md"
  - title: "默认配置"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L79-L95"
  - title: "方向检查与评估校验"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L18-L60"
  - title: "默认主动规则"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L62-L65"
  - title: "Mandate 数据结构"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/model.ts#L125-L133"
  - title: "恢复前验证"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/tickets.ts#L246-L269"
  - title: "后续消息的所有权"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/002-authorization.md#subscriptions-continuing-existing-work"
  - title: "策略变更通知"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/tickets.ts#L196-L207"
  - title: "重验证实现"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L213-L240"
  - title: "执行器实现"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/executor/dsh.ts#L24-L110"
  - title: "并发规则"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#concurrency"
  - title: "执行与后台任务"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#the-executor"
  - title: "主会话工具与等待限制"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/007-architecture.md#main-session-tools"
  - title: "SQLite Store"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/store.ts#L51-L89"
  - title: "持久化 effect"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/effects.ts#L40-L68"
  - title: "Outbox"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/outbox.ts#L21-L51"
  - title: "GitHub 渠道"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/github-channel.ts#L18-L46"
  - title: "飞书渠道"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/feishu-channel.ts#L19-L27"
  - title: "重启与恢复"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#restart"
  - title: "工单阶段"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#ticket-stages"
  - title: "持久化结构"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/007-architecture.md#persistence"
  - title: "模型读取接口"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/007-architecture.md#read-resources"
  - title: "memory.ts"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/memory.ts#L1-L16"
  - title: "数据保留现状"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/007-architecture.md#L482-L486"
  - title: "冯若航评论"
    url: "https://vonng.com/ai/ds-super-agent/"
  - title: "个人实践报告"
    url: "https://geekcoding101.com/posts/deepseek-dsh-superagent-deep-dive"
  - title: "Anthropic 官方工程文章"
    url: "https://www.anthropic.com/research/managed-agents"
  - title: "会话权限配置"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/sessions.ts#L137-L154"
  - title: "合并规则"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#merging"
  - title: "部署中的独立健康检查"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L133-L141"
  - title: "执行目录与进程准备"
    url: "https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/executor/dsh.ts#L242-L261"
---

当一个编码 Agent 能独立修复问题之后，团队马上会遇到另一组麻烦：谁来分派不断涌入的请求？如何把 Issue、群聊和代码审查串成同一件事？任务完成几天后收到新意见，应该恢复旧工作，还是重新接单？机器重启以后，怎样避免重复回复、重复执行？

DeepSeek 公开的 `dsh-superagent-prototype` 把这些问题放进了同一个工程原型。它最值得关注的部分，是对**工作状态、授权依据和人的注意力**进行了明确建模：什么消息值得处理，为什么可以开始工作，后续信息由谁接手，什么时候需要人介入，都不再完全依赖一个聊天窗口里的临场判断。[项目理念](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/000-philosophy.md)

这条路线能帮助解释 Agent 产品接下来的一项核心竞争：模型已经能做的事，系统能否把它们组织成可持续、可追踪、少打扰人的工作流程？

本文截至 2026 年 11 月 3 日，固定分析公开仓库提交 `8c32a9dc5d72c033816c6a8110b37f40cf94fba4`，采用源码与文档静态阅读，未独立部署或运行测试。设计文章通过公开的第三方英文镜像查阅，该页注明为中文原文的机器翻译；文中将开源实现、设计设想、作者实验和社区实践分开讨论。[固定版本](https://github.com/deepseek-ai/dsh-superagent-prototype/tree/8c32a9dc5d72c033816c6a8110b37f40cf94fba4) · [设计文章镜像](https://xitter.cf/DeepSeekHarness/article/2116857257245987236)

## 一 先分清模型 Harness 与这套原型

仓库首页把边界写得很清楚：这是供参考的研究原型，不是 DeepSeek 正式产品，也不应直接当作生产就绪的软件。公开代码经过整理，与团队内部版本及配套设计文章并不完全一致，文章中的部分方向尚未实现。[README 第 3 至 9 行](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/README.md#L3-L9)

理解项目，最好区分三个层次。

- **模型**提供理解、推理与生成能力。这个仓库没有发布新的基础模型权重，也不是一次模型训练成果。
- **DeepSeek Harness**提供运行 Agent 的基础能力，包括会话、工具、模型调用和后台任务。
- **dsh-superagent**是运行在 Harness 上的 bundle，围绕一个 GitHub 仓库接收事件，也可接入飞书，把消息变为有授权依据的工单，并协调执行与回复。

源码里的模型配置进一步说明了这种分工。`src/app/role-models.ts` 通过宿主解析 provider、model 和 reasoning effort，为新会话设置角色模型，不修改全局默认模型。协调与执行可以采用不同配置，但最终能用什么模型，仍取决于 Harness 的实际连接和能力。[角色模型实现](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/role-models.ts#L8-L43)

因此，评价它时不能把“系统更会并发调度”直接写成“模型代码能力提高”，也不能把架构探索当成某项正式服务的功能清单。本文关心的是，现有模型外面的这一层软件，究竟增加了哪些可验证的能力。

## 二 源码的中心是一张工单账本

只画 Router 和 Worker 两个方框，很容易漏掉项目真正的工程重心。

`docs/001-domain.md` 定义了一组贯穿代码、工具与界面的领域对象：Source 是外部事件来源，Trigger 是不可变事件，Thread 是同一讨论里的事件序列，Ticket 是获得授权的工作单元，Mandate 记录授权的范围与依据，Assignment 把工单交给某个执行器，Subscription 则把工单与讨论关联起来。[领域模型](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/001-domain.md)

这里最重要的区分是：**工单、讨论和模型会话并不等价。**

同一条讨论可以产生多项工作，一个工单可以关注多个相关讨论；工单可以经历多次派工，也可以在完成后恢复。底层模型会话的某一轮结束，并不意味着业务任务已经结束。代码用独立的 Ticket 状态表达这些关系，没有直接把 Session 状态当成项目管理状态。

这解决了一个经常被忽视的问题：Agent 的工作进度应该由业务事实决定，而不能只由“模型这次是否停止输出”决定。例如，代码已经准备好等待审查，与任务已经完成，是两个不同的状态。系统若把它们混为一谈，后续审批、CI 变化和补充意见就只能靠人重新解释。

从 `src/core/engine.ts` 和 `src/core/intake.ts` 可以追到一条完整的事件路径：

1. Source 把平台事件转换成 Trigger，入口先处理重复事件和来源范围。
2. Trigger 写入记录，并投递给订阅相关 Thread 的工单，作为后续上下文。
3. 没有被工单执行器接手的人类消息，以及需要独立判断的其他事件，进入 Eval 路径。
4. 获准接单后创建带 Mandate 的 Ticket，再通过 Assignment 启动执行器。
5. 执行结果转为结构化报告，由系统组织回复与后续状态。

订阅投递发生在“是否创建新工作”的判断之前。这个顺序使已有任务能连续收到代码审查、CI 和讨论更新，不必每条消息都重新走一次派单流程。[Engine 入口](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/engine.ts#L19-L48) · [Trigger 接收与扇出](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/intake.ts#L19-L60)

我的判断是，这比“多个 Agent 一起聊天”更接近可复用的系统能力。参与执行的模型可以变化，但团队仍需要知道每个请求去了哪里、为什么被接下、现在由谁处理。

## 三 主动工作被拆成代码准入与语义判断

“主动”最容易被误读成模型看到什么就决定做什么。公开实现的默认选择明显更谨慎。

第一层是确定性的 gate。它检查消息来源、发件人、是否直接提及 Agent、允许名单、机器人身份以及来源的准入配置。第二层才由模型判断语义：这是不是具体的工作请求，方向是否明确，是否符合团队写下的规则。明确请求与推断候选是两条不同路径；机器人不能因为发了一段像指令的文本，就获得明确请求的身份。[准入与权限代码](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L167-L240)

对推断出来的候选，系统提供三种模式：`off` 不接受这类候选，`observe` 只记录判断，`auto` 才允许符合条件的候选进入执行。**默认是 observe。** 这不妨碍符合准入条件的明确请求工作，但团队可以先观察系统本来会接什么，再决定是否打开主动执行。[授权文档](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/002-authorization.md) · [默认配置](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L79-L95)

对推断候选的完整 assessment，更具体的限制藏在 `directionAllowed()` 里。模型必须给出结构化判断：存在实现意图，目标不是未确定状态，并且不需要尚未做出的设计决策。这条路径接单还必须至少匹配一条启用规则，并提供意图依据。宿主会验证规则评估是否完整，而不是只接收一句“我认为值得做”。符合准入条件的明确请求则可由 `orchestrator_route` 直接接单，不必逐条匹配这些主动规则。[方向检查与评估校验](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L18-L60)

默认规则也很窄：文案、标点或已有翻译的修正，以及目标明确的小范围视觉修正。代码特意区分“有人觉得不好看”和“已有可执行的修改方向”，不允许把前者自动扩展成重新设计产品。[默认主动规则](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L62-L65)

这套分工的价值，是让概率判断受到可检查条件的约束。代码适合判断身份、模式和结构是否满足要求，模型适合理解意图与上下文。二者都不能替代另一方。

不过，结构化字段只让判断过程可校验，并不能证明语义判断一定正确。“目标是否已经确定”仍然需要模型理解。因此，observe 模式的重要性不只是保守：它给团队留下了收集误判、调整规则和检验边界的阶段。

## 四 Mandate 让授权跨越任务生命周期

一个任务获准开始后，权限如何随时间变化，是这份源码比普通 Agent 演示更深入的地方。

Mandate 保存接单时的策略版本、工作范围、请求强度、匹配规则，以及来源中的发件人身份等信息。工单完成不自动抹掉这份依据，后续人类消息可以让符合条件的旧工单恢复，恢复前要按照当前策略重新验证。人工停止则撤回授权，旧工单不再自动续接，继续工作需要重新接单。[Mandate 数据结构](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/model.ts#L125-L133) · [恢复前验证](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/tickets.ts#L246-L269)

这可以理解为：系统既记得“曾经让你做过什么”，也要检查“现在这项授权是否还成立”。对于持续数天、经历多轮审查的代码工作，这比每条消息都从零开始更自然。

与此同时，**上下文到达不等于授权扩大。** 订阅线程中的机器人消息、CI 结果或普通讨论可以送到执行器，但它们只是上下文。工单仍应受原有范围约束。执行器认为新请求超出范围时，需要把消息交回主会话重新路由；只有没有其他工单继续拥有该消息时，才重新进入评估。

这层设计还防止协调者与执行者同时处理同一条追问：某条人类后续消息已经由执行器负责时，主会话不能再随意接受、附加、忽略或重新评估它。系统为“谁负责接下来的决定”建立了明确所有权。[后续消息的所有权](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/002-authorization.md#subscriptions-continuing-existing-work)

边界同样需要讲清楚。策略改变会使正在评估的候选失效并重新排队，也会向受影响的活跃工单发送变更信息，**不会立即硬停所有在途工作**。结束的工单恢复时，才进行对应的 Mandate 重验证。它是一套工单级授权与生命周期机制，还不能描述成实时收回每一次工具调用权限的能力系统。[策略变更通知](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/tickets.ts#L196-L207) · [重验证实现](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/policy.ts#L213-L240)

对于工程团队，这意味着权限治理需要分层：业务层保存授权依据，执行层限制实际能力，代码托管平台再执行审查与合并要求。把三者都交给提示词，会让一条看似完善的流程失去真正的约束力。

## 五 并发设计把人的插话放在新任务之前

每个 Ticket 拥有自己的 Executor Session 和工作目录，执行器处理任务细节，主会话负责协调。默认正常 worker 并发数为 3，同时给人的后续消息或状态请求留出一个额外槽位；新任务不能持续占满队列，让人无法继续已有任务。[执行器实现](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/executor/dsh.ts#L24-L110) · [并发规则](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#concurrency)

这种优先级很有代表性。系统并不只追求把机器跑满，也要为人的纠正与决策保留响应能力。一个吞吐量很高、却总在用户说“先停一下”时忙不过来的 Agent，很难成为可靠的协作者。

长命令同样被当成响应性问题处理。路由和 worker 预设将前台 shell 的等待压到 5 秒，较长命令转到后台，结果以事件返回。这样，新输入可以在后续模型步骤被处理，而不必等一条长命令跑完。这里的“随时响应”仍受当前推理步骤与调度时机限制，不能理解为任意时刻都能中断模型计算。[执行与后台任务](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#the-executor)

源码还为主会话设置了等待限制，但协调者“不要自己读代码做重活”并不是一个完全由工具权限强制实现的隔离。公开版本的主会话仍具备部分 shell、读取等工具，文档明确承认相关约束包含提示词规则。这一点也提醒我们，设计图上的职责分离，需要逐层检查它到底由代码、预设还是提示词保证。[主会话工具与等待限制](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/007-architecture.md#main-session-tools)

## 六 可靠性来自持久化副作用与失败账本

多 Agent 系统最容易被演示掩盖的问题，往往发生在模型已经作出决定之后。

如果“接下工单”和“启动执行器”之间崩溃，会不会留下永远没人处理的任务？如果发出回复之后网络断开，重试会不会再发一遍？如果工作已经完成，但结果尚未写回，重启会不会重复修改？

原型为此引入了明确的状态持久化与副作用队列。`src/app/store.ts` 使用 SQLite，配置 WAL 与 `synchronous=FULL`；业务状态与待执行 effect 在事务中记录，提交后再执行外部动作。`src/app/effects.ts` 负责按键合并、代际检查、重试和退避等处理。[SQLite Store](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/store.ts#L51-L89) · [持久化 effect](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/effects.ts#L40-L68)

对外回复还有独立的 Outbox。它保存待发、已发与丢弃等状态，同一工单发往同一会话的消息通常按顺序等待；较早消息连续失败三次后会被标记为问题，不再阻塞后续消息。GitHub 渠道会检查消息标记，飞书渠道使用幂等标识，减少重试造成的重复发送。[Outbox](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/outbox.ts#L21-L51) · [GitHub 渠道](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/github-channel.ts#L18-L46) · [飞书渠道](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/feishu-channel.ts#L19-L27)

这些是实质性的工程措施，但仍不应该概括成“所有外部动作都只执行一次”。发送评论、推送代码、调用远端服务与本地数据库事务处在不同边界，结果不确定时仍需要核对外部事实。项目的恢复说明也要求执行器先检查目录、git 历史和 GitHub，再决定是否重复动作。[重启与恢复](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#restart)

另一个有用的取舍是失败显式化。`ready`、`blocked`、`failed`、等待回答、投递失败等状态有不同含义，面板依据结构化记录判断什么需要人。失败不会因为 Agent 还能继续生成文本，就被自动包装成成功。

这让系统具备了运营视角：人不必逐条读完整会话，也应该能够知道哪些工作等待审查、哪些必须补充信息、哪些只是后台正常运行。[工单阶段](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#ticket-stages)

## 七 记住业务事实与拥有长期记忆仍是两件事

这个项目容易引出“Agent 已经拥有永久记忆”的联想，但源码支持的结论应更具体。

公开版保存 Trigger、Thread、Ticket、Decision、授权依据、发送回执和版本化配置等业务状态；会话历史由 Harness 管理。模型还可以按资源标识读取相关工单、消息、线程与报告，用紧凑预览和分页减少一次性塞入上下文的内容。[持久化结构](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/007-architecture.md#persistence) · [模型读取接口](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/007-architecture.md#read-resources)

这些能力足以支持跨回合继续工作，却不等于已经解决长期知识整合。源码中的 `src/core/memory.ts` 尤其容易被误会：它是用于领域测试和临时 Engine 实例的内存仓库实现，并不是一个训练出来的长期记忆系统。[memory.ts](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/core/memory.ts#L1-L16)

文档甚至明确写出，目前没有清理旧记录的机制，多类状态会持续增长。它诚实地暴露了长期运行还要补的工程问题。[数据保留现状](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/007-architecture.md#L482-L486)

这里可以提出一个独立于具体厂商的判断：**保存所有历史，只解决“数据还在不在”；长期记忆还要解决“该取什么、哪些已经过时、哪些不得跨边界使用”。** 运行时间越长，检索质量、冲突消解、遗忘与权限变化就越重要。更多上下文并不会自动带来更好的判断。

## 八 实验显示了调度收益 也显示了 token 代价

配套设计文章报告的端到端实验，每轮约 300 条消息，其中约 20 条工作请求，每种设计运行 5 次；编码由耗时工具模拟。完成时间从工作请求到结果消息，缓存读取 token 汇总全部会话。因此它测试的是调度与协调，并不测真实代码质量。[实验来源 第 7.1 节 第三方镜像](https://xitter.cf/DeepSeekHarness/article/2116857257245987236)

| 设计 | 完成时间 p50 | 完成时间 p95 | 每轮缓存读取 token |
| --- | ---: | ---: | ---: |
| Super-agent | 12.4 分钟 | 15.7 分钟 | 23.2M |
| 去掉直通机制 | 12.6 分钟 | 15.5 分钟 | 31.8M |
| 单 Session 加 subagent 中性提示词 | 20.4 分钟 | 29.5 分钟 | 6.1M |
| 单 Session 加 subagent 委派优先提示词 | 13.8 分钟 | 29.0 分钟 | 10.8M |

这组数据首先提示，任务是否被稳定委派，本身就是系统性能的一部分。用户面对的最终延迟，不只取决于模型生成速度，也取决于请求是不是卡在协调会话里，以及不相关消息是否不断干扰执行。

第二，不能只挑更漂亮的延迟。独立会话有上下文成本，表中的 Super-agent 使用了更多缓存读取 token。**完成更快，与使用更少资源，是两个指标。** 缓存读取量也不能直接换算成总费用：还缺输出、非缓存输入、模型价格以及其他工具成本。

第三，从表里不能得出“直通让任务完成更快”。两种 Super-agent 的完成时间相近，去掉直通后主要增加的是缓存读取量。按表内数值计算，加入直通后这项读取量约少 27%；换一个分母，去掉直通后则约多 37%。两种说法描述同一组数字，不应混用。

样本规模与模拟任务也决定了外推上限。要证明真实研发收益，还需要实际仓库中的正确率、回归缺陷、人工审查时间、返工率与总成本。要证明节省团队注意力，则需要直接测量打断次数、人工接管与错误提醒，而不是把 p95 延迟当作注意力收益的替代品。

## 九 业界讨论的分歧在工作上下文是否足够显式

目前值得参考的外部讨论，主要是架构评论和小规模实践，还不足以称为行业共识。

冯若航在评论中认可异步派单的工程价值，但更强调工作上下文应明确呈现：仓库、机器、规则、权限和历史决定不能都让全局 Router 猜。他主张以群聊或项目空间承载上下文，并让不同模型协作、共享可迁移状态。这是作者的架构主张，不是对本项目完成的对照实验。[冯若航评论](https://vonng.com/ai/ds-super-agent/)

这个批评指出了一个值得保留的产品原则：用户可以不用管理底层 Session，但仍要能看清当前工作属于哪个项目、在哪个环境执行、具有什么权限。隐藏实现细节与保留业务边界，可以同时成立。

同时，源码也不支持把这份原型简单描述成“全靠一个 Router 猜”。它已经有明确的 Source、Thread、Ticket、Mandate 和 Subscription。更准确的问题是：当范围从一个仓库扩大到多个项目、多个团队时，这套映射与授权能否继续保持清晰？模型对任务范围的判断，需要多少显式界面与确定性规则配合？这是从现有实现延伸出的产品与工程问题。

GeekCoding101 则报告了一次 Apple Silicon Mac 上的小仓库实践：约 25 分钟到首个工单，约 1 分 42 秒得到包含回归测试的 PR，总 API 支出自述为 0.06 美元。其测试使用少量预置问题，固定版本为 `6337fc8`，与本文源码快照不同。这些数字只能作为单次实践记录，不能作为普遍成本或相对竞品性能。[个人实践报告](https://geekcoding101.com/posts/deepseek-dsh-superagent-deep-dive)

它提供的价值，是表明有人尝试走完了接单、修复、追问与恢复的真实流程；它没有提供足够证据说明复杂仓库也能维持相同速度。任务规模、验证难度和缓存条件发生变化后，也不能原样套用这组成本与时间。

从厂商的一手材料看，Anthropic 在 2026 年 4 月的 Managed Agents 工程文章中，也把持久会话日志、Harness 和执行环境拆开，强调组件可独立恢复，以及把凭据置于执行环境之外。[Anthropic 官方工程文章](https://www.anthropic.com/research/managed-agents)

由此可以作出一个有限的行业判断：长期 Agent 的工程重心，正在覆盖会话之外的状态、执行环境和身份边界。不同系统可能采用不同产品入口，但都会遇到相似的恢复与隔离问题。这说明问题具有共性，并不证明某一种架构已经胜出。

## 十 安全边界决定它能进入什么样的工作现场

公开原型对风险的说明很直接：Executor 以操作者的 OS 身份执行命令，不逐次请求批准；工作目录与命令包装提供默认环境，并不构成安全隔离。源码也确实设置了对应的宽权限执行模式。[执行文档](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#the-executor) · [会话权限配置](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/sessions.ts#L137-L154)

合并规则也必须分清软硬边界。文档中的交付要求可以要求审查、限制自动合并条件，但宿主没有独立的 merge 专用决策逻辑。真正需要强制的审批，应由仓库分支保护等平台能力执行。[合并规则](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#merging)

这不意味着项目没有权限设计。前面的准入、Mandate、版本检查和审计记录已经覆盖了重要问题。它意味着这些设计主要回答“为什么允许一项工作”，而机器隔离还必须回答“即使判断出错，最多能碰到什么”。

因此，评估这类原型的团队应先限定可信范围，使用隔离环境和最小权限账户，把生产凭据与执行代码分离，并让高影响操作受到模型之外的控制。安全评估还应覆盖外部消息进入上下文后的处理、跨任务信息边界，以及中止与撤权是否能真正阻止后续动作。这些是部署前的防御性要求，不能用“Agent 会遵守提示词”替代。

同样，恢复队列和进程存活也不等于工作方向始终正确。一个 Agent 可以技术上健康，却持续重复无效尝试。工程可靠性与语义上的有效进展，需要分别观察。

## 十一 后续演进应沿可验证的缺口推进

设计文章继续讨论了独立 Watchdog、执行与状态解耦、Router 扩展、长期记忆及跨边界 Agent 协作等方向。它们不应被列成这个公开 bundle 已交付的完整能力。[设计文章 第 5 至 8 节 第三方镜像](https://xitter.cf/DeepSeekHarness/article/2116857257245987236)

这里有两个需要精确说明的层次。公开版已经有健康状态、重试和后台任务控制，部署文档还指导操作者在另一个 Harness profile 中设置每小时健康检查，因此不能说它完全没有监控；但这不等于已经实现完整的语义进度监督。类似地，公开插件的执行器展示的是本地工作目录和进程执行，没有展示完整的远程机器注册、离线重连与跨设备调度控制面，也不能据此推断整个 Harness 的能力边界。[部署中的独立健康检查](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L133-L141) · [执行目录与进程准备](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/executor/dsh.ts#L242-L261)

结合源码，下面五个演进问题比“还能再加多少 Agent”更值得跟踪。这是本文的工程判断，不是项目已经承诺的发布时间表。

**第一 从能恢复到能判断是否真正前进。** 当前状态机可以记录失败、重试和等待，下一步还需要识别工作是否偏离目标、是否陷入低价值循环。监督者自身的权限、判断误差和停止条件也要受到约束，否则监控只会再增加一层自动化噪声。

**第二 从单仓库上下文到显式工作空间。** 每个工作空间应清楚绑定仓库、执行位置、人员权限与交付规则。跨项目任务则需要可审计的交接，而不只是更长的 Router 上下文。扩展时，信息共享与隔离应成为正式设计对象。

**第三 从工单授权到执行能力约束。** 保存 Mandate 很重要，但高风险动作还需要独立权限检查、可靠撤权与凭据隔离。授权记录和执行能力若不一致，系统就可能在“知道不该做”的同时仍然“有能力做”。

**第四 从不断保存到有治理的长期状态。** 记录保留、归档、检索、过期知识与权限变化都要有规则。更换模型或执行器之后，历史工作能否继续被准确解释，也是系统可迁移性的检验。

**第五 从调度实验到端到端价值评估。** 下一轮公开评估应同时报告成功率、人工干预、返工、延迟与完整成本，并覆盖任务取消、权限变更、服务中断与跨线程协作。只有把成功路径和失败路径一起测量，才能判断哪些复杂度真正换来了收益。

## 结语

`dsh-superagent-prototype` 提供了一份值得认真阅读的工程样本：它把持续到来的外部消息，转换成有来源、有范围、有状态的工作，并为后续追问、失败恢复和人的介入设计了明确路径。

它还没有证明复杂研发可以完全无人管理，也没有交付一个覆盖所有场景的通用自主系统。但源码已经把问题推进了一步：团队不只需要一个会调用工具的模型，还需要一个能保存授权依据、安排责任、处理恢复，并在合适时刻让人看见问题的系统。

未来值得比较的，除了谁能完成更难的单次任务，还有谁能在更长时间、更复杂环境里，稳定交付有用结果，同时让人付出更少、也更可预期的管理成本。
