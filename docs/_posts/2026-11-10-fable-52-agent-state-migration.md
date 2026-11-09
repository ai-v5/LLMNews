---
title: "Java SDK 3.7.0 接入 Fable 5.2：升级模型，也要检查 Agent 历史"
date: 2026-11-10T05:46:00+08:00
summary: "Anthropic Java SDK 3.7.0 新增 Fable/Mythos 5.2 的类型支持，但识别模型名不等于会话兼容。结合源码差异与官方迁移文档，梳理历史绑定、回退、动态工具和成本边界。"
section: explainer
label: "API 与 Agent 工程"
tags: [Anthropic, Fable, Java, SDK, Agent, API]
demo: false
sources:
  - title: "Anthropic Java SDK v3.7.0 官方发布"
    url: "https://github.com/anthropics/anthropic-sdk-java/releases/tag/v3.7.0"
  - title: "v3.6.0 至 v3.7.0 源码差异"
    url: "https://github.com/anthropics/anthropic-sdk-java/compare/v3.6.0...v3.7.0"
  - title: "Anthropic：Claude Fable 5.2 与 Mythos 5.2 发布"
    url: "https://www.anthropic.com/claude-fable-and-mythos-5-2"
  - title: "Fable 5.2 模型规格"
    url: "https://platform.claude.com/docs/en/models/fable-5-2/overview"
  - title: "Fable 5.2 迁移指南"
    url: "https://platform.claude.com/docs/en/models/fable-5-2/migration-guide"
  - title: "Fable 5.2 变化说明"
    url: "https://platform.claude.com/docs/en/models/fable-5-2/whats-new-fable-5-2"
  - title: "Preserved thinking 文档"
    url: "https://platform.claude.com/docs/en/build-with-claude/preserved-thinking"
  - title: "会话中系统消息与工具变更"
    url: "https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages"
  - title: "Fast mode 文档"
    url: "https://platform.claude.com/docs/en/build-with-claude/fast-mode"
  - title: "Enterprise Frontier Safeguards 原始说明"
    url: "https://www.anthropic.com/news/enterprise-frontier-safeguards"
---

**信息截止：2026 年 11 月 10 日北京时间 05:46。** 本次入选的新材料是 Anthropic 官方 Java SDK v3.7.0，GitHub Release 的 `published_at` 为 **2026-11-09T18:52:55Z**，即北京时间 11 月 10 日 **02:52:55**，明确处于本轮最近24小时窗口。本文依据该版本源码差异及官方 API 文档；Anthropic 模型主公告只标注11月9日，其精确发布时间未确认，不能用SDK时间替代模型首发时间。以下未执行SDK构建、真实API或生产回归测试。

## SDK 新增了什么，又没有替应用解决什么

