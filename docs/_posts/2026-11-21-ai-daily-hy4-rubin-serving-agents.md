---
title: "AI 日报｜Hy4 正式权重开放，TensorRT-LLM 接入 Rubin，智能体运行时补齐状态管理"
date: 2026-11-21T05:32:00+08:00
summary: "五条可核实的新进展：Hy4 发布 BF16、FP8 与 Base 权重；TensorRT-LLM 1.3 带来 Rubin 预览和后端迁移；Codex CLI 与 Hermes 更新远程执行、线程状态及提示缓存管理，OpenAI 发布药物化学推理基准。"
section: daily
label: "AI 动态"
tags: [开源模型, Rubin, 推理系统, 智能体, 性能工程]
demo: false
sources:
  - title: "Tencent Hy4 官方模型卡"
    url: "https://huggingface.co/tencent/Hy4"
  - title: "TensorRT-LLM v1.3.0"
    url: "https://github.com/NVIDIA/TensorRT-LLM/releases/tag/v1.3.0"
  - title: "Codex CLI 0.171.0"
    url: "https://github.com/openai/codex/releases/tag/rust-v0.171.0"
  - title: "Hermes Agent v0.23.3"
    url: "https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3"
  - title: "OpenAI MedChemBench 公告"
    url: "https://openai.com/index/introducing-medchembench/"
---

本期检索截至 **北京时间 2026 年 11 月 21 日 05:32**，观察窗口为此前 24 小时。本期保留五条，不用旧模型发布或新闻聚合页的刷新日期凑数。GitHub 项目按 Release 的 `published_at` 计时，不把更早的代码提交日期当作版本发布日期。

今天最值得关注的是：**大模型的竞争正在进一步落实到可部署权重、低精度执行路径，以及能长期运行而不丢状态的智能体基础设施。**

## 1. Hy4 正式版开放权重：从 API 能力走向可独立验证的部署对象

**公开进展日期：11 月 20 日北京时间。本次核验的三个官方权重仓库提交分别在当日 11:05:49、11:05:53、11:05:54 更新；这是仓库版本时间，不冒充精确上线时刻。本次增量是正式版权重，不是此前已上线的 API，也不是 Hy4 flash。**

