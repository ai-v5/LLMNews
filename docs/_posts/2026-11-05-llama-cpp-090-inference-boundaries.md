---
layout: post
title: "llama.cpp 0.9.0 解读：统一 KV、Gemma 4 预填充与多节点通信，三类加速各有边界"
date: 2026-11-05T05:52:00+08:00
summary: "llama.cpp 0.9.0 将多序列 KV 行索引、Gemma 4 图裁剪和 NCCL 多节点通信纳入版本更新。它们分别减少无效注意力工作、无用 token 计算和跨节点通信开销，但适用模型、并发条件及比较分母不同，不能合并成一个通用加速倍数。"
section: explainer
label: "开源推理解读"
tags: [llama.cpp, ggml, 推理优化, KV缓存, 张量并行]
demo: false
sources:
  - title: "llama.cpp v0.9.0 官方发行说明"
    url: "https://github.com/ggml-org/llama.cpp/releases/tag/v0.9.0"
  - title: "v0.9.0 Release API：published_at"
    url: "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/v0.9.0"
  - title: "同源码 nightly b12110 的发布记录"
    url: "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b12110"
  - title: "PR #29510：多序列 Flash Attention KV 行索引"
    url: "https://github.com/ggml-org/llama.cpp/pull/29510"
  - title: "PR #31356：Gemma 4 计算图优化"
    url: "https://github.com/ggml-org/llama.cpp/pull/31356"
  - title: "PR #28967：NCCL 多节点张量并行"
    url: "https://github.com/ggml-org/llama.cpp/pull/28967"
  - title: "PR #27512：OCP FP8 E4M3"
    url: "https://github.com/ggml-org/llama.cpp/pull/27512"
  - title: "PR #30881：批量张量拷贝 API"
    url: "https://github.com/ggml-org/llama.cpp/pull/30881"
  - title: "v0.9.0 对应的固定源码提交"
    url: "https://github.com/ggml-org/llama.cpp/tree/cd959bae99ff4bed22bef2604f45241c09bbb8c8"
---

llama.cpp 0.9.0 最值得研究的部分，是把推理路径中几种不同的浪费拆开处理：一个请求不必为其他序列的 KV 支付同样的注意力成本；不再产生 KV 的上层网络，不必继续处理所有提示词 token；跨进程的张量并行，可以使用后端提供的集合通信。

这些改动都可能让推理更快，但它们解决的不是同一件事。读懂版本更新，需要把**多请求吞吐、单请求提示词处理速度、生成速度和增加硬件后的扩展收益**分开。

## 版本与公开时间：新发布的是版本，不是所有底层想法

