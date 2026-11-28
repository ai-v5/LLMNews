---
layout: post
title: "MAGI-2 的 Head Parallel，会把 10T 模型需要的超节点做小吗？"
date: 2026-11-28T09:21:30+08:00
summary: "拆解 Multi-Head LatentMoE、MAGI-2 与 Kimi K3。推导 HP×EP 的通信账，并用 10T–40T 的状态分片算例说明：动态专家域可以缩小，但最快互联还要服务权重、梯度和长上下文。"
section: explainer
label: "训练系统解读"
tags: [LatentMoE, Head Parallel, 专家并行, FSDP, MAGI-2, 超节点]
demo: false
sources:
  - title: "Cui 等：Multi-Head LatentMoE and Head Parallel"
    url: "https://arxiv.org/pdf/2602.04870"
  - title: "HP 原论文公开实现"
    url: "https://github.com/kerner-lab/Sparse-GPT-Pretraining"
  - title: "Sand.ai：MAGI-2 480B 官方发布"
    url: "https://sand.ai/blog/magi-2/"
  - title: "Sand.ai：MAGI-2 Preview 架构与训练系统"
    url: "https://sand.ai/blog/magi-2-preview/"
  - title: "Moonshot AI：Kimi K3 技术报告"
    url: "https://arxiv.org/abs/2607.24653"
  - title: "NVIDIA：Generalized Tensor Parallelism"
    url: "https://arxiv.org/abs/2611.32057"
---

**我的判断：小 HP + 中等 EP 会缩小必须全速互通的动态专家域，但不会自动缩小整个 10T+ 训练所需的高速互联。** 可替换的是「所有专家卡都必须互相做动态 All-to-All」这个假设。不能一起删掉的是专家状态分片、长序列 CP 和多组通信同时发生时需要的带宽。对未来超节点，最有价值的变化是能按流量类型分层定规格，而不是把一个固定大域做成所有工作负载的唯一映射。

还有一个事实值得先纠正：**多头路由已有纯文本预训练证据，低维 LatentMoE 更已进入数万亿参数的语言模型；但公开数据还没证明「分头独立专家库 + HP」是 10T 文本模型的最优解。** Kimi K3 和 MAGI-2 正好说明这条路线两端分别证实了什么。

本文依据 2026 年 11 月 28 日可核实的公开资料。下文 10T–40T 规模、精度、分片和带宽均为独立假设算例，不是任何厂商产品或内部项目规格。

## 1. 分清三件事：低维专家、独立的 MoE 头、Head Parallel

| 方法 | 数据流 | Top-k 动态通信在哪里 |
|---|---|---|
| 标准 MoE + EP | 对全宽 token 选专家，再给各目的 rank 送 token，最后按权重组合 | EP 域；相同目的地可合并副本 |
| 单头 LatentMoE + EP | 先把 routed 分支投到更低维，再对一个全局专家库选 Top-k；共享专家可保留全宽 | 同样在 EP 域；改变的是每份副本宽度 |
| Multi-Head LatentMoE + 纯 HP | 投影后切成多个子向量；先按静态 head ownership 交换，再在头内选专家 | 头专家完整驻留、或算前已 materialize 时，路由只改变本地执行 |
| Multi-Head LatentMoE + HP×EP | 先按头交换，随后同一个头的多个 rank 之间分专家并执行 | 每个头片内还有动态 EP；只有外层 HP 不随 Top-k 增长 |

看一个 HP4 的具体形状。每个源 rank 有 N 个 token，每个 token 投影宽度 Dℓ，四个 rank 分别持有四份头分片。对各目的 rank 发出 **N × Dℓ/4**；一个目的 rank 收到 **4N × Dℓ/4**，因此逻辑元素数仍是 **N × Dℓ**，只是「少一些头，所有源的 token 都来了」。专家算完后逆转置、拼回 token，再做输出投影。

