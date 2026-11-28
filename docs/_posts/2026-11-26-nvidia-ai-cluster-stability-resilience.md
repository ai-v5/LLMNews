---
layout: post
title: "万卡集群怎样验收、定位慢卡和恢复训练？拆解 NVIDIA 31 分钟韧性演讲"
date: 2026-11-26T11:42:47+08:00
last_modified_at: "2026-11-26"
summary: "用时间轴梳理 NVIDIA China AI Infra Day 的训推集群韧性分享，从 23:29 的交付验收单讲到 kernel、NCCL 和三层重启，再把故障恢复拆成可量化的训练和推理指标。"
section: explainer
label: "集群韧性"
tags: [NVIDIA, 集群验收, 分布式训练, RoCE, NCCL, 推理]
demo: false
sources:
  - title: "NVIDIA 英伟达：提高大规模训练和推理集群的稳定性和弹性（原视频）"
    url: "https://www.bilibili.com/video/BV1dT1xBkEKe/"
  - title: "Meta：The Llama 3 Herd of Models"
    url: "https://arxiv.org/html/2407.21783"
  - title: "DeepSeek-V3 技术报告：推理与部署"
    url: "https://arxiv.org/html/2412.19437#S3.SS4"
  - title: "NVIDIA Resiliency Extension"
    url: "https://github.com/NVIDIA/nvidia-resiliency-ext"
  - title: "NVIDIA NCCL Profiler 插件接口"
    url: "https://github.com/NVIDIA/nccl/blob/master/plugins/profiler/README.md"
  - title: "NVIDIA Dynamo Shadow Engine Recovery（后续案例，不在视频内）"
    url: "https://developer.nvidia.com/blog/restore-llm-inference-capacity-in-seconds-with-shadow-engine-recovery-in-nvidia-dynamo/"
---

