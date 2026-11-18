---
title: "混元 Hy4 深度解读：Flash 省在什么地方？六款模型的架构、显存和任务成本对比"
date: 2026-11-18T10:46:00+08:00
summary: "对照混元 Hy4 Preview、正式版和 Flash，以及 DeepSeek V4.1 Flash、GLM-5.3-Flash、Kimi K3.1 Pro。拆开激活算力、权重驻留、上下文状态及 API 账单，区分公开配置、厂商口径与不可推定的性能。"
section: explainer
label: "模型架构与推理系统"
tags: [混元, DeepSeek, GLM, Kimi, MoE, KV Cache]
demo: false
sources:
  - title: "腾讯：Hy4 Preview 官方模型规格"
    url: "https://github.com/Tencent-Hunyuan/Hy4-preview/blob/main/README_CN.md"
  - title: "腾讯：Hy4 正式版发布"
    url: "https://www.tencent.com/tencent-launches-hy4-joining-the-ranks-of-the-worlds-leading-open-source-ai-models/"
  - title: "腾讯：Hy4 Flash 正式发布"
    url: "https://www.tencent.com/zh-cn/tencent-launches-hy4-flash-to-power-high-speed-cost-efficient-ai-deployment-for-everyday-workflows/"
  - title: "DeepSeek V4.1 Flash 技术报告"
    url: "https://arxiv.org/html/2609.19969v1"
  - title: "DeepSeek V4.1 Flash 1017 模型卡"
    url: "https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017"
  - title: "智谱：GLM-5.3-Flash"
    url: "https://z.ai/blog/glm-5.3-flash"
  - title: "月之暗面：Kimi K3.1 Pro 模型卡"
    url: "https://huggingface.co/moonshotai/Kimi-K3.1-Pro/blob/main/README.md"
  - title: "腾讯云 TokenHub 中国站价格"
    url: "https://cloud.tencent.com/document/product/1823/130055/"
---

**混元 Hy4 Flash 真正值得跟进的是，它同时改了专家计算、长上下文状态和生成长度。** 腾讯披露 224B 总参数、12B 激活、其中 64B 是 Engram，称 KV cache 降至 Hy4 的 1/6。这个比例说明的是缓存容量，不代表 HBM 流量、首 token 延迟或成本也都缩到 1/6。和另外三家对照，DeepSeek 把 prefill 与 decode 的激活规模拆成 8B 和 16B；GLM 把大部分层改成固定大小的线性注意力状态；Kimi 也走混合注意力，但把节省下来的预算用于 2.8T / 104B 的旗舰路线。

截至 2026 年 11 月 18 日，三款混元中只有 **Hy4 Preview** 有可下载的官方权重和逐层配置。正式版与 Flash 的 API 已上线；腾讯宣布发布或计划开源，但本文未发现两款的可下载官方权重、逐层配置或 Flash 完整技术报告。下文把可复算的规格与厂商声明分开，不用 Preview 的细节填正式版或 Flash 的空格。

## 六款模型放在同一张表里

