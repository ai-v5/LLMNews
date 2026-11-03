---
layout: post
title: "SGLang v0.5.23 深读：长上下文、融合解码与专家分页，分别改变了什么"
date: 2026-11-04T05:47:00+08:00
summary: "SGLang v0.5.23 把长提示词尾部重放、持久融合解码与 MoE 专家分页推进到新的可用阶段。沿原始 PR 与版本代码追踪，可以看清 1.5 倍、44%、30 倍各自的实验分母，以及数值一致性、流式工具调用和 PD 配套升级的生产边界。"
section: explainer
label: "开源推理系统解读"
tags: [SGLang, 推理优化, MoE, DeepSeek, GPU, 强化学习]
demo: false
sources:
  - title: "SGLang v0.5.23 Release"
    url: "https://github.com/sgl-project/sglang/releases/tag/v0.5.23"
  - title: "PR #44403：Decoder bounded replay 默认启用与配对实验"
    url: "https://github.com/sgl-project/sglang/pull/44403"
  - title: "PR #45107：Tail graphs 扩展至 prefill graph 与 DP attention"
    url: "https://github.com/sgl-project/sglang/pull/45107"
  - title: "PR #45450：NVIDIA megakernel 路径的主机侧开销优化"
    url: "https://github.com/sgl-project/sglang/pull/45450"
  - title: "PR #44353：AMD monokernel 集成"
    url: "https://github.com/sgl-project/sglang/pull/44353"
  - title: "PR #42557：Paged Experts 设计与对照实验"
    url: "https://github.com/sgl-project/sglang/pull/42557"
  - title: "PR #45787：Paged Experts 量化格式扩展"
    url: "https://github.com/sgl-project/sglang/pull/45787"
  - title: "PR #44850：Replay 下的 prompt logprobs 支持"
    url: "https://github.com/sgl-project/sglang/pull/44850"
  - title: "PR #45075：PD attention 默认值与 KV layout 握手"
    url: "https://github.com/sgl-project/sglang/pull/45075"
---

SGLang 在北京时间 2026 年 11 月 3 日 06:14:10 发布 v0.5.23。发布说明汇总了 257 位贡献者的 1007 个 PR，涉及模型支持、推测解码、量化、缓存、多平台和服务接口。对实际部署更有价值的问题是：这些改动到底消除了哪一种开销，代价落在哪里，哪些既有假设会随升级失效？

本文聚焦三条路径：DeepSeek-V4.1 长提示词的 decoder SWA bounded replay、面向小批量解码的持久融合内核，以及让 MoE 超出显存运行的 Paged Experts。三者分别削减计算行数、算子与主机调度间隙、主机到显卡的权重搬运量，收益不能简单相加，也不能互相替代。

**本文依据 v0.5.23 Release、关联原始 PR 和该 tag 的代码。性能数字均为项目贡献者自报，本文没有 GPU 独立复测。** PR 中的实验往往早于最终版本，不能把某个开发分支上的对照实验改写成 v0.5.22 与 v0.5.23 的全面对比。版本 tag 对应提交为 `297e54fd105e974cdf401e5b4d20253a22c16f90`。

## 一、长上下文提速：先减少后段计算，再减少剩余计算的调度成本

### 1. Bounded replay 具体省掉了哪些行

Prefill 阶段处理输入 token，并为后续生成建立模型状态。长提示词中，许多层需要处理大量行；即使后续只生成一个 token，前面的准备成本也已经发生。

DeepSeek-V4.1 的 decoder SWA bounded replay 利用模型的 KV 来源层结构，在后段层只处理每个请求本次 extend 的尾部行。v0.5.23 的 `deepseek_v4.py` 把切换点设在最后一个 KV source layer：先为完整输入行写入所需的压缩 KV，再将后续计算切换到尾部。代码对结构作了约束，例如该来源层不能携带 Engram，后面的层不能再自行执行特定压缩，避免把这种优化泛化到不满足条件的模型。[模型实现](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/srt/models/deepseek_v4.py)

尾部长度来自 SWA 窗口，当前代码为 128。`late_layer_tail_layout` 对普通请求保留最近 `min(128, extend_len)` 行，并为滑窗设置绝对起点。较早的尾部行不会再读取这一边界之前的滑窗位置。因此，虽然完整输入的压缩信息仍被保留，后段层的局部依赖计算已经改变。

