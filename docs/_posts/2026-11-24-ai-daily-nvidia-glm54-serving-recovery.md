---
title: "AI 日报：黄仁勋复任 NVIDIA CEO，GLM-5.4 上线，训推系统重新核算显存与等待"
date: 2026-11-24T05:29:00+08:00
summary: "NVIDIA 董事会宣布黄仁勋复任，智谱推出循环式 GLM-5.4。HyperParallel 核对故障恢复供体；Megatron 重叠 Muon 通信；vLLM 与 SGLang 更新权重驻留和 KV 路径；两篇预印本分别研究训推同卡与智能体历史裁剪。"
section: daily
layout: post
label: "AI 动态"
tags: [NVIDIA, GLM, HyperParallel, Megatron, vLLM, SGLang, 昇腾]
demo: false
sources:
  - title: "NVIDIA：董事会恢复黄仁勋职务"
    url: "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Board-Reinstates-Jensen-Huang-as-President-CEO-and-Board-Director/default.aspx"
  - title: "NVIDIA 8-K：董事会决定与 EDGAR 受理时间"
    url: "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000090/0001045810-26-000090-index.htm"
  - title: "Z.ai：GLM-5.4 发布"
    url: "https://z.ai/blog/glm-5.4"
  - title: "HyperParallel #1443：MindIO 进程级恢复"
    url: "https://github.com/mindspore-ai/hyper-parallel/pull/1443"
  - title: "vLLM #69446：DeepSeek V4.1 H100 TP1 驻留权重"
    url: "https://github.com/vllm-project/vllm/pull/69446"
  - title: "Megatron #9681：FSDP Muon 通信重叠"
    url: "https://github.com/NVIDIA/Megatron-LM/pull/9681"
  - title: "SGLang #49467 / #49463：KV 会话引用与加载顺序"
    url: "https://github.com/sgl-project/sglang/pull/49467"
  - title: "vLLM-Ascend #20289：异步稀疏 KV D2H"
    url: "https://github.com/vllm-project/vllm-ascend/pull/20289"
  - title: "CTRL 和 Contexture：11 月 23 日 arXiv cs.DC 公告"
    url: "https://arxiv.org/list/cs.DC/2026-11?show=2000"
---

资料核验截至北京时间 2026 年 11 月 24 日 05:29，以下覆盖此前 24 小时内的公开公告、上游合入及 arXiv 公告。合入主线不等于已进入稳定版或公开容器；性能数字均沿用原报告的配置和口径，不是独立复测。

## 1. NVIDIA 董事会恢复黄仁勋的 CEO 和董事职务

**11 月 23 日 21:57:54，[SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000090/0001045810-26-000090-index.htm)受理 8-K。** [申报正文](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000090/nvda-20261122.htm)记载，董事会于美国当地时间 11 月 22 日决定恢复黄仁勋的总裁、首席执行官及董事职务，立即生效；公司于当地时间 11 月 23 日[公开宣布](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Board-Reinstates-Jensen-Huang-as-President-CEO-and-Board-Director/default.aspx)。Colette Kress 继续担任 CFO，Harvey Jones 继续担任董事会主席。

**为什么关注：** 管理层变更本身是供应商治理层面的新信息。公告没有公布 GPU 路线图、供货安排或产品规格变化，不能用复任推导交付时间或出口政策改变。采购规划仍应以产品、交付和监管的独立披露为准。

## 2. 智谱发布 GLM-5.4，循环的是中间层，不是重新生成一遍答案