腾讯官方发布了 **Hy4、Hy4-FP8 和 Hy4-base**。模型卡给出的语言骨干为 770B 总参数、每 token 激活 49B；另有视觉编码器和 3.3B 的 DFly2 草稿模型。Base 是预训练模型，不能直接当作指令聊天版替代品。模型使用 **Tencent Hy License**，不能因“开放权重”就写成 Apache 2.0。[官方模型卡](https://huggingface.co/tencent/Hy4)、[FP8 权重](https://huggingface.co/tencent/Hy4-FP8)、[Base 权重](https://huggingface.co/tencent/Hy4-base)。

这次最有工程价值的细节是 **DFly2 复用主模型对应层的 KV 和稀疏索引**。官方描述中，每个草稿层使用索引器选出的约 2K 个位置，不单独维护一套草稿 KV；在 PD 分离中，草稿模型不参与 prefill。这提供了研究长上下文投机解码增量成本的对象。注意这属于架构设计，当前 SGLang 的 DFly2 部署路径不支持 P/D 或上下文并行，KV 要用 BF16；允许 FP8 权重不等于允许 FP8 KV。[SGLang 部署说明](https://docs.sglang.io/cookbook/autoregressive/Tencent/Hy4)。[DFly2 与部署说明](https://huggingface.co/tencent/Hy4#dfly2-for-speculative-decoding)。

**我们的判断：**下一步应在相同硬件、输入/输出长度和并发下，对照 BF16 与 FP8、开启与关闭草稿模型，报告准确率、接受率、每请求延迟和每卡吞吐。49B 激活参数只能帮助估算计算量，不能代替 770B 总权重的容量预算；“草稿不额外维护 KV”也不等于草稿权重和执行本身没有成本。本期没有运行这些权重，不能把模型卡的设计说明当成独立性能复测。

## 2. TensorRT-LLM 1.3：Rubin 支持进入公开版本，迁移成本与性能路径同样重要

**发布时间：11 月 20 日 10:45，北京时间；版本 v1.3.0。**

NVIDIA 的新版本加入 **Rubin SM107 预览支持**，并说明已在 Vera Rubin 上验证；同时列出 DeepSeek-V4、Kimi K3 等模型支持。对低精度系统设计更关键的增量包括：Rubin NVFP4 MoE 默认采用 uGPU locality，把访存尽量留在各 GPU die 本地；增加 MXFP8 W8A8 linear/MoE、DSA FP4/FP8 decode 内核；通过 Marlin 提供可在 Hopper/Ada 上执行的 NVFP4 **W4A16 权重低精度路径**。[官方 Release](https://github.com/NVIDIA/TensorRT-LLM/releases/tag/v1.3.0)。

这里必须区分两件事：**能够加载 NVFP4 权重，不代表所有硬件都获得原生 FP4 乘法吞吐；增加低精度内核，也不代表任意模型端到端均可保持精度并等比例加速。** 应分别核对权重存储、激活精度、实际选中的算子后端、HBM 流量与质量变化。

另一个重要变化是迁移：该版本**移除了 TensorRT 后端及旧 C++ Executor/runtime API，PyTorch 成为唯一后端**，旧的 `trtllm-build` 等路径不能照搬。RL 方面增加返回逐 token 专家路由的 Router Replay，以及运行中的权重更新支持。这些是减少训推衔接成本的接口基础，不是发布说明已证明的 RL 收敛或吞吐收益。

**我们的判断：**这是值得建立独立回归分支的大版本，不宜仅因版本号升级就替换生产环境。官方仍列出部分 NVFP4、PD 分离和 FP8 KV 配置的已知问题；评估应同时覆盖质量、稳定性、迁移后配置一致性和性能。Rubin 支持仍须保留“预览”限定。

## 3. Codex CLI 0.171：远程执行和子代理可观测性进入同一工作台

**发布时间：11 月 20 日 08:44:47，北京时间；稳定版本 rust-v0.171.0。**

官方 Release 将终端工作台默认打开，可在主对话旁查看文档、图片和子代理记录；新增 `codex exec --remote <ADDR>`，可在已有 app server 上启动或恢复非交互会话，并提供终端内的远程控制入口。模型目录加入 GPT-6.2 Sol/Astra，但这不是新的模型首发。[官方 Release](https://github.com/openai/codex/releases/tag/rust-v0.171.0)。

比界面变化更重要的是几项状态修复：切换或恢复会话时保留草稿、排队输入和中断输入的线程归属；更换工作目录时保持权限配置；避免上一轮的迟到完成事件取消新一轮审批；在执行中调整方向时保留较早编辑的累计差异。

**我们的判断：**多智能体工具不能只看同时开了多少 worker，还要看能否追溯谁改了什么、输入属于哪条线程，以及旧任务事件会不会污染新任务。此版提供的是更完整的控制与观察界面，并非“多 agent 自动提高正确率”的证明。对远程环境仍需独立配置访问权限；有远程入口不意味着可以省略安全边界。

## 4. Hermes Agent 0.23.3：缓存生命周期开始成为常驻智能体的显式机制

**GitHub 发布时间：11 月 20 日 08:34:38，北京时间。Release 正文标注 November 19，两者是日期口径差异，本期采用可核对的 UTC 发布时间换算。**

项目把上一版以来的大批变更打包为稳定发布，并注明完整整理后的说明将在 v0.24.0 给出。当前说明已列出提示缓存生命周期管理：长工具调用期间的缓存预热、在一小时缓存到期前压缩闲置会话、`cache_ttl` 默认采用自动选择；同时提到压缩时归档被移除的工具结果，以及默认开启的主动工具结果裁剪。[官方 Release](https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3)。

**我们的判断：**常驻 agent 的费用不只由模型单价决定，还取决于工具等待、空闲间隔、缓存命中与上下文压缩。预热会消耗资源，压缩也可能损失任务信息，因此不能直接推出“默认更便宜”。更合理的对照是：单位成功任务成本、缓存命中 token 比例、恢复任务延迟，以及归档信息能否被准确找回。

版本说明还区分了交付渠道：CLI、Store、容器与安装器桌面版不一定在同一时间得到同一批更新。因此看到 GitHub 新标签时，不能自动推断已经安装的桌面应用同步具备全部能力。

## 5. OpenAI 发布 MedChemBench：把药物化学推理拆成可评分的环节

**公告日期：11 月 20 日，按原始公告日期，未用推测填补具体时刻。**

[OpenAI 公告](https://openai.com/index/introducing-medchembench/)把 99 道基于公开研究的问题拆成结构识别、证据推理、候选排序和性质预测。在厂商报告的 xhigh 设置下，GPT‑6.2 Astra 获得 84.5% 的可得分值，GPT‑6 Astra 为 83.3%；这是含部分得分的基准成绩，不是答对题目的比例，也不是对新药成功率的估计。

**我们的判断：**拆分结构识别和性质预测，能看出模型到底是在读图、解释已知实验还是预测新结果时掉链子。题目来自公开文献，不能据此证明模型对未来未见实验同样有效，也没有替代前瞻验证。

## 今日判断

优先级上，**先看 Hy4 权重与 TensorRT-LLM 1.3，再看两个智能体运行时更新**。前两项提供新的模型与执行路径，后两项处理长期运行中的状态、缓存和远程控制问题。

共同的验证原则是：**能下载不等于能高效部署，支持一种精度不等于使用对应峰值算力，能并发执行不等于能可靠完成任务。** 性能评估最终仍应回到固定质量目标下的成本、吞吐、延迟和故障恢复。
