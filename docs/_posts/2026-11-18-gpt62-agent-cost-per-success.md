---
title: "GPT‑6.2 深度解读：做成一件事，到底要多少钱？"
date: 2026-11-18T07:24:00+08:00
summary: "把 GPT‑6.2 的降价、输出 token 减少和任务通过率分开算，再用同一批任务比较全 Astra、全 Sol 和 Sol 升档三条路线。"
section: explainer
label: "智能体系统"
tags: [GPT-6.2, 智能体, 推理成本, 模型路由, 缓存]
demo: false
sources:
  - title: "OpenAI：GPT‑6.2 Astra 与 Sol 发布，2026‑11‑17"
    url: "https://openai.com/index/introducing-gpt-6-2-astra-sol/"
  - title: "OpenAI API：价格与不同服务层的计费"
    url: "https://developers.openai.com/api/docs/pricing"
  - title: "OpenAI API：GPT‑6.2 Astra 计费详情"
    url: "https://developers.openai.com/api/docs/models/gpt-6.2-astra"
  - title: "OpenAI API：GPT‑6.2 Sol 计费详情"
    url: "https://developers.openai.com/api/docs/models/gpt-6.2-sol"
  - title: "Agents’ Last Exam：原始榜单与方法"
    url: "https://agents-last-exam.org/leaderboard"
  - title: "OpenAI API：Prompt Cache Diagnostics"
    url: "https://developers.openai.com/api/docs/guides/prompt-caching/diagnostics"
---

资料核验截至 **2026 年 11 月 18 日 07:24（北京时间）**。

GPT‑6.2 发布页同时给了三种不同信号：每百万 token 的价格、某些评测用掉的 token、以及产物通过验收的比例。三个数都重要，但不能混在一起。对编码和长任务，我会先比较每个**通过验收**的任务究竟花了多少模型费、多少时间、多少人工，再决定默认用 Sol 还是 Astra。

## 1. 降价和少生成，会同时生效，但不是同一件事

以下是公开 API Standard 短上下文价格，单位为美元／百万 token。不同服务层、长上下文加价、缓存写入和工具另计，不代表订阅配额。

| 模型 | 未命中缓存的输入 | 命中缓存的输入 | 输出 |
|---|---:|---:|---:|
| GPT‑6 Astra | 10.00 | 1.00 | 50.00 |
| GPT‑6.2 Astra | 8.00 | 0.40 | 40.00 |
| GPT‑6.1 Sol | 2.00 | 0.10 | 10.00 |
| GPT‑6.2 Sol | 2.00 | 0.10 | 10.00 |

[API 价格表](https://developers.openai.com/api/docs/pricing) · [Astra](https://developers.openai.com/api/docs/models/gpt-6.2-astra) · [Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol)

在 OpenAI 的内部 GDPval v2 评测里，6.2 Astra 比 GPT‑6 Astra 高 **6.2 个百分点**，输出 token 少 **22%**；6.2 Sol 比 6.1 Sol 高 **5.3 个百分点**。若按 Standard 单价把 22% 的用量变化折算到**输出费**，比例是 `0.8 × 0.78 = 0.624`，即低约 38%。它既不是整单降幅，也不是实测线上账单，更不能由此推出 GPU 生成速度提高 38%。[发布与评测说明](https://openai.com/index/introducing-gpt-6-2-astra-sol/)

例如，一次假想的模型调用有 20,000 未缓存输入、80,000 缓存输入、10,000 计费输出。不计工具、缓存写入和重试：

| 假想计费场景 | 输入费 | 输出费 | 合计 |
|---|---:|---:|---:|
| GPT‑6 Astra，10,000 输出 | $0.280 | $0.500 | $0.780 |
| GPT‑6.2 Astra，10,000 输出 | $0.192 | $0.400 | $0.592 |
| GPT‑6.2 Astra，假设输出降至 7,800 | $0.192 | $0.312 | $0.504 |

从第一行到第二行只改价格，从第二行到第三行才改用量。同一例子中，如果 6.2 Astra 的 80,000 输入 token 从缓存命中变成未命中，光这一项就多 **$0.608**；比这例子中输出缩短省下的 $0.088 多得多。它说明长任务值得采集实际缓存明细，但不代表缓存一定是每种任务的最大开销。

## 2. 先别把不同智能体运行方式排成一张榜

OpenAI 发布页引用 Cognition 的 FrontierCode 2.0：两者都用 max 档时，Sol 与 Astra 相差 0.5 分，成本约为后者五分之一。它支持一个**值得测试的假设**：有些真实仓库的改动，不必一开始就派最贵模型。它不证明 0.5 分以内适用于更久的跨工具工作、不同仓库，或要求识别故障并主动报告阻碍的任务。

[Agents’ Last Exam 的原始榜单](https://agents-last-exam.org/leaderboard)是另一种口径，允许模型在自己的运行框架中执行，运行时间不包含环境准备和评估；OpenAI 发布页还提示某竞品在使用后备模型的部分任务被排除。它适合描述交付系统在某个设定中的表现，不适合从两列分数倒推出同框架下的模型差距或纯 decode 速度。比较时，先检查任务集合、通过标准、失败是否进入分母以及工具和后备规则。

## 3. 怎么试 Sol → Astra，而不是先假定它省

先在同一组任务上配对跑三种策略：**全 Sol、全 Astra、Sol 先做后按验收信号升级 Astra**。保留相同仓库版本、沙箱、测试与工具权限；预先确定超时、重试、升级条件和人工审核规则。升级可以由测试失败、实测与要求不一致，或模型明确报告信息不足触发；不要只靠模型的自评信心。

- **主要指标：** `总成本 ÷ 按同一规则验收通过的任务数`，分子保留失败尝试、后备、工具和可计量的审核成本。并列报告通过率和任务墙钟 P50/P95；把超时占比另列，别只统计按时完成的好样本。
- **路由诊断：** 记升级率、升级前沉没成本和升级后成功数，再抽查“没升级但实际做错”的样本。低价模型若经常把错误包装成完整交付，低升级率反而可能是风险信号。
- **运行诊断：** 按回合记未缓存／缓存输入、计费输出、工具等待和缺用量回执的超时。API 返回的 `cached_tokens` 才能证实缓存用量；不要假定换模型可复用先前缓存。若对比调整推理档，可在支持配置下保持原始前缀，用追加式设置控制变量；这不是 6.2 首创，也不保证命中。[缓存诊断文档](https://developers.openai.com/api/docs/guides/prompt-caching/diagnostics)

一个便于做初筛的期望成本式：`每个分配任务的路由成本 = Sol 首轮平均成本 + 升级率 × 被升级任务的 Astra 后续条件平均成本 + 额外审核/调度开销`。再除以这套策略的通过率，才得到每个通过任务的成本。这里 Astra 后续费只对被升级的难题取平均，不能拿全量任务的均价替代。举例说，若每个已分配任务先花 $0.20，30% 升级，每次升级条件均值 $0.80，调度和审核平均 $0.05，分配成本是 $0.49；若 85% 通过，每个通过任务约 $0.58。**所有输入数值都是演算假设**。如果业务要求通过率至少 90%，它即使比全 Astra 便宜，也不应该上线。

**我的取舍：** 先用 Sol 承接测试能明确判定结果、失败易回退的任务；对不可逆变更、验收难或长链路返工昂贵的任务，直接把 Astra 作为试验基线。最终由同一套任务的通过率、端到端尾延迟和每个验收通过任务的成本来决定路由，而不是由最高跑分或最低 token 单价决定。
