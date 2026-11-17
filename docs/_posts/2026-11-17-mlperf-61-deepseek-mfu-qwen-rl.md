---
title: "拆解 MLPerf 千卡实测：DeepSeek-V3 的 MFU，和 Qwen3.5 RL 的真实瓶颈"
date: 2026-11-17T14:11:44+08:00
summary: "用 MLPerf v6.1 的原始日志复算 GB200、GB300、Rubin 的 DeepSeek-V3 模型 FLOPs，并拆开 Qwen3.5-397B GRPO 的达标时间、有效 token、卡时和训练等待。"
section: explainer
label: "性能分析"
tags: [MLPerf, DeepSeek, Qwen, MoE, 强化学习, 性能建模]
demo: false
sources:
  - title: "MLPerf Training v6.1 官方结果"
    url: "https://results.mlcommons.org/training"
  - title: "MLCommons v6.1 原始提交（固定版本）"
    url: "https://github.com/mlcommons/training_results_v6.1/tree/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA"
  - title: "MLCommons DeepSeek-V3 参考实现与训练口径"
    url: "https://github.com/mlcommons/training/blob/e309244f7f81ecb00da434cae98355a73fc50ff0/llm_moe_pretraining/nemo/README.md"
  - title: "MLCommons Qwen3.5-397B GRPO 参考实现与计时规则"
    url: "https://github.com/mlcommons/training/blob/e309244f7f81ecb00da434cae98355a73fc50ff0/llm_post_training/README.md"
---

**Rubin 比 GB300 快，不代表它吃满了更多峰值。** 同为 1,024 卡，Rubin 的 DeepSeek-V3 模型吞吐是 GB300 的 **1.96×**，但对各自的 dense FP8 名义峰值归一化，模型算力利用率约 **17.8% 对 31.7%**。Qwen3.5 GRPO 的同后端达标加速只有 **1.26×**：千卡结果更快，却比 256 卡多消耗约 **3 倍 GPU 卡时**。两个 benchmark 的区别不只是模型大小：前者每步的有效计算量大体固定，后者还要等 Agent 交互、有效轨迹、异步队列和权重更新。

本文用 MLPerf Training v6.1 Closed 组、同一提交方 NVIDIA 为主。取实际分配的 GPU 数；16 个 NVL72 机柜并不等于作业动用了 1,152 卡。以下分别标注**官方达标成绩**、**日志派生量**和**模型估算**，不把三者当同一种实测。

## 1. DeepSeek-V3：先算每步有效工作，再谈 MFU

这是从指定起点继续训练的 **671B MoE** 基准，不是从零训练，也不是重跑原论文的 14.8T tokens。参考实现使用 C4 和指定 checkpoint，达标条件是验证 loss ≤ 3.60。三项千卡提交均是 4,096 序列长度、全局 batch 15,360，即每个优化步处理 **62,914,560 个序列 token 位置**。九份日志在第 47 或 48 步达标，约 **2.96–3.02B** 个 token 位置；以下吞吐按每份日志的 `tracked_stats.train_step_time` 汇总，用总 token 除以总 step 时间，不用排行榜分钟直接反推。

