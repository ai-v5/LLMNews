---
title: "中国与海外大模型竞争力：2.8T 参数之后，真正的差距在哪？"
date: 2026-11-23T21:47:00+08:00
layout: post
summary: "用五张可复算图拆开模型参数、算力供给、实际训练、分项智能和验收成本。中国头部已做到同档 MoE 规模，部分任务进入前沿；更大的差距出现在难任务的稳定交付、算力供给及其转化效率。"
section: explainer
label: "产业深度"
tags: [大模型, MoE, 训练算力, 模型评测, 推理成本, 开放权重]
demo: false
sources:
  - title: "Artificial Analysis：同版智能榜与基准方法"
    url: "https://artificialanalysis.ai/leaderboards/models"
  - title: "Epoch AI：累计加速器到货估算方法"
    url: "https://epoch.ai/data/ai-chip-imports-documentation/methodology"
  - title: "Microsoft：MAI Base 2 预训练报告"
    url: "https://microsoft.ai/news/frontier-pre-training-at-microsoft-ai/"
  - title: "DeepSeek：V4.1-Flash 技术报告"
    url: "https://arxiv.org/html/2609.19969v1"
  - title: "Moonshot：Kimi K3.1 Pro 模型卡"
    url: "https://huggingface.co/moonshotai/Kimi-K3.1-Pro"
  - title: "ARE-bench：科研工作目录上的任务验收"
    url: "https://arxiv.org/html/2611.14364v1"
---

**规模已经同档，供给仍不对称，智能差距要按任务看。** Moonshot Kimi K3.1 Pro 和 Microsoft MAI Base 2 都披露了 2.8T 总参数，但二者分别是后训练交付模型和基座，不能用参数去排名。Epoch AI 估计，美国收到的新增加速器标称算力约是中国的 **7.5 倍**；这个数字也不能套到任一家实验室的训练上。到了任务层，Kimi 的 Terminal-Bench 4.0 为 **67.2%**，高于 GPT-6.2 Astra Max 的 **64.1%**，而同一家评测机构的科学终端任务则是 **34.3% 对 78.1%**。把这些读数合成一个“中国落后几个月”，会丢掉最能指导研发和选型的信息。

**截面：2026 年 11 月 23 日。** 模型按研发团队归类，不按训练芯片产地、训练机房或用户所在地归类。海外前沿能力样本以美国产品为主，同时纳入法国 Mistral 的开放权重对照；样本不代表区域全量产品。“厂商披露”“独立评测”“第三方估计”“本文情景计算”分列，不用猜测填补闭源模型空白。

## 一、模型规模：参数要拆成总量、激活量、状态和重复计算

![11 个模型公开总参数与激活参数对照；Kimi 和微软各 2.8T]({{ '/assets/data/cn-global-frontier/01-model-scale.svg' | relative_url }})