本版在受支持的 CUDA 配置中默认启用 decoder bounded replay，包括 PD 的 prefill 与 decode 两种角色；兼容性判断仍以启动时实际解析结果为准。

这说明了为什么它能够降低长 prefill 成本，也说明了为什么发布说明明确提醒：**bounded replay 与 full prefill 不数值等价。** “模型采用滑动窗口”本身不足以证明跨多层截断后的隐藏状态一致。这里的正确性判断必须包含任务质量、概率分布和使用场景，而不能只看最终文本是否大致相似。[尾部布局与窗口边界代码](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/kernels/ops/attention/dsv4/attn_metadata_kernels.py)

### 2. 28% 首 token 延迟下降，有清楚的实验条件

[#44403](https://github.com/sgl-project/sglang/pull/44403) 的受控实验使用同一台 4×GB300、DeepSeek-V4.1-Flash、TP4/EP4、FlashMLA、DSpark block size 5。输入是确定性的合成 token ID，关闭 EOS 提前结束，清除 radix cache，并在预热后测量。

单请求、仅输出一个 token 时：

| 输入长度 | Replay 关闭 TTFT | Replay 开启 TTFT | 延迟变化 |
|---|---:|---:|---:|
| 1,024 token | 42.89 ms | 42.92 ms | 基本不变 |
| 8,192 token | 174.50 ms | 172.54 ms | 约下降 1.1% |
| 32,768 token | 480.92 ms | 346.89 ms | 约下降 27.9% |
| 65,536 token | 974.77 ms | 700.62 ms | 约下降 28.1% |

这是客户端观察到的首 token 时间，不是单个 GPU 内核的时间。在并发 16、每次输出固定 128 token 的另一组实验里，32K 输入的输出吞吐从 256.38 增至 337.22 token/s，即 1.315 倍；其分母和单请求 TTFT 不同。

限制也需要一并保留：每种情况只做三次重复，先测关闭再测开启，没有交叉平衡顺序；实验使用保留的修复后运行环境，并非最终 PR head 的全新部署。短提示词单请求几乎无收益，并发 1K 输入的 TTFT 还从 163 ms 增至 184 ms。部署中的请求长度分布会直接影响结果。

质量证据同样不是“无损”证明。作者报告，无显式输出上限的 AIME 2026 两组均为 469/480；DeepSWE 从 78/113 变成 77/113，MMMU-Pro 从 1152/1730 变成 1147/1730。这些是有限、带随机性的样本。MMMU 两组生成长度明显不同，总耗时反而从约 7292 秒增至 8636 秒，不能拿输出 token/s 的变化替代固定工作量下的加速结论。

### 3. Tail graphs 处理的是另一层瓶颈

减少到每个请求最多 128 行后，后段层工作量变小，但如果仍逐个启动内核，主机发起调用的成本就更显眼。接续的 [#45059](https://github.com/sgl-project/sglang/pull/45059) 和 [#45107](https://github.com/sgl-project/sglang/pull/45107) 把这些尾部层组织为按行数分桶的 CUDA graphs。

实现不是简单地把完整 prefill 图反复播放。`DecoderReplayTail` 选择合适的尾部桶；较大的 prefill 图在切换点退出到真实尾部元数据，执行尾部图后再通过桥接缓冲区把结果交给后续图段。DP attention 下，各 rank 需要选择兼容的桶，空闲 rank 也参与相应执行，避免一部分 rank 运行图、另一部分走不同通信路径。[v0.5.23 尾部图实现](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/srt/models/deepseek_v4_replay_tail.py)

Release 中“最高 1.5 倍 prefill 吞吐”可追溯到 #45107：GB300、DeepSeek-V4.1-Flash、DSpark、DP4 attention + TP MoE、eager prefill、8K 输入、并发 64，吞吐从 93.7K 增至 140.9K token/s。基线是 #45059 之前的 main。另一个 TP4、breakable prefill graph 配置从 59.9K 增至 82.1K，约提升 37%；DP4 加 prefill graph 的配置则只提升约 12%。

这些数字很好地体现了瓶颈变化：同样是尾部图，原有调度方式不同，能省掉的空隙也不同。**不应把 1.5 倍再乘以 replay 的 1.39 倍，得出整套版本的累计加速。** 两组实验基线、配置和度量均不同。

图也占显存。#45059 报告，在 GB300 TP4 上，16 个桶额外使用约 2.2 GiB/GPU，且不计入原来的 KV sizing。显存已接近上限的服务需要重新检查余量；`SGLANG_DSV4_DECODER_TAIL_GRAPH_MAX_ROWS=0` 可关闭尾部图，但这与关闭 bounded replay 是两个独立的控制点。

## 二、融合解码：内核变快后，主机开始成为关键路径

### 1. 为什么小批量解码适合持久融合

小批量逐 token 解码往往难以持续填满 GPU。一个 decoder layer 中的投影、归一化、路由、MoE、张量并行归约以及下一层输入准备，形成很多短任务。某个矩阵乘法已经很快，任务之间的启动和同步仍可能占据可观时间。

NVIDIA megakernel 与 AMD monokernel 的方向，是把多个操作及部分跨卡同步纳入更连续的执行路径。NVIDIA 插件的已公开设计使用 mailbox 和 programmatic dependent launch 在内核间交接；AMD PR 描述将一个 decoder layer 的大部分工作连同 TP all-reduce 收进一到两次启动。这里的“融合”仍有形状和硬件覆盖范围，不能理解为整个模型从此只有一个万能内核。[NVIDIA 对应实验版本说明](https://github.com/sgl-project/sgl-nvidia-mega/blob/547bf4486e9/README.md)、[AMD 集成 PR](https://github.com/sgl-project/sglang/pull/44353)

SGLang 为插件提供配置检查、加载后构建和 forward 分发。受覆盖的 step 走插件，其他形状继续走标准模型路径。v0.5.23 的 NVIDIA binding 还检查不同 TP rank 的构建宽度是否一致，并确认实际捕获的 decode graphs 中确实有插件覆盖，防止“开了开关但没有任何图用到它”。[固定版本 binding](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/srt/kernel_plugins/nvidia/binding.py)

这类优化适合低并发交互，但不能仅由单用户结果推断高并发吞吐收益。批量增加后，矩阵计算、带宽与资源占用比例会变化，融合路径的优势也会改变。

### 2. NVIDIA 的 44% 是组合实验，AMD 的 75% 是另一套测试

[#45450](https://github.com/sgl-project/sglang/pull/45450) 给出了很有解释力的拆分实验。4×GB300、DeepSeek-V4.1-Flash、TP4、AgentX、并发 1、3600 秒窗口，比较相同的 220 个请求。所有组都以 main 提交 `f0b65907227` 为基础，并回退 #45421（`7d9bc104932`），以保留合成接受条件下的正常接受采样；下表“基线”因此不是未修改的 main：

| 配置 | 每用户解码速度 P50 |
|---|---:|
| 实验基线 main `f0b65907227`，已回退 #45421 | 694.0 token/s |
| 基线 + PR 前 18 项主机侧优化 | 709.7 token/s |
| 基线 + 默认 slots 的 megakernel 插件 | 762.2 token/s |
| 基线 + 全部 20 项优化 + 插件 42 slots | 995.7 token/s |

最后一行相对第一行提升 43.5%，对应发布说明中约 44% 的上限。但它同时启用了特定主机侧优化和额外插件 slots，**不是只安装 v0.5.23、保持默认参数就会得到的结果**。多项优化在最终 PR 中仍默认关闭。

实验还固定了 synthetic acceptance 为 3.51。它用于控制推测解码的接受长度，帮助比较执行开销；不能证明真实业务中 draft 与 target 的接受行为、最终答案质量也获得同等改进。PR 单独给出了真实接受条件下的质量测试，这两类证据应分开阅读。

另一个生产限制是流式尾时延：PR 报告，在 `NCCL_CUMEM_ENABLE=1` 且 `NCCL_MNNVL_ENABLE=1` 时，延迟提交 context-KV 可能使超过 256K token 的请求在最后一个流式 token 前额外停顿 45–105 毫秒；一次 AgentX 运行中为 87/209 个此类请求。上表环境未启用这两个变量，不能用表中速度排除该风险。

机制上的信号比最高数字更有价值：只有主机优化时收益约 2.3%，加上更快的 GPU 路径后，同类主机工作才明显暴露。输入准备、verify 元数据、接受结果记账、KV 提交等工作被移进图、合成更少的启动或移出关键路径。一次推理优化可能只是把瓶颈从 GPU 计算转移到了 CPU 与 GPU 的交接处。

AMD 的 [#44353](https://github.com/sgl-project/sglang/pull/44353) 则报告 MI350X、TP4、真实 DSpark 接受：单请求从 444.1 到 776.0 token/s，约提升 75%；4 和 8 个请求时，单用户速度增益约 22%。它另有强制接受长度的 AgentX 测试，P50 增益约 34.9%。不能把 AMD 的真实接受单流测试与 NVIDIA 的合成接受 AgentX 结果并排，当成硬件优劣榜。

### 3. RL rollout 的阻碍不只有数值误差

固定版本的 NVIDIA binding 明确为模型设置在线权重更新拒绝信息：捕获的内核持有从权重派生的状态，普通更新无法刷新这些状态。Paged Experts 的实现也有类似保护，原因是已驻留 GPU 的专家可能继续使用旧权重。

这对强化学习训练链路很实际。一个静态权重推理服务，可以长时间复用已构建状态；rollout worker 则可能频繁接收新策略权重。即使某个低延迟配置通过了答案质量测试，也不能据此认为它支持原有的在线权重同步流程。应验证框架如何拒绝更新、如何重建状态，以及重启成本能否被每轮采样量摊薄。

## 三、Paged Experts：用路由局部性换取更低的权重搬运量

### 1. 把专家权重做成 GPU 工作集

MoE 每层有 E 个专家，但一个 token 只路由到 top-k 个。若相邻 token 重复使用部分专家，每步把所有被 offload 的权重搬回 GPU 就会浪费带宽。

Paged Experts 为每层在 GPU 保留 K 个专家槽位，完整专家存储保存在主机内存。路由完成后，仅把本步需要但尚未驻留的专家搬入，专家计算仍在 GPU 上完成。v0.5.23 的 `LRUPolicy` 保护当前 wave 要使用的专家，并淘汰其余最久未使用的槽位；需求超过 K 时，按多个 wave 执行。[驻留与分批规划代码](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/srt/layers/moe/paged_experts/residency.py)

两条执行路径承担不同情况：

- `DeviceExecutor` 在 GPU 上决定换入计划并完成 gather，避免主机同步，适合所有路由条目能放进 K 个槽位的一波执行。
- `EagerExecutor` 在主机规划多个 wave，逐波换入并计算，再按 runner 约定完成 top-k 输出合并。

完整 decode CUDA graph 的捕获批量因此被限制在 `K // top_k` 以内。这是保守的覆盖条件：每个请求即使选到不同专家，条目总数也不会超过 K。超过该范围的批次需要走非完整图路径。[执行器](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/srt/layers/moe/paged_experts/executor.py)、[兼容性与捕获上限](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/srt/layers/moe/paged_experts/method.py)

K 同时与 KV cache 争夺显存。增大 K 可能减少专家换入，减小 K 则为更长上下文或其他驻留内容腾出空间。由此可推断，最优配置需要联合考虑请求并发、路由局部性、PCIe 带宽、上下文长度与 KV 占用，不能只看模型参数量。

### 2. “最高 30 倍”的基线尤其重要

[#42557](https://github.com/sgl-project/sglang/pull/42557) 中，30 倍来自 RTX 5070 Ti 16 GB、PCIe 5.0 x16、Qwen3-30B-A3B FP8 的单流解码：Paged Experts 约 87.7 token/s，而 SGLang `--cpu-offload-gb 18` 为 2.9 token/s。此对比说明按需换入远优于该场景下反复搬运大量 offloaded 权重。

但同一 PR 对经过调优的 llama.cpp 给出了更克制的比较。相近字节规模的 Q8_0 配置约 45.2 token/s，Paged Experts 约快 1.94 倍；两者量化格式并不相同。INT4、16 GB 显卡场景中，约 205.7 对 194.4 token/s，差距只有约 6%。原 PR 也明确修正了早先仅对比“全部专家在 CPU 计算”所夸大的优势。

短 prompt 的首 token 延迟可能更差：prefill 会触及很多专家，冷专家换入成本无法像连续 decode 那样摊薄。FP8 的短 prompt TTFT，分页约 284 ms，而 llama.cpp 的部分配置约 226–235 ms；2K prompt 时，GPU 计算优势则让分页方案占优。

小 K、高并发还可能造成反复换入。RTX 4070 Laptop 8 GB、PCIe 4.0 x8、K=26/128 的 INT4 测试中，单流分页约 30.6–32.9 token/s；4 请求输出吞吐降到约 11–12 token/s，而调优后的 llama.cpp 某配置约 41 token/s。**“模型能放进系统内存并启动”与“在目标并发下有竞争力”之间，仍需一次真实负载验证。**

### 3. 量化支持的难点在附属状态和求和顺序

后续 [#45787](https://github.com/sgl-project/sglang/pull/45787) 扩展了 AWQ、compressed-tensors、MXFP4、NVFP4、W8A8 等格式。这里重要的不只是格式列表：专家的 scale、zero point、bias 和 padding 必须与权重一起正确换入，repack 也必须能以 K 个专家为单位独立完成。

PR 报告，一个 AWQ 对照故意不换入 zero points，logprob 中位偏差从正常分页的约 0.003 nats 增至 1.67 nats。gpt-oss 的 Marlin padding 初始化也曾导致答案全被截断。最终实现从层参数推导专家张量，并增加分块 repack 独立性检查，正是为了把这些“格式支持”变成可验证的执行契约。

同样不能把“计算仍在 GPU”写成所有格式逐位一致。BF16、部分 FP8 路径在所测条件下可逐位相同；Marlin 的分块与求和行为受 batch shape 影响，某些格式存在数值容差。NVFP4 的部分支持走 Marlin W4A16，即权重量化到 4 bit、激活按 16 bit 计算，不应据此宣称获得了原生 W4A4 的全部吞吐特性。

当前版本还限定单 GPU，兼容性检查拒绝多种并行配置、推测解码与在线权重更新。主机专家存储需要足够的可锁页内存。不能把它直接视为已有多机 MoE 部署的透明替换，也不能在未测试时假定它与新 LoRA 引擎、所有融合路径自由组合。

## 四、升级时最容易漏掉的三个行为变化

### Prompt logprobs 已补齐，但数值一致性问题仍然存在

早期 #44403 文案写过 bounded replay 不支持 prompt logprobs。最终 v0.5.23 已包含 [#44850](https://github.com/sgl-project/sglang/pull/44850)：读取 prompt 行的请求在后段保留 whole extend，并恢复这些行的普通滑窗；尾部超过图容量时改走 eager。版本代码也明确实现了这一分支。[后端逻辑](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/srt/layers/attention/deepseek_v4_backend.py)

因此，不能照搬早期 PR，把新版写成完全不支持 logprobs。但“接口能够返回概率”也不足以证明 rollout 路径与 trainer 一致。Release 建议，若 RL rollout 的 logprobs 需要匹配训练端，显式传入 `--no-enable-decoder-swa-bounded-replay` 保持 full prefill；关闭之后仍应验证量化、attention backend、采样及其他路径带来的差异。

### DeepSeek 官方 codec 会改变客户端看到的协议细节

DeepSeek-V4/V4.1 chat 改用 `deepseek-recipe` 0.2.0 编码；配置对应 DeepSeek reasoning/tool-call parser 时，输出也通过官方实现解析。最终 [serving adapter](https://github.com/sgl-project/sglang/blob/v0.5.23/python/sglang/srt/entrypoints/openai/serving_deepseek_recipe.py) 比中途 PR 的实验开关描述更适合判断当前行为。

需要回归的具体事项包括：流式工具参数从整段到增量片段，首片段可含空的 `arguments`，客户端应按工具调用索引拼接后再解析 JSON；tool-call ID 改为官方格式；`developer` 消息按 system 渲染；V4 数字型 `reasoning_effort` 会返回 400；`tools` 与 `continue_final_message` 组合会返回 400。原生 `/parse_function_call` 还可能返回不在传入 `tools` 中的调用，并以 `tool_index=-1` 标记。

这些变化会影响 agent 的工具分发与历史重放。应用应继续执行自己的工具白名单和参数校验，不宜把“parser 返回了调用”当成执行授权。Release 也指出，sgl-router 与 sglang-server 暂时保留 Rust parser，因而不能只测试一个入口就认定整套网关行为统一。[编码 PR](https://github.com/sgl-project/sglang/pull/45315)、[输出解析 PR](https://github.com/sgl-project/sglang/pull/45907)、[原生端点 PR](https://github.com/sgl-project/sglang/pull/46219)

### PD 升级需要协调两端的 KV layout

DeepSeek-V4.1 在受支持 SM100/SM103 配置下，PD 两端默认采用 MegaAttention。FlashMLA 与 MegaAttention 的 KV 排布不同，仅检查 dtype 不足以确保对端能正确读取。

[#45075](https://github.com/sgl-project/sglang/pull/45075) 将 KV layout 加入握手，decode 端发现不匹配会报错。旧 decode 无法解析新增字段，因此 prefill 与 decode 应配套升级；若要保留 FlashMLA，按发布说明在两端都显式设置 `--dsv4-attn-backend flashmla`。这也是跨硬件配对时需要检查的配置。

不要把 PD 默认值推及所有聚合服务。由于 MegaAttention 的 64-head tile 在 attention TP 分片后可能产生填充开销，[#46263](https://github.com/sgl-project/sglang/pull/46263) 让相关聚合配置继续选择 FlashMLA。该 PR 还指出，不同布局的服务共享 HiCache 存储时需要特别注意：所述存储 key 不包含 layout。发布前应核对缓存隔离与兼容策略，避免仅凭模型名相同复用已有缓存。

## 五、如何把这一版变成可审计的生产收益

除了上述主线，本版还有两项值得纳入部署计划的更新。FlashInfer CUTLASS MoE 的 autotune 范围与 prefill 尺寸对齐，H200 上部分模型的 8K TTFT 自报下降 30%–58%，代价包括更长冷启动和额外工作缓冲区；这些是特定 runner 与配置的结果。[#43363](https://github.com/sgl-project/sglang/pull/43363) 还区分了新启动基线与已服务过流量的基线，说明旧版本的 tactic 状态会影响收益分母。

新 plan-driven LoRA 引擎则把 FP8、NVFP4 量化 MoE 的 adapter 服务能力向前推进。它属于显式启用的新执行路径，原始合并 PR 没有重新跑一组独立的新 benchmark。应先验证目标模型、provider、adapter 路由与图捕获组合，不能把“支持量化 MoE LoRA”扩大为所有量化格式和后端的通用兼容承诺。[#45892](https://github.com/sgl-project/sglang/pull/45892)

针对已有生产服务，较稳妥的评估顺序是：

1. **先固定语义。** 固定 checkpoint、tokenizer、完整启动参数和依赖版本，记录解析后的 backend，而不只保存启动脚本里的 `auto`。对相同请求核对 prompt token IDs、工具流、停止条件和 usage。
2. **再拆开性能变量。** 分别比较 replay、tail graphs、插件和 host 优化，保留冷/热 cache、输入/输出长度、并发、真实接受长度。至少同时记录 TTFT、ITL/TPOT、吞吐和峰值内存。
3. **单独测试训练契约。** 在 rollout 场景验证 logprob 对齐、策略权重更新和派生状态重建；答案准确率不能替代这些测试。
4. **覆盖部署边界。** 检查 PD 新旧版本组合、两端 KV layout、持久缓存隔离、启动预热时长，以及目标最大上下文和并发下的表现。

SGLang v0.5.23 展示的工程进展相当具体：长上下文可以通过有边界的后段重算减少工作，小批量解码可以压缩算子与主机间隙，MoE 可以利用路由局部性减少权重传输。它也把推理系统的评估要求推得更清楚。**真正可复用的成果，是带着配置、质量和生命周期边界的性能改善。** 对部署团队来说，把这些边界测清楚，比复述一个最大的加速倍数更有用。

## 资料范围与尚未验证部分

本文查阅日期为北京时间 2026 年 11 月 4 日，主要依据上述公开原始材料；代码链接固定到 v0.5.23，实验引用保留各 PR 自己的环境和基线。未独立验证最终发布镜像在全部硬件上的结果，也未验证真实生产 agent 长期运行、RL 训练收敛、全部功能交叉组合及各性能优化的叠加收益。上述数字应作为复现实验的起点，而非容量承诺。
