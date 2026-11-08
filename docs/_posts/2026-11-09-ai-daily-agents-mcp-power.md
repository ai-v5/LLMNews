---
title: "每日AI新闻｜桌面智能体、MCP 连接与供电布局"
date: 2026-11-09T05:31:00+08:00
summary: "Open WebUI 引入桌面伴侣，Activepieces 更新 MCP 连接，LiteLLM 与 llama.cpp 修复运行链路；FT 披露供电设备交易。"
section: daily
label: "每日AI新闻"
tags: [智能体, 开源, 推理系统, 数据中心]
demo: false
sources:
  - title: "Open WebUI v0.13.1"
    url: "https://github.com/open-webui/open-webui/releases/tag/v0.13.1"
  - title: "Activepieces 0.93.0"
    url: "https://github.com/activepieces/activepieces/releases/tag/0.93.0"
  - title: "LiteLLM v1.108.3 LTS"
    url: "https://github.com/BerriAI/litellm/releases/tag/v1.108.3"
  - title: "llama.cpp b12208"
    url: "https://github.com/ggml-org/llama.cpp/releases/tag/b12208"
  - title: "FT：Anthropic 发电设备交易报道"
    url: "https://www.ft.com/content/41bf5c6a-9735-4f1a-a8e3-2bcccad58ba0"
  - title: "Piper Sandler：OnePWR 交易记录"
    url: "https://www.pipersandler.com/investment-banking-transactions/onepwr-solutions-20260901"
---

本期检索窗口为 **北京时间 2026 年 11 月 8 日 05:31 至 11 月 9 日 05:31**，信息截至窗口结束。核查覆盖模型、智能体、芯片与推理系统、开源和产业应用；仅保留五条有明确增量的动态，不用旧闻补足数量。GitHub 版本时间以下述 API 的 `published_at` 为准，不混用提交或标签时间。

## 1. LiteLLM 1.108.3 LTS：修复大体积 MCP 返回和重复审核

