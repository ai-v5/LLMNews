---
title: "AI 日报｜GPT‑6.2 与 MAI Code 2 同日发布，AMD 完成 Taalas 收购"
date: 2026-11-18T07:19:00+08:00
summary: "OpenAI 与微软把智能体模型推向按任务算成本；AMD 完成专用推理芯片收购，NVIDIA 确认 Rubin 出货，Horizon 开放早期科研用户。"
section: daily
label: "AI 动态"
tags: [模型, 智能体, 推理芯片, 超算, 评测]
demo: false
sources:
  - title: "OpenAI：GPT‑6.2 Astra 与 Sol"
    url: "https://openai.com/index/introducing-gpt-6-2-astra-sol/"
  - title: "Microsoft：MAI Code 2 与 Code 2 Flash"
    url: "https://microsoft.ai/news/introducing-mai-code-2-and-mai-code-2-flash/"
  - title: "AMD：完成收购 Taalas"
    url: "https://newsroom.amd.com/news/amd-completes-acquisition-taalas-advance-ai-inference-innovation/"
  - title: "NVIDIA：2027 财年第三季度业绩"
    url: "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2027"
  - title: "UT Austin：Horizon 向早期用户开放"
    url: "https://news.utexas.edu/2026/11/17/horizon-opens-to-early-users-americas-most-powerful-academic-supercomputer-begins-serving-science/"
  - title: "Google：Gemini Tasks 免费开放与新功能"
    url: "https://blog.google/innovation-and-ai/products/gemini-app/tasks-in-gemini-free-new-features/"
  - title: "Sakana AI：JFinBench"
    url: "https://sakana.ai/jfinbench/"
---

截至 **2026 年 11 月 18 日 07:19（北京时间）**。回看过去约 24 小时；来源未披露具体时分的，保留当地发布日期。今天值得连起来看的是两件事：软件在比较一次任务究竟花多少钱，硬件在比哪种系统能以更低成本长期承接这些任务。

## 1. GPT‑6.2 Astra / Sol 发布，选型开始按任务算账

OpenAI 在 11 月 17 日发布 GPT‑6.2 Astra 和 Sol，面向 ChatGPT Work、Codex 和 API。标准 API 每百万 token 的输入、缓存输入、输出价格，Astra 分别为 8、0.40、40 美元，Sol 为 2、0.10、10 美元。OpenAI 的内部 GDPval v2 评测中，Astra 比上一代 Astra 高 6.2 个百分点，输出 token 少 22%。

**为什么重要：** token 单价和生成量可能同时下降，但这不能直接换算成端到端延迟或任务成本。实际选型应把失败重试、工具执行和最终验收放进同一账本。 [OpenAI：GPT‑6.2 Astra 与 Sol](https://openai.com/index/introducing-gpt-6-2-astra-sol/)

## 2. 微软在 Ignite 推出 MAI Code 2 与 Flash

微软 11 月 17 日推出自研的两档编码模型，并将其带到 GitHub Copilot 和 Foundry。微软称，在四项编码测试上，Code 2 平均达到 GPT‑6.1 Sol 的 98% 表现和 40% 任务成本。该成本使用了 MAI 的五折促销价；测试采用最高推理档，其中三项内部测试用 Copilot CLI 且没有子代理。

**为什么重要：** 值得对照企业代码库里哪些任务适合专用模型，尤其是常规改动与跨文件、高风险变更的分流。上述四项测试不是长期价格承诺，也没有测试同样的多代理工作流。 [Microsoft：MAI Code 2 与 Code 2 Flash](https://microsoft.ai/news/introducing-mai-code-2-and-mai-code-2-flash/)

## 3. AMD 完成 Taalas 收购，专用推理芯片进入路线图

AMD 于 11 月 17 日确认交易完成，将 Taalas 的专用推理芯片技术纳入加速器路线，与 Instinct、EPYC、ROCm 和 Helios 等平台互补。公告未披露整合后产品的性能或交付时间。

**为什么重要：** 衡量专用硅的价值，不能只看理想吞吐和功耗，还要看模型换代频率、适配成本和部署后的利用率。收购完成不是产品已经落地。 [AMD：完成收购 Taalas](https://newsroom.amd.com/news/amd-completes-acquisition-taalas-advance-ai-inference-innovation/)

## 4. NVIDIA 季度数据中心收入达 1,076 亿美元，确认 Rubin NVL72 开始出货

NVIDIA 11 月 17 日披露截至 10 月 25 日的 2027 财年第三季度业绩：总收入 1,158 亿美元，同比增长 103%；数据中心收入 1,076 亿美元，同比增长 110%。公司称 Vera Rubin NVL72 已开始出货，多家云合作伙伴已有机架运行。

**为什么重要：** 财报确认了从宣布到实际交付的进展，但没有按平台拆出 Rubin 的出货量或收入，也不能由数据中心收入反推可租集群容量。 [NVIDIA：2027 财年第三季度业绩](https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2027)

## 5. Horizon 向早期用户开放 4,000 GPU 阶段

得州大学 11 月 17 日宣布，TACC 的 Horizon 已向早期用户开放配备 4,000 张 Grace Blackwell 平台 GPU 的部分。官方列出 Quantum‑X800 InfiniBand、400 PB 全闪存、超过 12 TB/s 读取带宽；Vera CPU 部分预计 2027 年初加入。

**为什么重要：** 仿真和 AI 共用系统，不能只看 GPU 峰值。该读取数是全系统指标，不能当作并发 checkpoint 写带宽；132 PFLOPS 的 HPL 成绩也是 FP64 HPC 指标，不是大模型训练吞吐。 [UT Austin：Horizon 向早期用户开放](https://news.utexas.edu/2026/11/17/horizon-opens-to-early-users-americas-most-powerful-academic-supercomputer-begins-serving-science/)

## 6. Gemini Tasks 免费扩展，支付等操作仍有单独边界

Google 于北京时间 11 月 18 日 01:00 公布，Gemini Tasks 向美国、印度、加拿大、澳大利亚、日本、韩国的免费用户开放。支付、短信、邮件等新增动作有额外的地区、年龄和账户条件；通过 Google Pay 结账需要用户明确确认。

**为什么重要：** 这类产品的成本和可靠性不只是模型推理。长期执行还需要隔离环境、身份权限和可恢复状态；等待真人确认也必须纳入端到端体验。 [Google：Gemini Tasks 免费开放与新功能](https://blog.google/innovation-and-ai/products/gemini-app/tasks-in-gemini-free-new-features/)

## 7. Sakana AI 发布可更新的日语金融评测 JFinBench

Sakana AI 11 月 17 日正式介绍 JFinBench，从 2026 年度六类日本金融相关资格考试构造 321 道题，并评估 12 个模型。官方展示了通用榜单上接近领先模型的开放权重模型，在此测评中仍可能明显落后。

**为什么重要：** 按年度换题让评测有机会跟上法规和考试变化，但不能自动排除训练数据重合。资格考试得分也不是实际金融工作流程的合格证明。 [Sakana AI：JFinBench](https://sakana.ai/jfinbench/)