[v3.7.0发布说明](https://github.com/anthropics/anthropic-sdk-java/releases/tag/v3.7.0)明确列出新增 `claude-fable-5-2` 与 `claude-mythos-5-2`。该标签指向提交 `80c906a17bcefb4611ed39cce8ff1347b1e2e6b1`，可与v3.6.0比较，而不只依据模型发布宣传判断变化。

在[Messages的Model类型](https://github.com/anthropics/anthropic-sdk-java/blob/80c906a17bcefb4611ed39cce8ff1347b1e2e6b1/anthropic-java-core/src/main/kotlin/com/anthropic/models/messages/Model.kt)中，两个新模型都有常量，并进入字符串转换、`Known`和`Value`的识别分支。[Managed Agents模型类型](https://github.com/anthropics/anthropic-sdk-java/blob/80c906a17bcefb4611ed39cce8ff1347b1e2e6b1/anthropic-java-core/src/main/kotlin/com/anthropic/models/beta/agents/BetaManagedAgentsModel.kt)这次新增的则是Fable 5.2，不能把两个接口的枚举清单混写。

这个变化有具体价值：依赖已知模型常量的Java代码可以明确表达新型号，读取模型值时也不必把它当未知项处理。但类型系统与服务器能力不是一回事。该类本就允许通过`of(String)`承载任意字符串，而`known()`遇到未知项会抛异常。因此，不能反推“没有新常量就绝不可能发出请求”，也不能认为升级依赖就获得Mythos准入或所有平台功能。

更重要的是，[新增模型的补丁](https://github.com/anthropics/anthropic-sdk-java/commit/195b48862312e526d474f9a387a2d256326712d0)解决的是客户端型号识别，并没有替自行构造历史的应用重写会话。本文后面的迁移检查，是这次新支持与服务端协议之间的连接，不是声称这些协议都由SDK 3.7.0首次引入。Java SDK与会管理会话的Agent SDK也不是同一个层级。

## 从新型号支持，走到实际会话迁移

Anthropic 发布 Fable 5.2 和 Mythos 5.2，称两者来自同一个底层模型，但部署防护与准入条件不同。对多数自行开发 Agent 的团队，更直接的问题是：把模型名替换成 `claude-fable-5-2` 后，原来能运行的会话是否仍能继续？[发布公告](https://www.anthropic.com/claude-fable-and-mythos-5-2)

官方规格给出的 Fable 5.2 上下文窗口为 100 万 token，最大输出为 128K token；标准输入、输出价格分别为每百万 token 8 美元和 40 美元。API 默认 effort 为 high，不应与发布公告中 Claude 产品默认的 medium 混为一谈。[模型规格](https://platform.claude.com/docs/en/models/fable-5-2/overview)

这些数字不能替代迁移测试。**本文的判断是，最值得检查的是应用保存、修改和回放历史的方式。** 一个只发送单轮问答的冒烟测试，很可能覆盖不到长会话真正会触发的错误。本文主要面向自行构造历史消息的集成；官方说明 Claude Code、claude.ai、Managed Agents 和 Agent SDK 已处理相关请求构造。[迁移指南](https://platform.claude.com/docs/en/models/fable-5-2/migration-guide)

## 一、思考块绑定：历史不再能被悄悄改写

Preserved thinking 让后续请求保留模型先前生成的思考块。它不是可任意搬运的独立文本：官方将其绑定到生成它时的请求前缀，包括系统提示、工具定义和更早的消息。更改前面的内容，可能使该块及后续思考块失效。

Fable 5.2 的变化是对所有账户执行这一前缀检查。Fable 5.1 曾按账户创建时间区别默认行为；Mythos 5.1 则已经对所有账户执行。因而，不能把“我们旧账户上的 Fable 5.1 一直没报错”当成新模型兼容证据，也不能把整套机制说成今天才首次出现。[变化说明](https://platform.claude.com/docs/en/models/fable-5-2/whats-new-fable-5-2)

普通 Messages 请求发生前缀不匹配时，默认返回 400。启用相应 beta 控制后可以选择 `drop_block`，丢弃失效及后续思考块再继续；这不是无损修复，可能带来缓存失效、重新推理及额外延迟。**Message Batches 有例外**：未显式设置行为时，文档规定默认丢弃，而非把每条都报错。[思考块绑定文档](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking)

从应用设计看，应区分两类动作：

- **追加新事实**：用户补充要求、工具返回新结果，应成为后续消息。
- **重写旧事实**：清洗旧工具输出、重新编码历史图片、修改工具定义，可能改变思考块所依赖的前缀。

后者不一定是错误产品需求。隐私清理或上下文裁剪可能确实必要，但应用应明确地重建会话或处理丢弃结果，而不是假设旧推理仍能原样复用。这里的“保持历史”是协议约束，不意味着必须永久保存业务数据。

## 二、动态工具不是不能改，而是要记录“从何时开始改”

许多 Agent 每轮都会重新拼装工具列表。若顶层 `tools` 随权限、服务发现或 MCP 端工具目录变化，受影响的可能不只是工具可见性，还包括缓存和思考块绑定。

官方已有的中途系统消息方案，允许在历史末端记录新指令；工具新增或撤回则可用对应内容块。当前 Claude API、Claude Platform on AWS、Google Cloud（Anthropic managed）的 `inline-tools-2026-09-15` beta 还支持在消息中携带新工具定义。不同云平台、按引用增删和完整定义的支持范围不完全相同，不能直接复制一个请求格式到所有渠道。[会话中消息与工具文档](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages)

这给出的工程方向是：**把工具变化作为会话中可定位的事件，而不是覆盖会话最开头的工具清单。** 例如一个会话前半段没有数据库读取权限，后半段获得权限，历史应保留这两个阶段的区别。

但让模型看到工具，并不等于赋予真实业务权限。服务端仍须验证当前用户和每次操作的授权。缓存优化不能替代访问控制，这一点是本文的工程建议，而不是模型 API 能自动提供的保证。

## 三、回退模型可能请求成功，却不再保留原来的推理状态

迁移指南在 Claude API 与 Google Cloud（Google managed）渠道说明：Fable 5.2 可以读取 Fable 5.1 的思考块；反向切换时，5.1 无法读取 5.2 的块，API 会在送入模型前过滤它们，请求仍可成功。客户端历史不会因此被改写：持续原样回传完整历史，切回支持的模型后仍能读取旧块；客户端自行删除才会永久丢失。[迁移指南](https://platform.claude.com/docs/en/models/fable-5-2/migration-guide)、[模型切换文档](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking#switching-models-mid-conversation)

账户也有边界：5.2 思考块只能由原账户或关联账户使用，未关联账户回放时会被静默丢弃。[变化说明](https://platform.claude.com/docs/en/models/fable-5-2/whats-new-fable-5-2)

因此，负载均衡器的成功状态码不足以证明会话完整性。假设系统因限流临时从 5.2 回退到 5.1，再切回 5.2，应该检查的是整个往返过程中状态、成本和任务结果，而不只是路由是否恢复。

建议把回归样本至少分成以下几类：

1. 长会话经过存储、恢复后继续执行。
2. 工具目录、系统策略或旧消息在中途改变。
3. 模型降级再升级，以及跨账户转交会话。
4. 客户端裁剪历史与服务端压缩分别运行。

观察项应包含任务通过率、400 的原因、缓存读写量和端到端延迟；对支持的 beta 响应，再记录 `input_transformations` 所报告的丢弃原因。不要为了监控而保存不必要的用户内容。

此外，迁移还有独立兼容项：旧 `computer_20251124` 工具在 5.2 上需改用新版工具集，Amazon Bedrock 是文档列出的例外；advisor 配置也要满足 5.2 的兼容要求。始终开启思考和不支持强制指定工具等限制，则不是相对 5.1 新增的变化。[迁移指南](https://platform.claude.com/docs/en/models/fable-5-2/migration-guide)

## 四、快模式与低单价，要放回完整任务成本里看

官方 fast mode 的“最高 2.5 倍”描述针对输出 token 速率，不是首 token 延迟，也不是整个 Agent 任务提速。标准与 fast 的输入、输出单价分别为 8/40 与 16/80 美元每百万 token；fast 另有容量与限流约束。当前文档还明确，Fable 5.2 fast 并非在 Managed Agents 中可用。[Fast mode 文档](https://platform.claude.com/docs/en/build-with-claude/fast-mode)

举一个仅用于理解的算例：若任务总时间中只有一半花在输出生成，且这一半恰好达到 2.5 倍速度，其他时间不变，那么总加速只有约 1.43 倍。这不是实测，而是 1 ÷（0.5＋0.5÷2.5）的时间分解。工具执行、网络等待、重试和缓存未命中都不会自动随输出速率等比例缩短。

合理的比较单位因此是“完成一个合格任务的成本与时间”，并同时记录成功率。旧模型更便宜、新模型少重试，或 fast 更贵却减少等待，都需要在同一任务集合中验证，不能只凭价目表决定。

## 五、数据保留不是顺手绕过的迁移障碍

当前文档要求 Fable/Mythos 5.2 默认适用 30 天数据保留；零数据保留并非所有账户开箱可用，需满足明确授权条件。发布公告提到 Enterprise Frontier Safeguards 私测为符合条件的客户提供路径，合资格客户在实际部署 EFS 前也可能获准继续使用 ZDR；这不代表任何 ZDR 工作区都能直接调用成功。[模型规格](https://platform.claude.com/docs/en/models/fable-5-2/overview)、[发布公告](https://www.anthropic.com/claude-fable-and-mythos-5-2)

EFS 本身并不是本次才出现的新概念，其原始说明发布于 9 月 1 日，涉及客户控制的存储、监控和访问安排。部署团队应先核对自己的数据协议及获准配置，不能为了消除请求错误就降低隐私要求。[EFS 原始说明](https://www.anthropic.com/news/enterprise-frontier-safeguards)

## 我们的判断与未验证部分

Fable 5.2 值得研究的工程信号是：长任务 Agent 的升级单位正在从“模型 ID”变成“模型、历史状态和工具协议”的组合。保持可回放的历史、显式处理不兼容状态、测量合格任务成本，比追逐单一速度数字更能降低迁移风险。

本文未运行真实账户、云平台或生产负载测试；官方文档会继续更新，beta 接口尤其应在部署前再确认。本文没有依据无法完整核读的系统卡推导安全能力结论，也不把官方性能表述当作独立实测结果。