**11 月 23 日，[Z.ai 发布](https://z.ai/blog/glm-5.4)。** 官方称这是公司首个采用 Loop Transformer 的旗舰：在 GLM-5 基础上让其中 28 层执行两遍，并面向包含视觉输入的广义编码任务。[官方开发文档](https://docs.z.ai/guides/llm/glm-5.4)确认 Coding Plan 已开放，标注 1M 上下文和 128K 最大输出；通用 Model API 仍待评估，官方博客只宣布了后续开放权重的计划。

**为什么关注：** 共享参数可以在不等量增加权重的情况下增加每 token 的计算深度，但不保证同等吞吐，也不意味着各轮 KV 可以全部共享。官方把能力描述为接近更大模型，不宜当作独立的同预算评测结论。验证时应把实际层执行次数、显存驻留、每 token 延迟和任务成功率分开。

## 3. HyperParallel MindIO：权重相同的 rank 不一定是完整恢复供体

**11 月 23 日 19:51，[HyperParallel #1443](https://github.com/mindspore-ai/hyper-parallel/pull/1443)合入。** 这条进程级快恢复路径不只检查模型权重的副本坐标，还按实际优化器状态所有权进一步分组。恢复时需要仍在线且拥有相应版本完整状态的 donor；两个 rank 的权重一致，并不意味着它们持有相同优化器分片。[合入代码](https://github.com/mindspore-ai/hyper-parallel/commit/6ac182ef1e9401b88f08c9c0450bd63bf6ee0a86)。

作者在单台 8 卡昇腾主机、缩减版 Qwen3 MoE、2×4 HSDP、混合 Muon/AdamW 的试验中报告了前向或反向期间退出、两次连续故障及四个 rank 同时退出后的精确状态与 loss 对齐。更新期间和元数据镜像阶段的故障测试则在 PRELOCK 超时后退出，没有启动替换进程。

**为什么关注：** 故障覆盖要按每个完整 donor 组在预期故障域内是否还有存活成员核算，不按「有两份权重」估算。这也不是节点级、机柜级故障或静默损坏的验证；成功启动进程与恢复到首个正确训练步是两项验收。

## 4. vLLM 在 H100 TP1 避免额外权重副本：省的是驻留，不是改变 checkpoint

**11 月 24 日 04:02，[vLLM #69446](https://github.com/vllm-project/vllm/pull/69446)合入。** 针对 DeepSeek V4.1，H100 上此前的自动线性层路径会生成 BF16 GEMM 权重，并在适用层额外生成打包的 FP8 decode 权重。TP1 的 rank 持有完整的稠密层；即使专家分布部署，也不能稀释这些稠密副本的开销。新 guard 在这一特定组合选择平台原有 MXFP8 路径，未同样修改 TP2 及以上或显式后端选择。

三种数字不能混用：[原八卡报告](https://github.com/vllm-project/vllm/issues/68647)在不同夜版间看到每卡权重驻留 **47.67→60.21 GiB**；作者保留真实稠密形状、使用 dummy 权重、缩减专家且未启用 Engram 与 MTP 的 TP1 对照为 **28.37→17.52 GiB**；**12.44 GiB** 是对完整特征配置的张量头估算，不是补丁后完整模型的实测。缩减测试以短提示生成 256 token，按整段 wall time 除以生成步数；一请求和八请求约慢 1.0% 与 0.6%，不能当线上逐 token 延迟。

**为什么关注：** 看显存应看加载后各 rank 实际驻留的所有张量，不能只用 checkpoint 位数乘参数量。降低权重驻留可能让 KV 池变大，但这次未测可用 KV、并发上限或者达标吞吐。

## 5. Megatron 将 Muon 矩阵的通信放到当前计算前后

**11 月 23 日 13:20，[Megatron #9681](https://github.com/NVIDIA/Megatron-LM/pull/9681)合入。** 新路径为后续矩阵提早发起分片 gather，当前 owner 在所需数据就绪后计算 Newton–Schulz，再异步发回更新分片。这不会改变 Muon 的数学算法，也不是减少通信字节；代价是更多在途工作及缓冲区生命周期。

作者在 64×GB200、EP64、七层 DeepSeek V4 配方中报告：同一新实现的 lookahead 0/2/8 对应 **1,217 / 986 / 848 ms** 的优化器区间。0→8 区间约降三成，但不是训练 step 整体降三成；各配置只跑了一轮，采样 rank 与 step 有限。8×H100 小模型一致性测试是另一组验证，不代表大模型长训收敛。

**为什么关注：** 优化前先画清每个矩阵实际重构的域，再看 gather、计算和 scatter 在拓扑上的重叠率，以及最慢 owner 和在途峰值显存。若该阶段原本只占全步一成，即便其时间降三成且其他阶段不变，整步吞吐也只约升 3%。

## 6. SGLang 将「预取页能否留住」与「何时可写目标槽」分开处理

**11 月 23 日 22:33–22:35，[会话引用 #49467](https://github.com/sgl-project/sglang/pull/49467)与[加载顺序 #49463](https://github.com/sgl-project/sglang/pull/49463)合入。** 前者在外部 KV 预取写入 radix tree 后即登记会话引用，防止尚未入场的请求因引用缺失而过早被驱逐；这是优先保留，不是无条件固定在显存。后者只在索引就绪后提前解析槽位置，get session 和实际 range get 仍等前序 forward 栅栏，避免写到还在使用的槽。

在 24×B300、1P2D、640 会话重放前 13 分钟中，作者报告 prefetch 对照里排队淘汰从匹配 token 的 **1.5%→0.0%**，平均 TTFT **2.27→2.08 s**；两组都带有其他未合入该 PR 的 prefetch 改动。另一个 layer-wise 测试中栅栏释放后首组数据到达时间 p50/p90 **19/63→15/49 ms** 是位置准备与 read-done 联合结果（批次至少 2 GB），且两组都比主线提早打开 get session。两种路径不能叠加数字，也没有测出各自在纯主线条件下的收益。

**为什么关注：** 有效指标不止是存储读取成功或字节率，还包括请求入场实际消费的连续前缀、排队中被淘汰的匹配 token、栅栏后首层可用时间。

## 7. 昇腾稀疏 KV：把 D2H 搬进前向窗口，但不取消退役栅栏

**11 月 23 日 16:12，[vLLM-Ascend #20289](https://github.com/vllm-project/vllm-ascend/pull/20289)合入。** 在启动设备到主机拷贝前冻结 block、slot、generation 等信息；复制流等待上一轮真实 KV 写入完成，与下一轮前向重叠。下一次执行开始时先完成必要的退役，再改动请求或复用槽。只有成功完成且 generation 对应的前缀才可晋升；校验 generation 不是物理槽生命周期保护的替代品。这条路径仍用原有稀疏拷贝，不是新增 SDMA 后端。

作者跨主机对照的顺序为同步 D2H→异步 D2H→再加融合 prolog：输出吞吐 **1,310→1,388→1,506 tok/s**，TPOT **22.6→21.2→19.6 ms**。第一步才是拷贝重叠的对照；最终约 15% 的吞吐提升含算子融合。公开结果没有覆盖广泛负载和尾延迟，不能外推到所有昇腾配置。

## 8. 两篇研究论文：训推同卡与 Agent 历史裁剪，分别在测什么

**11 月 23 日，列入 [arXiv cs.DC 当日公告](https://arxiv.org/list/cs.DC/2026-11?show=2000)，两篇均为 v1、11 月 20 日提交。**

- [CTRL](https://arxiv.org/html/2611.27119v1)让每张 GPU 同时驻留 learner 与 rollout，通过 CUDA MPS 分享计算；优化器状态放在主机，训练权重走有界窗口，发布新策略前约束最旧的行为版本。8×H100、512 trajectories、配置滞后上限 2 时，作者报告三种子平均 **13,814 learner tokens/s**，为 stock verl 异步分时 **1.23×**、相同 learner 的 4+4 整卡拆分 **1.10×**。这里是学习器每墙钟秒消费的 prompt 加 response token，不是 decode 输出吞吐或 MFU；显存交换、重复 prefill 和权重发布仍有成本。
- [Contexture](https://arxiv.org/html/2611.26980v1)保留 Agent 的完整记录，按工具结果是否被后续操作替代来筛执行上下文；是否真的移除还要考虑共享 KV 压力和裁剪中段后重算的代价。八组配置的重放对照报告，在论文定义的会话 P90 slowdown 上限 10× 下，比不裁剪、harness compaction、AgentDiet 和 Continuum 四类比较组中最优者多完成 **20%–73% 会话/分钟**；完成指在任务时限内结束，不等于通过任务验证。完全 live 的吞吐对照覆盖更窄，不能把重放区间当作普适线上收益。

## 今日判断

今天几组数据指向同一条工程原则：**先区分为了快路径额外驻留的内存、为正确性不能跨越的栅栏，再测端到端结果。** 想比较部署方案，优先记录最紧 rank 的实际驻留、在请求入场时真正可消费的前缀、以及固定 SLO 和质量预算下的有效吞吐。单个内核、单个阶段或权重包的数字不应替代这些验收。