**事实。** [官方发布说明](https://github.com/BerriAI/litellm/releases/tag/v1.108.3)列出三项修复：MCP 工具结果超过 1 MiB 时可能出现 SSE 流提前结束；模型级 `post_call` guardrails 对同一响应检查两次、重复调用审核提供方；Bedrock 部署把 `api_base` 设为空字符串时请求报错。MCP 问题被注明自 v1.103.0 起存在。本版是在昨日 1.108.2 之后新增的 LTS 补丁。

**发布时间。** 北京时间 11 月 8 日 06:29:58（UTC 11 月 7 日 22:29:58）；[版本 API](https://api.github.com/repos/BerriAI/litellm/releases/tags/v1.108.3)标记为非预发布版。

**分析与边界。** 使用网关传输较大工具结果的智能体应用值得优先回归测试；重复审核修复可能减少无效请求，但实际费用和延迟变化取决于部署。以上是维护者说明，本站未运行升级测试，也不将修复等同于模型能力提升。

## 2. llama.cpp b12208：让 Top-K 并列候选的选择更可复现

**事实。** [b12208 发布记录](https://github.com/ggml-org/llama.cpp/releases/tag/b12208)收录 CUDA/Metal radix Top-K 确定性更新（[PR #31084](https://github.com/ggml-org/llama.cpp/pull/31084)）。维护者指出，Metal 原先以原子计数器收集候选，阈值处存在并列值时，顺序乃至入选子集会受到线程调度影响；修改采用确定性的排名与写入机制，并启用 Metal 后端的确定性自检。

**发布时间。** 北京时间 11 月 8 日 23:47:03（UTC 15:47:03）；[版本 API](https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b12208)标记为 **预发布版**。

**分析与边界。** 这是推理基础算子的可复现性改进，有助于定位并列值引起的运行差异；不能推出整套模型生成已完全确定，也不是全后端、全形状的性能承诺。PR 还明确指出，CUDA 在 CCCL 3.4.3 及以上版本的单行或双行输入仍走 DeviceTopK，并列选择仍可能不确定。相关 PR 讨论与发布记录包含不同硬件上的性能回退与后续调整，本站没有复测，因此不引用单一加速百分比。

## 3. FT 披露 Anthropic 发电设备交易：新的是报道，不是签约日期

**报道事实。** 《金融时报》11 月 8 日报道，Anthropic 在 9 月底以约 **34 亿美元**取得 OnePWR Solutions 的 **1.7 GW 燃气发电机采购承诺**；[路透社同日报道](https://www.reuters.com/business/energy/anthropic-secures-34-billion-generator-deal-ai-data-centers-ft-reports-2026-11-08/)也将消息归因于 FT，未独立核实该报道。本期将其作为新披露报道收录，不写成今日新签合同或已投运电源。

**原始佐证与限制。** 交易顾问 [Piper Sandler 的公开记录](https://www.pipersandler.com/investment-banking-transactions/onepwr-solutions-20260901)列出 2026 年 9 月、34 亿美元的 OnePWR 发电平台出售交易，买方只写“一家前沿 AI 实验室”，并未点名 Anthropic。这能佐证交易规模与月份，不能独立证明报道中的买方及全部设备细节。FT 与路透全文未能直接读取，报道信息依据公开索引核对；未取得合同或 Anthropic 的直接确认。

**发布时间。** FT 与路透报道均为 2026 年 11 月 8 日，属于本期窗口内的新披露；顾问交易记录对应 9 月，不作为今日新公告。

**分析。** 若报道属实，算力扩张的竞争进一步涉及供电设备交付，而不止芯片数量。设备采购承诺不等于可用电力，实际部署仍取决于工程、许可、燃料和交付条件。

## 4. Open WebUI 0.13.1：桌面伴侣 Tether 与编码智能体入口

**事实。** [官方版本说明](https://github.com/open-webui/open-webui/releases/tag/v0.13.1)引入面向 macOS、Windows 和 Linux 的 Tether 桌面伴侣，将本机文件、仓库和工具连接到 Open WebUI。在提供智能体的 Open Terminal 上，Claude Code、Codex、Pi 等可以出现在模型选择器中。版本还增加默认关闭的自动工具权限模式：审核模型评估工具请求，无法完成审核时请求批准。

**发布时间。** 北京时间 11 月 8 日 19:07:53（UTC 11:07:53），[版本 API](https://api.github.com/repos/open-webui/open-webui/releases/tags/v0.13.1)标记为非预发布版。

**分析与边界。** 这使聊天界面进一步接近执行工作台，但“接入本机”也扩大了可操作范围。自动审核会把工具、参数及最近消息送往配置的评分 API，部署者需评估数据边界。发布方另提示本版含安全修复，细节待 CVE 分配后公开；本站未做安全审计或客户端实测。

## 5. Activepieces 0.93.0：补齐 MCP OAuth2 与批量操作审批

**事实。** [官方发布记录](https://github.com/activepieces/activepieces/releases/tag/0.93.0)加入 MCP 客户端 OAuth2 支持，并调整连接页面、增加五个 AI 客户端入口；修复列表还包括聊天在批量操作改变数据前请求批准，以及部分 OAuth2 连接刷新问题。

**发布时间。** 北京时间 11 月 8 日 22:30:22（UTC 14:30:22），[版本 API](https://api.github.com/repos/activepieces/activepieces/releases/tags/0.93.0)标记为非预发布版。

**分析与边界。** 对自动化平台而言，连接认证和写操作审批与模型选择同样重要。这些是版本记录所述功能与修复，不代表对所有 MCP 服务的兼容性保证；自托管升级还应先检查项目的破坏性变更说明并回归现有工作流。

## 编辑说明

本期没有核实到足以纳入的窗口内重磅模型或新芯片发布，这不代表这些领域没有更新。聚合页面上的刷新日期不能替代原始发布日期；例如 [OpenAI 官方更新日志](https://developers.openai.com/api/docs/changelog)将 Agents API 自动审核列在 10 月 30 日、Live API 外呼 SIP 列在 11 月 2 日，因此不把它们作为 11 月 8 日新功能重报。
