---
layout: post
title: "Agentic RL 到底该配多少卡、多少 CPU：DeepSeek-V4.1 与 Kimi K3.1 的 GB300 三池推演"
date: 2026-11-24T16:21:00+08:00
summary: "从公开推理、训练和沙盒数据出发，用同一任务合同推演两种模型的 NVL72 配比，给出启动规模、每小时有效组数、策略滞后预算和瓶颈灵敏度。附可复算脚本与数据。"
section: explainer
label: "强化学习系统与集群容量"
tags: [Agentic RL, DeepSeek, Kimi, GB300, 算力建模, 沙盒]
demo: false
sources:
  - title: "DeepSeek-V4.1-Flash 模型卡与 1017 更新"
    url: "https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash"
  - title: "Moonshot：Kimi K3.1 Pro 模型卡"
    url: "https://huggingface.co/moonshotai/Kimi-K3.1-Pro"
  - title: "NVIDIA：公开推理 benchmark 原始数据"
    url: "https://developer.nvidia.com/search-data/nv_inference_benchmark.json"
  - title: "Megatron-LM：Kimi K3/K3.1 训练配方与进度"
    url: "https://github.com/NVIDIA/Megatron-LM/issues/6872"
  - title: "Amazon：Sandman 生产环境 trace"
    url: "https://arxiv.org/html/2610.39711"
  - title: "腾讯微信：WeEnv CPU 沙盒测量"
    url: "https://arxiv.org/html/2609.30766"
---

**先给一个可落地的量级：** 对同一组假设的代码智能体任务，DeepSeek-V4.1-Flash 以 **360 卡 rollout + 72 卡 learner + 3,072 个沙盒物理核**做预算；Kimi K3.1 Pro 以 **864 + 288 卡 + 2,304 个沙盒物理核**做预算。在这个场景下，前者每小时消耗约 **6,376 个完整有效组**，后者约 **4,666 组**；rollout、CPU、learner 分别约 **80% / 62% / 78%** 和 **80% / 60% / 79%** 的建模工作负载。按机柜采购是 6 柜与 16 柜。**这是两个独立作业的基线预算，不是两家官方集群，不是实测吞吐、质量排名，也不是已验证的部署配方。** 若要求的是一条生产线同时交错训练两个模型，应分别保留模型身份、版本和数据合同；CPU 只有在到达负载与尾部不完全同相且内存、镜像、租户隔离验收后才可合池。

这个结论最容易被三件事推翻：生成 token/轨迹翻倍、沙盒实际核秒成倍增长、训练序列被工具反馈撑长。第三件事往往不会反映在模型的输出 tokens/s 上。下文先校准证据，再把这些变化算成卡数、核数和队列，而不是从一次跑分推出固定的 3:1 配比。公开资料核对日期：2026 年 11 月 24 日。

[下载复算脚本]({{ '/assets/data/agentic-rl-gb300/model.py' | relative_url }}) · [下载场景 CSV]({{ '/assets/data/agentic-rl-gb300/scenarios.csv' | relative_url }})

## 1. 一条轨迹跑了什么

| 资源池 | 实际干的活 | 首先压哪种资源 | 最应采什么 |
|---|---|---|---|
| Rollout GPU | 首轮 prefill；循环生成工具调用和推理 token；把工具返回追加并再 prefill；长会话恢复 KV；记行为 logprob 和策略版本 | prefill 的算力与通信；decode 的权重和 KV 读，以及 EP；挂起时的 KV 容量 | **真实采样并发下** assistant 输出 tok/s、未缓存 prefill tok/s、缓存复用/回读、TTFT/TPOT、每轮队列与显存占用 |
| 沙盒 CPU | 起环境/恢复项目与依赖；执行 shell、构建、测试；最终 verifier 回归；写回结果并回收 | 过程峰值核数、主存、镜像拉取/盘、网络和准入；外部工具还可能被 QPS 限流 | 整轨迹 **核秒**、活跃进程/峰值、镜像命中、环境开到关的墙钟、起容器及 verifier P95/P99 |
| Learner GPU | 把可用样本组 pack；必要时重算 old/ref logprob；策略前反向；梯度通信、优化器、检查点和发权重 | 全参数状态容量、长序列激活与 CP、专家通信、权重转换/发布 | 真实计算的序列 tok/s、有效 loss tok/s、MFU 口径、有效组/s、停顿、权重发布与到样本消费的版本差 |

