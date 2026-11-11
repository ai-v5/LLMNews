---
title: "每日AI新闻｜决策模型、Qwen 预览与细胞级基因预测"
date: 2026-11-12T05:39:00+08:00
summary: "Gemini 推出封闭选项决策 API，Qwen4-Max 开始限时预览，AlphaGenome 2 开放研究 API；另看 DeepL 语音模型及 Ascend 推理优化的验证边界。"
section: daily
label: "每日AI新闻"
tags: [模型, 智能体, 科研, 语音, 推理系统, 开源]
demo: false
sources:
  - title: "Google：Gemini Decisions API"
    url: "https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/"
  - title: "阿里云：Qwen4-Max-Preview"
    url: "https://help.aliyun.com/zh/model-studio/qwen4-max-preview"
  - title: "DeepMind：AlphaGenome 2"
    url: "https://deepmind.google/blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/"
  - title: "DeepL：Aure"
    url: "https://www.prnewswire.com/news-releases/deepl-unveils-aure-its-most-lifelike-voice-ai-translation-model-yet-302935694.html"
  - title: "vLLM Ascend PR #20291"
    url: "https://github.com/vllm-project/vllm-ascend/pull/20291"
---

本期检索窗口为 **北京时间 2026 年 11 月 11 日 05:39 至 11 月 12 日 05:39**，信息截至窗口结束。筛选覆盖模型、智能体、芯片系统、开源与产业应用；收录五条具备窗口内发布、开放或实质更新事件证据的动态，不把日期不明的报道凑入清单。

## 1. Gemini Decisions API：对预设选项打分，不逐字生成答案

**事实。** [Google 推出 Gemini Decisions API](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/)，由 `gemini-decision-1` 驱动。接口针对工具选择、模型路由、规则检查等有边界的决策，可对共享的文本、图像、音频、视频或 PDF 输入，一次提交最多 1,000 个独立问题，返回候选项概率与置信度，支持是非、选择和有序评分。标价为每百万输入 token **0.10 美元**，不收输出 token 费用；每道题的指令与选项仍计入输入。