[公开代码](https://github.com/kerner-lab/Sparse-GPT-Pretraining/blob/e9ea58cc83c8cca1f9f336c16b4085ceb0bdfab6/src/model/modules/ffwd/mh_moe_hp_nrt.py)里，投影后按目的 rank 排列，等长 split 明传给 All-to-All，头数必须是 HP rank 数的整数倍；[collective 封装](https://github.com/kerner-lab/Sparse-GPT-Pretraining/blob/e9ea58cc83c8cca1f9f336c16b4085ceb0bdfab6/src/model/ops/all_to_all.py)在反向交换 input/output splits。原型实际使用默认 world group；不能把论文说的可组合性当作该仓库已交付生产 HP×EP。工程上若各源的有效 token 数不同，还要对齐、静态 padding 或管理变长 bucket；路由确定不了物理网络的排队，形状确定也不等于全模型 bitwise 确定。

**论文的 O(1) 是相对 Top-k。** 总字节仍随 N 和 Dℓ 增长，参与者增加会改变启动成本、bisection 和多租户干扰。固定 shape 不会消灭专家热点。纯 HP 中同一 head 收到同样多 token、总 assignment 可固定，但头内不同专家的 M 仍变化；细粒度小 GEMM、临时 buffer 和路由排序仍会影响每个 rank 的完成时间。若头内继续分 EP，热点可重新成为 rank 间流量不均。

### 多头不是可无损切换的通信开关

每头一套 router 和专家，只能在这个头的子空间里自由选专家。一个 head 的闲置容量不能直接替另一个 head 救火。输入／输出投影与共享分支可以重新混合跨头信号，但不会把它变成原模型的全宽专家。这会改变函数族、稀疏度、路由分布，以及专家量化和 数学／代码／长上下文的学习结果，不能只做系统配置改造。

忽略偏置，若每头 E 个 SwiGLU experts，头宽 d，expert 中间维度 m，共 M 个头、每头选 k，**routed 参数约 3·M·E·d·m，激活约 3·M·k·d·m**。总投影宽 Dℓ=M·d；固定 Dℓ 和 m 增加头数不会按 M 增加同一层的 routed 参数，却会增加独立专家单元数与 kernel 碎片。压低 Dℓ 后要补参数预算，可能得加中间维度、专家数或层数，不能只算缩小通信的一边。原论文用片上 streaming top-k、分块稀疏 FlexAttention 重写专家计算；MAGI-2 走 fused router、紧凑重排与 grouped SwiGLU 路线。两种结果都不能直接当成另一种算子库的实测。

## 2. MAGI-2 到底验证了什么？语言模型走到哪一步？

| 公开证据 | 已经验证的用法 | 没有证明什么 |
|---|---|---|
| [Cui 等，HP 原论文](https://proceedings.mlr.press/v306/cui26c.html) | H100/NVLink；12 层纯文本 decoder、2K context、10B FineWebEdu token。4.2B 总/0.2B active：标准 EP 55.34h，MH-HP 34.41h；PPL 15.01/15.02；五项均值 45.30/45.17。加细粒度变体 50.04h、14.82 PPL | 1.61× 是架构和实现整体比较，不是 HP 单项收益；也不是跨机 10T 训练或等价全量能力 |
| [MAGI-2 Preview](https://sand.ai/blog/magi-2-preview/) | 114B/6B active，模型宽 3072，12×256、每头 256 专家 Top-6，36 个稀疏层；跨机 IB 发静态头切片，机内 NVLink 用 ZeRO/FSDP 式状态分片 | 机内公布的是状态 gather/reshard，不是「中等动态 EP」；Preview 的头数、并行度不能外推到旗舰 |
| [MAGI-2 旗舰](https://sand.ai/blog/magi-2/) | 官方披露 480B/28B active、4T 预训练数据，HP+MagiFSDP、MagiMoE、MagiMuon。作者报告在同总 FLOPs、各自最佳配置下，相对**单头 LatentMoE**训练速度约 +22% | 详尽配置、HP 组规模、EP 或 FSDP 组大小、网络计数器和可复跑训练包未在发布文中给出；损失图的 8-head 消融不等于旗舰生产拓扑 |
| [Kimi K3](https://arxiv.org/abs/2607.24653) / [Nemotron 3 Ultra](https://research.nvidia.com/labs/nemotron/Nemotron-3-Ultra/) | K3 是 2.78T/104.2B active，7168→3584、896 routed/Top-16，一个 routed latent 空间；用 MoonEP 动态冗余专家把每 rank 执行量做平。Ultra 550B/55B active，采用 LatentMoE | 这证实 latent bottleneck 可用于大型语言主干；未证明独立多头专家库与 HP。K3 的 Per-Head Muon 针对注意力投影，不能当作 MoE Head Parallel |

Preview 的规模提供一个直观核算：3072 个专家单元不是 3072 个全宽专家。按每单元 3×256×1280，36 个稀疏层的 routed 权重约 **108.7B**；每 token 12×6=72 个小专家单元，对应约 **2.55B** routed 参数，不包括 attention、全宽共享与其他模块。在扩展到 10T 时，先问每头、每层有多少权重、在什么位置 materialize，而不是见到很大的专家个数就直接指定 EP 槽位。

MAGI-2 的训练划分比一个峰值数字更值得重视：**把静态激活交换放在 IB，把层内频繁的状态收拢放在 NVLink。** 拓扑布局不是「所有流量都可用低速网」，也不是「机内只做专家 All-to-All」。它示范的是给两类 collective 安排不同网络等级。MagiMoE 试图把共享专家、重算和 wgrad 与通信重叠；MagiMuon 按 head×expert 的小矩阵分布正交化工作，不需要把所有专家拼成一张大矩阵。但能否高效落地，还由具体分片是否切断 Muon 矩阵、运行时如何调度决定，不能从名字推断 FP32 master 或 optimizer 通信不存在。

**LLM 采用的可能性。** 最先扩散的很可能是单头 LatentMoE、稳定路由与轻量分组，再到部分层的多头。如果高 Top-k、跨岛通信、长序列、小激活比例持续增长，中间层的 MH-HP 很有吸引力；纯文本已有这个方向的研究证据，例如[早期 MH-MoE](https://arxiv.org/abs/2404.15045)。但视频 DiT 常见大 token 批次，语言模型高并发训练和低并发自回归 decode 是两个不同的形状：后者每头分到的 expert GEMM 更碎，而且 HP 必须联系所有头 owner。训练方案成立不等于推理也更快。更容易先落地的是**逐层混合**：关键层保留全局专家或全宽共享路径，其余层用低维分头；它能否保持同计算预算下的语言能力，需要实测。

## 3. 算清外层和内层的字节：HP8×EP128 不是零 EP

令 N 为 HP 前每 rank 本地 token 数，D 为 model width，Dℓ 为所有 head 的 latent 总宽度，b 为线上字节/元素，H 为 HP 度，E 为每个头片的 EP 度。取一个 **H×E 的二维 rank 网格 (h,e)**：

1. 沿 h 交换：固定 e、跨 H 个 rank 发出各自的 head slice。
2. 沿 e 路由：固定 h、在 E 个 rank 间把头内 token 发给专家。
3. combine 逆序执行。反向也有对应两个交换；激活重算若重做 collectives 另计。

用「每 rank 注入的单向远端逻辑字节」计数，不计 self、消息元数据、链路转发、对齐和临时搬运。均匀路由、不做同目的 rank 去重的简单模型，一次方向为：

- **普通 EP P**： N·k·D·b·(1−1/P)。单头 LatentMoE 换成 Dℓ。
- **外层 HP H**： N·Dℓ·b·(1−1/H)。
- **内层 EP E**： rank 拥有 H 倍 token、每个是 Dℓ/H 宽，约 N·k_head·Dℓ·b·(1−1/E)。若每个 rank 持多头，把各头宽度加总。

所以**头内 EP 的每卡字节并不会再凭空除以 H**。收益来自较窄 latent，以及把动态通信限制在小岛上。平坦 EP 的优化版本并不总为 k 个专家发 k 份网络 payload。若 k 次目标落点近似独立均匀，对 P 个 rank，远端不同目的 rank 数的期望是 (P−1)·[1−(1−1/P)^k]。节点去重、限节点路由、分层 relay、低精传输会改写真实账本。拥挤时则必须看每 rank 峰值、交换结构入口与割带宽，不能用均值取代。

**算例**：N=4096、D=8192、Dℓ=4096、k=k_head=8、BF16 通信。下列各行是不同组的一个方向，不直接相加成链路流量；F+B 极简近似取四个方向，同精度且不含重算。

| 交换 | 组规模 | 每 rank 一次方向 | F+B 四个方向 |
|---|---:|---:|---:|
| 平坦标准 EP | 1024 | 511.5 MiB | 2046 MiB |
| 平坦单头 latent EP | 1024 | 255.75 MiB | 1023 MiB |
| HP8 的外层静态交换 | 8 | 28 MiB | 112 MiB |
| 混合方案的内层 EP128 | 128 | 254 MiB | 1016 MiB |

物理上可以把八个 EP128 岛分别放在高速域，跨岛沿相同 e 位置做 HP8。此时**1024 张卡属于同一 stage 的 expert ownership 网格，不再是一个 1024 卡动态 EP 域**。代价是两个方向的 collective 都有 launch、重排、同步和延迟；同一时刻八个岛的 EP 端口与跨岛 HP 是否争同一注入口、是否抢 CP 带宽，要看映射和交换结构。这里说的是并行组与互联层级，不假设互相隔离的网络轨道，也不把多个独立并行组等同于多个网络平面。

## 4. 10T 状态账：能切小专家域，也可能换来很大的权重交换

把训练中的域区分开：

- **路由域**：动态 dispatch/combine 的 rank 数，混合方案取 E。
- **权重唯一归属域**：在一个 pipeline stage 内，MoE 头和专家的逻辑 owner 覆盖 H×E；Z>1 时再对 owner 权重做物理切分。
- **状态分片域**：再用 Z 组对这个 owner 的权重、梯度和优化器状态分片。在这个模型里，每个 Z 切片所在的 rank 仍参与一套激活计算，而参数通过 AG 临时恢复。H×E×Z 是下表的逻辑放置规模，不是三者必须在同一网络全速互连，也不代表完整模型只需这些卡。
- **序列通信域**：CP/TP/PP/DP 各自对应不同流量及同步时机，有时能复用 rank 轴，有时需独立资源；以下没有把它们机械乘进去。

先做一个能复算的理想模型。把 10T 权重近似都按 routed 路径均匀分片，80 个等重层、PP8，每阶段 10 层。取 **12 B/参数持久态**作为一个**假设**：BF16 工作权重 2B + BF16 梯度 2B + FP32 master 4B + FP32 单动量 4B。真实 precision/optimizer/梯度驻留策略各异，另需计 dense/共享、repeat buffer、激活和临时 full weight，**下面不是显存可行性证明**。每卡 routed 持久态约为：

`12 × P_total / (PP × H × E × Z)`

令 W 是一个 owner 对**单层**负责的参数数目，此例 W=(10T/80)/(H×E)。若 Z>1、前向后立即 reshard，BF16 权重前向／反向各 gather 一次、BF16 weight grad reduce-scatter 一次；一个方向单 rank 的理想环形等效字节分别为 `2W·(1−1/Z)`，三次共 `6W·(1−1/Z)`。不是所有实现都会做两次 gather，保留权重能省第二次但占 HBM；FP32 梯度、重算、跨域分层和 packet overhead 会改账。

| 映射（每个 PP stage） | 路由 EP | 分片 ranks | 每卡持久态 | 本 rank 单层 owner 权重全量（BF16） | 一次 AG 等效注入/卡 |
|---|---:|---:|---:|---:|---:|
| 普通 EP256，Z1 | 256 | 256 | 58.59 GB | 0.98 GB | 无 Z 轴 AG |
| HP8×EP32，Z1 | 32 | 256 | 58.59 GB | 0.98 GB | 无 Z 轴 AG |
| HP8×EP16，Z2 | 16 | 256 | 58.59 GB | 1.95 GB | 0.98 GB |
| HP8×EP8，Z4 | 8 | 256 | 58.59 GB | 3.91 GB | 2.93 GB |
| 纯 HP8，Z32 | 无 | 256 | 58.59 GB | 31.25 GB | 30.27 GB |

**同样 58.59 GB 持久态，动态 EP 可以从 256 降到 32，也可以进一步压到 8，甚至没有。付出的系统成本完全不同。** 第一阶段降低 EP 的好处主要靠头权重独立归属；再靠 Z 强压 EP 则逐渐变成每层搬大量权重。尤其纯 HP8/Z32，若假设每卡实效注入 200 GB/s，仅一次 30.27 GB AG 的传输下限约 **151 ms**，还没算可见程度、共存拥塞、临时峰值；相比 HP8×EP8/Z4 的 **约 14.6 ms**，已经不是同一类设计。用**模块分片、分块 materialization、跨微批权重复用、层间提前预取或 ETP**能改这个结果，但必须重新验证峰值显存、最慢 rank 与临界路径。不能从 MAGI-2 的方案直接宣布在这个算例里可把动态 EP 清零。

如果 64 GB/卡只用于上述 routed 持久态，PP8 保持不变，取整最低 H×E×Z 在 **10T/20T/40T** 时分别为 **235/469/938**；若用规则幂次分组示意，就是 **256/512/1024**。HP8、Z1 可对应 **EP32/64/128**；如果换成 16 B/参数，最低变成 **313/625/1250**，幂次示意为 **512/1024/2048**。强调：这些是 stage 分片下界，实际应按最重 stage、分片对齐、额外缓冲与冗余恢复预算核算。它们说明**动态 EP 域缩八倍，不代表物理高速域、stage 域或总卡数缩八倍**。如果为了藏住 AG/RS 把更多 Z rank 放回同一个快速池，这个池仍可能接近原先的大域规模。

还有一个独立方向：长上下文 CP 不因 FFN 被分头而变小。Attention/KDA/MLA 的并行、状态交换和长序列激活依然各算各的。[NVIDIA GTP](https://arxiv.org/abs/2611.32057) 在另一种 2T 模型上就把专家权重 gather 的暴露和 CP 跨 NVLink 域作为不同问题处理；论文在 8K、固定 EP64 下跑到 12,288 GB300，而不是每层建一个 12,288 卡 EP 组。它的指标不能移植到本算例，但能说明整项训练规模、最快互联覆盖和动态专家域三个数本来就不一样。另一方面，[Meta GEM](https://engineering.fb.com/2026/08/03/ml-applications/training-gem-at-llm-scale-meta-ads-recommendation-foundation-model/) 在推荐模型选择机内激活并行、跨机 FSDP，和 MAGI-2 Preview 的层级安排不同；该项目也观察到大模块的跨机参数交换盖不住。应根据各项字节量与预取窗口选择层级，不要给某一类 collective 硬编码唯一归宿。

## 5. 对超节点规格的建议：保留大规模能力，把“全域全速 EP”降级为一个选项

| 设计项 | 我建议保留的能力 | 决定该项规模的验收数据 |
|---|---|---|
| 一级高带宽岛 | 优先把动态 EP 与最频繁 AG/RS 放进去；支持多小组并发，同设备可组合但不假设无争用 | 用 EP32/64/128 的真实 token skew 测最慢 rank、交织 AG/RS 后的 BW、HBM 压力和 p99 暴露时间 |
| 二级超节点 | 保留多岛可达、较高割带宽与可重映射。静态 HP 可分层，CP 或高频权重通信按实测选一级还是二级 | 固定 shape HP 的 topologies、跨岛 CP、各岛同时出流的 bisection；不能用单组测速代表多组 |
| Scale-out 与故障域 | 支持有节奏的 DP/PP、跨系统 checkpoint 与通信降级；常规负载不用把路由扩成全局 | 计算/模型态恢复、慢岛隔离、跨机房链路饱和与多租户长尾；仅在质量或容量需要时扩动态 EP |
| 软件／芯片能力 | 固定 split All-to-All、collective overlap、可靠 AG/RS；小 M 低维 Grouped GEMM 和 fused router 是第一等能力 | 同一 FP16/BF16/低精数据和路由下测 kernel 时长、空专家处理、元数据、scale packing 及 tile fill；不以峰值带宽代替 |

**如果今天必须定计划，我不会取消大超节点，也不会让它只为一个千卡动态 EP KPI 买单。** 我会并行验证三条映射：

1. **传统／单头 latent 对照**：标准 EP 与 LatentMoE 同主干；测限节点和去重后需要的 EP 规模、FSDP 方案。保留这一条作为前沿文本模型主线的兼容能力。
2. **HP4／HP8 × EP32/64**：先保持相同 stage 权重分片数和总卡数，在同一拓扑下拆测固定 HP 和动态 EP，观察负载下的临界路径。不是只看小组独跑；要加 CP、共享专家、反向 AG/RS 叠流。
3. **减 EP、提高 Z 的反证**：分别跑 EP8/16 与多档 Z，看权重 gather 是否在可调的预取窗口内、额外临时空间有无顶掉激活预算。如果减少动态 EP 后 AG 成为第一瓶颈，就改分片或网络映射，不认为“已经解决互联”。

算整机收益时，只把**暴露在临界路径上的时间**计入可节省项。例：若原 step 有 20% 时间耗在动态 EP，优化后这段减半，但新增 HP、重排和参数 gather 占旧 step 的 6%，则 step 只缩短 4%，同 token/step 的吞吐约 +4.2%。若新增暴露时间超过 10%，即使跨岛动态字节锐减，step 仍变慢。反过来，若小岛能降低极端慢 rank、腾出 HBM 并提高可承载批量，收益也可能比这一固定批量算例大。超节点规划看**达标训练 token/卡时**和失败恢复，不看孤立 collective 峰值。

为了避免把模型与系统的收益混在一起，先做**同一个 MH checkpoint 的映射等价实验**：固定专家路由，在不同 H／E／Z 上比结果、loss 和 step；然后再做**架构对照**：单头、4/8 头、部分层多头，在相同训练 FLOPs、样本、训练 token 数和可比激活/总参数预算下，看交叉熵与实际应用，做不到全匹配就逐项列差异。记录 profiling-off step time、暴露通信、每个 head/expert 的真实 token 分布与并行占用。最后用长上下文、低批量 decode 和不同拓扑做联测。**只有文本能力持平，且压力测试下不靠大 Z 的搬运把瓶颈搬走，才有依据下调为动态 EP 专门预留的高速覆盖。**

最值得跟踪的，不是下一个模型发了多少个 MoE 头，而是它会不会公布三张能对在一起的表：**质量/训练 FLOPs、HP/EP/Z 拓扑、各 collective 的暴露时间与显存峰值。** MAGI-2 已让按流量分层从设想变成了公开工程案例；10T+ 规划应把这种可重映射能力做进超节点，而不是现在押注一种模型结构。