官方 GitHub Release 的 `published_at` 为 **2026-11-04 13:08:06 UTC，即北京时间 11 月 4 日 21:08:06**。这项时间证据来自 Release API，而不是 tag 创建时间或提交时间。v0.9.0 对应源码提交为 `cd959bae99ff4bed22bef2604f45241c09bbb8c8`；本文以该固定版本为准，不把之后的 nightly 改动混入。发行说明列出的配套 ggml 版本是 v0.29.0。[发行记录](https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/v0.9.0)、[版本说明](https://github.com/ggml-org/llama.cpp/releases/tag/v0.9.0)

同一源码提交的 nightly **b12110 已于 11 月 4 日 12:52:04 UTC（北京时间 20:52:04）发布**，比编号发行早 16 分 02 秒。两者都在本期窗口内；本文采用 v0.9.0 编号发行的时间标识版本更新，不把它说成该源码首次可用，也不将同一提交的 nightly 与编号发行计为两条新闻。[b12110 发布记录](https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b12110)

这是一次符合本期时间窗口的**软件版本更新**。下文分析的 PR 此前已经公开：KV 行索引 PR 于 9 月 27 日创建，NCCL PR 于 9 月 15 日创建，Gemma 4 PR 于 10 月 29 日创建。它们不是 11 月 4 日首次公开的独立研究成果。本文的新消息依据，是这些功能进入本次正式编号的发行版本。

本文做了发行说明、公开 PR 和固定源码的交叉核对，**没有在相应 GPU、手机或双节点设备上复测**。所有性能数值均为贡献者报告，重新计算的比例另作说明。

## 1. 统一 KV 的难点：共享存储后，别让请求为无关 token 买单

KV cache 保存历史 token 的 key 和 value，避免生成下一个 token 时重复计算已有状态。统一 KV cache 让不同序列在同一个缓存池内管理这些状态，但某个查询仍然只能关注属于它的有效历史。

旧路径的一个成本，是对较大的统一缓存构造稠密 mask，把其他序列的 token 排除。PR #29510 的做法是加入 `ggml_flash_attn_ext_rows`：K/V 仍然共享存储，每个 query slice 另外带一份 `kv_rows` 整数行索引，指向它实际需要的 K/V 行。接口还明确规定，负数行号代表 padding，对应 mask 必须为负无穷。[PR 说明](https://github.com/ggml-org/llama.cpp/pull/29510)、[固定版本接口定义](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/ggml/include/ggml.h#L2518-L2535)

可以把它理解为：保留一个共享仓库，但给每个请求一张紧凑的取货清单。它不是把上下文做有损摘要，也不是根据“重要性”丢弃本该参与计算的历史 token。收益来自避免对无关缓存范围做多余工作。

### 作者测到了什么

PR 的两组测试使用 RTX Pro 6000、Q8_0 模型、开启 Flash Attention 和统一 KV。每组为 **4 个并行序列，每个提示词 99,936 token、生成 64 token**，上下文容量为 400,000，batch 和 ubatch 均为 2,048。

| 模型 | 原 master 提示词总吞吐 | PR 提示词总吞吐 | 本文计算的吞吐比 | 生成总吞吐，原→新 |
|---|---:|---:|---:|---:|
| Gemma 4 26B-A4B Q8_0 | 2,982.14 token/s | 8,625.75 token/s | 约 2.89 倍 | 273.42→288.11 token/s |
| Qwen3.8-27B Q8_0 | 1,106.13 token/s | 2,778.22 token/s | 约 2.51 倍 | 90.29→102.08 token/s |

这里的分母非常重要。`llama-batched-bench` 对非共享提示词的 `S_PP`，使用**所有并行序列的提示词 token 总数除以提示词阶段耗时**。这组测试总共处理 399,744 个提示词 token，生成阶段总共计入 256 个 token。表中的 8,625.75 token/s 不是某个用户独享的生成速度，也不是首 token 延迟。[基准源码中的计数公式](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/batched-bench/batched-bench.cpp)

对应的提示词阶段耗时，Gemma 为 134.046→46.343 秒，Qwen 为 361.390→143.885 秒。生成吞吐的提升则分别约为 5.4% 和 13.1%，明显小于提示词阶段。PR 作者将结果描述为接近非统一 KV 路径的性能，同时保留统一缓存的好处；上表直接比较的仍然是 PR 与当时 master，不能改写成“超过所有非统一 KV 实现 2.89 倍”。[完整实验记录](https://github.com/ggml-org/llama.cpp/pull/29510)

### 适用边界在代码里

固定版本会探测后端是否支持该行索引路径，且该路径依赖统一 KV 和 Flash Attention；不支持时，源码注明会回到统一缓存的稠密 mask 路径。`LLAMA_KV_ROWS_DISABLE` 也可以禁用该优化，便于定位问题或做对照。[路径选择代码](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/src/llama-context.cpp#L396-L407)、[探测与回退](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/src/llama-context.cpp#L717-L723)

不能把“llama.cpp 支持某后端”直接等同于“该后端支持本项优化”。例如，这个固定版本的 SYCL 和 Vulkan 对带 K/V 行列表的操作明确返回不支持。软件整体的跨平台覆盖面，比每一项新优化的覆盖面更广。[SYCL 判断](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/ggml/src/ggml-sycl/ggml-sycl.cpp#L7655-L7657)、[Vulkan 判断](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/ggml/src/ggml-vulkan/ggml-vulkan.cpp#L15684-L15690)

## 2. Gemma 4 预填充加速：有些上层计算可以提前结束

另一项改动作用于 Gemma 4 E2B/E4B。贡献者发现，这些模型的部分上层会复用前面层的 KV，不再向 KV cache 写入新状态；但旧计算图仍让提示词中的全部 token 经过这些层。

新图在第一个共享 KV 的层之前，只留下需要输出的 token 行。在常规仅取最后位置输出的提示词处理场景里，中间 ubatch 的这些上层可以不处理 token，最后一个 ubatch 只需处理相应输出行。PR 同时简化了 per-layer embedding 投影中的缩放和数据布局。[PR #31356](https://github.com/ggml-org/llama.cpp/pull/31356)

这类优化有明确的模型结构前提。作者表示，E2B 受益最大，E4B 次之，26B 因所有层都参与 KV 写入，不获得这项层裁剪收益。

| M4 Pro、Metal、10 线程，官方 Google QAT Q4_0 | 原 master | PR | 本文计算的比值 |
|---|---:|---:|---:|
| E2B，pp512 | 1,613.78 token/s | 4,603.18 token/s | 约 2.85 倍 |
| E4B，pp512 | 805.91 token/s | 1,318.62 token/s | 约 1.64 倍 |
| E2B，tg128 | 109.65 ± 1.86 token/s | 110.98 ± 0.55 token/s | 均值约 1.01 倍 |
| E4B，tg128 | 63.39 ± 0.22 token/s | 63.62 ± 0.21 token/s | 均值约 1.004 倍 |

`pp512` 是 512-token 提示词处理测试，`tg128` 是 128-token 生成测试。生成项保留原 PR 报告的波动范围；微小的均值差不足以证明稳定的生成提速。它们的差异说明，这次改动主要减少提示词处理阶段的工作量，不能用 pp512 的倍数描述整个聊天过程。这里的基线是 PR 所报告的当时 master，**不是本文跑出的 v0.8.0 对 v0.9.0 整版回归结果**。[原始硬件、误差范围与其他长度测试](https://github.com/ggml-org/llama.cpp/pull/31356)

固定版本的门槛比“Gemma 4 都更快”更具体：裁剪逻辑要求 `n_seq_max == 1`，不处于 embeddings 输出模式，还检查相关层是否需要保留中间表示。PR 说明也将层裁剪限定于统一 KV。[v0.9.0 Gemma 4 源码](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/src/models/gemma4.cpp#L200-L231)

因此，第一节是**多序列场景的缓存访问优化**，本节的核心裁剪则有**单序列条件**。两项收益不能相乘成一个“llama.cpp 总加速倍数”。作者报告了文本、图像和音频输入输出检查，以及长提示词测试；这些是该 PR 的验证记录，不构成对所有输入和配置的等价性证明。

## 3. NCCL 多节点张量并行：先分清增加硬件和改进通信

PR #28967 为不同进程中的 rank 增加后端集合通信接口，在 CUDA 后端通过 NCCL 实现，并让 RPC server 在条件满足时使用它。引导阶段先交换建立通信所需的信息，之后集合通信在后端之间进行。[PR #28967](https://github.com/ggml-org/llama.cpp/pull/28967)、[CUDA 实现](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/ggml/src/ggml-cuda/ggml-cuda.cu#L1406-L1488)

这项改动的意义，是让跨节点 tensor parallel 有机会利用专门的集合通信能力。它不是把一次请求变成多个互不依赖的任务副本；各 rank 仍要共同完成模型计算并交换结果。

作者提供了 DGX Spark 的单节点、双节点 pairwise、双节点 NCCL 三组结果，重复参数为 `-r 3`。下面保留未增加 8,192-token 历史长度的两行，便于看清比较对象：

| 条件 | pp512 | tg128 |
|---|---:|---:|
| 单节点 | 846.54 token/s | 13.02 token/s |
| 双节点，pairwise | 961.61 token/s | 22.33 token/s |
| 双节点，NCCL | 1,348.29 token/s | 23.51 token/s |

由此计算，双节点 NCCL 相对单节点为约 **1.59 倍提示词吞吐、1.81 倍生成吞吐**。但若要隔离“从 pairwise 改为 NCCL”的收益，硬件数量应保持相同，比较结果为约 **1.40 倍提示词吞吐、1.05 倍生成吞吐**。把前一组直接写成 NCCL 的净收益，会把增加一台设备的贡献也算进去。

这组材料还有一个需要保留的核对边界：运行命令引用 `Qwen3.8-27B-GGUF:UD-Q4_K_M`，结果表的内部模型标签却显示 `qwen35 27B Q4_K - Medium`。本文不替作者猜测标签差异的原因。复现时应锁定实际 GGUF 文件及哈希、源码提交、NCCL 构建配置和互联条件，而不能只照抄模型简称。公开测试也不足以证明更多节点上的扩展效率。[原始三组测试](https://github.com/ggml-org/llama.cpp/pull/28967)

源码还显示，所有 rank 都具备后端 communicator 时才走该路径；否则使用旧 pairwise 路径，而这一回退只覆盖两个 rank。NCCL 对应函数受编译选项控制。这是一个有能力探测、构建条件和回退限制的实现，不是任意机器组网后就会自动获得同样收益。[RPC 协商与双 rank 回退限制](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/ggml/src/ggml-rpc/ggml-rpc.cpp#L2338-L2387)

## 4. 其余更新如何看：格式、接口和模型支持分开验收

v0.9.0 还引入 OCP FP8 E4M3 数据类型及相应模型文件类型，采用饱和模式。原 PR 明确把 KV cache、CUDA/Vulkan 支持和尺度处理拆到其他工作中。因此，“新增 FP8 类型”只说明这一层接口与表示发生了变化，不能凭这一项就认定每个后端的完整 FP8 推理路径都已覆盖，更不能推导模型质量不变。[FP8 PR](https://github.com/ggml-org/llama.cpp/pull/27512)

新的 `ggml_backend_tensor_set_n/get_n/copy_n` 则面向一批张量的拷贝。Metal 和 CUDA 实现了对应批处理钩子；其他后端可以回到旧二维路径或逐张量操作。它还被用于 context 的保存和加载。这里的价值是减少数据搬运调用和实现上的重复，但这份 PR 没有给出可以写成通用速度承诺的端到端倍数。[批量拷贝 PR](https://github.com/ggml-org/llama.cpp/pull/30881)

发行说明列出的模型支持包括 Clover 的 AR 模式、Limite、Metis-1.6 和 Mistral Large 4，也增加了 Chatterbox TTS、Nemotron 3.5 Transcribe 等音频相关能力。支持某个架构或接口，是升级理由之一；模型文件兼容性、实际可用功能和资源需求仍须按目标模型验证。[完整发行说明](https://github.com/ggml-org/llama.cpp/releases/tag/v0.9.0)

## 我们的分析：值得升级测试，但先按瓶颈选择验证项

这一版本的共同方向，是让软件更准确地表达“哪些工作真的有必要”。统一缓存的容量管理与注意力的访问范围可以分开，模型层结构可以成为裁剪计算图的依据，跨节点通信也可以交给专门后端处理。

对部署者，最有用的不是把三张性能表合成一个标题数字，而是对照自己的瓶颈：

1. **长提示词、多并发请求**：核对 KV 行索引路径是否实际启用；同时测总吞吐、每请求首 token 延迟及尾延迟，保留相同缓存配置和请求长度分布。
2. **Gemma 4 E2B/E4B 单请求交互**：分开记录提示词处理与生成阶段。若业务要求 embeddings、中间层表示或多序列运行，先确认裁剪条件是否仍满足。
3. **双节点部署**：用同一模型文件比较单节点、双节点旧通信与双节点 NCCL，并记录网络和构建配置。新增硬件后的速度增长，还要与成本、功耗和运维复杂度一起看。
4. **调用 C/C++ API 或依赖音频接口的应用**：先做编译、接口和功能回归，再讨论性能。新类型、新 API 和后端原生支持是不同验收项。

以上是基于公开代码和测试设计的分析建议。**未知的仍包括本文环境中的实际收益、完整业务请求分布下的尾延迟、更多节点的扩展曲线，以及跨模型和跨后端的普遍效果。**这些问题应由固定版本、固定模型和可复现负载回答，不能由发行说明中的“加速”二字替代。
