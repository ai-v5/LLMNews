---
title: "TorchFT 深度解读：坏一张卡，为什么要退一整组？"
date: 2026-11-17T19:18:24+08:00
summary: "TorchFT 把全局停训变成外层数据并行副本的摘除和在线回补。对 MoE，真正要算的是完整副本有多大、活副本能否持续提交，以及跨域梯度和恢复流量会不会抢同一个瓶颈。"
section: explainer
label: "训练系统"
tags: [TorchFT, 容错训练, HSDP, MoE, 超节点]
demo: false
sources:
  - title: "TorchFT 源码快照，2026-11-10"
    url: "https://github.com/meta-pytorch/torchft/tree/3a55d0241c38cd73798af3e0604ffe07ab77190f"
  - title: "PyTorch × Crusoe：300 张 L40S 的合成故障压力测试，2025-06-20"
    url: "https://pytorch.org/blog/fault-tolerant-llama-training-with-2000-synthetic-failures-every-15-seconds-and-no-checkpoints-on-crusoe-l40s/"
  - title: "Reve 2.0 训练基础设施报告：Ray auto-shrink 与 TorchFT"
    url: "https://app.reve.com/training-infra"
---

TorchFT 最重要的设计不是让一张坏卡原地恢复，而是让**其他完整的模型副本不必跟它一起重启**。副本内仍然是静态的 TP、PP、EP、CP 或 FSDP 分片拓扑；副本外的数据并行组可以缩小，等替补组从在线同伴同步到正确版本，再把它加回来。用在大 MoE 上，首先要问的不是「能扛几张坏卡」，而是「坏在哪个通信域，会牵连掉多大的完整副本」。

本文以 2026 年 11 月 10 日的公开源码 `3a55d02` 为准，区分代码机制、公开实验与工程推导。没有把 README 支持列表当作大规模性能证据。

## 1. 两层并行，两种故障边界

| 边界 | 正常运行 | 某个 rank 掉线以后 |
|---|---|---|
| **副本内：一个完整分片模型** | FSDP all-gather / reduce-scatter、TP collective、PP 点对点、MoE token dispatch/combine 等仍按既定拓扑执行 | 若该 rank 不可替换且组内 collective 失败，通常摘除并重启这个副本；TorchFT 不自动把缺失专家、PP stage 或参数 shard 重新编排到其他卡 |
| **副本间：同坐标 rank 组成的外层 DP** | 在 HSDP 中，同一 shard 位置跨副本归约梯度 | 外层成员可变。新 quorum 仍满足约束时，剩余副本可继续；新组用在线状态修复后加入 |
| **控制面：Lighthouse 与每副本 Manager 服务** | 收心跳，协调副本成员、quorum 版本和恢复；Manager 在组内收齐各 rank 的决定 | Lighthouse 是单点，不是高可用共识集群；故障域划分还要覆盖控制面、bootstrap store 和调度器 |

例如，四个各 128 卡的完整模型副本，故障使其中一组失效时，能继续的是其余 384 卡，而不是 511 卡。若 EP 或 PP 穿过四个所谓「副本」的边界，它们就不是四个独立容错单元。应该先画出参数、专家、pipeline stage 和数据流的依赖图，再确定最小完整副本，而不是把物理机柜直接当作副本。

## 2. 一步如何提交，旧副本如何回来

1. **确定成员与版本。** 每个副本的 Manager 服务先协调本组 rank，再向 Lighthouse 参与 quorum；Lighthouse 结合心跳、上轮成员与加入等待窗口决定新成员。非快速路径比较的是当前心跳健康的副本数，而不是最初分配卡数的多数，还要满足最低副本数。Manager 收到 quorum ID、最大已提交步 `max_step` 和恢复信息；成员变化时重配外层进程组。异步 quorum 能与前向重叠，但反向通信和提交仍有依赖，重配和数据恢复不会凭空消失。
2. **归约并设置提交门。** TorchFT 管理的集体通信把异常登记到 Manager；在有效参与者中归约并用有效参与数做平均。异步恢复中的成员可以出现在通信组中但不贡献有效梯度。反向之后、optimizer 更新之前，各 rank 调用 `should_commit()`；本组任一 rank 报错或有效副本数不够，就跳过这次 optimizer 更新。**这是副本内的共同决定，不是所有副本之间的全局两阶段提交。** 不同副本可以对一次提交得出不同结果。
3. **在线修复。** 落后组或新组从由协调器指派的最新版本同伴接收状态。匹配分片布局时按同一组内 rank 坐标传输，不必先在一张卡上聚齐全模型。状态可由 HTTP 或进程组 transport 传送；用户状态在安全点应用，异步模式下落后组不贡献本轮有效梯度。只有恢复到正确版本并满足后续成员条件，才重新贡献训练。持久化 checkpoint 仍负责整个作业掉电、所有有效状态消失和上线版本回滚。

