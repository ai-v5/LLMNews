---
layout: post
title: "Kimi K3.1 Pro 与 zero-mismatch 解读：把推理做快，也把训练真正对齐到推理"
date: 2026-11-05T10:00:00+08:00
summary: "从稀疏注意力、缓存与并行，到 KDA 批不变、MoE 归约、LoRA 同步和失配诊断，拆解 K3.1 Pro 的推理与 RL 工程。结合固定源码与 Day-0 PR，区分 vLLM、verl、Megatron、SGLang、Miles 的具体工作、交付状态和验证边界。"
section: explainer
label: "推理与强化学习"
tags: [Kimi, vLLM, 稀疏注意力, 强化学习, zero-mismatch, LoRA]
demo: false
sources:
  - title: "vLLM：Kimi K3.1 Pro Day-0 支持，2026-11-04"
    url: "https://vllm.ai/blog/2026-11-04-kimi-k31-pro"
  - title: "zero-mismatch K3.1 案例与实验结果，固定版本"
    url: "https://github.com/Inferact/zero-mismatch-rl/blob/abdcc241b847fc97da03e5fc05bc7c897a795de2/cases/kimi-k3.1/README.md"
  - title: "verl K3.1 训练配方，固定版本"
    url: "https://github.com/Inferact/zero-mismatch-rl/blob/4a177e27f6714942af695ab6de938aa55f540679/examples/grpo_trainer/run_k31_true_on_policy_preview_megatron.sh"
  - title: "vLLM K3.1 数值对齐实现，固定版本"
    url: "https://github.com/Inferact/zero-mismatch-rl/tree/5735778f43f7d94108d432706dc5b17765bf723a"
  - title: "Megatron K3.1 训练实现，固定版本"
    url: "https://github.com/Inferact/zero-mismatch-rl/tree/8dd1d2bcb8561380c0341391ecd5d1bda9a55380"
  - title: "debugging-mismatch 公开诊断指南，固定版本"
    url: "https://github.com/Inferact/zero-mismatch-rl/tree/abdcc241b847fc97da03e5fc05bc7c897a795de2/skill/guides/debugging-mismatch"
  - title: "vLLM K3.1 Pro GPU 模型适配 PR #65685"
    url: "https://github.com/vllm-project/vllm/pull/65685"
  - title: "SGLang K3.1 Pro cookbook，固定版本"
    url: "https://github.com/sgl-project/sglang/blob/bf40ca98f4287347ec8d19662aa390eacc253a1e/docs/cookbook/autoregressive/Moonshotai/Kimi-K3.1-Pro.mdx"
  - title: "Miles 模型适配与 LoRA RL 配方 PR"
    url: "https://github.com/radixark/miles/pull/4667"
---

Kimi K3.1 Pro 的这次发布，可以沿着两条线阅读：**推理系统如何少读数据、少做重复工作；强化学习系统如何确保生成轨迹的策略，就是训练时计算概率的策略。**前者影响服务成本与交互速度，后者影响训练信号是否可信。

两条线又在同一个地方相遇：kernel。矩阵乘法、缓存量化、专家归约和线性注意力的执行方式，既决定速度，也决定浮点计算实际得到的概率。模型参数相同，只是对齐的起点。

