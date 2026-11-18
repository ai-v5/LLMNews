---
title: "NVIDIA Rubin 低精度实测：FP8 训练、FP4 推理，以及 50 PFLOPS 的适用边界"
date: 2026-11-18T17:50:00+08:00
summary: "拆开 Rubin 的稠密与稀疏峰值、真实 SM107 算子、模型精度和 MLPerf 整机结果。FP8 训练和 FP4 推理已有强证据，FP4 大模型从零训练仍缺 Rubin 同机等质量对照。"
section: explainer
label: "芯片与训推系统"
tags: [NVIDIA, Rubin, FP8, FP4, NVFP4, MLPerf, 低精度]
demo: false
---

**结论先说：Rubin 已经证明 FP8 能把千卡训练做快，也证明 FP4 能在真实推理栈中发挥作用。尚未证明的是：Rubin 上把同一大型 MoE 的训练从 MXFP8 切到 NVFP4，能以相同质量获得多少净加速。** 峰值、算子 A/B、质量和端到端结果分别回答不同问题，不能拿其中一个替代另外三个。以下以截至 2026 年 11 月 18 日可核对的公开资料为限。

## 一、R200、VR200 和 50 PFLOPS 各指什么

NVIDIA 正式规格称 **Rubin GPU**；其基准表明确使用 **VR200-288GB**。部署商 [Verda](https://verda.com/blog/nvidia-vr200-r200-early-deployments) 在标题中用 R200 指向 HGX Rubin NVL8 的部署、用 VR200 NVL72 指向 Vera Rubin 机架。不要仅凭缩写给 R200 和 VR200 分配两套芯片 Time-to-Train；应核对实际系统。Rubin 的 CUDA 计算能力是 **10.7 / SM107**，不是 SM110。每个 Rubin GPU 封装有两个计算 die；一个 Vera Rubin Superchip 是 2 GPU＋1 CPU，NVL72 是 72 GPU＋36 CPU。下表每列都按 NVL72 系统内的一颗 GPU，而非一个 die 或一个 Superchip。

| 单 GPU 官方峰值 / 带宽 | GB200 NVL72 | GB300 NVL72 | Vera Rubin NVL72 | Rubin / GB300 |
|:--|--:|--:|--:|--:|
| FP8/FP6 稠密，PFLOPS | 5 | 5 | 17.5 | 3.50× |
| FP4 稠密，PFLOPS | 10 | 15 | 35（官方训练口径） | 2.33× |
| FP4 稀疏，PFLOPS | 20 | 20 | 50（官方推理口径） | 2.50× |
| BF16/FP16 稠密，PFLOPS | 2.5 | 2.5 | 4 | 1.60× |
| HBM 容量 | 186 GB（按当前规格页） | 288 GB | 288 GB | 1.00× |
| HBM 带宽 | 8 TB/s | 8 TB/s | 19.2 TB/s | 2.40× |
| NVLink 双向合计带宽 | 1.8 TB/s | 1.8 TB/s | 3.0 TB/s | 1.67× |

来源：[Rubin NVL72 规格与脚注](https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/)、[GB200 NVL72](https://www.nvidia.com/en-us/data-center/gb200-nvl72/)、[GB300 NVL72](https://www.nvidia.com/en-us/data-center/gb300-nvl72/)、[Blackwell Ultra 数据表](https://resources.nvidia.com/en-us-gpu-resources/blackwell-ultra-datasheet)。Rubin 整架 3600/2520/1260 PFLOPS 分别对应表中的稀疏 FP4、稠密 FP4、稠密 FP8/FP6。**50 不能除二当作稠密 FP4，也不能拿 50÷17.5 当作从 FP8 量化到 FP4 的收益。** 同为稠密、按表内口径，Rubin 的 FP4/FP8 峰值比是 2.00×，GB300 是 3.00×；代际增幅最大的是 FP8，不是 FP4。官方把 FP8/FP6 合列，并未为任意 FP8 配方、缩放方式和 GEMM 形状逐一承诺此峰值。

带宽也要锁版本和平台：Rubin **NVL72 官方产品页现用 19.2/3.0 TB/s**，旧架构文章及 [HGX 页](https://www.nvidia.com/en-us/data-center/hgx/) 部分单卡栏仍显示 22/3.6。做容量与性能预算用实际选定系统，不把这些数字拼到一个配置上。功耗同理；机架 MaxP、MaxQ、MaxLPS 是不同运行配置，不能直接视作单 GPU TDP 或实测功耗。GB200 容量按当前产品页两个 GPU 共 372 GB 换算；若设备标 192 GB，请以具体 SKU 和运行时可用容量为准。

## 二、低精度究竟改了哪一段

| 公开格式/路径 | 数值和缩放 | 对实际性能的含义 |
|:--|:--|:--|
| FP8 E4M3 / E5M2 | E4M3 多一位尾数；E5M2 指数范围更大。张量或分块缩放需另记。 | 都是 8 位输入，训练中前向、反向选择可不同；不能因格式同宽推断精度、吞吐相同。 |
| MXFP8 / MXFP4 | OCP MX：每 32 个元素共享 E8M0，FP4 元素为 E2M1。 | MXFP8 约 8.25 bit/元素，MXFP4 约 4.25；未计 padding、额外元数据和未量化模块。 |
| NVFP4（常规 E4M3 配方） | E2M1 数据，每 16 元素一个 E4M3 局部 scale，再叠加张量级缩放。 | 约 4.5 bit/元素，加张量尺度与对齐。小块和更细的局部尺度能减少部分离群损失，不消除舍入误差。 |
| W4A8 / W4A4 / W4A16 | 分别写明权重和激活位宽；KV、累加和输出另外记录。 | W4A8 可走原生混合 MMA；W4A16 可能先解包或反量化，不能领用 W4A4 的峰值。 |

格式依据：[OCP MX 规范](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)、[Transformer Engine NVFP4](https://docs.nvidia.com/deeplearning/transformer-engine/features/low_precision_training/nvfp4/nvfp4.html)。以实际内核为准：例如 CUTLASS 的 SM107 FP4 测试有 FP32 累加；这不代表所有变体或训练图都固定该累加策略。

Rubin 有三个更具体的变化。[NVIDIA 架构说明](https://developer.nvidia.com/blog/inside-nvidia-rubin-gpu-architecture-powering-the-era-of-agentic-ai/)和 [PTX ISA](https://docs.nvidia.com/cuda/parallel-thread-execution/index.html)显示：

- **加宽 K 维 MMA。** 对支持的路径，每条指令处理更多 K 元素；收益可能体现在发射、搬运和循环开销，而不只是峰值 TFLOPS。
- **3-bit LUT 存的是索引，不是通用 FP3 运算。** `tcgen05.mma` 的 `.decompress::lut::b` 让 B 操作数通过片上 LUT 恢复 E4M3；PTX 对 B 的类型、布局和架构目标有限制。厂商所说可接近 MXFP8 精度不是所有模型、所有层的质量保证。另有面向特定 NVFP4 指令的 UE5M3 缩放支持；不要把它与常规 E4M3 recipe 或 LUT 压缩混为一谈。
- **稀疏可以出现在注意力中间值。** 架构示例先做稠密 QK，再把中间值压成 2:4，随后执行相应 softmax 和稀疏 PV。它既不意味着 FP4 自动稀疏，也不能无条件假设动态压缩的精度和开销为零。

## 三、真正在 SM107 上跑过的算子

| 原始实测 | 条件 | 实测变化 | 能证明什么 |
|:--|:--|:--|:--|
| vLLM MegaMoE | DeepSeek-V4.1-Flash；同一 Rubin 上较旧 MMA 路径 vs SM107 K64 MXFP8×MXFP4；每 rank ≥8K tokens | 吞吐 **+8–11%** | 原生混合 MMA 和打包布局对大 token 批有实用增益。 |
| vLLM routed GEMM | 同 Rubin，低 batch 的路由专家 GEMM | **快约 12%** | 小批也受益，不能据此推算所有 shape。 |
| vLLM query up-projection | `[M,1280]×[1280,32768]`，M=4K–32K；cuDNN 旧内核换 FlashInfer CuTe DSL 的 SM107 K64 路径 | 内核 **快 13–18%**；16K–32K 的 DEP2 step 时间少 **1.1–1.7%** | 量出了局部收益传到整步后有多小；同时改了库和内核，非单变量微架构对照。 |
| vLLM decode MQA logits | K128 FP4 MMA 和 6-token query tile 一并启用 | **快 15–22%** | 量到的是指令与 tile 联合收益，不是 FP4 单因素。 |
| cuDNN FROST gated attention block | Rubin 212 SM，B=1、d_model=4096、Q/KV heads=32/2、head dim=256；同一 causal shape 比较融合路径 | 4K：MXFP8 **4.75×**，MXFP4 weights **4.84×**，MXFP4 weights＋NVFP4 O **4.87×**；32K 对应 **3.39×/3.41×/3.47×** | 三列相对同一 BF16 PyTorch 链，并非 FP4 比原生 FP8 快 4.87×。4K 只换 MXFP4 weights，融合 block 约增 **1.9%**；长序列部分差异落在控制组波动内，长形状还受功耗限频。另外，32K 非因果形状的两个融合 NVFP4 O 模式相较各自未融合版本慢了 11–12%，不是所有形状都应开启。 |

数据来自 [vLLM 真实权重与 token 的 forward profiling](https://vllm.ai/blog/2026-11-12-deepseek-v41-flash-vera-rubin) 和 [cuDNN Gated Attention Block](https://docs.nvidia.com/cudnn/fe-oss-apis/gated_attention_block/)。cuDNN 的 block 包含 projection、归一化、RoPE、SDPA、gate 和输出投影，不是裸 GEMM；FP4 只改部分阶段。vLLM 的低精指令 A/B 也不是 GB300 更换成 Rubin 的纯硬件对照。

[CUTLASS 4.8](https://docs.nvidia.com/cutlass/4.8.0/overview.html) 已有 SM107 稠密 FP8 与分块 FP8/FP4 测试与 CuTe 示例，但 Rubin 新接口仍属预览。**公开证据能给具体 kernel、shape 和软件版本打分；还不足以给 SM107 一个通用 FP8/FP4 GEMM 的利用率，更不足以说 Rubin 的所有 FP4 算子都是 GB300 的 2.33×。** 需要补一套固定 M/N/K、scale、累加类型、时钟、电源上限的跨芯片大矩阵 sweep，以及含真实专家负载分布的小 M grouped GEMM sweep。

## 四、训练：Rubin 的强证据在 FP8，FP4 配方的强证据主要来自 Blackwell

| 证据 | 规模、精度与对照 | 应当如何读 |
|:--|:--|:--|
| **Rubin 实机，MLPerf Training v6.1** | DeepSeek-V3 671B，1024 GPU：GB200 **12.360 min**、GB300 **8.033 min**、Rubin **4.142 min**。Rubin 配置是 **MXFP8**；显式设定 FP8 attention 和 param gather，并非 NVFP4。 | 对 GB300 **1.94×** 的达到目标时间优势是可验证的整机成绩。对照跨硬件、软件和并行实现，不能全归因于 Tensor Core。 |
| **Rubin 实机，MLPerf RL** | 1024 GPU 的 vLLM 路线，GB300 **13.78 min**、Rubin **10.94 min**；Rubin actor 只把路由专家线性层用 MXFP8，rollout 也保留一批模块的高精度。 | 是达到基准目标的 RL 系统成绩；不是完整 FP8，更不是 FP4，也不是 decode 吞吐或 actor MFU。 |
| **NVIDIA，12B hybrid、10T tokens** | 低精预训练：NVFP4 vs FP8，MMLU-Pro **62.58 vs 62.62**；模型高精度评估。 | 能证明配合配方可长程收敛，不能证明所有层纯 FP4、量化部署精度或 Rubin 速度。 |
| **NVIDIA，8B、1T tokens，Blackwell** | B200 精度实验 MMLU **45.64 / 45.98**（NVFP4 / BF16），两者 BF16 eval。另一个 GB200 吞吐实验 BF16/MXFP8/NVFP4 为 **1165/1540/1850 TFLOPS/GPU**。 | NVFP4 对 MXFP8 **1.20×**，对 BF16 **1.59×**，但 NVFP4 用更大 microbatch，且尾部层保留 BF16；不是只切换 dtype。 |
| **Thinking Machines，Inkling 2 Small，GB300** | 594B/17B 激活；MoE 前向用 NVFP4，梯度路径主要 MXFP8，最后约六分之一层保留更高精度。作者报告比全 MXFP8 MoE **预训练快 8%、RL 快 20%**，预训练等 loss 约有 **2%** 的计算效率代价。 | 大模型真实可用的混合配方。作者也明确说全 NVFP4 试验质量下降过多。不是 Rubin 同机对照，也不使用 3× 的 GB300 FP4/FP8 峰值比作为全系统加速。 |

训练来源：[MLCommons v6.1 原始提交](https://github.com/mlcommons/training_results_v6.1/tree/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7)、[DS-V3 Rubin 精度配置](https://github.com/mlcommons/training_results_v6.1/blob/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/benchmarks/deepseekv3_671b/implementations/hecate_ngpu1024_ngc26.09_nemo_cudnnv9.26.1/config_common_mxfp8.sh)、[Qwen actor 精度配置](https://github.com/mlcommons/training_results_v6.1/blob/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/benchmarks/qwen35_397b_grpo/implementations/hecate_ngpu1024_nemo_rl_vllm/conf/te_routed_mxfp8_fwd_bwd.yaml)、[NVIDIA v6.1 报告](https://developer.nvidia.com/blog/nvidia-vera-rubin-nvl72-achieves-up-to-2x-blackwell-ultra-performance-in-mlperf-training-v6-1/)、[12B 论文](https://arxiv.org/abs/2509.25149)、[8B 实验](https://developer.nvidia.com/blog/using-nvfp4-low-precision-model-training-for-higher-throughput-without-losing-accuracy/)、[Inkling 数值配方](https://thinkingmachines.ai/blog/end-to-end-4-bit-training/)。

训练所说的 NVFP4 通常是选择性降低 GEMM、激活或通信的精度，不是把主权重、累加、优化器状态都改成 4 位。小块缩放、Hadamard 变换、权重 2D scaling、梯度 stochastic rounding 和高精度保底各有成本。**评估应该以相同评测精度、达到相同质量的 GPU 小时为主，而不是只看同 token 数的训练吞吐。** 上一篇 [MLPerf 千卡拆解](https://ai-v5.github.io/LLMNews/2026/11/17/mlperf-61-deepseek-mfu-qwen-rl/) 按 FP8 峰值归一得到 Rubin 约 17.8%、GB300 约 31.7% 的名义 MFU，这与 Rubin 绝对吞吐领先并不矛盾：有用吞吐上涨约 1.96×，FP8 峰值却上涨 3.50×；混合算子和通信等仍占时间。

## 五、最有说服力的 FP4 推理消融：同 Rubin、同预算，比 MLA 的 FP8 和 FP4

[NVIDIA 的 NVFP4-MLA 论文 v1](https://arxiv.org/html/2611.18972v1) 给出了比跨代榜单更能回答问题的对照。在同一 Rubin 平台和 TensorRT-LLM 运行时中，比较规定的 FP8 MLA 与带残差补偿的 NVFP4 MLA。它不是只压缩 KV 后再反量化回 FP8：NoPE latent 用 16×16 块让 QK、PV 共用低精数据和尺度，RoPE 离群通道加一个 NVFP4 残差，在线量化 Q 和 softmax score，使两次 BMM 走原生 FP4。

| 指标 | DeepSeek-R1 | Kimi-K3 |
|:--|--:|--:|
| 九项任务均分：BF16 MLA → 直接 NVFP4 MLA → 补偿版 | 59.80 → **54.09** → **59.82** | 80.27 → **63.79** → **80.28** |
| 存储的 MLA KV：相对 FP8 MLA 的压缩比 | **1.60×** | **1.52×** |
| 单卡 attention kernel：相对 FP8 MLA 的最高加速 | **2.82×** | **2.71×** |
| AgentX 等 KV 容量，代表性并发下的 p90 TTFT | 48 sessions：**108 → 30.9 s** | 128 sessions：**11.0 → 5.24 s** |

这组结果同时说明三件事：

1. **FP4 不天然保精度。** 未补偿的朴素版本让 Kimi-K3 九项均分掉了约 16.5 个百分点；补偿后均分恢复，但不能替代逐项长上下文和工具成功率验收。Kimi-K3 还有两层 MLA 保持 FP8，且 1.52× 只指 MLA KV，**不包括 69 层 KDA recurrent state**。这里不是 Kimi K3.1 Pro。
2. **算子最高值不是整机倍率。** 同一 Rubin 的 attention kernel speedup 依 KV 长度、batch、split-KV 和 MTP 改变；不仅变了数学位宽，也变了带宽、tile 和数据通路，因此 2.82× 不与稠密峰值 2× 矛盾。论文中 DeepSeek-R1 的 MTP=3 将 FP8 MLA 算术强度由 484 拉到 1934 FLOP/B，超过按 17.5 PFLOPS／19.2 TB/s 计算的 911 FLOP/B 拐点，解释了为何此处只把 KV 存小、仍然做 FP8 MMA，并不够。
3. **TTFT 大幅下降来自避免重做 prefill。** 两组占用相同的 KV 容量，FP4 可以保住更多历史；DeepSeek-R1 的代表点前缀命中率 **77.0%→87.1%**。这是缓存受压时的收益，不是单 token 算子突然快 3.5×，也不能外推到缓存本来就容纳得下的负载。这是论文作者实验，不是 MLCommons 独立认证的精度消融。

模型权重降精也应按类似方式检查。例如 [NVIDIA Model Optimizer 的 Qwen3.6-35B-A3B 实验](https://nvidia.github.io/Model-Optimizer/announcements/20260916-qwen36-w4a4-qad.html) 中，W4A16 经反量化的路径 12 个 shape 里 10 个慢于 BF16；W4A4 原生 FP4 路径 9 个更快、最高 1.30×。同一个案例里 MMMU-Pro 是 BF16 **74.6**、PTQ **73.4**、500 步 QAD **73.9**；QAD 后 SciCode 的平均输出长度增加约 91%，得分却未改变。这不是 Rubin 的硬件对照，却是很好的部署反例：**权重文件变小、kernel 变快、完成同一任务更省，三者不能互相替代。**

## 六、整机：72 卡对 72 卡能说明什么

下表为 MLPerf Inference v6.1 Closed 中 NVIDIA 的同卡数提交，Rubin 为 Preview，数字从[GB300 原始日志](https://github.com/mlcommons/inference_results_v6.1/tree/main/closed/NVIDIA/results/GB300-NVL72_GB300-288GB_aarch64x72_TRT)及 [Rubin 原始日志](https://github.com/mlcommons/inference_results_v6.1/tree/main/closed/NVIDIA/results/VR200-NVL72_GR200-288GB_aarch64x72_TRT_preview)四舍五入。

| 场景 | 单位 | GB300 NVL72 | Vera Rubin NVL72 | 倍率 |
|:--|:--|--:|--:|--:|
| DeepSeek-R1 Offline | 输出 tok/s | 679,740 | 1,183,327 | **1.74×** |
| DeepSeek-R1 Server | 输出 tok/s | 596,944 | 1,175,890 | **1.97×** |
| DeepSeek-R1 Interactive | 输出 tok/s | 253,506 | 652,750 | **2.57×** |
| Qwen3-VL-235B Offline | samples/s | 1,305.0 | 2,392.7 | **1.83×** |
| Qwen3-VL-235B Server | queries/s | 1,210.5 | 2,323.3 | **1.92×** |
| Qwen3-VL-235B Interactive | queries/s | 349.3 | 1,306.6 | **3.74×** |

两代的 R1 都声明 FP4 权重；[Rubin R1 配置说明](https://github.com/mlcommons/inference_results_v6.1/blob/main/closed/NVIDIA/src/configs/VR200-NVL72_VR200-288GB_aarch64x72_TRT/deepseek-r1/README.md)指向 NVFP4 checkpoint、P/D 分离且禁用 prefix reuse，不包含完整服务端 engine/scheduler 配置，不能据此认定每个 kernel 或 KV 的精度。Qwen 两代都指向名称明确含 NVFP4 与 FP8-KV 的 checkpoint，但粗粒度 measurements 字段写 BF16，不能据此判整个图都用其中一种精度。这张表证明**低精推理系统的代际能力**，不是把 GB300 FP8 切到 Rubin FP4 的单变量实验。

**不能把 58× 或 10× 横移到日常负载。** vLLM 的 [AgentX 58×](https://vllm.ai/blog/2026-11-12-deepseek-v41-flash-vera-rubin) 是在指定交互速度处对比的系统点，吞吐同时计入缓存输入、未缓存输入和输出。更细的 [MLPerf Endpoints 比较](https://developer.nvidia.com/blog/nvidia-vera-rubin-nvl72-leads-agentic-inference-performance-on-mlperf-endpoints-v1-0/)中，Kimi K3 在最低 50 tok/s/user 的门槛上得到约 11.1× TPS/预配置 kW，但并发是 1024 对 48、部署 32 对 48 卡。固定并发 1024 后，交互速率约 50.4 对 16.8 tok/s/user，TPS/预配置 kW 比约 **1.77×**。Rubin 相关 Endpoints 点为 provisional，GB300 对照为 verified；预配置功率不是电表读数。**要对齐的是质量、SLO、上下文和计数单位，再比较完成任务所需资源。**

## 七、竞争力判断与验收建议

**相对 GB300：** Rubin 的优势不止是 4-bit 数字更大。训练端最大、最确定的公开增益由 MXFP8 整体路径兑现；推理端，FP4 与更快 HBM/互联、布局、稀疏、融合和 KV 容量共同影响好用的吞吐。易踩的坑是把 **35 PFLOPS** 写成 FP4 整图实跑算力，把 **50 PFLOPS** 写成通用稠密吞吐，或以为 FP4 精度相同就可以复用同一个吞吐倍率。

**相对同代 AMD：** [MI455X 官方规格](https://www.amd.com/en/products/accelerators/instinct/mi400/mi455x.html)列 MXFP4 **40.3 PFLOPS**、MXFP8 **20.1 PFLOPS**、432 GB HBM4、23.3 TB/s；不可拿它的稠密 MXFP4 直接与 Rubin 50 PF 的稀疏 NVFP4 排名。AMD 自测 DeepSeek-R1 Offline 为 **21,333 output tok/s/GPU**；对比本文 72 卡 Rubin 提交折合 **16,435 tok/s/GPU**，约高 30%。[AMD 原始披露及脚注](https://newsroom.amd.com/news/amd-advances-instinct-mi400-series-ai-scientific-computing/)明确这是厂商按 MLPerf Offline 配置的内部测试与 NVIDIA 已发布条目的对比，不是同轮同口径官方对打。结果至少说明：不能从峰值或一条 NVIDIA 榜单推出 Rubin 单卡在每个低精场景都领先；证据更强的是 Rubin 在多个可追溯软件栈与负载上已兑现性能。

建议按下列顺序做选型，先跑快的层级，再决定是否扩大投入：

- **硬件/算子：** 固定 dense、grouped 和低 M decode 三组 shape，记录 W/A/scale/accumulator/output、稀疏度、实测频率、功率限制、单 die 与跨 die 内存布局；分别计量量化、重排、GEMM 和 EP 通信。有用 FLOPs 与实际执行 FLOPs 分开，不把填充或重计算作有用吞吐。
- **训练：** 同一 Rubin 软件版本运行 BF16、MXFP8、NVFP4 前向＋MXFP8 反向三个基线；先逐层查损失、梯度与路由尾部，再跑多 seed 的等质量比较。记录 tokens/s、GPU·h 到目标 loss/能力、低精覆盖比例、通信字节与失败重跑；RL 分开记录 rollout、actor 和评测墙钟。
- **推理：** 在固定模型版本、数据集、并发、上下文、P/D 配比、功率模式下，至少拆三组：FP8 基线、仅 W4、W4A4／原生 FP4 attention；以输出 tok/s、p90 TTFT、p99 TPOT、前缀命中、实测焦耳/成功任务为主，分开报缓存输入 TPS。质量门槛失败的点不计入 Pareto 曲线。

**最终分级：FP8 训练，可作为当前强基线；FP4 推理，针对命中原生 kernel 且精度校准过的模型，竞争力已有强证据；FP4 大规模训练，值得试，但暂不把 Rubin 35 PFLOPS 折算进等质量交付承诺。** 下一份最有价值的公开数据不是更高的机架峰值，而是 Rubin 上同一 MoE、同一训练 recipe 只改精度，并同时公开等目标质量时间与回退算子比例。