| 代表模型 | 总量或可核实小计 | 每 token 激活 | 可部署性和容易误读之处 |
| --- | ---: | ---: | --- |
| 中国 · Kimi K3.1 Pro | 2.8T | 104B | [权重及定制许可证](https://huggingface.co/moonshotai/Kimi-K3.1-Pro)；[在 K3 基础上加强后训练](https://www.kimi.com/en/blog/kimi-k3-1-pro)，不代表重新从头训练了一遍 2.8T |
| 美国 · Microsoft MAI Base 2 | 2.8T | 80B | [公开基座规格](https://microsoft.ai/news/frontier-pre-training-at-microsoft-ai/)，不等于开放下载；[MAI-Code-2 卡](https://microsoft.ai/pdf/MAI-Code-2-And-MAI-Code-2-Flash-Model-Card.pdf)说明 77B 激活与额外 3B 嵌入的计数 |
| 中国 · Qwen4-Max | 2.4T 主干 + 328B N-gram 表 | 71B | [Qwen 官方发布](https://qwen.ai/blog?id=qwen4-max)；与 [Qwen3.8-2.4T-A95B](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B) 是不同版本，不把后者权重、许可或评测套给前者 |
| 中国 · 腾讯 Hy4 / Hy4 flash | 770B / 220B | 49B / 12B | [Hy4](https://huggingface.co/tencent/Hy4) 的 770B 是语言主干；[flash](https://huggingface.co/tencent/Hy4-flash) 的 220B 含 64B Engram，不能直接作逐层同比 |
| 中国 · DeepSeek V4.1 Flash | 552B 主干 + 196B Engram | 8B 预填充 / 16B 解码 | [9 月架构报告](https://arxiv.org/html/2609.19969v1)；视觉编码器和草稿模块另计；两版公开配置一致，[1017](https://api-docs.deepseek.com/news/news261017/) 是后训练修订 |
| 中国 · GLM-5.3-Flash | 320B | 18B | [MIT 权重](https://huggingface.co/zai-org/GLM-5.3-Flash)；[GLM-5.4](https://z.ai/blog/glm-5.4) 已发布，Loop Transformer 的 750B 规模实验并不补齐生产版总量、激活量、等预算分数；独立评测图暂不收录 |
| 法国 · Mistral Large 4 | 1.05T | 52B | [开放权重](https://huggingface.co/mistralai/Mistral-Large-4-1T-A52B)；52B 包含嵌入/输出部分，去掉为 49B，视觉编码器另列 |
| 美国 · Meta Muse Spark Open / NVIDIA Nemotron 3 Ultra | 816B / 550B | 42B / 55B | [Muse 定制许可、权重需同意条款](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B)；[Nemotron 官方模型](https://research.nvidia.com/labs/nemotron/Nemotron-3-Ultra/)采用 Mamba、Attention 与 LatentMoE 混合 |
| 美国 · GPT-6.2 Astra、Claude Fable 5.2、Gemini 4 Neon/Carbon、Grok 4.7 | 未披露 | 未披露 | [OpenAI](https://openai.com/index/introducing-gpt-6-2-astra-sol/)、[Anthropic](https://www.anthropic.com/claude-fable-and-mythos-5-2)、[Google](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-carbon-now-available/)、[xAI](https://x.ai/news/grok-4-7) 披露了产品、能力或架构线索，未找到相应的完整规模数 |

总量主要决定 **权重驻留、专家分片和训练状态**。假设全部常驻，2.8T 的理想原始权重体积在 BF16、8 bit、4 bit 分别为 **5.6、2.8、1.4 TB**（十进制）；不含量化比例、保留高精度层、KV、专家副本与碎片。激活量影响每 token 的矩阵工作，但它不是实际访存量：低 batch 时每个专家可能只服务很少 token，权重重用差；高 batch 时专家被覆盖得更多，会同时考验 HBM 带宽、路由不均和跨卡 All-to-All。表查找增加容量和随机访存，通常不能按同体积的密集权重乘上 (2N) 去估 GEMM；Loop 复用参数也可能增加执行次数而不增加同等权重。

**中国模型的一个可见竞争点是用结构降低同一工作负载的成本。** 以 V4.1 Flash 为例，输入与输出路径分离，prefill 的激活量只有 decode 的一半；压缩、跨层复用、FP4 KV 将厂报常驻 HBM 的全局 KV 降到 **890 字节/token**。按 100 万 token 是约 **0.89 GB 的全局 KV**，不含滑窗状态、运行时/分片开销，也不是 100 万 token 的有效记忆分数。它对长前缀、短输出、多轮复用的 Agent 有直接价值；对低命中、大输出或专家通信受限的工作负载，收益会不同。[DeepSeek 报告 §2–3](https://arxiv.org/html/2609.19969v1)

## 二、算力：到货、园区、单作业是三层证据

![Epoch AI：美国累计芯片到货占比 66.8%，标称算力占比 72.2%；中国分别 18.2% 和 9.6%]({{ '/assets/data/cn-global-frontier/02-chip-arrivals.svg' | relative_url }})

**供给层。** [Epoch AI 估算](https://epoch.ai/data/ai-chip-imports-documentation)从 2022 年到 2026 年 6 月约有 **2,740 万 H100 当量**到货，其中美国约 **1,980 万**、中国约 **260 万**（替代结构假设下中国约 **190 万–420 万**，不是同一统计模型的置信区间）。美国与中国的芯片颗数占比相除约 **3.7 倍**，算力占比相除约 **7.5 倍**。颗数到峰值能力的差额反映样本芯片构成；既不能说中国“只有 260 万张卡”，也不能把该比值视为现场 MFU、实验室租用份额或者当前库存。该方法使用销售、海关、国内生产和到货滞后假设，既非晶片序列号普查，也不是 11 月即时读数。海外机房所在国和使用方也不一定相同。

**园区层。** 同一机构的案例：[和林格尔](https://epoch.ai/data/ai-data-centers/directory/huawei-horinger)估计约 **8.1 万 H100e / 170 MW IT**，[Colossus 2](https://epoch.ai/data/ai-data-centers/directory/colossus-2)约 **111.2 万 H100e / 946 MW IT**。按点估计，13.7 倍可拆成约 **5.6 倍 IT 电力**乘以约 **2.5 倍标称 H100e/MW**。这是卫星、冷却、电力与设备配置重建，不是端到端能效；和林格尔约 **3.6 万–14.1 万 H100e** 的 90% 估算区间也提醒我们，不能用两个园区替代国家普查。[Epoch 现场方法](https://epochai.substack.com/p/what-huaweis-horinger-data-center)；[SpaceX SEC 文件](https://www.sec.gov/Archives/edgar/data/1181412/000162828026042639/spaceexplorationtechnologi.htm)将两批各约 11 万颗的已投运设备与后续扩建能力分开，也未披露 Grok-5 单作业用了多少设备。

**网络层。** [华为 Atlas 960E](https://www.huawei.com/en/news/2026/9/hc-ascend960-supernode) 4096 NPU 超节点和更大的互联设计上限、[阿里 V900](https://www.alibabagroup.com/en-US/document-2039431633571938304) 50 万卡级单集群设计能力、[微软 Fairwater](https://blogs.microsoft.com/blog/2025/11/12/infinite-scale-the-architecture-behind-the-azure-ai-superfactory/) 本地集群与跨园区 WAN，是不同层面的声明。一个同步训练作业能占多少卡，还要问 EP/CP 的实际拓扑、跨域带宽和尾延迟、故障域、整租配额、恢复时间。常见工程布局会尽量把高频 EP/CP 放入高速域，跨域放更能分层或重叠的 DP/PP；它不是所有厂家的实际布置结论。参见本站[从几台机器到几十万卡的规模推演]({{ '/2026/11/22/ai-scale-out-rocev2-veroce-ubg/' | relative_url }})。

### 能核对的训练作业

| 样本 | 明确公开的范围 | 能推导什么；不能推导什么 |
| --- | --- | --- |
| [DeepSeek-V3，2024](https://arxiv.org/html/2412.19437v2) | 671B / 37B，14.8T token，2,048 H800；主预训 266.4 万 GPU·h，含长上下文扩展和后训练的官方运行 278.8 万 GPU·h | 6ND 粗算约 3.29×10²⁴ FLOP；常被引用的 557.6 万美元按 2 美元/GPU·h 折算，不含前置研发和试验 |
| [Meta Llama 3 405B，2024](https://arxiv.org/html/2407.21783v3) | 15.6T token；论文列 3.8×10²⁵ FLOP 和超过 1.6 万 H100 | 密集模型与 V3 MoE 的活跃工作量不同；约 11.6 倍只是两个同年例子的模型 FLOP 数量级比较，不是性能或国家倍率 |
| [Microsoft MAI Base 2，2026](https://microsoft.ai/news/frontier-pre-training-at-microsoft-ai/) | 约 1.6 万 GB200、38 天、50T token；21% MFU、89% goodput，以 2.5 PFLOP/s BF16 为分母，MFU 不含重算和优化器 | 按 16,000 卡约 1,460 万日历 GPU·h；6ND 粗算 2.4×10²⁵ FLOP。若 21% 只计有效步时，则再乘 goodput，得约 2.45×10²⁵；这是量级交叉检查，不代表厂报明确给了两个指标可相乘的采样窗口 |
| [Mistral Large 4，2026](https://huggingface.co/mistralai/Mistral-Large-4-1T-A52B/blob/main/assets/technical_report.pdf) | 技报列 3,840 GB200、45 天、36% MFU、94.1% goodput | 约 415 万日历 GPU·h；使用 FP8 Tensor Core，MFU 却按 BF16 峰值归一，不能拿 36% 当 FP8 峰值利用率 |
| [美团 LongCat-2.0，2026](https://www.meituan.com/news/NN260630164005904) | 厂商披露在 5 万卡国产算力集群上完成端到端训练 | 公告给的是集群和工作流，不给同一并行阶段峰值卡数、GPU·h 与可复算 MFU；不能转用给 2.5 |
| [DeepSeek V4.1 Flash，2026](https://arxiv.org/html/2609.19969v1) | 45T 多模态预训 token 和训练架构；未披露完整 GPU·h | 两个激活数是推理前缀/解码口径，训练图含损失路径、视觉和注意力，不能任选一个填 6ND |
| [Xiaomi MiMo-V2.6，2026](https://arxiv.org/html/2610.11959v1) | Pro/Flash 预训 30T/48T；披露 RL 运行成本 Pro 260 万、Flash 90 万美元量级；单作业数千卡，未列确切卡型/卡数 | Pro 报告内开销分拆 rollout 43.8%、learner 43.5%、grader 12.7%。不是整个模型的研发开销；每步 2.7–3.7B 训练 token 也不是纯新生成 token |

[LongCat-2.5 的独立技报](https://tech.meituan.com/2026/11/02/Meituan-LongCat-2.5.html)给出了另一条更可操作的证据：在小于 80 GB 的国产加速器上，用超节点内 EP/FSDP/CP 处理长序列阶段；厂报相对 DDP 基线的 SFT 单卡吞吐提高 86%。这能说明并行方案解决的瓶颈，不能证明和其他厂商芯片的同口径比值。

这里的 6ND 是线性层主导、一次前向和两部分反向的数量级估计，N 应按**训练路径**定义；不自动覆盖注意力、嵌入、视觉、路由、重算或优化器。用于估工期时可写成「有效模型 FLOP ÷（卡数 × 峰值 × 步内 MFU × 推进率）」；若采用已经按日历时间统计的 MFU，不应再扣一遍推进率。举个纯情景：在相同 BF16 峰值、相同作业形状下，步内 MFU 由 30% 到 45%、推进率由 80% 到 95%，有效吞吐从峰值的 24% 到 42.75%，约 **1.78 倍**；不能据此把全国 7.5 倍的供给差距缩成某个实验室倍率。

微软另报告同自家持出集 BPB 和 scaling ladder 下，相对 DeepSeek-V4-Pro-Base 的等损失拟合计算优势为 **4.2–12.3 倍**。这是在微软的四组数据上、在其拟合区间内求匹配点的厂商估计；可以讨论数据质量和配方，但不能改写成训练实际账单比、助理能力倍数或两国技术倍数。与此不同，[MLPerf Training v6.1](https://mlcommons.org/2026/11/mlperf-training-v6-1-insights/) 用同一个 DeepSeek-V3/Qwen3.5-GRPO 基准比较不同芯片系统的达标时间，是可比的工程实验；并未复现这些模型历史训练的硬件与总预算。

## 三、智能：看同一评测协议，再看任务分布

![Artificial Analysis v5.0.1 代表样本：Fable 65、Astra 62、Neon 61、Sol 57、Kimi 46、Qwen4 43]({{ '/assets/data/cn-global-frontier/03-intelligence-index.svg' | relative_url }})

**综合截面。** [Artificial Analysis v5.0.1](https://artificialanalysis.ai/leaderboards/models) 的 Fable 5.2（Max，Default Fallback）65、Astra（Max）62、Gemini 4 Neon（Xhigh）61、GPT-6.2 Sol（Max）57，领先 Kimi K3.1 Pro 46 和 Qwen4 Max 43。但美国的 Grok 4.7 Xhigh 为 35，法国的 Mistral Large 4 High 为 26。在这个截面上，技术路线和推理档位造成的组内差异也很大。指数点不是正确率百分比，也不是跨版本恒定单位；没有给新模型 GLM-5.4 填上前代数值。

![六项 AA 分项：Kimi 在 Terminal-Bench 4.0 和 GDP.pdf 的观察值较高；Astra 与 Fable 在科学终端及前沿代码有明显优势]({{ '/assets/data/cn-global-frontier/04-benchmark-breakdown.svg' | relative_url }})

- **科学与复杂代码的差距较大。** 相对 Kimi，Astra Max 在 Terminal-Bench Science 高 **43.8 个百分点**、FrontierCode-AA 2.0 高 **19.9 个百分点**。前者测五域的科学工作，后者有真实仓库变更与阻塞检查；这两个点比把指数折成“几倍聪明”有用。HLE Diamond 题中含图，不能当纯文字推理。
- **终端任务有反例。** [AA 的 Terminal-Bench 4.0](https://artificialanalysis.ai/evaluations/terminalbench-4-0)有 66 项任务，固定 mini-swe-agent，每题做三次、分别按单次是否通过汇总。Kimi **67.2%**、Gemini 4 Carbon High **65.2%**、Astra Max **64.1%**，这是最高观察点，不作统计显著性宣称。同一数据集和工具不等于用了一样多的推理 token、时长或算力；也不能外推为任意代码仓都更强。
- **换 harness，差距会变。** [Search-SWE 11 月 20 日快照](https://search-swe.github.io/leaderboard/)的 47 个搜索系统构建/优化题，在 Claude Code 2.1.309 内，Opus 5.5 Max **48.4**、Sonnet 5.5 Max **38.4**、DeepSeek 1017 Max **27.6**、Kimi Pro Max **26.6**、Hy4 High **21.5**、GLM-5.3-Flash Max **16.4**。同一 DeepSeek 1017 Max 换 Codex 得 **21.1**，换 Pi 得 **18.4**；Opus 有一题引用旧版本回退，避免把分数解读成纯权重效应或成功率。
- **偏好、多模态和工作交付应分开。** [Arena 文本](https://arena.ai/leaderboard/chat/text)、[中文子集](https://arena.ai/leaderboard/chat/text/chinese)、[视觉](https://arena.ai/leaderboard/chat/vision)分别受投票者、提示分布和对战覆盖影响，不能跨榜做 Elo 减法。11 月 20 日视觉榜已有 Qwen3.8-Max 进入前十的样本，但这证明不了高风险图表抽取的回归一致性。[Epoch 的开放工作评测](https://epoch.ai/publications/how-good-are-fable-5-2-and-gpt-6-2-astra-at-real-work)也发现：综合指数领先模型在开放式实验设计、持续迭代等工作仍会掉链子。

分项来源：[Fable 对 Kimi](https://artificialanalysis.ai/models/comparisons/claude-fable-5-2-vs-kimi-k3-1-pro)、[Astra 对 Kimi](https://artificialanalysis.ai/models/comparisons/gpt-6-2-astra-vs-kimi-k3-1-pro)、[Qwen 对 Kimi](https://artificialanalysis.ai/models/comparisons/qwen4-max-vs-kimi-k3-1-pro)、[AA 方法](https://artificialanalysis.ai/methodology/intelligence-benchmarking)。结论是**美国最强样本在难科学、复杂代码和综合任务的覆盖更广；中国头部在一些明确的任务上已处于前沿**。现有公开数据不能证明训练数据、预训规模、RL 或测试时算力当中哪一项单独造成差距。同一机构的旧版综合榜、不同厂家的发布表和新版本不要拼接作国别趋势。

## 四、成本和开放生态：按单位验收成本，而非仅每百万 token

| 官方价卡，美元/百万 token | 未缓存输入 | 缓存命中 | 输出 | 口径 |
| --- | ---: | ---: | ---: | --- |
| [DeepSeek V4.1 Flash 1017](https://api-docs.deepseek.com/quick_start/pricing/) | 0.30 | 0.006 | 1.20 | 峰价；相应谷价减半 |
| [GLM-5.3-Flash](https://docs.z.ai/guides/overview/pricing) | 0.15 | 0.03 | 0.50 | 国际 USD |
| [Kimi K3.1 Pro](https://platform.kimi.ai/zh-hans) | 2.00 | 0.20 | 10.00 | 写缓存另按服务规则 |
| [Qwen4-Max](https://docs.qwencloud.com/developer-guides/run-and-scale/explicit-cache-qwen4) | 1.50 | 0.075 | 4.50 | 新加坡；显式缓存写入另计 |
| [GPT-6.2 Sol / Astra](https://developers.openai.com/api/docs/pricing) | 2 / 8 | 0.10 / 0.40 | 10 / 40 | Standard 短上下文档 |
| [Claude Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5) / [Opus 5.5](https://www.anthropic.com/claude-opus-5-5) | 2 / 4 | 0.10 / 0.20 | 10 / 20 | 短期写入另计 |
| [Gemini 4 Carbon / Argon](https://aistudio.google.com/docs/pricing#gemini-4-carbon) | 2.00 | 0.10 | 10.00 | 正常服务 11 月促销价；该表所示 12 月起价另有变化 |

不是每款国产模型都更便宜，Kimi 的短档未命中输入和输出价与 Sol、Sonnet 同档。甚至同是国内 Flash，分界也取决于工作负载。设缓存命中率为 h、输出/输入 token 比为 r，按相同已计费输入量，DeepSeek 与 GLM 的峰价差为 **0.15 − 0.174h + 0.70r 美元/百万输入**。r=2% 时，DeepSeek 需约 **94.3%** 的命中才更便宜；若使用 DeepSeek 谷价，阈值约 **7.4%**。这是账单情景，不含写入、缓存存储、重试或供应商 tokenizer 造成的 token 差，也不代表任务性能相同。

![ARE-bench 成本和整项验收：GLM 约 $0.20/30.67%，DeepSeek $0.53/39.56%，Sol $2.17/66.22%，Opus $5.69/56.89%]({{ '/assets/data/cn-global-frontier/05-task-cost-quality.svg' | relative_url }})

[ARE-bench §4.2、§4.5](https://arxiv.org/html/2611.14364v1)以 75 个恢复了文件和历史上下文的科研任务做三轮，整项通过必须满足全部适用检查项。GLM-5.3-Flash 较便宜，GPT-6.1 Sol 胜在更多任务一次交付。用「平均每次模型费 ÷ 整项通过率」算该批次每次通过约 **$0.65 / $1.34 / $3.28 / $10.00**（图中从左到右），并非同一道题反复重试的期望。Sol 使用 Codex，其他图中模型使用 Claude Code；主评委为 GLM-5.3，论文做了有限的换评委敏感性检验；DeepSeek 成本只覆盖 222 条有 token 记录的运行而验收覆盖 225 条。价格冻结于 11 月 2 日，且不含沙箱、工具、审核和返工，不应拿前一张新价卡替换论文成本。

一个可执行的系统方案是**便宜模型跑高量、有验收器的任务，把难题和不确定结果升级给更强模型**。盈亏条件可以用实测条件概率写：若第一段支出 C₁，升级条件命中率 u、升级成本 C₂，则平均模型费为 C₁+uC₂；联合通过率要用「第一段成功 + 失败后被正确升级并最终成功」，不能假设两模型失败独立。若失败被误判成通过，应将漏检计入风险成本。决策要画**固定质量与 P95 时延下的总成本曲线**，而非只看跑出了多少 token。

开放权重的竞争力在于可迁移、离线部署、量化、微调和路由接入。[DeepSeek 1017](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017) 与 GLM-5.3-Flash 提供 MIT 权重；[Kimi 权重](https://huggingface.co/moonshotai/Kimi-K3.1-Pro/blob/main/LICENSE)、[Meta Muse Spark](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B) 有定制条款；开放权重不自动包含数据与全训练配方。法国 Mistral 的万亿级权重也说明海外并非只有闭源。反过来，能下载 2.8T 权重不等于有低成本地跑它的机房。训练来源、芯片国际供应和引擎是交叉的：中国模型可在 NVIDIA、AMD 或国产加速器上服务；国产模型价低不能直接归因于国产硅。[OpenRouter 平台样本](https://openrouter.ai/data/newsletter/the-token-state-of-play)显示 2026 年 9 月前开放权重 token 份额一度到 79%，仅表示该网关的 token 消费，不是全市场收入、客户份额或实际生产部署地域。

## 五、下一轮竞争，看哪三个可验证指标？

1. **看前沿作业吞吐，不看园区卡牌。** 预训练公开卡型、卡数/并行域、训练 token 定义、有效 MFU、日历推进率与故障损失。同模型比较 p50/p99 step time，给 EP/CP 通信重叠和慢卡的消融。后训练分开测 actor 的独立生成、重 prefill、learner 的 MFU、grader 和策略陈旧度，主指标用**实际消费且有效的训练 token/秒、单位 GPU·h 带来的验收改善**，而非只追 decode token/s。
2. **看成对任务，而非最大推理档对最大档。** 固定代码起点、提示、工具白名单、验收器和时限，分别扫描预算与推理档，重复运行，记录同题配对结果、失败类型和区间。用自有中文业务、跨文件迁移、长上下文视觉和会造成真实返工的任务。保留 API 产品原生设置那一组，再测等预算同 harness 那一组；两者共同回答“该买哪个”和“差距出在哪”。
3. **看服务侧有没有把结构优势交付成 SLA。** 量化和缓存需要先做质量守门。同版模型固定输入长度、输出长度、命中率、并发分布和卡级功率，报 TTFT、TPOT、P95/P99 与验收吞吐；将 HBM 容量、单请求状态、A2A 尾延迟和电力分列。只有国内模型在同质量下真正交付了更低 TCO，或者在同 TCO 下提高了难任务通过率，算法与工程优势才算兑现。

**总判断：** 参数规模已经不足以区分中国和海外的领先者。现在最明显的供给护城河是大规模可用算力，美国最领先产品的能力护城河则是难任务的覆盖和完成稳定性；中国代表性的竞争力是高水平开放权重、对长上下文和缓存成本的设计，以及若干任务上已经可与最强产品交锋。未来的分水岭是能否用更多**有效**训练试验和更好的端到端交付，把这些单项优势变成可复现的广谱能力。

[下载五张图使用的数据与来源（CSV）]({{ '/assets/data/cn-global-frontier/chart-data.csv' | relative_url }})。各图为本站按公开读数重绘，基准会动态更新；CSV 保留数值、单位、来源和口径，不用于填补缺失值。