[原视频《提高大规模训练和推理集群的稳定性和弹性》](https://www.bilibili.com/video/BV1dT1xBkEKe/)全长 **31:25**。在 [23:29](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=1409)，NVIDIA 的验收页给出了一条清晰顺序：**单机先验算力、PCIe、NCCL 和烧机；多机从小到大，先测通信，再跑 GPT 训练验证应用表现。** 这个顺序同样适用于今天的多平面 RoCE 集群：机内和端口没有达到各自基线时，跨万卡的平均数很难说明根因。

前半篇按时间轴整理原视频，后半篇把这些方法拆成工程验收项和可量化指标。公开原片保留在上方，正文不转载完整逐字稿或课件。

## 一、原视频内容纪要：跟着 31 分 25 秒走一遍

以下按全片可见换页组织，时间码为近似起点。纪要依据原视频画面和能读清的课件，数值另与一手资料交叉核对；未能可靠核验的口头发挥、课件小字不补写。录制于 2025 年 10 月 24 日的 China AI Infra Day，B 站于 2025 年 11 月 5 日发布。片头标注讲者为 NVIDIA 解决方案架构师杨广楼。演讲中的软件版本和路线图均是当时口径。

### [00:00–05:04｜开场与 AI Factory 基础设施](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=0)

开场把主题放在“规模上去之后，系统能否稳定、高效地跑”。从约 00:47 开始的 AI 工厂图由下而上展开：供配电、液冷和散热，机柜布局及走线，主机 CPU/内存/PCIe、GPU/NVSwitch/NVLink，再到东西向计算网络、南北向服务网络、存储和管理。几种网络的责任不同：东西向承载训练与推理跨节点通信，采用面向 rail 优化的胖树，举例为 InfiniBand 或 RDMA 网络；南北向以独立 BlueField 智能网卡承载存储、多租、卸载与隔离；带外管理不依赖业务进程，用于监控与处置。数十万 GPU 被描述为由多个可扩展单元和网络结构组合的建设规模；课件没有给定一个数十万 GPU 单作业的拓扑或实测结果。

### [05:04–08:08｜大规模训练的两类问题：停机和慢机](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=304)

从十亿到万亿参数，机器数上升，电源、CPU、GPU、内存、软件、网络与线缆都可能导致中断。还有一类问题不直接报错：某个组件性能降级，仍在线的所有 rank 被同步依赖拖慢。故障后的人工定位、恢复及回滚也吃掉进度。因此重点是有效训练时间，不是只有训练跑起来时的 FLOPs。配图把 GPT-175B 的并行示意（8-GPU 节点内 TP、6 节点 PP、64 组 DP）和 3,072 卡、502 PFLOPS 的数字放在一起。这里应拆开读：[Megatron-LM 原论文](https://arxiv.org/abs/2104.04473)的摘要将 502 PFLOP/s 对应到万亿参数模型的训练迭代，不宜归给 175B。

### [08:08–10:04｜PD 分离与大 EP 让推理也成为跨节点系统](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=488)

Prefill 与 Decode 分开，可放在同构或异构资源池；Prefill 端建好 KV，Decode 端需要可靠地接收并继续用。两侧的并行域内部也可能各自有高性能网络需求，不能只盯中间一次 KV 传输。演讲用 DeepSeek-V3 的生产部署经验举例，列出 Prefill 单元最少 4 节点/32 GPU、Decode 单元最少 40 节点/320 GPU。[DeepSeek-V3 技术报告 §3.4](https://arxiv.org/html/2412.19437#S3.SS4)可以交叉核对；[后来的 V3/R1 推理系统说明](https://github.com/deepseek-ai/open-infra-index/blob/main/202502OpenSourceWeek/day_6_one_more_thing_deepseekV3R1_inference_system_overview.md)则给出了 18 节点的 EP144 Decode 单元，属于另一套部署配置。这是特定 LargeEP 实例的部署单元，不是所有 DeepSeek 推理或后续产品的最小卡数，也不是 32 张预填充卡永远配 320 张解码卡的最优比例。

### [10:04–11:43｜相关工作：已有工具各自看哪一层](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=604)

讲者列的材料不限于 NVIDIA：Meta 的 OPT 与 Llama 3 报告及训练日志；字节的 MegaScale 和 veScale；蚂蚁的 DLRover 与 xpu_timer；阿里的 AICB 与 C4D；腾讯的 CUDA hook 慢卡/挂起定位与 TCCL；上海 AI Lab 的数据中心大模型研发工作负载研究；微软的 NPKit；以及 NVIDIA 的 NVRx 和 NCCL profiler。可分别用来参考故障画像、调度与恢复、通信仿真/基准、算子与通信事件定位。视频此处是文献地图，并未为每个工具给同一场景的横评。

### [11:43–16:01｜Meta 经验：准备备用节点，并把人工排障变成流程](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=703)

- **OPT-175B：**演讲回看约千张 A100 的训练，列出 40 多次重启及 ECC、IB、NCCL、GPU 掉卡、作业挂起、配置不一致等问题。应对包括备用节点、脚本换节点、GPU 烧机、IB 自动测试和扫描训练日志里的 loss 尖峰/挂起。原始背景见 [OPT 论文与日志入口](https://arxiv.org/abs/2205.01068)。
- **Llama 3：**约 16K H100 的过程里，大家关注的不只是故障数量，而是怎么把作业重新拉起来。讲者强调缩短启动、加快 checkpoint、快速定位问题，并用 Meta 的 NCCLX 与 PyTorch Flight Recorder 说明如何查失败或未完成的 collective，观察 rank 之间通信进度。中断统计在后面的解读中按 Meta 原始报告拆开计划内与计划外；不要把视频口语中的“重启”直接当成某一种硬件失效率。

### [16:01–18:23｜训练作业流程：故障按硬件和软件分流](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=961)

从新平台导入、压力基准、基础设施设计与交付验收开始，过关的节点进入资源池；作业启动后持续做带内/带外监控和 checkpoint。出现失败，先定位并验证。软件缺陷修复后可回归验证，再安排重启；硬件、固件或驱动类问题走排查和节点下线维修路径，节点修好也要重新验证才归池。健康资源可另起作业，不必等修好的旧节点回来。流程图把“作业重新运行”和“故障节点最终修好”画成两条可并行的工作线。

### [18:23–22:41｜韧性 profiling：把整段墙钟时间分账](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=1103)

时间轴覆盖准入健康检查、调度、容器启动、框架/通信初始化、加载 checkpoint、稳定训练、保存、故障后的丢失工作，以及关停和健康检查。课件把可以下手的地方分成五组：集群交付（架构、拓扑、存储、软硬件一致性、烧机与 GEMM/通信/应用基准）；运行时挂起、loss 和 GPU/网络信号的监测；故障专项健康诊断；Kubernetes/框架/进程各级启动和重启；分布式并行或异步保存与内存到全局存储的分层 checkpoint。示意图的分钟和秒用于说明不同层级的设计目标，不是任意规模的实测承诺。

### [22:41–23:39｜提高稳定性：从部署顺序到 23:29 的验收单](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=1361)

前一页按网络开通、环境部署、Kubernetes 安装、Kubernetes 上的训练/推理、性能验证展开。涉及 BF3/DOCA、RoCE 与 GPUDirect RDMA，GPU 驱动、Fabric Manager、容器与 DCGM，再到 NeMo、Triton、TensorRT-LLM 及相应的基准。该页是参考部署顺序，不是当前版安装手册。

[23:29 画面](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=1409)是交付检查与测试页。左侧是**全节点分布式检查与结果汇总**，覆盖版本、枚举、内存和互联等配置，找出离群节点。右侧把测试明确分成两档：

| 原页的验收层级 | 右侧可核实的项目 |
|---|---|
| 单节点 | Peakperf 检查 BF16、FP32、TF32 计算；做 PCIe 带宽检查、单机 NCCL 性能测试及 GPU Burn 持续压测 |
| 多节点，从小到大 | 先用 NCCL 验证网络，再跑 GPT 训练验证应用层表现 |

页底是集群汇总结果示例。视频画质不足以可靠抄录左侧每条命令、机台行号或阈值，这些细节不作复原。此页给出的是交付项目与检查层次，没有证明某种 40 万卡组网已经验收。

### [23:39–24:53｜监控套件与两页故障经验](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=1419)

- **监控套件：**SMBPBI 带外看链路、功率、温度、时钟和 ECC 等；DCGM Exporter 接入 Prometheus，补 GPU 运行指标；驱动模块、Fabric Manager、进程卡在 D 状态，以及未必被单一指标覆盖的 Xid，另查系统日志。IB 场景用 UFM/Grafana 的端口流量和错误计数；这不是说 Ethernet/RoCE 应原样使用 UFM 的 IB 计数器。
- **经验一：**NVLink/NVSwitch 故障、驱动问题、性能异常、GPU 静默数据损坏分别处理。举例包括 SXid 或总线错误、驱动挂起或设备消失、拓扑错误识别/时钟降低/PCIe 设置与 GDR 路径问题，以及训练中出现 NaN。由日志、单节点与跨节点 AllReduce、专项诊断和应用 loss/gradient 一致性逐步缩小范围。NaN 是症状，不能凭它单独认定硬件损坏。
- **经验二：**掉卡、ECC/UCE、作业挂起、网络 link flap 与观测工具本身引入抖动都要考虑。示例包含启动前配置检查、运行中进度与系统日志检查、超时/退出机制，以及把问题节点移出后重新启动。课件所列部分 Xid/固件与驱动例子依赖年代和平台；换到其他 GPU、固件或 NIC 时应以对应官方支持说明为准，不能直接照抄版本号。

### [24:53–28:08｜从 GPU kernel 追到 NCCL 与网络事件](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=1493)

- **24:53，GPU kernel 级。** MegaScale 用 CUDA event 记录关键操作，配合 TP/PP/DP 维度的热图找慢 rank 和跨 rank 依赖。[MegaScale 论文](https://arxiv.org/abs/2402.15627)给出这种诊断图的原始语境。xpu_timer 通过 CUDA Runtime、cuBLAS、NCCL 等接口记录计算与通信，辅助查看健康/降速/挂起时间线和栈。
- **26:01，NVRx 慢 rank 检测。** 针对 PyTorch 分布式作业，在指定区段先看 CPU 墙钟；可选通过 CUPTI 汇聚 GPU kernel 时间。课件区分以当期最快 rank 为参照的相对表现与以自身历史为参照的表现。前者回答“是否落后同伴”，后者回答“是否较过去退化”。
- **26:44，网络 kernel 级。** NPKit 把 NCCL 中的 GPU 传输及 CPU 侧收发等事件放到统一时间线，可按 channel 和尺寸对照。C4D 从通信域、rank、设备、collective 类型/算法等维度定位慢、挂、故障，画出有助于排查的矩阵。
- **27:36，NCCL Profiler 插件。** 课件展示插件按 communicator 建上下文，记录起止与进展事件，并以事件掩码决定采集范围。图上的 group/collective、P2P、proxy 和 network 插件等层级，是把大段“等通信”拆成可定位阶段的关键。环境变量和事件覆盖以实际 NCCL 版本和 [插件接口文档](https://github.com/NVIDIA/nccl/blob/master/plugins/profiler/README.md)为准。

### [28:08–30:19｜提高韧性：NVRx 和三层重启](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=1688)

NVRx 在课件上是一个开源 Python 扩展：自动重启、分层 checkpoint、故障检测、GPU/NVLink/NIC 健康检查四类能力并列。自动重启图给三个 **目标量级**：

| 层级 | 课件目标 | 适用故障边界 |
|---|---|---|
| 进程内 In-process | 约 10–20 秒 | 进程本身仍能信任时，重启训练循环，示例是 Python CPU 异常、瞬时网络故障 |
| 作业内 In-job | 约 1–2 分钟 | 保留作业分配、重建训练进程，可考虑热备；示例为训练进程已退出或需要新的 CUDA 上下文 |
| 作业级 Job restart | 数分钟 | 由调度器重启作业，应对更难恢复的永久故障 |

策略从健康检查和健康 worker 会合开始，视情况用热备、在框架允许时降 batch size 或升级到更外层重启。进程内示意通过 Python 包装通知 ranks、销毁旧进程组、停止目标函数、做健康检查、重新分配 ranks，再重新进入目标；分布式 store 与超时贯穿其中。作业内示意则不假定原进程还能活着：基于修改过的 Torch Elastic 启动器和 rank 监视客户端/服务端，靠周期心跳、失联和挂起来触发诊断，必要时重建 CUDA 上下文，从最后有效 checkpoint 启动。超时可按已观察到的迭代时间校准或手设，并配 GPU/NIC 健康检查。切换到热备或缩卡也不等于能无损保留任意并行切分。

### [30:19–31:25｜OAIC 与当时的路线图](https://www.bilibili.com/video/BV1dT1xBkEKe/?t=1819)

压轴介绍 OAIC（Open AI Cloud）方向：把裸金属/虚拟化、OpenStack/Kubernetes、调度与作业管理、监控以及性能和有效训练时间目标做成可部署的软件栈，而不仅是一份架构文档。末页按 IaaS、PaaS、稳定性和框架分列规划，含 GB200 适配、监控/健康检查、训练与 PD 分离/LargeEP 等。区分这里的 **OAIC 路线图 v0.4** 与前面 **NVRx 开源版本**的语境；都不应拿来判断当前功能已上线。最后展示 GPU 系统知识库与配套资料入口。

## 二、技术解读：把稳定性和弹性拆成可以验收的指标

### 1. 先问故障后还剩多少有效工作，而不是只问机器有没有起来

稳定性减少异常发生和异常外溢；韧性缩短故障停机、减少进度回滚，并保证恢复后的结果正确。横向容纳更多卡并不自动提高两者。训练最常见的漏算，是监控已显示网络恢复，训练仍在等待另一个 rank、重建 communicator、重新装载优化器状态，或者前一轮未提交的 step 必须重算。推理的漏算相反：健康副本已接受新请求，老流式请求却被断开，或 PD 交接的 KV 已经失效。

用四个时间刻度来验收：**告警发现、流量恢复、首个正确的 collective/训练 step、恢复到目标吞吐或 SLO**。另记两个损失量：训练丢失的已算 token / step，推理在途请求无需客户端重试完成的比例。把“训练有效时间”与 MFU 分开：前者把调度、失败停机、恢复与回放纳入分母；后者如果按稳定 step 的有用 FLOPs 计算，就不会反映这些损失。近似地，若稳定期 MFU 45%，有用训练时间占 90%，长期有效算力利用率约 40.5%，而不是 45%。

[Meta Llama 3 技术报告 §3.3.4](https://arxiv.org/html/2407.21783#S3.SS3.SSS4)给出一个可复核的量级：16K GPU 环境，54 天观察期有 466 次作业中断，47 次计划内、419 次非计划内，非计划中断间隔按窗口平均约 **3.09 小时**。论文报告有效训练时间超过 90%，并不表示无故障；意味着自动化、快速定位和恢复抑制了故障成本。论文中的 GPU 问题约占非计划中断的 58.7%，不是全部中断，也不是任何其他集群的先验比例。把这个间隔线性外推到 40 万卡，会忽略故障相关性、作业分片、热备和机房级共因。

可用一个明示假设的一阶模型把账算出来。设相关故障平均间隔为 M，成功且持久的 checkpoint 间隔为 T，同步前台开销为 C，故障后恢复到首个正确 step 的时间为 R。若故障近似独立、小损失且均匀落在 checkpoint 区间，长期损失约 **C/T + (R + T/2)/M**，最优间隔近似 **√(2CM)**。这里异步写只拿真正暴露在关键路径的停顿作 C；尚未持久化的异步副本不能作成功 checkpoint。机柜或供电共因明显、快照写入排队、频繁故障导致多次重启时，要用实测分布和故障域仿真替代这个式子。 例如 **M=3 小时、C=20 秒、R=120 秒** 时，模型给出的 T 约 11 分钟；同期望损失约 7.2%，其中 checkpoint 前台停顿与回滚各约 3.0%，恢复约 1.1%。这是示意，不是 Meta 或 NVIDIA 实测。

### 2. 交付验收：按拓扑分层放量，先验证最差路径

23:29 那页有价值的地方，在于把交付检查放到故障恢复之前。建议每层都有保留原始产物的通过条件，并附软件版本、rank→GPU→NIC→交换机端口映射、布线/光模块型号和压测矩阵。下面是解读给出的模板，不是讲者原表的逐字复刻。

| 闸门 | 要跑什么 | 最容易被平均值掩盖的失败 |
|---|---|---|
| 节点与机柜 | GPU/HBM、PCIe、NVLink/NVSwitch、功耗热稳态；重复冷启动与持续负载 | 单卡降频、链路降宽、可纠正错误率爬升 |
| NIC 与链路 | 核对实际 lane、FEC/可纠错或不可纠错错误、光功率、端口速率；双向与不同消息尺寸 | 单方向错包、同一物理 cage 下两条 breakout 同失效 |
| 轨/平面/Pod | 按每条轨或平面分别测，覆盖短/长路径、跨楼边界、热点与反压；检查 QoS、ECN/PFC 及队列行为 | 流量偏置、PFC 向上游传播、路径哈希碰撞、慢 rank |
| 作业和服务 | AllReduce、AllGather、ReduceScatter、AllToAll，最后跑真实 EP/CP/PP/DP 或 PD；故障前后对比 | AllReduce 平稳，EP incast 与 P99 却已失控；形成能用的通信域但运行时无法重建状态 |
| 故障复测 | 用受控验收环境演练单链路/单平面丢失、进程失败、GPU/节点故障，并验证状态一致性 | 路由已切换但 communicator 卡住；重启成功但 step 不一致或在途请求全部丢失 |

[NVIDIA 后来发布的集群验收工具说明](https://developer.nvidia.com/blog/validate-gpu-cluster-readiness-before-ai-workloads-land)也把 DCGM 诊断、NCCL 多类通信和真实 NeMo 训练分开检查，这是讲后新资料，不是原视频中的部署工具。数据面跑满不等于成功验收。把报表里的算法带宽、busbw、端口线率和有效 payload 分开，标明十进制单位以及单向/双向口径；不要把 bidirectional 数字当单向上限。40 万卡场景先按 Pod、楼、平面、轨分层取样，再做跨域并发和故障演练，而不是把某次 256/512 卡好成绩外推。两平面覆盖同一可达集合；隔离多轨只有轨内原生直达，PXN 等中转路径的 NIC/本地互联成本还要独立测。拓扑容量与端口账另见 [40 万卡 RoCE 的设计推演](https://ai-v5.github.io/LLMNews/2026/11/25/roce-400k-xai-clos-design/)。

### 3. 慢在哪里：跨层拼接，而不是见到 NCCL 等待就换光模块

一条有用的 trace 至少能拼出 job → step → rank → kernel/collective → communicator/channel → 物理端口。**先看谁晚进入，再看已进入之后谁迟迟不退。** 晚进入常见于数据加载、CPU 调度、模型分支和 MoE 专家偏斜；大家齐进但少数路径尾很长，再去看网络、队列、重传、FEC、PCIe 或 NVLink。一个 GPU 等在通信 kernel 里可能只是受害者。GPU kernel 时长回答的是“哪里等”；要看跨 rank 时间线和网络事件才能回答“谁让它等”。

日常持续跑低开销的 rank/step 分位数与拓扑计数器；触发时再打开采样 trace 或 profiler，以免长时间全量采集改变负载或制造存储瓶颈。[NCCL RAS](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting/ras.html)偏 communicator 状态与挂起诊断，[NCCL Profiler 插件接口](https://github.com/NVIDIA/nccl/blob/master/plugins/profiler/README.md)偏事件时间线，二者都不是自动恢复机制。训练 straggler 要同时看“比同类 rank 慢”和“比自身历史慢”；不同 PP stage、专家负载和 GPU 频率区间不能混用同一个绝对阈值。再用进程进度、故障计数器和拓扑邻近性验证，以免用重启掩盖正常的模型负载变化。

### 4. 恢复阶梯：把进程、作业、网络与请求分开测

| 恢复边界 | 保留什么 | 必须验证什么 |
|---|---|---|
| 进程内重启 | 作业分配与仍可用的外层进程 | 旧通信/设备上下文是否可清理，所有 rank 是否回到共同状态 |
| 作业内重启 | 保留调度 allocation，重新创建工作进程；能否替换节点取决于编排与余量 | rank 重映射、回滚时间、checkpoint 可读性、重启不会反复落在同一坏节点 |
| 作业级重启 | 只依赖持久 checkpoint 和外部调度状态 | 重排队、节点隔离、新拓扑带宽以及首个正确 step |
| 推理容量恢复 | 可用副本或热备重新接纳流量 | 剩余容量是否承压，冷 prefix 是否导致 TTFT 尾升高 |
| 在途请求恢复 | 能否迁移/重建请求状态，另含工具或流式输出状态 | token 是否重复/漏发，是否需要客户端重试，端到端达标率 |

网络平面切换、NCCL communicator 重组与作业状态回滚，是三个不同层级。仅从 [NCCL communicator API](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/api/comms.html#ncclcommshrink)看到存活 rank 能组成新 communicator，并不能推出 TP/EP/PP 的模型或 optimizer 分片能在少卡下正确继续；重新映射与状态恢复仍由运行时负责。[NVRx](https://github.com/NVIDIA/nvidia-resiliency-ext)也应按使用的版本和后端检查能力，不能把视频里一张 2025 年路线图当成现行支持矩阵。

**PD 的恢复还需要检查三条边。** P 故障时重路由能否重新预填充，取决于输入是否保留、P 池余量和 TTFT 限额；P→D 传输故障时，应核对 KV 交接的完成标记、目的布局与重试去重；D 故障时，即使 P 还活着，已生成 token、采样状态、会话和流式边界也未必仍在。把 KV 传输 P99 与 D 内部 EP A2A P99 分开，不然同样表现为长输出卡住，却可能修错资源池。

推理侧有一个后来发布的交叉例子，**不是视频内容**：[NVIDIA Dynamo 的 GLM-5.2 双 worker B200 实验](https://developer.nvidia.com/blog/restore-llm-inference-capacity-in-seconds-with-shadow-engine-recovery-in-nvidia-dynamo/)杀掉一个 worker 后，第二个 worker 恢复服务从冷启动的 **283 秒**缩短到 **7.3 秒**。它依赖同一批健康 GPU 上预初始化的影子进程与共享权重。[版本文档](https://docs.nvidia.com/dynamo/v1.6.1/kubernetes/fault-tolerance/shadow-engine-failover)明确区分进程故障与 GPU/节点故障，并不承诺无损保留这批在途请求或其 KV。这里应记录“容量恢复 7.3 秒”，而不是“服务 7.3 秒无损恢复”。

归根结底，**验收终点应是首个正确 step 或足量正确且达标的请求，然后看能否稳定维持**。如果交付报告只填一列“故障恢复耗时”，它无法区分是路由切了、worker 接单了，还是业务已经真正恢复。