源码入口：[Lighthouse 成员选择](https://github.com/meta-pytorch/torchft/blob/3a55d0241c38cd73798af3e0604ffe07ab77190f/src/lighthouse.rs#L141)、[Manager 恢复](https://github.com/meta-pytorch/torchft/blob/3a55d0241c38cd73798af3e0604ffe07ab77190f/torchft/manager.py#L643)、[提交门](https://github.com/meta-pytorch/torchft/blob/3a55d0241c38cd73798af3e0604ffe07ab77190f/torchft/manager.py#L849)、[进程组 checkpoint transport](https://github.com/meta-pytorch/torchft/blob/3a55d0241c38cd73798af3e0604ffe07ab77190f/torchft/checkpointing/pg_transport.py#L170)。

两个一致性边界容易漏掉：

- **最新版本标号不是状态校验。** 官方协议假设同一有效步的模型状态一致；官方部署说明也要求新旧成员有重叠，并警告多个独立 Lighthouse 可能形成分裂。它不是任意网络分区下的强一致系统，也不检测静默权重损坏。故障注入中应验证参数和 optimizer shard 哈希，而不只是 step counter。
- **参与卡数变化不是纯系统问题。** 动态参与会改变每步的有效全局 batch；副本梯度等权平均也不自动等于按有效 token 加权。需明确 token 归一化、梯度累积、LR scheduler、数据游标和随机状态分别如何推进：全局共享、按副本重建，还是写入持久 checkpoint。TorchFT 自带的 [DistributedSampler](https://github.com/meta-pytorch/torchft/blob/3a55d0241c38cd73798af3e0604ffe07ab77190f/torchft/data.py#L23) 明确允许掉组时丢弃部分样本，不提供 exactly-once。应用还要测试提交门通过后、optimizer 或调度器尚未完成时的 crash。

[官方故障假设与部署建议](https://meta-pytorch.org/torchft/assumptions_and_recommendations.html)

## 3. 健康时有没有额外开销？坏了以后又怎么量？

公开的 PyTorch × Crusoe 故障注入用了 30 个 10 卡副本、300 张 L40S，示例模型是 Llama 3 1B；组内是 NCCL，跨组用 TCP Gloo。部分故障通过取消整组 Slurm 作业注入，不能等价成每种真实 fabric 故障。

| 合成故障频率 | 尝试步 / 提交步 | 提交率 | 平均参与副本 | 原报告口径的训练效率 |
|---|---:|---:|---:|---:|
| 约每 60 秒 | 6,249 / 5,145 | 82.3% | 29.6 / 30 | 81.2% |
| 平均约每 15 秒 | 888 / 268 | 30.2% | 18.9 / 30 | 13.4% |

这验证了反复失组时仍可提交和恢复，也表明**跑得下去，不等于跑得经济**。最后一列是原报告定义下的效率，不是 MFU，也不是生产 MoE 的预计损失。实验里 Gloo 便于尽快失败和重建，不意味着 TorchFT 必须用 Gloo；固定版本文档还列出原生重配路径（要求 PyTorch 2.14+ 和支持的后端，文档列举 Gloo 与 nccl2），并强调 bootstrap store 存活、独立外层 PG 和受管理的 collective。该路径的可用性与稳态开销应按目标版本实测。NCCL 组内故障、超时级联、重配首个 collective 卡死，都不能由这组 L40S 数据排除。[源码版本的进程组说明](https://github.com/meta-pytorch/torchft/blob/3a55d0241c38cd73798af3e0604ffe07ab77190f/docs/source/process_group.rst)

另一个参考是 Reve 2.0 团队的公开技术报告：Ray 负责集群 auto-shrink，TorchFT 维护生存副本的成员及提交。它证明了接入编排层的具体方案，不证明每个 Reve 训练作业都启用了它，也没有给出一个可移植到千卡 MoE 的开销系数。

建议按同模型、精度、数据和质量目标，与「定期持久 checkpoint + 整作业重启」做对照，同时跑无故障基线：

| 指标 | 应怎么量 |
|---|---|
| **稳态税** | 无故障时比较有效 tokens/s、step P50/P99 和 MFU；单列 quorum、梯度归约、提交门、诊断同步的暴露时间。不要用 Gloo 配置与 NCCL 配置的差直接当容错开销 |
| **保进度能力** | `已提交的有效 token / 墙钟秒` 和 `已提交的有效 token / 分配卡时`；分母计入留作替补和仍被占用的失组资源。再报尝试/提交比、每步有效副本数、达同等质量的卡时 |
| **两只恢复时钟** | `故障 → 幸存组第一次有效提交` 与 `故障 → 修复组重新贡献有效梯度` 分开报 P50/P95/P99；后者拆成检测、隔离、调度、重配、状态传输与应用。故障发生后作业没退出不是恢复指标 |
| **恢复干扰** | 量 donor/receiver 的 HBM、NIC 与交换机割集带宽；比较回补前后健康组 step P99、EP all-to-all 和外层 DP 的暴露时间。长时间没有进度要计入，而不是只统计成功恢复 |

需要分清三个层次：[NCCL shrink/grow](https://docs.nvidia.com/deeplearning/nccl/archives/nccl_2326/user-guide/docs/usage/communicators.html)解决 communicator 成员变化，不负责 optimizer 状态版本和数据语义；TorchFT 把这些通信能力接到训练提交与在线修复，但不替代持久化 checkpoint；[LocalSGD / DiLoCo](https://meta-pytorch.org/torchft/local_sgd.html) 更换的是跨副本同步对象和频率，并非无代价的每步 all-reduce 优化。把同步间隔从 1 拉到 H 步以后，正常期跨域通信可能下降，但失败时可能丢掉一个同步区间的本地工作，收敛也要重新对照；TorchFT 官方仍把 DiLoCo 支持标为实验性。

一个简化的盈亏线：把损失全部折算成「满配集群的等效损失秒」。R 个等大副本中一个缺席 τ 秒，假设健康组吞吐线性且不受干扰，代价是 `τ/R`；再加检测/中止期间的全局停顿、未提交计算和回补争用（重叠窗口不要重复计入）。周期性 checkpoint 的全局恢复代价约为重启耗时加平均重算量；仅在故障均匀落入 checkpoint 间隔时，平均重算才约等于间隔的一半。在线容错省下的损失还要超过健康期一直支付的稳态税。这个账比单报「恢复用了几秒」更能回答是否值得上。

## 4. 给大 MoE 超节点算两笔账

**第一笔是稳态梯度。** EP/CP/FSDP 的高频通信尽量留在完整副本内，外层 DP 跨隔离的故障域。注意：MoE 的每 token 激活参数少，不意味着跨副本梯度只按 active 参数记账。若在一个全局 batch 内更新全部专家，并对分片梯度使用稠密归约，流量取决于实际参与归约的**总 gradient payload**。以均匀 ring all-reduce 为例，R 个同构副本、每个副本合计 G 字节梯度，则每副本发送约 `2 × (R−1)/R × G`，接收也约这么多；这是通信量模型，不是 TOR 或每条链路实测，不能把单向发送数拿去除以双向标称带宽。分层归约、压缩及 EP 组实际映射都可能改变割集流量。

**第二笔是修复流量。** 用一个假想算例：4T 总参数，128 卡做完整分片，每参数只有 2 B 权重和 4 B optimizer 状态需要传输，不含 master weights、冗余副本或其他状态。回补一个组理论 payload 就是 24 TB；均摊约 187.5 GB/发送–接收 rank 对。若端到端瓶颈给该组留出 2 TB/s 单向有效带宽，**仅传输的理想下限是 12 秒**。若健康训练只能让出 0.5 TB/s，就是 48 秒；若两个回补共享同一 2 TB/s 割集，则两组完成的聚合带宽下限为 24 秒。实际还要考虑最慢 shard、状态打包、链路拥塞、GPU copy 和应用状态。应把「版本正确的状态」与「可真正跑到的备用带宽」分别核算。

这两笔账决定了我会优先验证什么：

1. **完整副本多大才划算。** 一个副本不必等于一个超节点，但越大，一处故障牵连的健康卡越多。只用独立故障近似会漏掉机柜供电、交换机、同版本驱动的相关故障；副本放置和 quorum 必须用联合失效场景验证。
2. **先验证外层可恢复，再追求组内单卡替换。** 在目标 CUDA/NCCL 或昇腾/HCCL 栈，先注入 rank 退出、collective 超时、慢卡、交换路径中断和 Lighthouse/定位服务不可用。验证 communicator abort、重建、P2P 恢复、状态一致性和回退。公开源码的 CUDA 路径不是对 HCCL 等价能力的证明。
3. **把回补限速纳入作业调度。** 至少比较无回补、受限单组回补、并发回补三个档位。健康组长尾不可接受时，可先用少量 donor 分散流量或错峰回补；用状态一致性和达标 GPU·h 决定能否上线，不以「几秒换卡」单独验收。

**结论：TorchFT 用一个更合适的重启单位保住已完成的工作。** 当作业能拆出多个独立完整的分片副本、跨域梯度负载可控、并且回补不把健康组拖进长尾时，它值得做在线容错基线。如果一个模型只能依靠单个巨型分片域运行，优先问题仍是域内替换、冗余和 checkpoint 恢复，而不是给外层套一个弹性的 DP。作为不同研究方向，[ElasWave](https://arxiv.org/html/2510.00606v1#S7) 探索用 DP/PP 重映射回收失组后的健康卡；两者分别解决“先保住进度”和“再把剩余卡用起来”，不应拿不同后端的单组跑分替代机制对照。