**时间证据。** 直接读取的 [Google 官方 RSS](https://blog.google/rss/)对应公告 `pubDate` 为 **11 月 11 日 18:00 UTC**，即北京时间 **11 月 12 日 02:00**。

**分析与边界。** 把“从已知选项中选择”从长文本生成中分离，可能简化智能体路由。置信度并不保证真实正确率，仍需用本地任务校准阈值和安排人工复核。厂商延迟数据有上下文长度与测试条件，不应推成所有长输入、所有问题数量下的承诺；本站未实测。

## 2. Qwen4-Max 开始限时预览，接入前要核对退役日

**事实。** [阿里云官方文档](https://help.aliyun.com/zh/model-studio/qwen4-max-preview)给出 `qwen4-max-preview` 的限时预览安排。该模型支持文本、图像和视频输入，以及工具调用与联网搜索。预览期间不做变更，结束后该模型下线；模型仅通过 Token Plan 提供，不提供按量付费。文档还提示，OpenAI Chat Completions 兼容接口中的 `max_tokens` 与 `max_completion_tokens` 等价，约束思考与最终回答的 token 总量。

**事件时间。** 文档明确预览从 **北京时间 11 月 11 日 10:00**开始，到 **11 月 25 日 24:00**结束。这里入选的是窗口内开始开放的事件，不将页面更新时间或首次提及该型号的时间当作模型首次披露时间。

**分析与边界。** 短期预览适合受控评估，生产接入需考虑停止服务后的替换路径。输出预算语义会影响最终可见回答长度，迁移时不能只沿用旧参数。本站未测试模型能力或访问资格，也不将服务预览写成开源权重发布。

## 3. AlphaGenome 2：把 DNA 变异预测细化到细胞类型和状态

**事实。** [DeepMind 公告](https://deepmind.google/blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/)介绍 AlphaGenome 2，将 DNA 序列与目标细胞类型或状态共同作为条件，预测变异对相应生物学活动的影响。官方宣布研究 API 已可用于非商业研究，商业研究则为私有预览；公告明确产品尚未验证或获批用于临床和诊断。

**时间证据。** 原网页 `article:published_time` 与 `datePublished` 均为 **11 月 11 日 15:00 UTC**，即北京时间 **23:00**；较晚的修改时间不替代发布时间。

**分析与边界。** 细胞状态条件化有助于研究者提出更具体的实验假设，但预测不是致病因果关系的最终证明。API 可用不等于模型权重已经开放，也不代表可以将个人基因检测结果直接用于诊断。本站未复现实验，不将官方评估结果视作本站验证。

## 4. DeepL 发布 Aure，语音翻译继续追求表达保真

**事实。** DeepL 在[公司新闻稿](https://www.prnewswire.com/news-releases/deepl-unveils-aure-its-most-lifelike-voice-ai-translation-model-yet-302935694.html)中推出 Aure 语音 AI 模型，重点是在实时翻译中保留说话者表达随对话变化的特征，而不只是声音身份。[DeepL 原始公告](https://www.deepl.com/en/press-release/aure-voice-ai-model)称该模型自动应用于 DeepL Voice 会议、面对面对话及 Voice API；首批支持英、德、西、法、意、日、葡、韩八种语言，不含中文。

**时间证据。** 公司发布稿标注 **11 月 11 日 03:00 ET**，即 **08:00 UTC、北京时间 16:00**。

**分析与边界。** 语气和表达会影响跨语言交流体验，但自然声音不等于语义准确；重要场合仍须核对译文与关键数字。新闻稿中的质量评价属于厂商陈述，本站未完成多语言听测。该条依据官方公告与公司发行稿的公开搜索正文核对，直接页面抓取未成功。

## 5. vLLM Ascend 优化 PR 有新测试反馈，尚不能视为正式性能升级

**事实。** [vLLM Ascend PR #20291](https://github.com/vllm-project/vllm-ascend/pull/20291)针对 DSA V4.1 的元数据处理融合。作者在[新评论](https://github.com/vllm-project/vllm-ascend/pull/20291#issuecomment-6784605293)中补充 A2/A3 正确性与算子性能结果，并获得[审阅批准](https://github.com/vllm-project/vllm-ascend/pull/20291#pullrequestreview-5852993099)，该审阅记录明确绑定下述当前提交；截至本期核验，PR 仍开放、未合并，最新提交为 `9e75feb195a5c2e8691cb3674c9b09e31c6006ed`。

**更新时间。** 新测试评论发表于 **11 月 11 日 01:49:23 UTC**，即北京时间 **09:49:23**。公开[事件时间线](https://api.github.com/repos/vllm-project/vllm-ascend/issues/20291/timeline?per_page=100)显示，其后在 **02:20:45 与 02:50:55 UTC**发生两次强制推送。新闻点是测试反馈和审阅推进，不是本日首次引入内核重写。

**分析与验证边界。** 新评论的测试结果没有明确绑定候选提交，且早于这两次推送，不能直接当作最新版已经验证的结论。[此前 A3 回退与整数精度问题的报告](https://github.com/vllm-project/vllm-ascend/pull/20291#issuecomment-6674437488)明确针对旧提交 `5474d7a`，也不能移植成最新版的失败结论。最新提交的 CPU 检查通过不等于 NPU 正确性已验证；所需精度/NPU 测试未运行，[CI 门禁因缺少测试启用标签失败](https://github.com/vllm-project/vllm-ascend/actions/runs/42948787492/job/130294950097)。作者的 eager 模式算子计时与此前图回放计时边界不同，不适合直接对比，更不能扩大为完整模型服务吞吐提升。本站未运行硬件复测。

## 编辑说明

本期以公开原始公告、官方文档和开发记录为依据，明确区分发布时刻、开放事件与代码更新。未纳入窗口外的正式版本，也未把预发布、待合并 PR 或厂商效果评价写成已普遍上线或本站实测的能力。
