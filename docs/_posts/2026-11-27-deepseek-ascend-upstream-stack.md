---
layout: post
title: "DeepSeek 开源两个月更新：把 950DT 的通信、低精算子和 V4.1 推理链拆开看"
date: 2026-11-27T18:23:00+08:00
last_modified_at: "2026-11-27"
summary: "追踪 DeepEP-Ascend V1.1、DeepGEMM、FlashMLA、DeepSelect、DeepJIT 和 DeepInfer 的公开提交，核对 950DT 的 EP 带宽、低精算子、实际运行时依赖，以及训推下一步该怎么测。"
section: explainer
label: "DeepSeek 源码与昇腾系统"
tags: [DeepSeek, 昇腾, 950DT, DeepEP, MoE, 低精度, 推理]
demo: false
sources:
  - title: "DeepEP-Ascend V1.1 合入 #32"
    url: "https://github.com/deepseek-ai/DeepEP-Ascend/pull/32"
  - title: "DeepGEMM-Ascend 11 月更新 #35"
    url: "https://github.com/deepseek-ai/DeepGEMM-Ascend/pull/35"
  - title: "FlashMLA 昇腾融合与 head128 #255"
    url: "https://github.com/deepseek-ai/FlashMLA/pull/255"
  - title: "DeepInfer 公共主线快照与子模块"
    url: "https://github.com/deepseek-ai/DeepInfer/tree/a679bb86ce36e883a98a97733492b686e5b9a08e/vendor"
  - title: "vLLM Ascend 950DT V4.1 Flash 双机部署更新"
    url: "https://github.com/vllm-project/vllm-ascend/pull/23365"
---

**过去两个月，DeepSeek 在昇腾上最大的进展，是从「有一批算子」走到「有一套可以追到源码的 V4.1 运行链」。** 9 月底公开 950 算子与通信库，10 月公开 DeepInfer 离线引擎，11 月底又集中更新通信、注意力和融合 MoE。但代码阅读揭示了一个比峰值更重要的事实：**公开 DeepInfer 主线不只锁着较早的 FlashMLA，模型层还显式把融合注意力开关限制在 GPU。** 因此，库里已有新算子、模型跑得起来、线上实际启用新算子，是三个需要分别举证的问题。

