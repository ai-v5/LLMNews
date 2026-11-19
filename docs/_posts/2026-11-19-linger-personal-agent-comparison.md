---
title: "Linger 把个人 Agent 搬回本机：对比 Meta Muse、Grok Bot 与 ChatGPT dots"
date: 2026-11-19T12:03:00+08:00
summary: "拆解 Linger 的模型运行时、长期记忆、工具权限与 PolyStrata 的 MoE 分层推理；用产品级评测区分功能、模型能力和可信交付。"
section: explainer
label: "个人 Agent 与推理系统"
tags: [Linger, PolyStrata, Muse, Grok Bot, ChatGPT dots, 本地推理, Agent]
demo: false
---

**Linger 最有竞争力的地方，是把本地模型、文件、工具和长期记忆放进同一个可自托管的个人 Agent。它的最大缺口不是功能表少几项，而是还没有可信证据说明：在弱硬件、长上下文与有真实副作用的任务里，它能以多高概率把活做对。** 对本地文件、私有代码、离线资料，我会优先试 Linger；对关机后也要盯工作、跨 SaaS 跟进与核验结果，优先试 dots；家庭生活入口看 Muse；团队把多个 Bot 放进共享工作流，看 Grok Bot。这是按场景划分的选型判断，不是总排名。

本文截至 2026 年 11 月 19 日，基于公开文档、源码、项目方性能数据及第三方产品评测；未进行四款同机同题实测。Linger 指 Simplex AI 的 [simplexai-labs/linger](https://github.com/simplexai-labs/linger)，[桌面首版](https://github.com/simplexai-labs/linger/releases/tag/desktop-v0.1.0) 于 11 月 10 日发布。其创始人曾是 [DeepSeek-VL 项目负责人](https://github.com/deepseek-ai/DeepSeek-VL)，项目发布主体不是 DeepSeek。源码公开，[许可证](https://github.com/simplexai-labs/linger/blob/main/LICENSE) 基于 Apache 2.0 另加条款，包括第三方托管服务限制；不要把可自用部署等同于可无条件做商业托管。

## 一、Linger：四层拆开，才知道哪些数据留在本机

| 层 | Linger 的设计 | 实际边界 |
|:--|:--|:--|
| 交互与任务 | 桌面工作区承载对话、文档、文件和工作任务；TeamHub 支持分享与协同 | 远端团队部署与本机桌面是不同的信任域；安装了客户端不表示每项数据都只驻留该机器 |
| 模型与运行时 | 支持本地模型，也可选已有订阅或自带凭证；运行时选项包括 Claude Code、Codex 和 Pi | 同一 Linger 界面可以有完全不同的模型能力、数据出站与权限行为；本地 UI 不等于本地模型 |
| 记忆与执行 | 本地优先的知识与记忆工作区、可安排的任务、桌面工具与连接器；连接器让 Agent 能从对话走到外部动作 | Composio 连接器、Soniox 语音及远端模型路径分别引入外部服务；看清数据发给谁、后台由谁运行。源码架构说明 Pi 路径不经同样的 review，不能把审批承诺泛化到所有运行时 |
| 推理 | PolyStrata 提供本机模型端点，可把 GPU、主存、存储分层使用 | 推理设备需可用。PC 休眠、断电或离线时，不能仅凭有定时功能就假定本机任务继续；远端自托管也不是“数据永不出设备” |

依据：[源码架构](https://github.com/simplexai-labs/linger/blob/307f2ab438b3ed28e95f073e8e381b9442239f42/docs/architecture.md)、[自托管](https://github.com/simplexai-labs/linger/blob/main/docs/self-hosting.md)、[官方文档](https://docs.heylinger.com/)。如果目标是真正离线，验收条件应当具体到：使用本地模型，关掉不需要的外部连接与远端语音，用断网环境验证所选记忆、检索、文件和任务路径。连接器可扩展能力，也会改变威胁模型。原始信息在机器上存着，并不能阻止工具调用或模型请求把它带出去。

### 记忆和执行：Linger 真正值得拆的三处

1. **共享 Wiki 和私有记忆分开。** Personal Wiki 按项目、联系人与主题等归档，多个 Agent 可搜；每个 Agent 自己的跨 Room 记忆则不默认共享。检索把 Wiki 与原始消息/文档的关键词和时间信号分别排序，结合 RRF 融合，不依赖 embedding 或 reranker。该实现的取舍是好解释、好溯源，但跨词汇与模糊语义召回仍需测；委派任务与文档工作并不自动进入文档所述的私有记忆提取路径。[记忆](https://github.com/simplexai-labs/linger/blob/307f2ab438b3ed28e95f073e8e381b9442239f42/docs/wiki-and-memory.md)
2. **主动性是轮询、判断、调度。** 代码里的连接器事件监听是 600 秒轮询，先判断是否值得唤醒，再决定提醒、准备还是静默；不能当毫秒级 webhook，也不能理解成模型一直在思考。反馈可以改变文本行为规则，不是在线更新模型权重。[主动机制](https://github.com/simplexai-labs/linger/blob/307f2ab438b3ed28e95f073e8e381b9442239f42/docs/proactive.md) · [监听代码](https://github.com/simplexai-labs/linger/blob/307f2ab438b3ed28e95f073e8e381b9442239f42/apps/teamhub/internal/proactive/listener.go)
3. **本机执行与委派有真实边界。** 控制面包含 Go TeamHub 与 PostgreSQL，电脑上的 Daemon 主动连出，事件可落 SQLite 后重放；TeamHub 的 Docker 部署不等于模型搬入 Docker。后台独立会话靠任务简报继承上下文，协作以 `team.md` 明示角色交接。调度文档给交互高于后台优先级，反映了本机算力争用。连接器写入有操作 ID 和未知结果不直接重发的设计，不要把这理解成所有外部服务都保证事务式、恰好一次执行。[委派](https://github.com/simplexai-labs/linger/blob/307f2ab438b3ed28e95f073e8e381b9442239f42/docs/task-delegation.md) · [协作](https://github.com/simplexai-labs/linger/blob/307f2ab438b3ed28e95f073e8e381b9442239f42/docs/team-md.md) · [调度](https://github.com/simplexai-labs/linger/blob/307f2ab438b3ed28e95f073e8e381b9442239f42/docs/model-scheduling.md)

## 二、PolyStrata：是异构执行，不是用 12 GB 显存装下 125B 权重

[PolyStrata 实现说明](https://github.com/simplexai-labs/PolyStrata/blob/main/docs/DETAILS.md) 的要点是把高频专家留在 GPU，冷专家留在主存并可由 CPU 算，与 GPU 执行重叠；prefill 的分块和专家 staging、MTP 候选并行验证也会改变速度。量化进一步减少权重占用。SSD 能帮助摆放或加载权重，并不能由此推断每步都适合按 SSD 带宽流式供数。

可以把一次 decode 的代价粗看为 `串行开销 + max(GPU 计算、CPU 冷专家、能重叠的搬运) + 未掩盖的同步/搬运`，实际还要看运行图依赖。输出 tok/s 在使用投机解码时按**接受的输出 token**算，不等于主模型逐 token 的原生步速。决定性变量是路由热度能否延续、CPU 内存带宽、PCIe 搬运、KV 与热专家争抢显存，以及 MTP 接受率。不能把 125B 总参乘以 tok/s 当 HBM 流量；训练 FP8/FP4 的峰值也不能拿来解释这个 CPU/GPU 混跑的服务。

**把真实消费机台架和模拟预算的成绩分开。** PolyStrata [型号与测试表](https://github.com/simplexai-labs/PolyStrata/blob/main/docs/MODELS.md) 列 RTX 5070 12 GB、Ryzen 7600、64 GB RAM 的 Qwen3.8-Flash-Next 自测：

| 量化 | 短对话 decode | 128K decode | 32K prefill |
|:--|--:|--:|--:|
| Q2_0 | 94 | 76 | 2,650 |
| IQ2_XS | 79 | 63 | 2,090 |
| IQ3_S | 53 | 46 | 1,620 |

单位 token/s；不同列的输入长度不同，不可组合成一个端到端结果。不同量化不是等质量对照，裁过专家的 Coder 变体也不能代替完整模型。另看 [Linger 的本地推理说明](https://github.com/simplexai-labs/linger/blob/main/docs/local-inference.md)：部分所谓 8/12 GB 档实际是把 **96 GB 卡限制到该预算**，并不复现廉价 GPU 的算力、带宽或 PCIe 行为；Mac 24/32 GB 档也有用 **256 GB M5 Ultra** 代测的情形，缩规划预算并未缩物理内存和页缓存。模拟 12 GB 档的一组 62K 输入首 token 约三分钟，说明短 prompt decode 快不能代表长任务响应快。实验未证明本地量化模型整体达到 Claude；项目方的能力对标与台架测得的 token/s 不是同一实验。

## 三、四款功能横评：区别在它替你守着什么

以下是公开可核功能，不把未披露记成“不支持”，也不保证所有地区、账号或套餐都开放。

| 维度 | Linger（Simplex AI） | Muse（Meta） | Grok Bot（xAI） | ChatGPT dots（OpenAI） |
|:--|:--|:--|:--|:--|
| 执行位置 | 本机优先；TeamHub 可自托管；本地或接云基座 | 云端 Secure VM 和浏览器；服务按地区开放 | 云电脑与工具，可在共享工作空间里组织多个 Bot | 专属云电脑/浏览器；可授权接入自己的电脑，云执行不依赖个人 PC 通电 |
| 模型选择 | 可换模型、量化、运行时；能针对性调整硬件和成本 | 发布时说明 Muse Spark；Wonder 是独立发布的模型系列，推出进度和套餐不能从模型榜推给每个 Muse 账号 | 官方 FAQ 称按任务选模型，无用户 model picker；不指定所有任务由某版 Grok 固定完成 | 首发 GPT-6 Astra；11 月 3 日公告已扩到含 GPT-6.1 Terra 的模型族，可能按工作环节使用不同模型 |
| 长期记忆 | 工作区、历史与记忆检索；模型与后端路径影响数据边界 | 主对话与 side chats，跨对话记忆，可读、可编辑的记忆界面 | 持续存在的 Bot，学习个人/团队上下文与 routines | 持久偏好与任务背景、读取已授权来源；有公开隐私设置和活动视图 |
| 主动性与执行 | 支持后台任务/安排；离线调研要以实际运行时和所在机器验证存活 | Goals、计划/事件触发，结合个人生活、购物、跨模态和 WhatsApp 场景 | 个人 Bot 或共享 Team Bot，可进 Slack、Teams 与会议；面向有分工的团队工作流 | 支持定时及相关事件、主动研究与委派 Work/Codex。官方明确其主动研究模式是只读，不等同于所有后台工作都只读 |
| 控制边界 | 可控部署和本机文件是优势；运行时 review 与远端连接须逐条核验 | 审批、活动记录、VM 隔离；不是产品绝无越界的证明 | 1.0 声明按用户权限和共享频道可见性控制、敏感动作审批 | 内置管控与 Custom Rules；授权电脑、应用、渠道分别管理，外部操作仍需验结果 |

来源：[Meta Muse 发布](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/)、[Muse 产品设计](https://muse.ai/blog/how-we-designed-muse)、[Muse Wonder 发布](https://about.fb.com/news/2026/10/introducing-muse-wonder-models/)、[Grok Bot 1.0](https://x.ai/news/grok-bot-1-0)、[Grok Bot 概览](https://docs.x.ai/grok-bot/overview)及 [FAQ](https://docs.x.ai/grok-bot/faq)、[OpenAI dots 发布及更新](https://openai.com/index/introducing-dots/)、[dots 公开隐私与安全 FAQ](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs)。

## 四、智能横评：看实际交付，不用底座榜代替 Agent 测试

个人 Agent 的“聪明”至少包括四件事：能理解任务与优先级、能记住并正确更新用户偏好、能从真实应用拿到当前状态、能在授权内完成并验证动作。这四件事要连起来。意图分析再好，如果选错联系人、把草稿当成已发送，实际任务仍然失败。反过来，工具很全也不能修复模型没发现日期冲突的问题。

| 产品 | micro1 PersonalAgentBench：完成 / 可信完成 | Assistant Benchmark：日常体验分 |
|:--|:--|:--|
| Linger | 未纳入，不评分 | 未见该项目有公开得分 |
| OpenAI dots | 16/20（80%） / 16/20（80%） | 8.6/10 |
| Grok Bot | 13/20（65%） / 13/20（65%） | 8.8/10 |
| Meta Muse | 11/20（55%） / 11/20（55%） | 9.3/10 |

[micro1 原始报告](https://www.micro1.ai/personal-agent-bench) 对账号状态、权限、持久上下文等给出任务完成和可信完成双口径；每题 1 个首个合格样本，20 题偏 Google Workspace，提示、连接账号与历史不完全相同。按 20 题的分辨率，每多做对一题就是 5 个百分点；这不是严格的跨用户胜率。[Assistant Benchmark 原榜](https://assistantbenchmark.com/) 是截至本文核对时的另一把尺子，覆盖日常购买、沟通、权限、主动性等，受已评分维度与测试设置影响，不能和完成率合成总分。两者给出了不同顺序，是任务、版本和评估口径不同的实证提醒。两榜都没有为 Linger 填上成绩，不能用本地吞吐或模型对标填补。

据此，**对复杂工具型工作的有根据默认选择是 dots，而不是说它对每项都赢；Muse 日常生活体验的证据并不弱；Grok Bot 最清晰的差异在共享 Team Bot 与多 Bot 分工；Linger 最值得优先验证的是本地数据闭环和成本，而不是预设其综合智能领先或落后多少。** 云侧托管的区别并不是都能 24/7 推理，而是用户电脑熄屏后仍有运行地点和任务状态；本地托管可以用常开机器提供类似可用性，但部署、更新与恢复成本转给了使用者。

## 五、如果实测，怎么分离模型、框架和部署的影响

建议做两条赛道。**产品赛道**每款用默认推荐设置与等价的应用权限，保留各自记忆和任务机制，测全链路。**归因赛道**对 Linger 固定同一运行时换云/本地模型，再固定模型、量化文件与工具权限换运行时；闭源服务不能换底座就不做伪控制。统一任务副本、输入规模、时限和判分，记录执行版本、账号地区、授权和预算。用合成账号或沙盒数据，不用私人邮箱和真实支付跑破坏性任务。

| 建议任务 | 主要验收 |
|:--|:--|
| 研发目录里从日志找性能回归，保留用户已有改动 | 原始证据、差异范围、分析正确率、重跑时间；分别测离线与有联网工具 |
| 记住一条规则，次日修订，再撤回 | 该用时能调用、撤回后不再误用；测试在不同联系人/工作区边界不泄露 |
| 邮件与日历中的优先级任务，有同名联系人且仅授权起草 | 外部账号状态与输出一致、零误发；记录漏做和不必要的确认次数 |
| 等待对方回复或文件变化，中途关掉控制端 | 唤醒是否成功、重复通知、重试或恢复后是否重复执行 |
| 多 Agent 形成一个交付稿，中途撤销外部写入授权 | 新授权是否生效、子任务是否重复和冲突、最终结果是否可查证 |

性能同时记 **冷启动/冷缓存 TTFT、暖缓存 TTFT、固定长度 decode、任务 P50/P95、可信完成率，以及每个可信完成的成本**。最后一项用总成本除以可信完成数，算上失败重试、当地电费、机器摊销、云工具费与人工复核；本地没有云 token 账单不等于系统成本为零。对 PolyStrata 同时记真实物理配置、CPU/RAM、PCIe、GPU 峰值显存、KV dtype、MTP 接受率和长 prompt 的 p95；按 [社区基准规范](https://github.com/simplexai-labs/PolyStrata/blob/main/docs/COMMUNITY_BENCHMARKS.md) 避开 prefix cache 和引擎顺序造成的偏差。

**最终判断：** Linger 公布的技术路线已经让消费机运行更大的 MoE 成为可以认真测试的选项。它现在要补的是可复现的长任务、受控动作和离线连续性证据。选个人 Agent 时，“能跑多少 tok/s”适合回答机器能否胜任；“有多少任务在授权内真的完成”才适合决定要交出多少责任。