本文依据 2026 年 11 月 4 日的 [vLLM 发布文章](https://vllm.ai/blog/2026-11-04-kimi-k31-pro)，以及 11 月 5 日核查的 Inferact 开源案例和固定源码。**没有进行 GB300 集群复测**；实验数值均为项目方报告，公式推导和工程判断另行说明。本文讨论的是 K3.1 Pro 的推理与 LoRA RL，不据此评价它在所有任务上的模型能力排名。

## 一、先建立一张系统地图

理解这项工作的关键，是把三种不同的“稀疏”分开。

| 结构 | 在系统中承担什么角色 | 容易误解的地方 |
|---|---|---|
| KDA 线性注意力 | 用递推状态承载历史信息 | 状态递推的数学等价，不保证不同 kernel 的浮点结果相同 |
| MLA 加 DSA 索引 | 先筛选历史位置，再访问选中位置的 latent | 筛选器仍须扫描历史，不能把全流程写成与上下文长度无关 |
| MoE | 每个 token 只激活部分专家 | 活跃计算较少，不意味着全部权重无需驻留或调度 |

发布材料给出的模型规格是：**93 层中 69 层 KDA、24 层 MLA；后者加入 top-2048 DSA 索引。总参数 2.8T、激活参数 104B；896 个专家中每 token 激活 16 个，支持 1M 上下文。**这些规格来自发布方，不是本文独立测量。[架构与公开数据](https://vllm.ai/blog/2026-11-04-kimi-k31-pro#whats-new-in-kimi-k31-pro)

从工程角度看，这是一个必须同时管理**逐 token 的历史缓存、逐请求的递推状态、分布式专家权重**的模型。只把注意力 kernel 换快，未必能让整个系统获得相同比例的收益。

## 二、稀疏注意力减少的是“每一步读取多少历史”

### 2.1 为什么先做一个小索引有价值

长上下文生成时，新 token 的 query 需要从已有历史中获得信息。如果每次都读取所有位置的完整 latent，历史越长，显存带宽压力越大。DSA 的做法可以理解为两级访问：先用较小的 key 做筛选，再读取入选位置的较大 latent。

这类设计的收益来自两个宽度之间的差距，而不是“历史消失了”。以发布材料的 FP8 口径为例，索引 key 含尺度为 **132 字节**，MLA latent 为 **576 字节**，选中位置上限为 **2,048**。因此，设历史长度为 N，并暂不计输出、元数据和缓存重用，本文得到一个简化读流量模型：

```text
稠密 MLA：576 × N
DSA：    132 × N + 576 × min(N, 2048)

当 N ≥ 2048：
DSA / 稠密 MLA ≈ 132/576 + 2048/N
               ≈ 22.92% + 2048/N
```

在足够长的上下文下，这个比值趋近 23%。**这是特定注意力层、特定格式的近似读取字节比例，不能直接倒数后宣称整个模型快 4.36 倍。**索引打分、top-k、稀疏 gather、MoE、KDA、通信和调度都仍然需要时间。[字节口径与机制](https://vllm.ai/blog/2026-11-04-kimi-k31-pro#sparse-attention-in-k31-pro)

这个公式还揭示了两个部署判断：上下文较短时，固定 top-k 的完整 latent 读取项占比更高；上下文很长时，索引扫描自身又成为不可忽略的线性成本。因此，“做了稀疏注意力”并不自动解决所有长度下的延迟问题。

### 2.2 exact 必须说明相对于谁

这里至少有两层不同的精确性：

- **选中集合上的注意力计算**：可以精确计算该稀疏模型所定义的注意力。
- **分布式 top-k 的合并**：可以与对同一组索引分数做全局 top-k 得到相同结果。

两者都不能推导出“与原来的全量 dense attention 输出相同”。DSA 本来就是模型所采用的筛选机制；量化索引 key 也可能改变分数与入选集合。迁移格式之后应测试质量和路由稳定性，而不是仅检查 kernel 是否跑通。

## 三、容量和带宽不是同一个优化目标

有一个看似反直觉的结果：**增加索引之后，每一步读取的字节可以减少，但要保存的状态反而可能增加。**因为 latent 没有消失，旁边又多了一份历史索引。

可以把长上下文系统的资源账分成三本：

1. **持久状态账**：模型权重、所有仍活跃请求的 KV、KDA 状态。
2. **工作区账**：prefill、通信、量化和 CUDA graph 等执行路径的临时或预留内存。
3. **传输账**：每个生成步读写多少字节，跨 GPU、跨 prefill/decode 实例传输多少字节。

减少第三本账，不一定减少第一本；给通信增加工作区，甚至可能牺牲一点可缓存 token 数换取更低延迟。这也是不能只看“模型显存占用”的原因。

### 3.1 混合缓存为何需要重新组织

逐 token 的 MLA latent、索引 key 和逐请求的 KDA 状态大小不同。若强迫所有层使用相同的大页，较小对象可能被 padding 浪费；若每一类都独立管理，调度和传输又会碎片化。

发布方案采用按 block 打包多种状态的布局。其工程意义是把**物理分配单元**和 **kernel 需要的逻辑页**分开：分配器管理连续块，计算入口通过映射得到自己需要的地址。这种做法也有利于 prefill/decode 分离时合并传输。[缓存布局](https://vllm.ai/blog/2026-11-04-kimi-k31-pro#a-kv-cache-for-three-kinds-of-state)

我们的分析是：对混合模型，缓存已经不只是 attention 的私有实现细节，而是调度、前缀复用、抢占恢复与跨实例搬运共同依赖的接口。增加一种递推状态或改变量化格式，都可能要求重新检查这些生命周期。

### 3.2 “能放下多少个 1M 请求”不能当作并发性能

原文的[容量交互图](https://vllm.ai/blog-assets/interactive_pages/kimi-k31-kv-capacity.html)说明，测量使用 8×GB300、dummy weights、`max-model-len=1M`、`max-num-seqs=64`；“contexts fit”由引擎报告的 KV token 容量除以上下文长度得到。并发上限还单独受 `max-num-seqs` 约束。

所以，这类数值回答的是**缓存预算允许装多少历史**，不是“这么多个真实会话同时运行时，每个都能获得目标速度”。真实容量验收还要加入权重加载方式、工作区、请求长度分布、KDA 状态、前缀共享和碎片等条件；性能验收则需要另跑延迟和吞吐测试。两者都应使用最终生产配置。

## 四、并行的难点：把省下的计算留住，别又花在通信上

### 4.1 Prefill 为什么不能只按 head 切

MLA 的 latent 被多个 head 共享。如果按 head 分工，每张卡只有少量 head，却重复读取整份历史，那么设备数量增加并不等于这部分工作均匀减少。轻量索引若也被重复执行，重复开销会更显眼。

按 token 分工的思路，是让每张卡处理部分 query 位置和完整 head 集合，再将结果搬回其他模块需要的布局。它用两次布局交换，换掉多份重复计算。因果注意力不同位置的历史长度不同，还必须让各设备的 query 工作量尽量均衡。

这里可以得出一个通用判断：**模型的并行布局不必从头到尾保持一致。**某个子模块在布局 A 更快，另一个在布局 B 更快时，是否值得转换取决于节省的计算能否覆盖通信，而不是某一种并行策略名称是否更先进。

原文在 **8×GB300、真实权重、单请求、340K prompt** 下报告 token-sharded prefill 的 TTFT 从 **15.89 秒到 9.42 秒**。这是端到端首 token 时间对照；它与原文其他单层 attention 微基准不能互换。[测试条件](https://vllm.ai/blog/2026-11-04-kimi-k31-pro#prefill-shard-the-attention-by-token-not-by-head)

### 4.2 DCP 把历史切开，也引入全局选择问题

当 KV 按 token 分散到不同卡，每张卡只能看到自己的历史片段。对稀疏注意力而言，局部排名还不够，需要确定全局入选位置。

一个常见的通信优化思想，是先交换少量候选，再检查是否遗漏本应入选的元素，必要时补发。**“平均情况下少传”必须与“最坏情况下仍正确”同时成立。**否则减少流量可能以改变注意力集合为代价。vLLM 发布方案在这一步保留了检测与补发机制。

这里的取舍很明确：历史分片使多卡显存更有效地承载长上下文，但多了每层跨卡协作。低并发、缓存本来就够的场景，额外通信未必划算。部署者应同时比较 TP 与 DCP 的容量、TPOT 和尾延迟，而不是只比较容量倍数。

原文的 **4.1–4.3 倍 DCP prefill 改善是单层 attention 口径**；fused decode 在 **DCP8、32K 上下文、单并发**时报告 TPOT **11.48→5.96 ms**。二者不能相乘，也不能推广成所有请求的统一收益。[DCP 与 decode 数据](https://vllm.ai/blog/2026-11-04-kimi-k31-pro#long-context-decode-context-parallelism-with-a-sparse-indexer)

### 4.3 投机解码与 AgentX 要用两种证据看

投机解码把“昂贵模型串行生成多个 token”改成“便宜模型提出候选，昂贵模型批量验证”。净收益取决于候选接受长度、验证成本、batch 与请求长度，而不只取决于草稿 token 数。

发布材料的 DSpark preview 在 **GSM8K、temperature 1.0、top-p 0.95、7 个 draft token** 下报告平均接受长度 **4.597**，并在 **8×GB300、TP8、batch 1** 下报告约 **3 倍 decode 加速**。

但 AgentX 图采用的是 **synthetic acceptance length**。它用于控制接受率条件、观察服务系统的性能前沿，不能写成真实 agent 任务上已经自然获得相同接受率的端到端结果。图中“每用户速度”与“每 GPU 总吞吐”还属于不同指标，前沿的最快交互点和最高吞吐点也不是同一个配置。尤其应保留原图的 total tokens/s 定义，不把总工作负载吞吐直接改称输出生成速度。[DSpark 与 AgentX 原始说明](https://vllm.ai/blog/2026-11-04-kimi-k31-pro#speculative-decoding-with-dspark)

我们的判断是：把真实采样接受率曲线与服务调度曲线分开，是阅读这组结果的最低要求。用于业务决策时，再把它们放回同一组真实请求中联合测量。

## 五、zero-mismatch 究竟在消除什么

### 5.1 相同权重不代表相同的实际策略

强化学习的 rollout 引擎根据当前策略生成回答，并保存生成 token 的 log-prob。训练器随后对同一轨迹重新计算概率，用来构造策略更新。

理想情况下，同一权重版本、同一 token 前缀在两个引擎中应给出相同概率。但实际部署中，推理可能逐 token 解码、连续批处理、读取量化 KV；训练可能将整段序列打包成大矩阵，使用不同 attention 和归约 kernel。浮点加法不满足结合律，执行顺序变了，结果就可能变。

对 MoE 和 DSA，误差还可能越过离散 top-k 的边界。两个很接近的分数交换顺序，就会选择不同专家或不同历史位置。误差不再只是最后一个小数位，而可能变成后续计算路径的变化。

设在同一前缀上，rollout 给出的行为概率为 `p_rollout`，训练器在同一旧权重下重新计算为 `p_train_old`。一个直观的诊断是：

```text
数值失配：Δ = log p_train_old − log p_rollout
对应比值：exp(Δ)

理想对齐：Δ = 0，因此比值 = 1
```

只要 Δ 不为零，训练系统看到的差异中就混入了执行引擎的贡献。它不全是策略学习造成的变化。zero-mismatch 的目标，是让这部分执行差异消失。异步 rollout 使用旧权重导致的策略陈旧属于另一问题；如果生成与训练的 policy version 本来不同，数值一致性不会替代版本对齐或离策略校正。

### 5.2 四个“零”不要混在一起

1. **同一权重、同一轨迹的 rollout/trainer 数值失配为零**：这正是当前工作的核心主张。
2. **新策略与旧策略的差异为零**：训练更新后通常不应如此，否则策略没有变化。
3. **策略与 reference model 的 KL 为零**：属于另一种约束和比较对象。
4. **完整词表概率分布的数学 KL 严格为零**：仅凭采样 token 的日志指标，不能独立证明所有输入、所有 token 上的这一命题。

因此，博客摘要中的“PPO KL 为零”，应结合正文和代码读成**所报告运行中的 rollout/trainer 对齐指标**。它不表示优化器更新之后所有策略差异都为零，更不表示训练从此不需要控制更新幅度。[案例与配方](https://github.com/Inferact/zero-mismatch-rl/blob/abdcc241b847fc97da03e5fc05bc7c897a795de2/cases/kimi-k3.1/README.md)

## 六、源码里的核心方案：让训练前向复用推理的数值定义

这个方案比“双方都设置同一个随机种子”更深。它要约束的是每个 token 的运算表达式、量化位置、归约顺序、LoRA 合并方式，以及不同执行形状下的 kernel 行为。

### 6.1 KDA 是最有代表性的难点

线性注意力通常具有两种高效形式：prefill 用分块并行，decode 用逐 token 递推。两种形式可以在实数数学上等价，却因舍入和累加顺序不同而不逐 bit 相同。混合批次更麻烦：同一个 decode token 如果因调度被送入另一条路径，概率可能受其他请求影响。

CF-BI 的思想是给两条路径定义同一份**行级计算契约**：当前位置依赖 chunk 入口状态和此前行；prefill 批量计算这些行，decode 计算其中的新行，但两者遵循同一运算顺序。系统因此不只保存最终递推状态，还保存开放 chunk 的必要行缓存和位置。

必须特别记录一个版本差异：案例 README 及早期设计文档仍描述 **64-token chunk**，但本文核查的 vLLM 固定提交中，`k31_kda_cfbi.py` 默认已是 **contract v6、16-token chunk**，每个 head 的行缓存为 FP32 `[17][256]`；v5 通过环境变量显式选择。**本文按当前固定源码解释默认实现，不把旧设计草稿当作最终参数。**[当前 KDA runtime](https://github.com/Inferact/zero-mismatch-rl/blob/5735778f43f7d94108d432706dc5b17765bf723a/vllm/models/kimi_k3/nvidia/k31_kda_cfbi.py)、[v6 CUDA 实现](https://github.com/Inferact/zero-mismatch-rl/blob/5735778f43f7d94108d432706dc5b17765bf723a/csrc/k31/kda/kda_cfbi_v6.cu)

这项设计的代价也很具体：更多状态需要分配、复制和恢复；改变前缀缓存边界或权重同步行为时，必须确认所有状态都被正确处理。确定性不是一个与缓存管理无关的开关。

### 6.2 TP/EP 改了，归约的数学顺序仍要固定

张量并行将一个矩阵乘法拆到多张卡，再把局部和加起来。若改变 TP 后，局部乘法分块和加法树也变了，那么最终低精度舍入可能不同。仅保证某个固定拓扑内每次运行都可重复，还不足以保证训练与推理使用不同拓扑时一致。

当前 `k31_tp_ordered.py` 把行并行结果按**全局 chunk 顺序**组合，使用 FP32 中间累加，并在约定的位置完成 BF16 舍入。这使“在哪里计算”和“以什么顺序求和”能够分开。[TP ordered 实现](https://github.com/Inferact/zero-mismatch-rl/blob/5735778f43f7d94108d432706dc5b17765bf723a/vllm/distributed/device_communicators/k31_tp_ordered.py)

MoE 同样需要固定专家输出的组合顺序。专家放在哪张卡是部署问题，但如果卡的布局改变了求和顺序，概率就受部署布局影响。对齐方案将这些数值约定纳入推理前向与训练前向的共同实现，而不是只在输出端增加一个容差。

### 6.3 LoRA 不只是两个矩阵同步过去

当前配方只训练 adapter，基座冻结。参数更新后，adapter 被同步到常驻的 rollout 引擎。这里需要检查的不仅是 A、B 两个矩阵是否同名同值，还包括：`alpha/r` 在什么位置乘入、何时转 BF16、基座与增量先相加还是先舍入、专家共享的 adapter 参数如何归约梯度。

例如，`round(base + delta)` 与 `round(base) + round(delta)` 一般不相同。把 scaling 先乘入高精度 B 再转低精度，也不必等于先转低精度再乘 scaling。它们在纸面上容易被当作同一公式，在逐 bit 对齐中却是不同算法。[训练线性层与 LoRA](https://github.com/Inferact/zero-mismatch-rl/blob/8dd1d2bcb8561380c0341391ecd5d1bda9a55380/experimental/lite/megatron/lite/model/k31/vllm/primitive/linear.py)

发布中的“whole-model LoRA”应理解为 adapter 覆盖广泛的注意力投影和全部专家，**不是更新全部 2.8T 基座参数，也不是每个内部张量都挂了 LoRA**。当前实现对离散索引等路径有冻结和特定边界。[训练配方的 LoRA targets](https://github.com/Inferact/zero-mismatch-rl/blob/4a177e27f6714942af695ab6de938aa55f540679/examples/grpo_trainer/run_k31_true_on_policy_preview_megatron.sh)

### 6.4 对齐的不只是模型，还有软件环境

配方将 `VLLM_BATCH_INVARIANT=1` 与指定的 KV dtype、attention/top-k 后端、工作区和运行环境一起检查。镜像安装脚本保存文件清单和哈希，并验证安装依赖后关键文件没有被替换；启动时还检查各 Ray GPU 节点实际导入的包是否一致。

这些检查说明，项目并没有把“设置一个环境变量”视为充分条件。训练进程与 rollout 进程若意外导入不同版本，数值契约可能在尚未开始训练前就已失效。[镜像定义](https://github.com/Inferact/zero-mismatch-rl/blob/4a177e27f6714942af695ab6de938aa55f540679/docker/Dockerfile.k31_true_on_policy_preview)、[安装校验](https://github.com/Inferact/zero-mismatch-rl/blob/4a177e27f6714942af695ab6de938aa55f540679/docker/k31/install_k31.sh)

## 七、一个必须保留的边界：前向一致，不等于梯度精确

这是读源码后比博客标题更值得注意的一点。

当前 Megatron 的 `primitive/kda.py` 明确说明：**CF-BI 没有专用 backward kernel**。前向调用 rollout 的计算路径；反向则重算 FLA `chunk_kda` 的可微函数图，用它的 vector-Jacobian product 传播梯度。代码将其描述为 straight-through 的相邻函数梯度。

这意味着系统可以同时满足：

- rollout 与 trainer 前向得到逐 bit 相同的 token log-prob；
- 训练反向对某些算子使用近似或代理梯度，而非对实际所有舍入、量化和离散选择逐步求精确导数。

这并不自相矛盾。低精度训练中经常需要可用的梯度估计，但应把两项验收分开：**前向概率一致性**与**反向梯度质量**。源文件给出了其特定梯度测试的误差说明；这些测试不能替代长时间训练稳定性、不同数据分布与不同配置的验证。[KDA autograd 实现与边界](https://github.com/Inferact/zero-mismatch-rl/blob/8dd1d2bcb8561380c0341391ecd5d1bda9a55380/experimental/lite/megatron/lite/model/k31/vllm/primitive/kda.py)

同样，zero-mismatch 不能消除奖励噪声、数据偏差、优势估计方差或过大的策略更新。它移除的是一个重要的系统误差来源，而不是为强化学习的所有不稳定性提供总解。

## 八、实验证明了什么，又还缺什么

### 8.1 当前可引用的结果

[固定案例 README](https://github.com/Inferact/zero-mismatch-rl/blob/abdcc241b847fc97da03e5fc05bc7c897a795de2/cases/kimi-k3.1/README.md)报告：在 **4 节点×4 GB300、rank-32 LoRA、100 个 DAPO 训练步**的运行中，rollout/trainer log-prob mismatch 每步为零；AIME 2024/2025/2026 的 **mean@8 从 0.451 到 0.664，pass@8 从 0.633 到 0.867**。训练器是 Megatron/mLite 与 verl，rollout 为 vLLM。

这提供了“对齐路径能够完成真实训练并获得指标改善”的证据。它没有单独证明所有改善均由 zero-mismatch 导致。要回答后一个因果问题，需要相同数据、种子、计算预算、adapter 初值和评测规则下的完整对照，并报告波动范围。

另外，README 的一般支持配置与 100 步实验的硬件行写有不同 rollout 布局：前者列 TP8/EP8，后者列 DP16/EP16。应按各自实验读取，不能把一般配置和后续成本测试拼成一套“100 步完整复现参数”。下表也保留为独立成本对照。

### 8.2 当前一致性仍有速度成本

案例 README 给出的 BI on/off 对照使用同一镜像与配方、每个请求带 LoRA；rollout 为 4 个 GB300 节点上的两个 TP8/EP8 副本：

| 比较项 | BI off | BI on | 项目报告的变化 |
|---|---:|---:|---:|
| RL 第 1 步 rollout，显存利用率 0.87 | 353 秒 | 412 秒 | 耗时增加约 17% |
| RL 第 1 步整体耗时 | 1,330 秒 | 1,525 秒 | 耗时增加约 15% |
| 带 LoRA serving，利用率 0.90、并发 128 | 1,708 token/s | 1,543 token/s | 吞吐降低约 9.7% |

这里要保留三个限定：**前两项是第 1 步，不是 100 步均值；第三项是独立 serving 条件；不能把成本百分比当作所有 workload 的固定税率。**案例还指出，在另一显存利用率条件下，BI off 的 CUDA graph 占用影响了可用 KV，速度关系会变化；README 同时注明根因仍在测量中，不能视为已经完全定论。[成本表与说明](https://github.com/Inferact/zero-mismatch-rl/blob/abdcc241b847fc97da03e5fc05bc7c897a795de2/cases/kimi-k3.1/README.md)

对训练团队，更有用的评价指标应是“达到目标质量的总 GPU 时间”，而不只是一轮 rollout 的 token/s。数值对齐可能减少诊断、重跑或补偿负担，但公开材料还不足以给出普遍的净成本收益。

### 8.3 公开代码还不是通用开箱即用方案

项目说明三个代码分支是工作树的单提交快照，尚不是一组清晰分层、可直接 cherry-pick 到任意上游版本的补丁。Docker 构建需要匹配的基镜像、vLLM、Megatron 和 verl 来源；当前 KDA kernel 构建目标含 `sm_100a/sm_103a`。案例中的 **CP=2 仅有与 CP=1 逐 bit 对照的微基准，尚无 RL 运行验证**。

因此，不能从“vLLM Day-0 推理支持多种硬件”推导出“这套 zero-mismatch RL 已在所有这些硬件上验证”。推理可用性、最快服务路径、批不变路径和训练反向支持，是四个需要分别核实的能力。

## 九、Day-0 适配到底做了什么：从“能加载”到“能训练”

发布当天宣布支持，背后可能对应完全不同的交付层次：模型注册已合入、专用镜像可用、性能路径在预览分支、训练脚本尚在 Draft PR、某后端只有源码安装。**Day-0 是时间承诺，不是统一的成熟度等级。**

下面的状态核查截至 **2026-11-05 02:05 UTC（北京时间 10:05）**。它说明当时公开材料的状态，不保证这些 PR 此后保持不变。本文主体对象为 **Kimi K3.1 Pro**；其他仓库的 PR 若使用“Kimi-K3.1”简称，保留原名，并按其 checkpoint 和架构说明判断范围。

### 9.1 模型接入的第一层：把 checkpoint 正确地解释出来

以 [vllm-torchtpu #2775](https://github.com/vllm-project/vllm-torchtpu/pull/2775) 为例，原有 K3 模型路径会把 MLA 层构造成 dense attention，并没有为 K3.1 的 indexer 权重提供相应模块。因此，适配不能只增加一个模型名字，至少需要：

- 识别新的 config 与 `dsa_config`，在指定层构造稀疏 MLA。
- 注册模型类，并映射 `indexer.wk`、`indexer.weights_proj` 等 checkpoint 张量。
- 保留 K3 的聊天渲染、工具调用 token 语义，避免模型能算出 logits，却在应用接口上出错。
- 在加载大规模权重前拒绝不支持的配置，避免花很长时间加载后才失败。

这是 Day-0 最基础、也最容易被性能宣传掩盖的工作：**参数加载正确、架构定义正确、输入输出协议正确。**其中任何一项不对，后面的吞吐数字都没有可比性。

### 9.2 推理引擎真正的亮点：新结构进入现有服务系统

vLLM 的贡献不只在 DSA kernel 本身，还在让它与混合缓存、前缀复用、并行策略和投机验证共同工作。前文拆解的 packed cache、token-sharded prefill、DCP 与 fused decode，分别对应分配、重复工作、容量扩展和低延迟路径四个问题。

GPU 主线的模型适配 [vLLM #65685](https://github.com/vllm-project/vllm/pull/65685) 于 **11 月 4 日 15:35:36 UTC** 创建，在核查时仍 **Open**。[官方 recipe 源码](https://github.com/vllm-project/vllm/blob/7ecc83a9877552a5f4be31c133ab8502dd40f50e/recipes/models/moonshotai/Kimi-K3.1-Pro.yaml) 明确标记 `nightly_required`、禁用 pip 安装，并说明支持尚未进入 wheel；提供 NVIDIA 的 `vllm/vllm-openai:kimi-k31` 和 AMD 的 `vllm/vllm-openai-rocm:kimi-k31` 专用镜像。页面出现的 0.34.0 最低版本字段也不应被误读为“0.34.0 正式版已发布并可直接安装”。

recipe 还显式把低延迟路径限制在特定 TP/DCP 布局，列出 NVFP4 KV 与独立索引精度，并按硬件生成不同命令。这些可执行配方是 Day-0 交付的一部分；博客中的各项优化并不意味着可以任意组合开关。

跨硬件适配也不能理解为“同一 CUDA kernel 换个编译器”。TPU PR 需要处理统一缓存池与 per-layer 数组之间的关系，并让共享 block id 在 prefix-cache copy-on-write 时正确复制；它还显式处理 DSpark draft 的 dense MLA 缓存预算。这里的亮点是**把状态生命周期补齐**，而不仅是一次前向能够结束。

但该 TPU 模型 PR **当时仍 Open**；[vLLM recipe #65725](https://github.com/vllm-project/vllm/pull/65725) 也仍 Open，并明确说明尚无正式发行或公开镜像携带该支持，需要源码安装，当前为 **text-only**。PR 还列出 DSpark 与 DCP 不能组合、异步投机调度依赖另一个 PR、P/D 不支持等边界。

因此，博客的“TPU Day-0 支持”有实现与测试依据，但不能被改写成“任意当前发布版开箱即用，且所有 GPU 功能已对等”。本次查询也发现博客与 recipe 对 TPU slice 的芯片计数表述不完全一致，本文不将其折算成跨平台每芯片性能结论。

### 9.3 verl、Megatron 与 vLLM 的协作：不是给 rollout 外面套训练循环

zero-mismatch 路线将工作分成三个角色：

| 角色 | 具体工作 | 重要边界 |
|---|---|---|
| vLLM 专用分支 | 批不变 KDA、固定顺序归约、LoRA-aware kernel、可被训练复用的前向 | 不能用最快普通 serving 路径替代后仍声称原数值契约成立 |
| Megatron/mLite 专用分支 | 将推理前向封装为训练模块，提供可微反向，处理 PP/EP、checkpoint 与 adapter 布局 | 前向一致与代理梯度质量要分开验证 |
| verl 专用分支 | 组织 rollout、评分、更新和 adapter 同步，校验运行配置与各节点软件来源 | 配方、模型、镜像、拓扑必须匹配，单个环境变量不足以复现 |

这里引用的来源是 **Inferact/zero-mismatch-rl 的三个专用工作树快照**，不是据此宣布所有改动已经进入 `vllm-project/vllm`、`verl-project/verl` 或 NVIDIA Megatron 上游正式发行。该区别直接影响升级和维护：专用分支能展示完整工程路径，但用户仍要承担与上游版本对齐、私有接口变化和构建来源管理的工作。

值得肯定的细节，是配方除了 theta0 对齐，还包含 `quick_alignment_test` 和完整 `aligned` 模式，前者安排多次更新与同步检查。这比只拿未训练 adapter 做一次“零误差”截图更接近真实 RL 的风险点。[配方与启动检查](https://github.com/Inferact/zero-mismatch-rl/blob/4a177e27f6714942af695ab6de938aa55f540679/examples/grpo_trainer/run_k31_true_on_policy_preview_megatron.sh)

### 9.4 Miles 展示了另一条训练适配路线

[Miles #4665](https://github.com/radixark/miles/pull/4665) 的文档于 **11 月 4 日 21:44:59 UTC** 合并；但依赖的模型实现 [#4666](https://github.com/radixark/miles/pull/4666) 与 W4A16 LoRA 配方 [#4667](https://github.com/radixark/miles/pull/4667) 在核查时仍为 **Draft**。文档明确要求 `radixark/miles:kimi-k31` 镜像以及 SGLang 的 `sglang-miles-kimi-k31` 专用分支，不能把“文档已合并”当作“训练代码已进入 main”。

其工作中有三类值得注意的细节：

**第一，稀疏训练与 rollout 的离散路径对齐。**模型 PR 在 MLA 层加入 DSA indexer，支持 replay rollout 选择的索引；zigzag CP 下，还要把局部查询、gather 后的 KV 和 replay 索引转换到同一全局 packed 坐标。这解决的是“训练到底看了哪些历史位置”，不是只把 tensor shape 对上。

**第二，冻结专家保留 MXFP4，避免为 LoRA 训练展开全部 BF16 基座。**配方 PR 保留 `weight_packed/weight_scale`，在专家计算时反量化；训练状态主要是 BF16 adapter。adapter 导出改为按模块、按 PP stage 流式同步，降低一次性聚合的内存峰值。这里的重点是**显存可行性与同步成本**，并非宣称所有专家进行低精度全参数训练。

**第三，工具调用 token 协议。**TITO 路径要处理引擎在工具调用分隔符处停止，与 chat template 完整消息闭合方式之间的差异。若模板补全不一致，相同会话在 rollout 与训练中可能对应不同 token，数值对齐无从谈起。它提醒我们：所谓训推一致，最前面的一关就是“双方看到同一段 token”。

该配方公开了 32 H200 与 16 B300 路径，但其报告的 log-prob gap 仍为非零。**Miles 的 replay 与量化 LoRA 适配不能被当成 Inferact zero-mismatch 的同一项结果。**两条路线解决的问题有交集，证据、内核约束和验证指标不同。

### 9.5 SGLang：把长会话服务策略做成可选择的配置

本文读取并固定了 [SGLang cookbook 源码](https://github.com/sgl-project/sglang/blob/bf40ca98f4287347ec8d19662aa390eacc253a1e/docs/cookbook/autoregressive/Moonshotai/Kimi-K3.1-Pro.mdx)。它要求 `kimi-k3.1-day-0` 分支或 `lmsysorg/sglang:dev-kimi-k31-pro` 等专用镜像；不能据此推断任意 stock release 已有相同功能。

其适配亮点可以按服务形态看：

- **Prefill 与 decode 分别选布局。**高吞吐 prefill 提供 PP4×PCP2 与 MegaMoE；decode 则有 TP8、DCP8 等不同目标的路径。流水并行、上下文并行和专家并行承担不同分工。
- **DFlash2 与状态恢复协同。**混合 KDA 模型的投机验证不能只保存普通 KV，还要处理递推状态；配方要求相应 ReplaySSM 路径。P/D 分离时，prefill 与 decode 都要运行 draft，因为前者要产生后者读取的 draft KV ring。
- **HiCache 不只搬 MLA KV。**KDA state 的 host slot 也可能先限制前缀命中率。AMD 配方因此分别配置 host KV 与 KDA 状态预算，并注明部分 monokernel 路径不能与 HiCache 组合。
- **把验证状态细分到命令。**文档区分 Verified、验证进行中和未验证；同一硬件上的 Playground 派生配置，并不自动继承已测配置的结论。

同样要保留其证据边界：cookbook 的 GB300 AgentX 配置是 **11 月 3 日调优活动的状态快照**，固定接受长度，使用 `9ab3c28176` 加未合并改动构建的镜像；文档明确说该组命令**不是 InferenceX 提交**，且没有验证公开 dev 镜像与这些命令完全一致。工程方向值得研究，但不能把不同快照、不同路由器和不同验收状态的数字拼成 vLLM 对 SGLang 的公平排名。

### 9.6 如何评价这些 Day-0 工作

我们的判断是，真正值得关注的不是支持列表长了多少，而是模型新增结构是否穿过了完整工程链：

```text
config / 权重映射
      ↓
attention 与 MoE 的真实计算
      ↓
KV / 递推状态 / 前缀缓存的生命周期
      ↓
并行、通信、投机验证和调度
      ↓
训练反向、adapter 导出与权重更新
      ↓
功能、质量、数值和性能的分层验收
```

K3.1 的难度恰好在于这些层都发生了耦合。最有价值的细致工作，往往是映射、缓存复制、更新后重建派生状态、固定归约顺序以及让测试真正覆盖目标分支。这些工作不容易用一个加速倍数概括，却决定系统能否长期使用。

## 十、debugging-mismatch 指南：把“数值不对”变成可定位的问题

仓库中的 [debugging-mismatch](https://github.com/Inferact/zero-mismatch-rl/tree/abdcc241b847fc97da03e5fc05bc7c897a795de2/skill/guides/debugging-mismatch) 是一套**证据驱动的诊断规程**。它的价值在于规定比较对象、观察边界和归因顺序，避免一看到 KL 异常就切高精度或打开更多 deterministic 开关。

### 10.1 先分离问题属于哪一边

可以把诊断组织成四组实验：

| 实验组 | 固定什么、改变什么 | 主要回答 |
|---|---|---|
| 推理内部 | 固定输入和权重，比较重复运行、单请求与混合 batch、prefill 与 decode | rollout 是否受调度或执行形状影响 |
| 训练内部 | 同一轨迹同一权重，比较重复计算与不同 packing | 训练前向是否自行产生差异 |
| 训练与推理之间 | 固定 token、policy version 和评分定义 | 是否存在跨引擎语义或数值差异 |
| scorer | 输入同一份 logits，核对 dtype、temperature、logsumexp、词表分片归约 | 差异是否产生在模型之后的概率计算中 |

这个顺序能避免过早怀疑最大的模型算子。假如两边 logits 相同而 log-prob 不同，继续调 attention 精度没有意义。若同一个 prompt 的多个回答在共享前缀上已经不一致，则应先调查引擎侧执行，而不是奖励函数。

### 10.2 找最早的语义分歧，而不是最大的误差

指南建议从 block 边界粗扫，再深入第一个可疑模块，在相同输入下做算子 A/B。比较点必须具有相同语义：norm 前还是后、residual 加之前还是之后、LSE 用自然对数还是 log2，都需要对齐。

这里的“bisect”不能机械理解为任意层号上的二分搜索：某些差异经过舍入可能消失，误差并不保证随层数单调。发现第一个不同输出也不等于证明该算子有错，还需证明它的输入本来相同。

排查次序应是：**输入与 mask → 权重及版本 → top-k 等离散路径 → kernel 数值 → 精度契约**。遇到 MoE 或稀疏索引，要比较选择集合、顺序、tie-break 与 flip rate；如果路由都不同，直接讨论后面输出的浮点容差，很容易把语义错误伪装成数值噪声。

### 10.3 消融实验最危险的是隐藏联动

关闭 CUDA graph 后误差消失，并不能立刻证明 graph 有 bug。开关可能同时改变 batch、调度、kernel 选择或工作区分配。有效的归因需要固定离线输入与 batch，并用日志或计数确认目标路径真的执行过。

一个测试可以输出 `max_abs=0`，却没有任何有效 token，或根本没走到待测路径。指南将这种情况视为 **VACUOUS（空验证）**。跨节点初始化成功也不等于跨节点传输已被验证，更不等于带宽合理。

对 bitwise 验证，应保留原 dtype 并按位比较，而非只检查浮点数值相等，后者会把 `+0.0` 与 `-0.0` 视为相同；不能先做类型转换或从打印日志重建数值，再声称原始字节逐 bit 一致。还要保留 request id、有效 token mask、权重版本和 packing 映射，避免只比较两边共有的那部分样本。

### 10.4 这不是已经附带所有脚本的自动排障产品

`06-artifacts.md` 明确说明，仓库**没有提供通用的 log-prob、逐层 trace 和 replay 比较脚本**；文中列出的 `fixed_token_oracle.py`、`rl_source_snapshot.py` 等属于未包含在本仓库中的 companion toolkit。公开可直接使用的主要是操作规程、实验模板与小段示例，具体框架仍需实现自己的采集和比较工具。[工具与证据边界](https://github.com/Inferact/zero-mismatch-rl/blob/abdcc241b847fc97da03e5fc05bc7c897a795de2/skill/guides/debugging-mismatch/06-artifacts.md)

指南也包含历史案例、source audit 与尚待验证的机制解释。它们可以帮助提出假设，不能一概写成已合入上游的修复，或推导某种 TIS 策略普遍优于另一种策略。

这份指南与 K3.1 的联系很直接：zero-mismatch 给出一个严格对齐的工程实例，debugging-mismatch 则解释怎样建立或反驳这类主张的证据。它的普适价值是**让差异可复现、可定位、可归因**，并不要求所有项目无条件追求逐 bit 相同。

## 十一、如何设计自己的验收，而不是只复现标题数字

以下是基于公开实现的工程建议，不是项目方已经完成的额外测试。

### 推理验收

1. **锁定版本与格式**：记录模型、adapter、vLLM 与 kernel 依赖版本，分别记录权重、latent、index key 的精度。
2. **分开测四类指标**：长 prompt TTFT、缓存前缀后的短追加 TTFT、生成 TPOT、带尾延迟约束的吞吐。
3. **用实际会话分布**：覆盖长短上下文混合、前缀共享、持续会话与高并发，记录抢占和重计算。
4. **把容量测试与性能测试分开**：确认真实权重配置下可用 KV，再验证在该并发下是否满足服务目标。
5. **投机解码跑真实接受率**：保留采样参数、draft 版本和每种任务的接受长度，不把 synthetic acceptance 当实测。

### RL 对齐验收

1. **同权重同输入先验收**：比较采样 token log-prob 的非零差数量、最大绝对差和比特一致比例，避免平均指标抵消正负误差。
2. **主动改变 batch 组成**：相同样本分别单独运行、混合长短序列、走 chunked prefill、接续 decode，检查数值是否改变。
3. **覆盖状态生命周期**：前缀命中、缓存复制、抢占恢复、LoRA 加载卸载和多轮更新后都应检查；首次 adapter 同步成功还不够。
4. **按宣称范围测试并行布局**：TP/EP/PP/CP 的支持矩阵要逐项列出，不能把某一微基准通过扩写为全部组合受支持。
5. **单独验梯度**：有限值、参考梯度误差、专家共享参数归约、长期 reward 与验证集曲线都需要检查。
6. **再比较总成本**：在相同任务质量与资源预算下比较 BI on/off，而不是把不同后端、不同缓存容量的两次速度差全部归因于一个环境变量。

## 结论：推理引擎开始成为训练方法的一部分

K3.1 推理优化体现的，是围绕长上下文重新分配数据与工作：更窄的索引筛选、更适合的缓存布局、按模块选择并行方式，以及减少小 batch 路径上的执行开销。

zero-mismatch 展示的则是更深一层的协同：**让训练前向直接服从部署引擎的数值约定。**这使推理实现不再只是“模型训练完成后的加速器”，而成为训练所优化策略的具体定义的一部分。

这条路线值得关注，但判断其成熟度应同时看三件事：前向一致性的覆盖范围、代理梯度与长跑训练的可靠性、达到目标质量的总成本。公开结果已经给出有价值的工程样本；将它推广到其他模型、精度和硬件，仍需逐项建立证据。

### 阅读与复现入口

- [vLLM 原始发布文章与交互图](https://vllm.ai/blog/2026-11-04-kimi-k31-pro)
- [K3.1 案例结果，main 文档固定提交 abdcc241](https://github.com/Inferact/zero-mismatch-rl/blob/abdcc241b847fc97da03e5fc05bc7c897a795de2/cases/kimi-k3.1/README.md)
- [训练配方，verl 固定提交 4a177e27](https://github.com/Inferact/zero-mismatch-rl/blob/4a177e27f6714942af695ab6de938aa55f540679/examples/grpo_trainer/run_k31_true_on_policy_preview_megatron.sh)
- [推理代码，vLLM 固定提交 5735778f](https://github.com/Inferact/zero-mismatch-rl/tree/5735778f43f7d94108d432706dc5b17765bf723a)
- [训练代码，Megatron 固定提交 8dd1d2bc](https://github.com/Inferact/zero-mismatch-rl/tree/8dd1d2bcb8561380c0341391ecd5d1bda9a55380)

*核查日期：2026-11-05。本文为公开资料和源码解读；除明确标注的计算外，实验结果归属于原项目，未在本文环境独立复现。*