复核窗口为 **2026 年 9 月 27 日至 11 月 27 日**。在 [deepseek-ai 的 47 个公开 GitHub 仓](https://github.com/orgs/deepseek-ai/repositories) 中，组织级检索返回 66 个已合 PR 候选；另查重点仓默认分支历史、直接提交和子模块，不把检索结果当成所有 Git 合并的总数。下文区分上游主线、上游开发分支、合作生态和作者报告的实测。未在本次研究中独立运行任何 NPU 测试。

## 一、两个月到底合了什么？

| 时间 | 公共仓与改动 | 昇腾工程意义 |
|---|---|---|
| 9/29–30 | [DeepEP-Ascend 首次公开](https://github.com/deepseek-ai/DeepEP-Ascend/tree/3b25377)、[DeepGEMM-Ascend 首发](https://github.com/deepseek-ai/DeepGEMM-Ascend/tree/8491bbb)、[FlashMLA #229](https://github.com/deepseek-ai/FlashMLA/pull/229)、[DeepSelect #23](https://github.com/deepseek-ai/DeepSelect/pull/23)、[TileKernels v2.0 #34](https://github.com/deepseek-ai/TileKernels/pull/34) | 集齐 950 的 EP、低精 GEMM、V4.1 稀疏注意力、TopK 与通用量化算子。FlashMLA 同步切换缓存格式、移除主线旧模型和 Hopper 支持。 |
| 10/14–20 | [DeepGEMM-Ascend #12](https://github.com/deepseek-ai/DeepGEMM-Ascend/pull/12)、[TileKernels v2.1 #38](https://github.com/deepseek-ai/TileKernels/pull/38)、[DeepInfer 首发快照](https://github.com/deepseek-ai/DeepInfer/tree/d585e6542c0571176272d703f03c4807ae901284)、[deepseek-recipe 0.2](https://github.com/deepseek-ai/deepseek-recipe/blob/93b0fd2/CHANGELOG.md) | 算子端补 sparse/paged MQA 打分和 GEMM 接口；引擎提供 V4.1-Flash-1017 离线运行。recipe 提供 prompt 编码与流式解析，覆盖工具调用、续写、推理段和 logprobs。 |
| 11/3–24 | [EP #8](https://github.com/deepseek-ai/DeepEP-Ascend/pull/8)、[DeepJIT #38](https://github.com/deepseek-ai/DeepJIT/pull/38)、[#48](https://github.com/deepseek-ai/DeepJIT/pull/48)、[#53](https://github.com/deepseek-ai/DeepJIT/pull/53) | 迁移官方 SIMT API，加入并行预编译和按需 AICPU 启动；PyTorch 2.13+ 可走稳定 C++ ABI 获取 NPU stream。 |
| 11/26–27 | [DeepGEMM-Ascend #35](https://github.com/deepseek-ai/DeepGEMM-Ascend/pull/35)、[FlashMLA #255](https://github.com/deepseek-ai/FlashMLA/pull/255)、[DeepSelect #37](https://github.com/deepseek-ai/DeepSelect/pull/37)、[DeepEP-Ascend V1.1 #32](https://github.com/deepseek-ai/DeepEP-Ascend/pull/32)、[TileKernels v2.2 #51](https://github.com/deepseek-ai/TileKernels/pull/51) | 从单算子扩到注意力与 MoE 融合、FP32 TopK 和归约、冗余专家及 CP/DP 通信原语。v2.2 的源码变更覆盖两套后端的量化、SwiGLU、mHC、Engram 和 MoE gate 等路径。 |

## 二、DeepEP-Ascend V1.1：从搬 token 到管理专家和多种通信

**初始化和数据面要分开。** [拓扑发现代码](https://github.com/deepseek-ai/DeepEP-Ascend/blob/f5ea304/csrc/comm/topology.cpp#L127-L152) 先从本地 CANN 拓扑接口取得域与 plane 信息，再用 PyTorch ProcessGroup 交换各 rank 的报告；本地探测失败也进入交换，避免一端抛错、其他 rank 等不到。新版移除了 HCOMM bootstrap、拓扑探测和 UBMEM 通道对 HCCL runtime 的直接依赖。[构建仍链接](https://github.com/deepseek-ai/DeepEP-Ascend/blob/f5ea304/setup.py#L130) HCOMM、AscendCL、torch_npu 和 topoaddrinfo，应用层也仍可选用 HCCL ProcessGroup。跨 scale-up 域还有 UB_RTP 通道前提。这里的 plane 是该通信栈的拓扑信息，不应用来推导以太网的多轨或多平面部署。

DeepJIT 的 [AICPU bootstrap #48](https://github.com/deepseek-ai/DeepJIT/pull/48) 把按需编译的 loader 放进应用的 AICPU 调度进程，才能访问该进程的 URMA/UBMEM 资源；并行预编译则把编译与正式运行分开。[#53](https://github.com/deepseek-ai/DeepJIT/pull/53) 在 950/CANN 9.3/PyTorch 2.13 上通过了作者报告的 AICPU、SIMD/SIMT 等功能测试。稳定 ABI 去掉的是相关扩展对 `libtorch_npu.so` 的**直接链接**，不是运行模型无需 torch_npu。另需留意，DeepEP-Ascend V1.1 固定的 DeepJIT 子模块是 `b1221a1`，早于 #53；不能把单独仓的最新构建能力当成 V1.1 的默认依赖。

**训练最值得跟的是冗余专家的完整数据闭环。** [三个公开接口](https://github.com/deepseek-ai/DeepEP-Ascend/blob/f5ea304/deep_ep/buffers/ep.py#L642-L728) 分别做统计和物理 slot 重映射、向冗余 slot 预取专家权重、按同一张映射把副本的 FP32 梯度累加回原专家。预取提交与 CQ 完成、退出屏障分开，调用侧需要显式等待正确的 handle。路由重映射减少最慢 rank 的负担，但复制权重消耗显存和带宽，反向还要回收梯度；只有省下的**关键路径**时间大于新增暴露时间，整步才会变快。开源代码提供了原语，没提供百卡训练收敛或端到端 MFU 提升的结果。

**EP、Bucket 的能力范围不能混用。** V1.1 增加 buffer resize、FP32 combine、确定性 FP32 all-reduce、可跨域的 Bucket reduce-scatter/all-gather，以及 CP ring 和 standby buffer 接管。CP ring 与冗余专家的权重/梯度交换仍限于 scale-up 域；Bucket 有混合域能力，不能据此宣称 EP 的 hybrid dispatch/combine 或 EP 图捕获已支持。[README 的限制](https://github.com/deepseek-ai/DeepEP-Ascend/blob/f5ea304/README.md#ongoing)也保留了 PP/Engram 的实验性质。备用 buffer 和可恢复错误提高了上层可控性，但不等于训练进程可无回滚续跑；要跟踪恢复后首个成功 collective 和首次完成的优化器更新。

### EP64/128 跑到三百多 GB/s，究竟测了什么？

| 规模 | Dispatch | Combine |
|---|---:|---:|
| EP8 | 373–375 GB/s | 345–347 GB/s |
| EP64 | 323–327 GB/s | 294–298 GB/s |
| EP128 | 313–320 GB/s | 272–278 GB/s |

这是 [DeepEP-Ascend README](https://github.com/deepseek-ai/DeepEP-Ascend/blob/f5ea304/README.md#performance) 的 **950DT、CANN 9.2、手工配置 PoC HDK** 数据，测试用外部 Clos、16,384 tokens/rank 容量、hidden 7168、top-6、256 experts、FP8 dispatch 和 BF16 combine。范围是各 rank，不是重复运行的置信区间。两列分别用本阶段时长，含 issue/drain，不含最终 epilogue；[测试分子](https://github.com/deepseek-ai/DeepEP-Ascend/blob/f5ea304/tests/ep/test_ep.py#L412-L416)按收 token 的逻辑张量字节计算，**包括本地 token**，不等于 TX+RX 板端计数，也不能把两个 GB/s 直接相加。初版 [`3b25377`](https://github.com/deepseek-ai/DeepEP-Ascend/blob/3b25377/README.md#performance) 就有同一张表，因此它不是 V1.1 的 A/B。可比较的做法是分别给出逻辑字节口径、物理链路双向计数、完整调用及整层外露时间。

## 三、低精栈：位宽、数据移动与融合要分账

### DeepGEMM-Ascend：同样的 4-bit 权重，有两条完全不同的上限

![950DT 大形状稠密 GEMM 微基准：BF16 乘 BF16 431，FP8 乘 FP8 和 FP8 乘 FP4 均为 861，FP4 乘 FP4 为 1701 TFLOP/s。]({{ '/assets/deepseek-ascend-bench-gemm.svg' | relative_url }})

*图解：据下文链接的 DeepGEMM-Ascend README 重绘。CANN 9.2 微基准，不是 11 月新版本 A/B，也不是 decode 实测。* [查看原图]({{ '/assets/deepseek-ascend-bench-gemm.svg' | relative_url }})。

[950DT 冷 L2 大矩阵基准](https://github.com/deepseek-ai/DeepGEMM-Ascend/blob/fd5d22d/README.md#dense-gemm)的形状统一为 M=4096、N=7168、K=16384：

| 输入乘法格式 | 实测 | 项目采用的峰值口径 |
|---|---:|---:|
| BF16 × BF16 | 431 TFLOP/s | 432 TFLOP/s |
| FP8 × FP8 | 861 TFLOP/s | 865 TFLOP/s |
| FP8 × FP4 | 861 TFLOP/s | 865 TFLOP/s |
| FP4 × FP4 | 1,701 TFLOP/s | 1,730 TFLOP/s |

在这组大形状下，**W4A8 和 W8A8 的矩阵峰值同档**。W4A8 的价值还包括权重更小、可能降低小 M 的搬运成本；上表不能保证小 M 加速，更不能用 W4A4 行的 1,701T 代入 W4A8。比如同一份基准的 FP8、N=2112、K=7168，M=128 只有 **258T**，M=4096 才到 **790T**。同样的实际模型，decode 的 expert token 偏斜会进一步改变每个分组的 M。README 的这组测量标 CANN 9.2，而 11 月新源码最低要求 **CANN 9.3.0**；不能把它包装成 #35 前后的提升。

[11 月实现](https://github.com/deepseek-ai/DeepGEMM-Ascend/pull/35)更有价值的是把数据再读写和串行段缩短：MegaMoE 合并 dispatch、两次 grouped GEMM、SwiGLU 和 combine，可选 combine 后 FP32 RMSNorm，针对偏斜和低延迟 decode 加路径；Shifted mHC 推理可做 NPU 图回放。FP8 随机舍入是部分输出 epilogue 的选项，不代表整个训练图用了 FP8 梯度，更不证明收敛。还有一个移植陷阱：昇腾端按 K 成对把 UE8M0 scale 打包进 int16，并采用 MN-major。**接口兼容不等于权重、scale 和 KV 布局可以原样共享。**

### FlashMLA 与 DeepSelect：DSA 要测整条链，不能只测 attention

![DSA 的数据路径：MQA 打分、TopK 选位置、按索引读稀疏 KV。核对版本和开关后，再检查实际调用的算子。]({{ '/assets/deepseek-ascend-dsa-stack.svg' | relative_url }})

*图解：按下文公开调用链重绘，模块名为对应实现，不表示所有引擎都使用同一版本或融合路径。* [查看原图]({{ '/assets/deepseek-ascend-dsa-stack.svg' | relative_url }})。

V4.1 的索引器先做 MQA logits 打分、做 TopK，再按索引读取稀疏 KV。[DeepInfer 的索引器实现](https://github.com/deepseek-ai/DeepInfer/blob/a679bb8/deepinfer/model_executor/models/v4_modules/index_attn.py)能看到 paged/sparse MQA 与 DeepSelect 的衔接。DeepSelect 11 月追加昇腾 FP32 TopK，打开采样和 logits 提取的另一段；其 README 的对比是特定形状上的 `torch.topk`，不是全模型的速度比。

[FlashMLA #229](https://github.com/deepseek-ai/FlashMLA/pull/229)把 V4.1 decode KV 改为 **量化值、scale 按 token 相邻**。典型 FP8 记录为 512+16=528 B；FP4 是 256+32=288 B，但该接口规定 FP4 只用于 FP8 主 cache 的 extra cache。此处是算子记录格式，不等同于完整模型的 KV 字节/token，也不能假设旧 checkpoint 所在引擎、P/D 传输或外部池能直接互换缓存。11 月 [#255](https://github.com/deepseek-ai/FlashMLA/pull/255) 增加 128 个 Q heads 和融合路径，把 Q 侧 RoPE、注意力、O 侧逆 RoPE 与 FP8 cast 连成一段；接口支持可选 Q-norm，V4.1 不用该选项。

README 公布普通稀疏 prefill/decode 的最高值从 **410/360** 更新到 **425/372 TFLOP/s**；新融合路径另报 **406/350**。这些是各自公开的最高值，不能视为同形状整机 A/B。融合应与「拆开版各阶段的耗时总和」比较，可能省的是 launch 和中间张量 HBM 写回，不需要核心矩阵 FLOP/s 更高才有收益。该仓的稠密 MHA 前反向核仍标为 CUDA only，不能拿 Ascend 的推理 FlashMLA 证明通用 MHA 训练反传。

## 四、调用链核查：这批 11 月合入跑到哪里了？

| 路径 | 公开快照能确认的事实 | 还不能下的结论 |
|---|---|---|
| DeepInfer 上游默认分支 | [`a679bb8` 的 vendor](https://github.com/deepseek-ai/DeepInfer/tree/a679bb86ce36e883a98a97733492b686e5b9a08e/vendor) 固定 EP `3b25377`、GEMM `3a35326`、FlashMLA `2e5429f`、DeepSelect `bfa4507`。 [注意力开关](https://github.com/deepseek-ai/DeepInfer/blob/a679bb8/deepinfer/model_executor/models/v4_modules/attn.py#L84-L92)还要求 `PLATFORM.is_gpu`；[MegaMoE 开关](https://github.com/deepseek-ai/DeepInfer/blob/a679bb8/deepinfer/model_executor/models/v4_modules/mlp.py#L177-L188)允许昇腾 FP8×FP4；名为 is_within_nvl_domain 的 [拓扑辅助函数](https://github.com/deepseek-ai/DeepInfer/blob/a679bb8/deepinfer/model_executor/parallel_utils/parallel_state.py#L130-L134) 在 NPU 分支直接返回 True，这个开关本身不是跨域能力证明。 | 单独升级子模块就会走 Ascend fused attention；或 11 月新算子已在正式服务运行。README 的离线吞吐曲线来自 SM100，batch-invariant 与确定性采样也限定 NVIDIA。 |
| vLLM Ascend 独立适配 | [1017 部署文档](https://github.com/vllm-project/vllm-ascend/blob/main/docs/source/tutorials/models/DeepSeek-V4.1-Flash.md#72-accuracy-results)公开 A3 W4A8 与 950DT 原生 MXFP 两套部署，GPQA **89.9 / 90.4**。[#23365](https://github.com/vllm-project/vllm-ascend/pull/23365)给出双机 DP8/TP1、Mooncake V2 传输与 Memcache，`enable_fused_mc2: 3` 依赖 `cann_ops_transformer`。 | 不同硬件和量化配置的 0.5 分差不能单独归因。新双机配方只做了文档、脚本和 CI 校验，PR 明确未实机验证该配置；同名 MegaMoE 并不能证明调用了 DeepGEMM-Ascend #35。 |

运行时小细节决定能否上线。例如 [#21397](https://github.com/vllm-project/vllm-ascend/issues/21397)记录过 950DT 上原生 MXFP routed-expert 路径：1017 的中间维度 2304 在 TP8 下 gate+up 为 576，不满足该 SwiGLU 量化核要求的 128 对齐。这是一个特定版本及执行路径的证据，不是「950 不支持 TP8」。 [外部 KV 命中](https://github.com/vllm-project/vllm-ascend/blob/3ed46a4360b375b0bd28d8382d8d310bcb66f157/docs/source/tutorials/models/DeepSeek-V4.1-Flash.md#L1922-L1953)也应独立验证：先关本地 prefill 前缀缓存，复用相同前缀并换后缀，采集所有 prefill rank 的计数、MetaService DRAM get-hit 增量和实际 load 日志。Decode 的 external hit 还包含 PD 传输，不足以辨认 DRAM hit。

## 五、旁线更新：NVIDIA、存储、客户端

- **NVIDIA 通信和算子同步演进。** [DeepEP V2.5](https://github.com/deepseek-ai/DeepEP/pull/763)拆分 EP/PP/Engram/Bucket，去掉 V1/NVSHMEM，使用 DeepJIT；[V2.6](https://github.com/deepseek-ai/DeepEP/pull/841)补跨域冗余映射、copy-engine collective 图捕获、CP ring 和 FP32 combine。 [CUDA DeepGEMM 11 月版](https://github.com/deepseek-ai/DeepGEMM/pull/525)也补了低延迟 MegaMoE、RMSNorm 与 FP8 随机舍入。相近 API 方便共享上层调用，但 NVLink/RDMA 的同步与访存不等于 UBMEM/URMA。
- **RTX PRO 6000 是拓扑决定性能的一个对照。** DeepInfer [SM120 #289](https://github.com/deepseek-ai/DeepInfer/pull/289)和 [Cake MegaMoE #291](https://github.com/deepseek-ai/DeepInfer/pull/291)合到 `nv-dev`，不是默认主线。八卡测试的 decode **7.18→9.93 steps/s**，prefill **4520→4457 tok/s/GPU**。旧路径的大量 peer 数据绕 NIC，新路径能利用可达的 PCIe P2P，并融合 MoE 步骤；改变了传输与执行两件事，不能归因于单个 kernel，也不能外推昇腾。
- **存储可关注正确性，客户端不混入 NPU 结论。** 3FS 补了 [COW 截断保护并发读](https://github.com/deepseek-ai/3FS/pull/461)、[崩溃恢复保留删除意图](https://github.com/deepseek-ai/3FS/pull/462)及 [RocksDB 迭代错误传播](https://github.com/deepseek-ai/3FS/pull/464)。这些是正确性改进，不是训练 IO 带宽提升。 [DeepSeek Harness 0.2.3-alpha.2](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.2.3-alpha.2)属于客户端与插件生态。

## 六、如果资源有限，先做哪三组验证？

1. **通信：先把 EP 的数字换成 step 瓶颈。** 在固定商用 HDK、拓扑、rank 映射与路由分布下对照 V1.0/V1.1；分别扫小 batch、饱和流量和真实偏斜，在 EP64/128 记录 dispatch、combine、epilogue、最慢 rank 和与 GEMM 重叠后的暴露时间。启用冗余专家时，再记权重搬运字节、等待时间、梯度归约、峰值显存和最终的 step A/B。跨域先验明通道和拓扑，不用 API 名称代替验证。
2. **推理：先确认符号确实被调用，再比较性能。** 固定 1017 权重、引擎和 CANN 版本，记录实际加载模块、算子名与图模式。拆开测试 attention 融合、MoE 融合和 KV 池；前两项固定 KV 精度/预算与路由，池化性能另扫复用率和容量。用相同的到达率、输入输出分布，先固定推测解码配置并记录实际接受率，再报告 TTFT/TPOT、p95/p99、客户端 SLO goodput 和接受的输出 token。可参照[此前的昇腾 KV 命中正确性解读]({{ '/2026/11/26/ascend-kv-hit-correctness-gates/' | relative_url }})。
3. **训练：先做数值及故障门禁，再计 MFU。** 锁定框架调用路径，比较 FP32 归约、EPLB 梯度回收、CP ring 与基线的数值、重算、显存及暴露时间，测恢复后首个真正进入更新的 step。MFU 的分子用模型约定的有效 FLOPs，分母用同一精度口径的硬件峰值乘实际总步时；不要把 EP effective GB/s、GEMM 峰值和训练 MFU 混成一列。

**结论：** 950DT 现在已有公开实现、单项实测和可检查的 1017 模型部署，尤其值得看 EP 专家复制闭环和低精融合；真正缺的是**同一运行栈上，11 月新提交前后的端到端对照**。下一轮验证应该先查路径有没有启用，再看省掉的是哪段关键路径。