| 模型 | 参数口径 | 注意力、专家与特殊结构 | 上下文与输入 | 权重与复现 |
| --- | --- | --- | --- | --- |
| **Hy4 Preview** | 主干 770B / 49B；另有 MTP 10B / 0.7B | 78 层（1 dense + 77 MoE），256 路由专家选 8、另加 1 共享；Gated DSA + IndexCache；4 路 iHC | 1M；文本 | Apache-2.0；[BF16](https://huggingface.co/tencent/Hy4-preview)、[FP8](https://huggingface.co/tencent/Hy4-preview-FP8) 与配置 |
| **Hy4 正式版** | 腾讯云公布 770B / 49B；视觉与 MTP 未找到分列口径 | MoE；扩大预训练和后训练规模，新增视觉理解与电脑操作，逐层细节未核实 | 1M；图文 | API；权重和系统卡已预告，未核实到公开下载 |
| **Hy4 Flash** | 224B 含 64B Engram；12B 激活 | 混合注意力、LatentMoE、Engram；层表、专家路由与量化细节未公开 | 1M；图文 | API；权重计划公开，未核实到下载 |
| **DeepSeek V4.1 Flash 1017** | 552B 主干、另有 196B Engram；prefill 8B / decode 16B 激活 | 20 层因果 encoder + 20 层 decoder；384 路由专家选 6、另加 1 共享；CSA2 跨层复用、FP4 主 KV、局部 SWA、有界重放 | 1M；图文 | [MIT 权重与配置](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)；1017 是后训练小版本 |
| **GLM-5.3-Flash** | 320B / 18B 激活 | 45 层 = 34 KDA + 11 DSA；前 3 层 dense，288 路由专家选 8；4 路 mHC | 1M；智谱 API 支持图像与视频等输入 | MIT；[FP8](https://huggingface.co/zai-org/GLM-5.3-Flash)、[BF16](https://huggingface.co/zai-org/GLM-5.3-Flash-BF16) |
| **Kimi K3.1 Pro** | 2.8T / 104B 激活 | 93 层 = 69 KDA + 24 Gated DSA；LatentMoE，896 路由专家选 16、另加 2 共享；401M 视觉编码器 | 1,048,576；原生多模态 | [MXFP4 权重 / MXFP8 激活](https://huggingface.co/moonshotai/Kimi-K3.1-Pro)；Kimi K3.1 Pro 自有许可证 |

首发时间属于不同版本：混元 Preview 8 月 28 日、正式版 11 月 4 日、Flash 11 月 16 日。DeepSeek 的 V4.1 架构是 [9 月 10 日](https://api-docs.deepseek.com/news/news260910/)公布，10 月 17 日[更新权重与后训练](https://api-docs.deepseek.com/news/news261017/)。GLM 指 8 月 26 日发布的 **5.3-Flash**，不是旗舰 5.3 或更快的 FlashX。Kimi K3.1 Pro 于 10 月 24 日首发，官方权重随后公开；本文价格用标准档，不是 K3，也不是 HighSpeed API。

## 混元三版：从可复现的架构到可见的产品取舍

**Preview 可以算到每层。** [公开配置](https://huggingface.co/tencent/Hy4-preview/blob/main/config.json)给出 hidden 6144、专家中间维度 2048，Q/KV latent 秩 2048/512，64 个注意力头。Gated DSA 的 indexer 用 32 个 128 维 query head 对历史位置筛选，注意力每个 query 取最多 2048 个位置；IndexCache 则把选出的索引跨层复用，减少部分层重复打分。它减的是**重算索引**，不是把每层 MLA 的历史 K/V 都缩成只存 2048 个位置。长上下文瓶颈至少有三项：要留存多少位置、索引要扫多少历史、选中位置如何从 HBM 读取。4 路 iHC 多了残差状态和层间混合；权重压缩和投机解码也不会消掉这部分成本。

一个可复算的容量例子：仅对 Preview 的 MLA 主缓存，按每层每 token 一个 512 维 KV latent 加 64 维 RoPE key、均用 BF16，不做复制，逻辑容量为 `78 × (512 + 64) × 2 = 89,856 B/token`；1,048,576 token 约 **87.75 GiB/序列**，不含 indexer、page 元数据、对齐和工作区。这是单副本全层的逻辑预算，不是单卡、不是实际后端的 HBM 占用。DSA 稀疏选择和 indexer 复用不能直接拿来除掉这个容量，除非部署实现改变缓存表示或留存规则。

**正式版的变化主要是训练和任务范围。** 同为 770B / 49B 的公开口径，不代表 checkpoint 完全同构。视觉输入引入视觉编码、投影和额外 token；电脑操作更依赖多轮工具、截图和长任务状态。测正式版时，应把视觉预处理、模型 prefill、工具执行和最终验收分开。不能从 Preview 的公开权重或部署吞吐推断正式版。

**Flash 对应三条独立数据路径。** 混合注意力改变 context 增长时的 KV 或状态容量；LatentMoE 在更窄表示里做专家计算，存在减少专家 GEMM 或 token dispatch 字节数的机会，但是否能少传数据取决于投影是在发送前还是接收后、共享分支如何布置、以及实现是否真的用窄格式跨卡。占总参约 28.6% 的 64B Engram 则把一部分知识容量变成条件查表：应单列查表字节、热点命中率、请求批内复用和 host↔device 流量，不能认为它不占任何内存。单按参数数估算，64B 表在 8-bit/4-bit 情景分别是 **64/32 GB**，未计 scale、索引和副本；这也不代表腾讯的 Engram 实际使用该精度或放在主机。

腾讯还披露了 Hy4 自蒸馏、RL 后典型任务输出长度降低 50%，以及 4-bit、megakernel、DFly 优化下的 **150+ tok/s**。这三个方向分别减少生成 token 数、每步代价和服务内开销，不能把 150+ 当成独立测试、每卡速度或高并发吞吐。用一个理想例子说明差别：如果 decode 原占端到端时间一半，而输出减半、其他耗时和 token 速率不变，那么任务只会快 1.33 倍。公开资料未给出足够的卡型、卡数、上下文与 batch 条件；WorkIndex 的单任务成本比较也仅限腾讯的任务集和价格假设。

## DeepSeek、GLM 和 Kimi：三条不同的长上下文路径

**DeepSeek V4.1 Flash 对输入和输出使用不同的计算预算。** CED 在 prefill 端面向长历史，用更轻的 encoder 激活路径；decoder 的全局注意力复用 encoder 末端的缓存，生成端仍维持更大的激活预算。CSA2 跨层共享 KV、索引键和选中索引，FP4 进一步压缩主缓存。报告中的 **890 B/token** 对应常驻 HBM 的全局 KV 口径，按 1,048,576 token 折合约 **0.87 GiB/序列**，不含全部局部状态、权重和运行时开销。其“约 1/4 HBM 全局 KV”和“约 1/8 持久 KV”均对比自家 V4 Flash；后者含 SWA 有界重放，以激活/重算换避免长期保存局部 KV。不能把 0.87 和 Preview 的逻辑例子直接做部署显存倍率。1017 同架构小版本有自己的[同表对照](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)：例如 Terminal-Bench 4.0 在 Claude Code harness 下由 31.2 到 42.3，不应拼接不同 harness 的成绩。

**GLM-5.3-Flash 把增长型 KV 限定在少数层。** [官方配置](https://huggingface.co/zai-org/GLM-5.3-Flash/blob/main/config.json)是 34 KDA + 11 DSA，hidden 4096；DSA 的 KV latent 为 512、索引 Top‑2048，并配置 index pooling。KDA 用随序列更新的递归状态，decode 时每序列的该部分状态不随历史长度线性增长；但短序列高并发下，状态读写、并行复制和 chunk/prefill 内核都可能主导。衡量该方案不能只看“每 token KV”，至少要保留 **每序列固定状态 + 每 token 增长状态** 两个桶。[智谱 API 文档](https://docs.z.ai/guides/vlm/glm-5.3-flash)还规定有思考强度档，比较时需要固定档位。

**Kimi K3.1 Pro 验证了同类方法在旗舰规模上的用途。** 相比 K3，69 层 KDA 保留，原有的 24 层 Gated MLA 改为 Gated DSA；Top‑2048 约束选中值的读取，但可能仍需做索引打分。896 选 16 + 2 shared、专家 latent 3584、FFN 中间维 3072。大批量时触及的不同专家数会迅速增加，单 token 只用 104B 并不能推出整副本只读 104B 权重。模型公开的是通过量化感知训练得到的低精度权重；即便 MXFP4，2.8T × 0.5 B ≈ **1.4 TB** 也只是所有参数理想 4-bit 裸值预算，不是实际文件体积或运行时显存。[月之暗面技术文章](https://www.kimi.com/en/blog/kimi-k3-1-pro)披露 K3.1 Pro 自 K3 出发做大规模联合 RL，适合用作质量上限参照，不该作为 Flash 的同价位对手。

## 在同一个 API 平台算账

下面用 [腾讯云 TokenHub 中国站目录价](https://cloud.tencent.com/document/product/1823/130055/)统一使用广州地域的人民币口径，不混用原厂美元、国际站、订阅和临时促销。DeepSeek 用原厂直供路由的空闲 / 高峰两档，Kimi 用标准档。最后一列是一个固定 token 账单：**20k 未命中输入 + 80k 命中输入 + 10k 输出**；不含缓存写入、工具和重试。部分测试服务实际输出包含思考 token，应按账单对应计费字段取数。

| 模型 | 未命中输入 ¥/M | 命中输入 ¥/M | 输出 ¥/M | 例：每次成本 ¥ |
| --- | ---: | ---: | ---: | ---: |
| Hy4 Preview | 6 | 0.3 | 18 | 0.3240 |
| Hy4 正式版 | 6 | 0.3 | 18 | 0.3240 |
| Hy4 Flash | 0.5 | 0.02 | 2 | 0.0316 |
| DeepSeek V4.1 Flash 1017（空闲 / 高峰） | 1 / 2 | 0.02 / 0.04 | 4 / 8 | 0.0616 / 0.1232 |
| GLM-5.3-Flash | 0.8 | 0.23 | 2.8 | 0.0624 |
| Kimi K3.1 Pro | 13 | 1.3 | 68 | 1.0440 |

固定用量下，Hy4 Flash 约为 Hy4 的 **1/10.3**；腾讯内部任务集的 1/20 是另外一组真实任务、生成长度和评测假设，不与本表冲突。TokenHub 另列 Flash 至 11 月 30 日 12:00、Hy4 正式版至 12 月 31 日 23:59:59 的五折优惠，均为北京时间，不能用作长期预算。作为一个调度边界，如果每次尝试的 token 账单固定，Flash 不通过后只升级一次 Hy4，那么先试 Flash 的期望费用在 `Flash 首次验收通过率 > 0.0316/0.324 ≈ 9.8%` 时低于总是直接跑 Hy4。这个阈值仅比较 **token 成本**，假设升级任务的账单及质量不变，不代表双跑的延时、工具风险或质量可接受。有复杂状态修改的任务，应避免把失败后升级等同于无副作用重试。

**能力数据单看评测方版本。** [Artificial Analysis v5.0.1](https://artificialanalysis.ai/models/releases) 同口径快照中，[Kimi K3.1 Pro 46、Hy4 正式版 35](https://artificialanalysis.ai/models/comparisons/tencent-hy4-vs-kimi-k3-1-pro)，[DeepSeek 1017 Max 33、High 29、GLM-5.3-Flash 28](https://artificialanalysis.ai/models/comparisons/deepseek-v4-1-flash-1017-vs-glm-5-3-flash)。未核实 Hy4 Flash 与 Preview 的同版本成绩，不拿旧版本指数或腾讯内部 WorkIndex 拼成六款统一名次。上述结果来自面向不同推理强度的端点，不能代表同成本或同延迟条件下的质量。

**Flash 已有应用层对照。** [Plotly 的数据分析测试](https://plotly.com/blog/hy4-flash-plotly-data-analytics-bench/)里，Flash 答对 39/43，正式版 42/43；全套费用分别为 $0.13 和 $2.11，单题中位时间 29 秒和 117 秒。这个样本里 Flash 约快 4 倍、费用约为 1/16，但少答对 3 题，而且 Flash 的输入缓存命中约 88%。这是特定任务、端点和缓存条件下的观测，不能当作等质量加速或每卡算力结论。

## 性能建模该量什么

1. **驻留容量和读写流量分账。** 容量分权重、Engram、全局 KV、局部 KV、递归状态、工作区和复制因子；Decode MBU 用实测 HBM 读写字节 / 活跃解码时间 / 标称带宽，另报含排队和空转的墙钟口径。Flash 的 1/6 只属于第一类中的 KV，不能替代后者。
2. **把算力与通信按阶段拆开。** Prefill 记录实际输入 token、TTFT 与 context cache hit；decode 在相同 batch、输入长度和输出配额下测 TPOT、每卡吞吐、专家 HBM 字节和 EP all-to-all。长上下文再单测 indexer 打分、稀疏 gather、KV / 状态迁移。混合注意力不要以传统全注意力的单一 CP 带宽公式代替，LatentMoE 不要用 hidden 宽度猜线上 dispatch 负载。
3. **用同样的验收线算任务账。** 同一工具集合、思考档、最长输出与缓存预热条件，分 8K、64K、256K 和 near-1M，记录首轮成功率、重试/升级率、P50/P95 完成时间与每个验收任务的总费用。今天做自部署对照，选配置可复算的 Preview、DeepSeek 1017、GLM 或 Kimi；做 API 对照，优先测 Hy4 Flash 对 GLM 和 DeepSeek，复杂长程任务再与 Hy4、Kimi 两个旗舰档交叉对照。

后续最值得等的不是另一张榜单，而是 **Hy4 Flash 层表、Engram 分层和 150+ tok/s 的测量条件**。有了这三项，才算得清它把多少成本从算力与 HBM 移到了查表、链路和服务调度，进而判断哪些优化值得移植。