三个池并非简单串联。一个 episode 在 GPU 和沙盒之间往返，结尾才结算 reward；GRPO 还要等同题多个 sibling 汇合。Reward 可以是确定型 verifier，也可能是模型打分；后者若占 GPU，要单列第四个容量项，不该塞进免费的 CPU 假设。沙盒里有用和无用的样本都会耗核秒；超时、同质奖励过滤、旧版本丢弃、环境重试都要记。**“可进训练的组”不等于“模型答对的组”。** 基线是代码/工具类任务分布，不是纯数学、未限定外部工具的互联网任务，也不是把 1M context 一律跑满。

## 2. 公开实验：先审计分母

### 模型和机器

- **DeepSeek-V4.1-Flash**：官方报告是 **552B backbone + 196B Engram**，不含单独的视觉/DSpark 等辅助账；40 层 Causal Encoder–Decoder，prefill 路径约 8B、decode 路径约 16B 激活，以及 1M 上下文。1017 是后训练小更新；11/20 InferenceX 点的配置指向原始权重 repo，未写死该 checkpoint SHA，不硬认作 1017。[原始配置](https://github.com/SemiAnalysisAI/InferenceX/blob/1b1eec0/inferencex-e2e/configs/nvidia-master.yaml#L6820-L6881)**不是 1.6T 的 V4-Pro**。分阶段激活意味着 learner 不能拿较小的 8B prefill 一键乘 6；必须核对训练走哪一条路、生成位置是否复走 decode 路径。[技术报告](https://arxiv.org/html/2609.19969v1) · [模型卡](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash) · [1017 更新](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)
- **Kimi K3.1 Pro**：公开权重卡 2.8T 总量、104B 激活，93 层中 69 KDA + 24 门控 DSA，896 路由专家选 16，另有 2 共享专家，1,048,576 context。官方 QAT 前向权重 MXFP4、激活 MXFP8，不代表梯度、主权重和 optimizer 都是 4/8 bit。Moonshot 只披露比 K3 投入更多后训练算力，没有披露自家生产分池和每步资源账。[模型卡](https://huggingface.co/moonshotai/Kimi-K3.1-Pro#2-model-summary) · [官方发布](https://www.kimi.ai/blog/kimi-k3-1-pro)
- **GB300 NVL72**：36 Grace、72 GPU，约 8 TB/s HBM 带宽/卡，公开规格有 288 GB 标称与 279 GB 的数据表口径；容量账保守取 279 GB，实际上线查进程可用字节。360 PFLOP/s 是机柜 BF16 稀疏峰值口径，对应每卡 **2.5 PFLOP/s BF16 dense**。不要用结构化稀疏或 FP4 峰值给 BF16/混精 learner 算效率。[NVIDIA 规格](https://www.nvidia.com/en-us/data-center/gb300-nvl72/) · [Blackwell Ultra 数据表](https://resources.nvidia.com/en-us-blackwell-architecture/blackwell-ultra-datasheet?lx=AJq6FY) · [NVIDIA dense 口径实例](https://research.nvidia.com/labs/gear/gr00t-2/assets/gr00t2_whitepaper.pdf)

### Rollout 锚点：只有输出才进第一笔账

| 模型/实验 | 公共数据可复算的例子 | 能用于什么 |
|---|---|---|
| DS-V4.1-Flash，GB300，MLPerf Endpoints，4 卡 | c128 输出 14,287 tok/s（3,572/卡），P90 TTFT 158 ms；c512 输出 35,185（8,796/卡），P90 TTFT 311 ms；c1024 输出 49,702，P90 TTFT 4.07 s | 同模型的短输出曲线、量化 serving 路径。输出平均约 0.9–1.1K，不能把 18×4 卡线性复制当整柜实测。[MLPerf run](https://results.mlcommons.org/endpoints/report?run=2089aadd-d1d0-4083-8d74-b059c10f4d31&source=phase2&submission=c0b99dd8-3157-4985-a669-acb2a6659c2a) |
| DS-V4.1-Flash，GB300，InferenceX AgentX，11/20 | 10P+32D 点 151,371 输出 tok/s ÷ 42 = **3,604/分配卡**，P90 TTFT 2.41 s；24P+32D 点 424,594 ÷ 56 = **7,582/分配卡**，P90 TTFT 7.11 s | 原始 output total ÷ wall time 再除 P+D；后一点字段约 13,252 **每 D 卡**，不能乘 56；按整柜购买计分别约 2,102/5,897。理论前缀命中约 97%，不是 RL 版本切换下的命中。[原始数据](https://developer.nvidia.com/search-data/nv_inference_benchmark.json) · [运行](https://github.com/SemiAnalysisAI/InferenceX/actions/runs/43089248484/attempts/2) |
| Kimi K3.1 Pro，GB300，AgentX | NVIDIA Dynamo 无投机，8 卡 TP8/c32 **39.89 系统输出 tok/s/卡**；24 卡 2P1D/c48 **23.08**。另一个 11/08 InferenceX/Dynamo vLLM 的 48/56/32 卡运行，公开 output 字段 **148/228/286**，P90 TTFT 3.50/8.08/11.38 s | 两套后端不同，后者使用 MTP，原始行未给输出总数及 P/D 卡分母分项，保留字段、不当作整柜保证。同名 case 的 19.2K/37.8K 是含输入与 cache 的**总** token 指标。[Dynamo](https://docs.nvidia.com/dynamo/dev/recipes/kimi-k3-1-pro#performance-results) · [InferenceX](https://github.com/SemiAnalysisAI/InferenceX/actions/runs/42501370812) · [vLLM](https://vllm.ai/blog/2026-11-04-kimi-k31-pro) |
| Kimi K3.1 Pro，短数学 RL，16 GB300 | Inferact 一对旧诊断单步：BI 一致路径 2,640 生成 tok/s，约 **165/卡**；计入 actor 等整个 1,336 s 只约 **49.5/卡**；截断约 45% | 32 prompt ×8、≤2K 提示、≤6K 响应，rank-32 LoRA、共置。不是长程 Agentic 轨迹或全参生产；仅当另一个弱校准点。[原始记录](https://github.com/Inferact/zero-mismatch-rl/blob/main/cases/kimi-k3.1/reports/bi0-bi1-claim-conditions.md) |

可交叉复算的第三个 DS 锚：[vLLM 10/23 原图](https://vllm.ai/blog-assets/interactive_pages/dsv41-pd-agentx-curve.html) 的 64 张活跃卡点，标题是 954,146 **总** tok/s/卡；切换 Output-only 实际为 6,866 输出/活跃卡，约 439,418 全系统输出/s，P90 TTFT 7.97s。相除不是 RL 缓存效率，而只是这个回放中输入体量远大于输出。

同一个 AgentX 家族也不等于同请求、同缓存、同量化、同 P/D 或同 SLO。部分真实回放 DS 4 卡点只有约 51–386 输出/卡，扩到大批量 wide EP 才换到另一条曲线。AgentX 用既有编码任务的长度、到达和前缀块结构回放，文本合成，未运行真实工具，也没有 RL 参数更新。**本文选 DS 820、Kimi 250 assistant tok/s/分配 rollout 卡作为必须在试点验证的基线规划假设**，不是公开测出来的 agentic RL 效率，也不是两个模型的本征倍率。两条曲线从「并发数/归一口径/采样一致性」三个不同地方来。Kimi 250 偏有条件：若只能稳定到 165 或 40，原 GPU 池按同合同约降到 **3,079 或 747 有效组/小时**，其余池会闲。DS 若只能拿到 300，约 **2,333 组/小时**。若每个分配 GPU 的上限复现不了，先调 SLO/并发/拓扑或缩 learner，而不是先买更多 CPU。

### Learner 和端到端锚点

- [Megatron-LM #6872](https://github.com/NVIDIA/Megatron-LM/issues/6872) 的 K3 全 93 层 mock 数据、强制均衡路由，64K/256K/1M 分别约 964/655/266 **序列** tok/s/卡（256/256/512 卡）。K3.1 仅证实 9 层代理 64 GB300 的 cuDNN 约 703 TFLOP/s/卡；完整 93 层 256K 配方通过配置验证，公开 tracker 仍未给实跑结论。代理的按卡序列吞吐绝不能直接套给全模型。64K 与 1M 相差 3.6×，有效 TFLOP/s 反而都在 760–813 的范围，这正是 token 口径不是固定工作量的例子。
- [MLPerf Training 6.1 Qwen3.5 RL 原始日志汇总及复算]({{ '/2026/11/17/mlperf-61-deepseek-mfu-qwen-rl/' | relative_url }})：GB300 千卡明确 **768 rollout / 256 actor**，中位到目标约 827 s，前九步 actor 约 296 s，暴露生成约 110 s，权重同步约 32 s。actor 约 1,795 **全输入** tok/s/卡；每步全输入约是有效 loss token 的 5.4×。此配方有过滤、没开动态采样、跳过 reference logprob；不含真实代码沙盒，也不能拿 3:1 当适用所有工作负载的答案。
- [AReaL](https://arxiv.org/html/2505.24298v5#S7.SS1) 在一组 1.5B 数学条件跑固定 250 步，41.0h→14.8h；[AsyncFlow](https://arxiv.org/html/2507.01663v2#S7) 在 7/32B 数学、32–512 昇腾卡上相对其适配基线平均 1.59×。它们证明队列、重叠和受控版本管理能回收空泡，不能乘到本文两种模型上。[StreamRL](https://arxiv.org/html/2504.15930#S7) 的固定生成长度 trace 与真实质量实验也要分读。

**为什么还建独立 GPU 池？** [DeepSeek 报告 §5.2](https://arxiv.org/html/2609.19969v1) 披露同物理卡分时、样本级维持在途并发、满组训练、以多个 checkpoint 段复用路由和 KV。 [Moonshot K3 报告 §5.3](https://arxiv.org/html/2607.24653v2#S5.SS3) 也有数百卡级共置实验、滚动续跑、host KV 与 NVMe 状态卸载；不是 K3.1 的配卡披露。本文采用隔离资源池便于独立量化 CPU、上线扩容和观测。对稳定长夜间 job，独立池常能掩盖工具尾部；对样本少、且发布和状态换入代价低的开发作业，共置可能更省。理想共置下同一 GPU 先后消耗 rollout 与训练 GPU 秒，整作业需要两者**相加**，不是用两池中较大的 GPU 秒；真实 idle/state swap 另加。两者必须在相同有效数据与质量约束下比较。

### 沙盒锚点：峰值、CPU 核秒和环境墙钟三本账

[Amazon Sandman](https://arxiv.org/html/2610.39711) 两个训练场景中模型等待占 rollout pod 生存时间约 74–91%；另一个 198 个 pod 的加权样本用了约 10.5% 请求 CPU。它既不是“活跃墙钟就是 10.5%”，也不能把几个百万 pod 的用量全套上。在一个 workload，沙盒启动 64 个在 1 秒内，另一个短爆发 132/s 对均值 1.8/s。用平均核数配置而不给镜像和启动通道留突发额度，GPU 可以在看起来 CPU 很闲时饿住。

[微信 WeEnv](https://arxiv.org/html/2609.30766) 的 8K SWE-Smith Python 任务，**每任务峰值** P50 约 1 核、P90 17.7、P99 68.3 核，P99 内存约 7 GiB；容器按需加载中位 32.5→10.6 秒，P95 83.5→35.1 秒。这些是峰值与初始化墙钟，不可相乘当成核秒。弹性 CPU 配额、冷镜像预取和 verifier 独立排队比给每个等待中的 episode 预留几十核划算。[Miles/Harbor MI355X 工程记录](https://www.lmsys.org/blog/2026-10-22-miles-mi355x-agentic-rl/) 的 384 在途/24 rollout GPU ×2 vCPU 配额折成 32 **请求 vCPU**/rollout GPU，不是 32 持续活跃物理核；其正常完成轨迹模型/沙盒墙钟约 77%/22%，云端启动 P50/P99 1.9/3.7 秒。[Miles Vera 实验](https://www.lmsys.org/blog/2026-11-13-miles-vera-sandboxes/) 在特定 H200 作业下显示更快沙盒还可减少闲挂 KV，但不能把 Vera 结果直接等同 Grace。

## 3. 用“每个实际尝试”统一三池

设 `λ` 是每秒**启动的轨迹尝试**（失败、重试均计入），`O` 是每尝试平均 assistant 生成 token，`D_CPU` 是每尝试累计物理核秒，`f` 是最终被消费的有效 sibling 槽 / 所有尝试，`S` 是最终被收录轨迹的平均 learner 计算序列 token，`G` 是组大小。分子分母用同一稳态窗口，队列积压有变化时记窗前窗后差；不假设每次独立成功。

```text
A_roll = N_roll × d / O                 # d: 全分配 rollout 卡，实际混合请求下的输出率
A_cpu  = C_phys / D_CPU                  # 核秒来自进程/容器 CPU usage 的累计差
A_train= N_train × a / (f × S)           # a: 训练池日历秒的序列 token/卡
λ_plan = min(0.80×A_roll, 0.65×A_cpu, 0.80×A_train)
消耗有效组/h = λ_plan × f × 3600 / G
各池负载 = λ_plan / A_i ; 这里不是 SM Active、MFU、MBU 或网卡利用率
```

这里的 `d` 是**混合负载服务曲线**的点，不能把架构直接代入。拆 P/D 时再加两个约束：`λ×Pmiss ≤ uP×NP×p`，`λ×O ≤ uD×ND×dD`；`Pmiss` 加总每轮新工具结果、无前缀命中和权重换代重建的真实 prefill，不重复把缓存命中的历史序列计费。另检验 KV transfer 和发布流量的共享链路切面。P/D 的初值由每轨迹资源秒决定；同卡上的 prefill/decode 争用时要用二维服务曲线，不能用两个孤立峰值同时承诺。例：若每次尝试实测 9K 真正未缓存 prefill token，DS 的 19.68/s 另需约 177k 未缓存输入/s；策略刷新后恢复使它翻倍，则是 354k/s，输出仍是 236k/s。此时是扩 P、先修复 cache/version 行为，还是改共置，都应先把 profiler 和跨 P/D 链路约束代入。

对 learner，`a ≈ 10^6 × F_eff(PF/s)/F_tok(GF) × U_calendar`。本例用 `6×P_active` 近似一次线性层前反向，再加 attention/index/KDA、路由及 shape 效应的规划裕度；跑实测时改为逐序列、逐组件算。用同一 FLOP 定义衡量 `F_eff` 和 `F_tok`，不要把重计算、padding、优化器通信既加进 FLOP 又重复从计时扣。额外参考/旧策略前向或 critic 未计入基线，应单独加对应 pass；rollout 的 logprob 可否直接复用需先做同权重分布测试。长轨迹混合时统计 `ΣL²/ΣL` 等长度加权量；对 DSA 还要计长索引、对 KDA 区分递归、边界状态和 CP。prompt/工具 token 即使 loss mask 为 0，经因果依赖仍可参与训练计算。不是给 12K output 做一次 `6N` 就结束。

## 4. 算例、显存与整柜约束

同一任务合同：8 sibling/组、每次尝试平均 12K assistant 输出；有用槽比例 72%；收录轨迹平均 18K learner 序列 token；核秒 **96**（规划分解例：9 次工具 × 4.5 秒 × 2 个平均忙核 +15 核秒终验/启动；不是行业平均）；沙盒从启动到结束墙钟基线 DS 480s / Kimi 660s，包含模型等待；平均每活会话主存 0.5 GiB。**均值只喂容量公式，P95/P99 和分位共现由 trace 单独验。** 两模型使用同一 72% 仅为了量级对照，线上须分别重测。其性能和接受率不会由参数量线性决定。

| 项目 | DS-V4.1-Flash | Kimi K3.1 Pro |
|---|---:|---:|
| 活跃训练期间有效计数性能（按配置卡摊，假设） | 600 TF/s | 703 TF/s |
| 单训练序列 token 的模型计算预算 | 125 GF（16B active 作为前反向规划基数，加约 30%） | 810 GF（104B，加约 30%） |
| 训练日历可用率（同步和调度外露，无 checkpoint 长停） | 95% | 95% |
| 日历 learner 速度 | 4,560 序列 tok/s/卡 | 825 序列 tok/s/卡 |
| GPU 分池 / CPU 资源 | **360 / 72 / 3,072 核** | **864 / 288 / 2,304 核** |
| 原始轨迹/s 的独立池上限（rollout / CPU / learner） | 24.60 / 32.00 / 25.33 | 18.00 / 24.00 / 18.32 |
| 准入轨迹/s / 完整可用组/h | **19.68 / 6,376** | **14.40 / 4,666** |
| 负载（rollout / CPU / learner） | **80.0% / 61.5% / 77.7%** | **80.0% / 60.0% / 78.6%** |
| 平均在途会话（若生命周期内都保留沙盒） | 9,446 档；约 4.61 TiB RAM | 9,504 档；约 4.64 TiB RAM |

![三池配置估算及负载：DS 360+72 GPU、3072 核；Kimi 864+288 GPU、2304 核]({{ '/assets/agentic-rl-gb300-pools.svg' | relative_url }})

例如 DS 每秒 19.68×12,000=236,160 输出 token；learner 处理 19.68×.72×18,000=255,053 **输入序列** token。二者不是一个口径。假设整个配置常驻，仅作资源账，分别约 **0.068 / 0.247 GPU·小时每有效组**（包含两池余量），与 0.48 / 0.49 物理核·小时每组（配置量）；不是两系统达到同质量的成本。Kimi 虽然买的 GPU 更多，**在这个共同任务合同下**目标启动率更小，所以所需 CPU 核反而更少；这不是 Kimi 单任务更省 CPU。固定 DS 的目标启动率运行 Kimi，仍要约 **2,907** 个可用沙盒核心（按 65% 负载，按主机取整还是约 3,072），另外至少约 **1,181 rollout 卡**和 **387 learner 配置卡**，再按柜/拓扑取整。实际提速可把 GPU 等待从沙盒 wall 中移出，却不会同比减少 CPU 核秒。

**如何找配比。** 先固定预算和架构闸门，再枚举整柜组合，最大化公式中的最小准入率，只有余量足够才进一步择低成本/低尾延迟。以 CPU 固定在表中配置、DS learner 至少 1 柜、Kimi learner 至少 4 柜的约束为例：6 柜 DS 的 4R+2L 只给 15.74 次尝试/s；5R+1L 给 19.68。16 柜 Kimi 的 11R+5L 给 13.20；12R+4L 给 14.40，而 13R+3L 未过 learner 容量闸门。DS 或 Kimi 各加一整 rollout 柜而不加 learner，仅约 **+3.0% / +1.8%**；余量很快改由 learner 决定。这是固定单位服务曲线近似，不是在坏柜、组相关、共享链路或新 TP 配置下求得的全局最优。脚本的 `--racks` 可复算。

**显存先过闸门。** 以全参训练每参数 16 B 为会计情景（BF16 模型+梯度各 2，FP32 master 4，Adam 两个 FP32 moment 共 8），理想完美切分静态约 DS backbone 8.83 TB；若连 196B Engram 都按相同 16 B 更新则 11.97 TB；Kimi 44.8 TB。若只许静态占用 279 GB×65%=181.35 GB/卡，容量下限约 **DS 49（仅 backbone）或 66（含 Engram）/ Kimi 248 卡**，尚未计 PP/EP 不均、共享参数副本、激活、通信 buffer、重算、本机 host 和 optimizer I/O。实际 16 B 随 FP32 梯度、Muon、ZeRO/分片、offload、冻结权重改变；64 活跃 DS 卡若把 Engram 全按 16 B 放 HBM，即使完美切分也超该 65% 预算约 0.36 TB，需要另验专用优化器/卸载或增加可用卡。两套基线不是“一张模型卡乘几个 NVL72 就已通过”：若 learner 实际采用 **64/256 在算**，另 **8/32** 是机柜未用槽，则要达到表中同一目标且保留 20% 余量，需要活跃卡约 **4,982/911** 日历 seq tok/s（分别约 **655/777** TF/s 的活跃计算要求）；实测只到原选的 600/703 则应限流，不要把备用卡算成工作卡。Kimi 全参 ≥256K 和 1M 必须重新选物理 CP/PP/EP 拓扑，512 卡近邻实测是容量规划信号，不是 288 卡已能训练。

Rollout 不给 HBM 一个虚假的「总权重×0.5 B」保证。DS 4 卡、Kimi 8 卡是公开 serving 支持的起点。DS 官方全局缓存 890 B/逻辑 token 的量级，例如 128 Ki token 约 116.7 MB/轨迹，仍需另加 SWA、复制、碎片等；不同内核格式不可照搬。实际核对权重文件、TP/EP 后每 rank 份额、未量化模块、draft/MTP、激活 workspace、KV 预留，再测 P/D 或全同构复制。Kimi 的 [vLLM KV 分析](https://vllm.ai/blog/2026-11-04-kimi-k31-pro#kv-cache-footprint) 给出 24 个 DSA 层 **FP8 16,992 B/token/卡**（TP 复制口径），FP4 缓存约 10,080 B，另有 69 层每会话 KDA 状态；DCP8 与 FP4 一起可把该 8 卡原测的 1M 并发从约 3 提到约 36，不能转写成训练容量。应监控 `λ×E[整生命周期 KV 字节·秒]`，而不只看活跃 decode batch。工具等待时可分层保留 KV，默认按版本隔离，比较回读与再 prefill；只有训练配方明确允许跨版本复用、记录旧段状态和行为概率时，才额外验收其质量与收益。

**CPU 按独立物理集群预算。** 24/18 台 ×128 个可调度物理核是示例（每节点需另验 p95 负载/系统保留，内存可先用 512 GiB 档）。机器数量不能只看核：9,500 个活会话若各占 2 GiB，就已接近 18.6 TiB，不含镜像缓存和 verifier 峰值；考虑 store/writeback、超时回收、NUMA、SSD IOPS、镜像注册表、网络和运行时 quota。[DGX GB300](https://www.nvidia.com/en-us/data-center/dgx-gb300/) 的 2,592 个 Grace CPU 核是**整柜物理总数**，不是可承诺给环境的核。host 还要喂 NCCL/数据、控制 offload、网络和故障恢复；x86 项目镜像不一定能直接跑 Arm。优先实测独立 CPU 池，再考虑只把经过兼容性验证、轻且不污染 host 的负载搬近 GPU。

## 5. 长尾、版本锁和网络，把“均衡”变成可验证

**组长尾。** 严格 8 条 sibling 齐备才可入队，组完成是八条的最大值。即使单条在给定时限内完成率为 95%，独立近似的组及时率也是 `0.95^8=66.3%`，真实数据含共享冷镜像、同题难度和执行相关性，必须从组 trace 直接量。提前只拿最快 K 条会改变 reward 方差和难题覆盖；用同题全组对照，按长度、任务类型、奖励分桶检查，不能拿选择偏差换曲线好看。全部八个 reward 都相同的组怎么处理，看算法；DAPO 的 [动态采样](https://arxiv.org/html/2503.14476#S3.SS2) 可滤无区分度组，其成本应算到前面三池，不等同 benchmark 平均正确率。

**版本预算。** 每 token 记录行为策略版本和 logprob，按组统计生成中、ready 等待、发布/安装分别造成多少 lag。以表中吞吐、每个优化器步消费 256 条不同的有效轨迹（若用多 epoch 或 minibatch，需要按实际步频另算），优化器步间隔约 18.1/24.7 秒。若端到端轨迹起始到消费的 P95 是 900/1,200 秒（压力测试假设），按每步发布则已是约 **50/49 更新步**，还没加版本安装偏差；若试验合同只允许 4 个优化器步，单靠加 CPU、缓存或每 16 步少发一次不能满足。少发确实减少通信和“服务发布版号差”，但不会消掉 learner 内部策略变化。可做：限制准入和 ready 深度、缩短并分桶长轨迹、阶段性冻结 learner 版本、适度放宽 lag 并做校正和收敛对照，或降低更新频率/增每步有效 token。不能把初始版本当后续所有 turn 的版本。同步小基线要保留：量化、核、采样与训练端不一致先独立排查，再只调 staleness。[AReaL 算法监控](https://github.com/areal-project/AReaL/blob/main/docs/en/best_practices/algo_perf.md) · [同权重 mismatch 对照](https://vllm.ai/blog/2026-11-06-zero-mismatch-async-rl) · [RLinf 两种 KV/权重边界](https://rlinf.readthedocs.io/en/latest/rst_source/guides/async_agentic.html)

**发布和通信。** 只算一份模型、按发布格式平均 1 B/param，则 DS backbone 552 GB（若 Engram 同发则两者 748 GB）、Kimi 2.8 TB；100 GB/s **有效聚合**切面理想下界分别 5.52s（含 Engram 7.48s）、28s，还不含量化/pack、重排、广播、install barrier、回冷 KV。BF16 传输翻倍，按每 18–25s 独立全量发一次时，Kimi 的例子连单份切面都超过周期。各 rollout 副本不是免费的 multicast：链路要按实际扇出、树复制和同时间 EP/CP/IO 汇总，TC/网卡标称峰值不能代替 goodput。用 shard-to-shard/分层广播、版本双缓冲、错峰或 lossless delta/LoRA（算法允许时），同时重测 KV 温度和版本差。单份模型 5.5/28s 与基线 5% 外露预算并不矛盾：**5% 是可被重叠之后的待验收目标**，若全程停发才可更新，两套基线都得下修。优先把低路由延迟 EP/CP 域放在同 NVL72；跨柜只用可验通信计数的 RDMA，不把 72 卡 NVLink 带宽用到整作业。[SparseRL-Sync](https://arxiv.org/abs/2605.07330) 是减少字节的一种研究方向，不预填其报告的压缩倍率。

## 6. 固定资源，先看瓶颈怎么移动

| 只改一个输入（基线参数见 CSV） | DS 有效组/h / 先触顶 | Kimi 有效组/h / 先触顶 |
|---|---:|---:|
| 基线 | **6,376** / rollout | **4,666** / rollout |
| 实际 rollout 每卡输出 −40% | 3,826 / rollout | 2,799 / rollout |
| 沙盒核秒 96→288 | 2,246 / CPU | 1,685 / CPU |
| 收录轨迹的训练 token 18K→36K | 3,283 / learner | 2,375 / learner |
| 每尝试输出 12K→24K | 3,188 / rollout | 2,333 / rollout |
| 同样生成开销，可用槽 72%→50% | 4,428 / rollout | 3,240 / rollout |
| learner 有效 TF/s −25% | 4,925 / learner | 3,562 / learner |
| 可用槽 72%→85% | 6,566 / learner | 4,749 / learner |

![固定卡数和核数时不同压力下的有效组吞吐，基线为100]({{ '/assets/agentic-rl-gb300-sensitivity.svg' | relative_url }})

这些是**独立冲击**。真实负载会同时变长、降低 cache hit、占用更多 KV、累积陈旧组，不能把各行当彼此独立的概率。若目标不变，训练 token 翻倍而每卡性能不变，learner 至少要约 **140 / 566 配置卡**，按整柜约 **2 / 8 柜**；长 context 往往进一步拉低每卡速度。CPU 核秒变三倍时，要维持原目标并守住 65%，约 **8,720 / 6,381** 个可用核；不是把沙盒内并行线程翻三倍就必然能恢复，因为有镜像、内存、I/O 和启动限额。守住各池 65/80% 也不是唯一最优：如果仍是同一个池触顶且该池容量不变，从 80% 抬到 90% 才能多 12.5% 原始吞吐，但若新负载下的有效率相对于旧条件降超过 11.1%，**有效组反而减少**。

工程上先做以下验收，而不从 6/16 柜直接起量：

1. **先抓同一批任务的多轮 trace。** 分桶文本/代码、短长上下文、冷/热镜像、测试强度，记录每个 episode 和 sibling 的 CPU 核秒、生成/未命中 prefill、峰值 KV 与挂起字节·秒、verifier 和重试，以及 policy 版本。冷启动、预热后稳态、极端组都要保留。实测填 `O,S,f,D_CPU`，不要乘各自独立平均假装捕捉了尾部。
2. **小规模三通道试点。** DS 可从单个 4–8 卡 rollout 单元加一柜级训练验收、Kimi 从 8 卡 rollout 路径及约 256 活跃训练卡配方的可运行性开始；没有全参资源，先用 LoRA/截层验证数据流程，明确不用于给全参采购签字。试跑 warm/cold、Kimi 160/250 和 DS 300/820 目标，测每步实耗，跨柜一并验证事务式权重安装与恢复。
3. **按物理单元扫描，不按算术配比硬分。** 固定任务合同与 token/版本约束，把某一池加/减一组实际 TP/EP 单元或一柜，重跑同样的到达批次。脱敏 trace replay 至少包含主流稳态、沙盒突发镜像冷源、长序列升档、故障掉一柜四组。记录 queue depth 的斜率、组 P95 入队到消费，用有效组/小时、每有效组 GPU/CPU 小时、持出集 time-to-quality 选 Pareto 点。若待用队列堆涨、重要性权重尾部/ESS 或覆盖恶化，即使 tokens/s 增长也不扩。
4. **判断该加谁。** GPU decode 等工具多但实际 CPU 核负载低：先查排队、镜像和 verifier，不增加闲核；R 池输出已饱和而训练等数据：加 rollout 或修前缀/路由；ready 长期涨而 learner 忙：加 learner/优化 packed 训练和 ref 旁路；GPU 两边都低、age 或同步高：先解版本、共享链路与 group barrier。不同阶段难度随训练变，配比需要逐阶段复算。

最后用四条口径收工：**集群端到端看有用组/小时与达标时间；rollout 服务看真实混合负载生成吞吐；沙盒看核秒与每环境尾延迟；learner 看全序列吞吐加训练质量。** GPU、CPU、learner 三条线任何一条只交一个漂亮利用率，都还不能解释系统为什么慢。