| 1,024 GPU，NVIDIA 提交 | 官方达标分钟 | 平均 step | 全集群 token/s | 每卡 token/s | 模型计算 PFLOP/s/卡（估） | dense FP8 归一化 MFU（估） |
|---|---:|---:|---:|---:|---:|---:|
| GB200，[6.1-0045](https://github.com/mlcommons/training_results_v6.1/tree/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/results/tyche-hsg_ngpu1024_ngc26.09_nemo_cudnnv9.27.0/deepseekv3_671b) | 12.360 | 15.57 s | 4.04M | 3,947 | 1.029 | **20.6%** |
| GB300，[6.1-0030](https://github.com/mlcommons/training_results_v6.1/tree/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/results/theia-jhb_ngpu1024_ngc26.09_nemo_cudnnv9.26.1/deepseekv3_671b) | 8.033 | 10.11 s | 6.22M | 6,078 | 1.584 | **31.7%** |
| VR200 / Rubin，[6.1-0116](https://github.com/mlcommons/training_results_v6.1/tree/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/results/hecate_ngpu1024_ngc26.09_nemo_cudnnv9.26.1/deepseekv3_671b) | 4.142 | 5.16 s | 12.20M | 11,918 | 3.106 | **17.8%** |

计入整个原始 `run_start → run_stop` 并用各自中位用时那条日志的实际样本数，三项 MFU 约 **20.4% / 31.4% / 17.4%**。排行榜三项又统一乘了提交目录内约 1.0053 的 scaling factor；达标时间和原始 step 时间不混用。按官方时间，256→1,024 卡的达标扩展效率为 **GB300 97.7%、Rubin 97.3%**（256 卡分别 31.404、16.124 分钟）；这个百分比描述加卡的边际效率，不是卡内的 MFU。

### 260.64 GFLOP/token 怎么算

直接套 `6 × 37B` 是一个粗估，给出 **17.5% / 27.0% / 15.1%**。为处理 MLA 序列项和提交实际启用的一层 MTP，我按 [DeepSeek-V3 参考架构](https://arxiv.org/html/2412.19437v2)及日志张量维度复算。按一次 FMA = 2 FLOPs，反传约为前向的两倍；分子不含激活重算、padding 空算、优化器、通信、norm 和 softmax 等开销。

- 隐宽 H=7168，61 层（3 dense、58 MoE），路由 Top-8 加一个共享专家。Dense FFN 隐宽 18432，MoE 每专家 2048，故两者每 token 的三矩阵有效权重均为 `3 × H × 18432`；MoE 层再加 256 路 router 投影。
- MLA 的 Q/KV 低秩分别 1536/512，128 头，每头 QK 192、V 128。每层 Q/K/V/O 投影合计等价 **187.105M** 权重。词表按 129,280；主模型每 token 触达线性等价权重约 **36.625B**，MTP 的一层、融合投影及再次使用输出头另加 **1.615B**。线性训练约 **229.44 GFLOP/token**。
- 因果 Attention 按平均约半个方阵，QK+AV 的训练项约为 `3 × 4096 × 128 × (192+128) × 62`，即 **31.21 GFLOP/token**。合计约 **260.64**。这与公开日志打印的约 **3.1 PFLOP/s/卡**数量级一致；日志的 MODEL_TFLOP 也是软件 FLOPs 估计，不是 Tensor Core 硬件采样。

`MFU_proxy = token/s/GPU × 260.64 GFLOP/token ÷ 单 GPU dense FP8 名义峰值`。名义峰值取 **5 / 5 / 17.5 PFLOP/s**：[GB200 NVL72 规格](https://www.nvidia.com/en-us/data-center/gb200-nvl72/)、[Blackwell Ultra GPU datasheet（第 5 页）](https://dam-cdn.nvd.orangelogic.com/AssetLink/1k0p832eq8r5ca0u5383ie5o4tp3bst1.pdf)、[Rubin 规格](https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/)。Blackwell 的 10 PF 是单 GPU 的 **sparse** FP8 数，不是 MoE 路由自动获得的 2:4 稀疏加速。NVIDIA 的 [DGX GB300 网页](https://www.nvidia.com/en-us/data-center/dgx-gb300/)对 720 PF/rack 有不同标注；这里以 GPU datasheet 的明确 sparse/dense 脚注为准。若采用 10 PF，GB300 表值会降到 15.8%，所以比较 MFU 必须同时给分母和不依赖分母的 PFLOP/s。

**这是名义 FP8 上限归一化，不是实际算子精度的综合峰值。** 三项都是 MXFP8 主路径，但不代表每个算子、累加和通信都在 FP8。Rubin 的 dense BF16 名义峰值为 4 PF，而 Blackwell 为 2.5 PF；假定仅作敏感性分析的 20% 有效 FLOPs 在 BF16、80% 在 FP8，同一设备上串行理想时间按 `Σ(F_precision / peak_precision)` 计算，则三项相对这个基准约 **24.7% / 38.0% / 29.7%**。20% 不是从日志测出来的，也不把此模型用于声称精度路径实际串行。

### 系统比较能解释什么

GB200→GB300 的名义 dense FP8 并未变快，但有效模型吞吐提高 **1.54×**：这是容量、并行布局和实现都可能改变训练效率的实例。三者均 PP4 / EP32 / CP1（虚拟流水线 vPP4）；GB200 用 TP2 和选择性 MLP 重算，GB300、Rubin 用 TP1 且提交未启用这项重算。GB200 名义 HBM 约 186 GB、8 TB/s；GB300 约 279 GB、8 TB/s；Rubin 288 GB、19.2 TB/s。更大容量给减 TP、减重算留出空间，不能说日志单独证明了这两项各贡献多少。原始提交还换了节点间网络和部分软件版本：Tyche 是 CX7 InfiniBand，Theia 是 CX8 Ethernet，Hecate 是 CX8 InfiniBand。两代 Blackwell 名义 NVLink 为 1.8 TB/s/卡；Rubin 产品规格与发布博客分别写 3.0 和 3.6 TB/s，且提交未填实际链路速率，这里不任选一值当实测。参见 [三套系统描述](https://github.com/mlcommons/training_results_v6.1/tree/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/systems)及 [三套 DS 配置](https://github.com/mlcommons/training_results_v6.1/tree/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/benchmarks/deepseekv3_671b/implementations)。

Rubin 的每卡模型 PFLOP/s 近乎翻倍，但 FP8 峰值分母增了 3.5×，HBM 名义带宽只增 2.4×；简单 `FP8 peak/HBM peak` 从 **625** 升到约 **911 FLOP/byte**。这是算子的带宽平衡点，不是已经证明整步 HBM 受限。EP dispatch/combine、并行流水线、算子精度和 GPU 时钟同样可能决定吞吐；原始配置没有给足可以证明跨柜流量、有效 A2A 带宽或峰值时钟的计数器。**相同 EP32 不等于相同通信时间，更不能把 17.8% 的补数当成 82.2% GPU 空转。**

## 2. Qwen3.5 RL：第一指标是达标时间，不是 Decode tok/s

Qwen3.5-397B-A17B 从预训练 checkpoint 起跑，以 GRPO 在 R2E-Gym 的 SWE 任务中生成多轮轨迹，运行工具，并按测试通过与否得到奖励。固定 held-out 251 题，每题采样 4 条，至少一条通过即记该题成功；**pass@4 ≥ 0.69** 等价于至少 **174/251** 题通过。这不是训练过程里的平均 reward，也不是 4 条都通过。

**计时边界：** 榜单匹配第一个离线验证达标的 checkpoint，但截止时间回填为该 checkpoint **最后一次更新权重**的时间。不计该 checkpoint 写盘及其离线评估时间；准备/排队等是否计入须按 `run_start`，不能把榜单说成「提交作业到确认质量」的实际交付时间。这个场景下另应记录部署世界的 submit-to-verified。举例：千卡三条中位日志的离线 `eval_start → eval_stop` 分别 **227 / 251 / 145 秒**，均在榜单计时之外，亦不应直接加到榜单得出完整交付时间。GB300 中位原始日志里，从 run_start 到实际记录 pass@4 约 **26.33 分钟**，但榜单只计 **13.78 分钟**；两者间还包含 checkpoint、离线作业切换等。不要用这条单次观察另排官方榜。

### 同后端、同提交方的达标与资源成本

| GPU / 生成后端 | GB300 用时 / 分配 GPU·h | Rubin 用时 / 分配 GPU·h | Rubin 加速 |
|---|---:|---:|---:|
| 64 / vLLM（0035、0122） | 42.48 min / 45.31 | 32.18 min / 34.33 | 1.32× |
| 64 / TensorRT-LLM（0034、0121） | 36.99 min / 39.46 | 25.93 min / 27.65 | 1.43× |
| 256 / vLLM（0040、0131） | 20.11 min / 85.82 | 14.33 min / 61.15 | 1.40× |
| 512 / vLLM（0043） | 14.52 min / 123.89 | 无对照 | — |
| 1,024 / vLLM（0031、0118） | 13.78 min / 235.22 | 10.94 min / 186.77 | **1.26×** |
| 1,024 / TensorRT-LLM（0117） | 无对照 | **10.44 min / 178.26** | — |

分配 GPU·h = GPU 数 × 榜单小时数，不含前后不计时作业，不等于计费、活跃时长或能耗。相同 1,024 卡，10.44 对 13.78 分钟是可用方案之间的 **1.32×**，不是同 backend 的硬件收益。GB300 在 512→1,024 卡时只省约 **44 秒**、GPU·h 却涨 **90%**；Rubin 256→1,024 卡少约 **3.39 分钟**，卡时却涨 **3.05×**。256→1,024 的达标扩展效率只有 GB300 **36.5%**、Rubin **32.7%**。这个结果适合用来挑时延预算下的卡数，不适合拿它说 GPU 空闲了 60–70%。示例：若只要求 vLLM 跑进 15 分钟，仅看这些提交，GB300 512 卡、Rubin 256 卡就已做到。

### 千卡日志：训练池只有 256 卡，剩下 768 卡做生成

三项千卡配置都是 **32 prompts × 16 trajectories = 512/步**、分置的 **256 actor + 768 rollout GPU**，达标 checkpoint 均为第 10 步。训练消耗的 5,120 是名义 trajectory slots；不是 5,120 个不同题，也不是全通过或全部贡献同等梯度的轨迹。下表取各项三份里榜单时间中位所在日志，有效 token 累计第 1–10 步；阶段计时只取前 9 步，避免第 10 步混入 checkpoint 保存，计时列均为秒。

| 1,024 卡 | 原始中位日志 / pass@4 | 轨迹槽位/s（榜单窗口） | 有效 loss token/s（榜单窗口，约） | 前 9 步外层用时 | policy training | exposed generation | 权重同步 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| GB300 vLLM | [result_1](https://github.com/mlcommons/training_results_v6.1/blob/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/results/theia-jhb_ngpu1024_nemo_rl_vllm/qwen35_397b_grpo/result_1.txt) / .7570 | 6.19 | 34,001 | 451.0 | 295.7 | 109.8 | 31.6 |
| Rubin vLLM | [result_0](https://github.com/mlcommons/training_results_v6.1/blob/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/results/hecate_ngpu1024_nemo_rl_vllm/qwen35_397b_grpo/result_0.txt) / .7410 | 7.80 | 43,502 | 378.8 | 237.2 | 104.3 | 24.9 |
| Rubin TRT-LLM | [result_1](https://github.com/mlcommons/training_results_v6.1/blob/d5458b9f8c3c4a767e6f2c894b008cb95200e6f7/NVIDIA/results/hecate_ngpu1024_nemo_rl_trtllm/qwen35_397b_grpo/result_1.txt) / .7570 | 8.17 | 44,868 | 401.6 | 234.4 | 89.7 | 70.3 |

三条日志的 `global_valid_toks` 累计约 **28.12M / 28.56M / 28.12M**，按全分配卡时约 **33.2 / 42.5 / 43.8 loss tokens/s/GPU**。该计数把 token mask 与样本 mask 合在一起，只衡量参与 loss 归一化的有效 token；它不等于所有前后向输入、所有生成 token 或训练 FLOPs。三项实测每次均在第一次允许验证的 checkpoint 达标，因此表里的 pass@4 不支持给三个系统排最终模型能力。

两池重叠运行，**exposed generation** 是训练关键路径上露出来的生成/数据等待，不是生成池工作总时长；buffer starvation 是其中一部分，不能再相加。一些计时嵌在其他项内，也不要拿列和硬凑 100%。同 vLLM，Rubin 的前 9 步 policy time 少了 **58.6 s（20%）**，exposed 等待只少 **5.4 s（5%）**，占比反从 **24.3% 升到 27.5%**。算得越快，没被掩盖的生成/调度等待越显眼。Rubin 上 TRT 的前九步等待更短、同步却更久，且其这九步总用时反而较长，但官方达标更快。首批轨迹、计时窗口和第 10 步的差别不可略去；这些是有用的诊断，不是对硬件或 backend 的单变量归因。

生成池有一条可核实的容量线索：GB300 和 Rubin 的千卡 vLLM 日志中，代表性 worker 报告可用于 KV cache 的预算分别 **159.46 与 161.0 GiB**。这是分配预算，不是实际 KV 水位或 HBM 带宽；两者预算接近，也不意味着访存速度和并发相同。

日志名字还有两个坑。该提交版本的 [NeMo RL 吞吐实现](https://github.com/NVIDIA-NeMo/RL/blob/a6ec8a93df4062e5991e225166f60ea981d170e3/nemo_rl/algorithms/utils.py#L797-L909) 的生成组 Tokens/sec 以 `total_num_tokens` 作分子；异步分母是 policy、logprobs 与 exposed 等时间，不是纯 decode GPU 工作时间。另一个 `Training Worker Idle Time Ratio` 的实现，在 exposed 等待大于 0.1 秒时反而**返回 0**。这个字段不能证明训练卡完全没有空转。

### 原始日志复算提示

解析每行 `:::MLLOG` 后的 JSON。DS 用 `tracked_stats.value.train_step_time`，按三条日志汇总 `条数 × 15360 × 4096 / Σ(step_time) / 1024`；原始达标窗口按 `run_stop.metadata.samples_count × 4096` 做分子。RL 先对三条 `(run_stop.time_ms - run_start.time_ms)/1000` 取中位日志，用该日志的 `samples_count / global_batch_size` 找达标步；按步累加 `tracked_stats.value.global_valid_toks`，按前九步分别累加 `train_step_time`、`policy_training_time`、`exposed_generation_time` 和 `weight_sync_time`。不要累加达标后的第 11 步。

## 3. 下一次怎样测，才能据此选卡、配并行

1. **对 DeepSeek 式预训练，先标定有效模型 PFLOP/s，再追瓶颈。** 固定 seq、batch、精度、EP/TP/PP 布局及 GPU 频率，分别对照 TP1/TP2 和 MLP 重算开关。按每 step 采 Tensor Core 活跃、实际 HBM read/write bytes、MoE token 分布和 exposed A2A；NVLink 与 NIC 的 TX/RX 分开计，不能拿合计和单向峰值相除。用 Nsight/CUPTI、DCGM 和交换机端口时序定位，跟同时满载的微基准作对照，而不是用标称峰值替代。预训练的 GPU·h、有效模型 PFLOP/s、带宽指标与 MFU 分开看。
2. **对 RL，先量质量与经济性，再分池。** 用通过目标的最早合格 checkpoint 的时间、分配 GPU·h 和（生产环境）确认评估时间；固定模型、任务、每题采样数、seed、上下文与工具超时。再统计训练消费的轨迹、正奖励有差异的 prompt group、保留的 loss-mask token、过长/失败/过期丢弃率、轨迹新鲜度。更快地产生冗长输出未必训练更快。
3. **Decode 只当诊断指标，且应至少报两种分母。** 从服务引擎单独收集真正交付的 assistant output tokens（不含 prompt、工具输出、未接受的 speculative token），分别除以 rollout 池整段墙钟、以及卡级实际 decode-active 时长。前者计入工具等待、排队和空闲；后者更接近引擎能力。再配 TTFT、TPOT、未命中缓存的 prefill tokens、KV 占用/抢占、工具队列 p95/p99、测试沙箱 CPU/IO，以及每次 refit 的实际链路字节和停顿。现有公开日志提供部分引擎瞬时值和阶段代理，不能复原全部 768 卡在计分窗口的同口径纯 Decode 吞吐；也不能反推可靠的 HBM%、NVLink%、Tensor Core 活跃百分比或焦耳/达标。日志甚至明示该 Qwen 配置不支持内置 FLOPs tracker；actor MFU 要独立建模：用实际参与前后向的全部上下文和 loss mask 分开计数，考虑混合 GDN/Attention、MoE 和重算，再只除训练池的 GPU 时长，不能用 loss token × 6×17B 代替。
4. **第一轮实验优先试卡池比例和长尾。** 固定节点总数、质量协议和任务预算，扫描 actor:rollout 卡数及环境 CPU 并发；每个组合跑相同 seed 集，报告 time-to-target 和 GPU·h 的 Pareto 前沿。若 trainer 常等 buffer，就用同步 trace 判断是 decode 慢还是工具/测试沙箱慢；若 buffer 常满或年龄触顶，先减少无效生成、缩短 refit 或增加 actor 吞吐，而不是盲加 rollout 卡。

**结论：** DeepSeek 千卡最有用的两个数是 **GB300 1.58、Rubin 3.11 PFLOP/s/卡的有效训练工作率**；RL 最有用的两个数是 **同 vLLM 13.78→10.94 分钟且 235→187 GPU·h**。前者能校准 MoE 训练模型，后者能校准达标成本。Decode 吞吐、HBM 带宽和通信计数负责解释原因，不能替代这两个系统级结果。
