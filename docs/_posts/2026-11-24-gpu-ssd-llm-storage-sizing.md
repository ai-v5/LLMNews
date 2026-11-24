---
layout: post
title: "GPU 为什么需要 SSD：大模型六类存储路径、NVIDIA 方案与带宽容量推演"
date: 2026-11-24T16:25:00+08:00
summary: "从 HBM、DRAM 到本地 NVMe 和共享 SSD，拆解训练数据、检查点、模型权重、KV 和优化器；对照 GPUDirect Storage、CMX、Storage-Next，用实测与算例推导带宽、容量、尾延迟和写寿命。"
section: explainer
label: "GPU 存储体系与容量规划"
tags: [GPU, SSD, NVMe, GPUDirect Storage, CMX, KV缓存, Checkpoint]
demo: false
sources:
  - title: "NVIDIA GPUDirect Storage：数据路径及兼容模式"
    url: "https://docs.nvidia.com/gpudirect-storage/overview-guide/software-architecture.html"
  - title: "NVIDIA：CMX 共享推理上下文存储"
    url: "https://www.nvidia.com/en-us/data-center/ai-storage/cmx/"
  - title: "NVIDIA：cuObject、SCADA Server SDK 与 Storage-Next"
    url: "https://developer.nvidia.com/blog/expanding-ai-storage-access-with-nvidia-cuobject-and-the-nvidia-scada-server-sdk"
  - title: "DeepSeek：生产部署与共享 KV 池"
    url: "https://github.com/deepseek-ai/DeepInfer/blob/main/doc/inference_deployment_qa.md"
  - title: "FlatCake v2：KV 大块直读"
    url: "https://arxiv.org/html/2610.38355v2"
  - title: "MLPerf Storage：公开评测场景"
    url: "https://mlcommons.org/benchmarks/storage/"
---

**GPU 需要 SSD，是因为作业需要比 HBM 大得多、关机后仍存在的字节空间；GPU 需要快一点地接近 SSD，是因为每次中转、等待或重算都有成本。** 但两者都不意味着 GPU 应该在生成每个 token 时到盘上找常用权重。GB300 一卡 HBM 约 **8 TB/s**（[NVIDIA 规格](https://www.nvidia.com/en-us/data-center/gb300-nvl72/)），一块量产 PCIe 6.0 企业 SSD 的顺序读标称约 **28 GB/s**，差近 300 倍；换成 4 KiB 随机读、同步单请求和生产尾延迟，不能沿用这个顺序读数。

最值得优先建设的是两种“可以提前一些搬完”的路径：**训练 checkpoint 从本地快照刷到共享持久层；推理在新一轮开始前，把下次会话要复用的 KV 搬回 HBM。** SSD 真正会改变 GPU 采购的是模型能否启动、同样 HBM 能服务多少长期会话，以及很多卡故障时能多快恢复。采购必须同时过四道闸：**容量、吞吐、尾延迟、写寿命**。本文使用 2026 年 11 月 24 日前的公开材料；所有自建算例均标注假设。

[下载容量与带宽脚本]({{ '/assets/data/gpu-ssd-llm/sizing.py' | relative_url }}) · [下载算例 CSV]({{ '/assets/data/gpu-ssd-llm/cases.csv' | relative_url }})

## 1. SSD 接在哪一层：三种“直连”容易混为一谈

NVMe 盘连接在 PCIe 域里。在常见主机式路径，CPU/应用提交请求，SSD 控制器 DMA 到主机内存，再经 GPU 拷贝引擎搬到 HBM。GPU 不需要为给每个盘配一条独占直连线，也不靠 GPU 指令把 SSD 当寄存器。系统可有三条不同路径：

| 路径 | 谁发请求、谁搬数据 | 何时合适 / 核对什么 |
|---|---|---|
| CPU 缓冲 / 页缓存 | 主机线程发，NVMe/NIC→DRAM，CUDA 拷贝→HBM | CPU 要解包、解析、解压时合理；热页缓存可能比直读盘快。读第二遍得到的是 DRAM 成绩，冷盘要另测 |
| GPUDirect Storage（GDS） | cuFile 由 **CPU 发出**；本地是 NVMe DMA，远端是 RNIC DMA，在支持配置中直达 GPU buffer | 大块、对齐并行 I/O；绕开 CPU 中转而非绕开元数据、驱动或应用控制。检查文件系统、mount、拓扑和真实 direct 字节比例 |
| GPU 发起 I/O | GPU 并行线程/队列驱动细粒度请求；系统仍需 host 配置、权限与异常处理 | 不可预测的小粒度 lookup 动机强；软硬件仍得符合实际 SDK/设备成熟度。不是所有 GDS，也不是让 NAND 获得 HBM 延迟 |

[NVIDIA cuFile API](https://docs.nvidia.com/gpudirect-storage/api-reference-guide/usage.html) 明说 API 从 CPU 发出；[GDS 软件架构](https://docs.nvidia.com/gpudirect-storage/overview-guide/software-architecture.html) 说明本地 NVMe 或远端 NIC 可以做直接数据搬运。从 CUDA 12.2 起，满足对齐等条件的非 O_DIRECT 文件描述符也**可能**走 O_DIRECT 对应路径；不等于任意文件都能直通。从 CUDA 12.8 起支持额外的上游 PCI P2PDMA NVMe 路径，文档标注 x86_64、驱动与内核条件，不外推到任意 Grace/SNAP 及所有 SKU。GDS 可能回退 CPU bounce，内部 GPU bounce 也有独立计数。同一应用在 `gdscheck` 能看到设备，不等于每个读请求都走了 direct。生产验收应同时看应用端 actual bytes、进程 CPU、`/proc/driver/nvidia-fs/stats` 或对应新版计数、链路和盘侧 telemetry。[O_DIRECT 要求](https://docs.nvidia.com/gpudirect-storage/o-direct-guide/gpudirect-storage-requirements.html)

拓扑上区分 **本地 NVMe PCIe**、**远端并行文件/对象存储**、**NVMe-oF**、**GPU 内 HBM 及机内 NVLink**。在远端路径，可能是 SSD→存储节点内存→网络→GPU 节点，存储节点及客户端也可能各自有缓存。RDMA 最后一跳不证明全链路无 DRAM，也不证明从 GPU kernel 发起。NVLink 130 TB/s 等机柜聚合口径不能拿来当 NVMe 或共享存储带宽。

![从数据及快照、共享上下文到本地 NVMe 和 GPU HBM：按工作负载走不同路径]({{ '/assets/gpu-ssd-storage-paths.svg' | relative_url }})

## 2. 大模型六类 SSD 需求：读写模式不同，优先级也不同

| 工作负载 | 盘上放什么 / 何时有价值 | 一定要验的指标 |
|---|---|---|
| 预训练数据 / 多模态输入 | shard、token、图像/视频、索引、shuffle；本地 NVMe 减少共享 FS 重读、支持快迭代 | 冷/热两态、每工作节点真实读放大、文件/对象打开 OPS、输入等待；图像解码、帧抽样和 batch 拼装也会饿 GPU |
| Checkpoint / 恢复 | 权重、主权重/optimizer 状态、RNG、数据游标；本地低停顿 staging + 共享层抗节点/机架故障 | GPU 前台暂停、远端完成提交、真正的 RTO/RPO、尾 rank、回灌与网络/训练竞争、每日写量 |
| 权重启动 / 弹性切换 | 把分片模型、adapter 预放本地，一次装进 HBM；在线保热、灰度、缩扩容 | 冷启动/并发加载 P95、权重校验和版本原子切换；TP/EP 是否重复拉同一份 |
| 推理 KV 复用 | 低复用概率的历史前缀、工具调用间隙、跨会话上下文；在下一轮 prefill 或 decode 前回读 | 命中交付到 GPU 的有效比例、错过恢复 deadline、读放大与写放大、P95 TTFT/TPOT、重算盈亏 |
| 小容量模型/专家/条件表卸载 | 容量优先的离线权重 streaming、热点专家/稀疏 lookup、不常访问的 Engram | 未命中每步字节、层 deadline、随机块大小与队列、热集在 HBM/DRAM 的比率；不可把离线 throughput 当在线 TPOT |
| 训练参数 / optimizer / 激活卸载 | 内存挡住训练时，把冷状态分片到 CPU/NVMe；计算仍在 CPU/GPU | 每步读写工单、双向混合服务率、可重叠窗口、最大分片、NAND 写寿命；实在无空间时才支付代价 |

**Agentic RL 还有一条旁路**：沙盒镜像、源码仓、构建缓存和工具产物落在环境节点，优化镜像大小和热集能减少 GPU 等待；该盘的 I/O 不能当成 GPU 读权重。长工具间隙中模型 KV 可能又在推理存储池。应分开采两池在途和尾延迟，不能合并一张写带宽图。[三池示例]({{ '/2026/11/24/agentic-rl-gb300-capacity-model/' | relative_url }})

## 3. NVIDIA 的产品分别解决了哪一段

1. **节点本地：DGX 系统基线。** [DGX GB300 参考架构（PDF）](https://docs.nvidia.com/pdf/dgx-spod-gb300-ra.pdf) 的 DGX GB300 compute tray 数据盘为 4×3.84 TB E1.S NVMe、软件 RAID0，18 tray 合计 **276.48 TB raw data cache**，约 3.84 TB/装机 GPU 的容量当量；这是 18 组本地缓存，不是统一、有冗余的 276 TB 共享池，不含 boot 盘。[DGX Vera Rubin 指南](https://docs.nvidia.com/dgx/dgxvr-user-guide/storage.html) 也列本地 E1.S RAID0、可选 cachefilesd 和临时 checkpoint，再刷入共享并行 FS。Vera Rubin NVL72 [已有出货/爬坡披露](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Expands-Commitments-With-Supply-Chain-Partners-to-Support-AI-Infrastructure-Buildout/default.aspx)，**不说明**每个部署都装 CMX 或新 GPU 发起 SSD。
2. **主数据通道：GDS/cuFile、NIXL、Dynamo。** GDS 优化搬运路径；NIXL 是传输抽象，后端可用不同内存、网络和存储；Dynamo 负责 KV aware routing 和存储分层/生命周期。一个“Dynamo + NIXL”部署可以是后端纯 DRAM，也可以接盘，不保证 GDS 命中，更不保证 NVMe 是 decode 内环。[NVIDIA 全栈说明](https://developer.nvidia.com/blog/five-ways-nvidia-co-design-maximizes-the-value-of-every-byte-in-the-ai-factory/)
3. **跨节点上下文层：ICMS/CMX、BlueField-4 STX、DOCA Memos。** NVIDIA 把 HBM、主机 DRAM、本机 SSD 之外的 Pod 级共享临时 KV 叫 **G3.5**；上层仍有共享文件/对象 G4 做大容量持久数据。CMX 用 BlueField-4/STX 与 Spectrum-X，把空闲 context 放到池中并在实际复用前预置到 DRAM/HBM，缓解跨节点复用和恢复压力。计算侧 BF4 标称最高 800 Gb/s 与存储端 BF4-STX 最高 1.6 Tb/s 是不同单元的**线速**，分别只等价 100/200 GB/s 原始单向速率，不是端到端 SSD p99。厂商 up to 5× 类宣传的对照是其传统存储口径，不是与 HBM 横比，也未见公开同配置、可复刻的普遍应用 SLO 结论。[CMX](https://www.nvidia.com/en-us/data-center/ai-storage/cmx/) · [分层与预取](https://developer.nvidia.com/blog/introducing-nvidia-bluefield-4-powered-inference-context-memory-storage-platform-for-the-next-frontier-of-ai/) · [STX 与 BF4 线速口径](https://developer.nvidia.com/blog/scaling-agentic-ai-factories-through-extreme-co-design-with-nvidia-bluefield/) · [STX 公告](https://nvidianews.nvidia.com/news/nvidia-vera-bluefield-4-stx-brings-agentic-ai-storage-processing-with-in-silicon-security)
4. **细粒度新路线：Storage-Next、SCADA 与 cuObject。** NVIDIA 的 [SCADA/cuObject 技术说明](https://developer.nvidia.com/blog/expanding-ai-storage-access-with-nvidia-cuobject-and-the-nvidia-scada-server-sdk) 将服务器 SDK/原型、GPU 发起细粒度 I/O 与 cuObject RDMA 对象路径分开。研究上的 [BaM](https://arxiv.org/abs/2203.04910) 和 [Tutti](https://arxiv.org/html/2605.03375v1) 展示了 GPU 侧发起、队列与并行控制空间，不是出厂功能。Kioxia **GP1 功能样品**公告为 PCIe 6/NVMe 2.2，最高 **10M 随机读 IOPS@512 B=5.12 GB/s**；较早超过 107M 是**仿真器**结果，100M@512 B 意味 51.2 GB/s 聚合有效负载，非单盘 Gen6 x4 实物成绩；100M 是下一代目标。不要把标准路径、器件样品、采购可得产品、应用实测写成同一件事。[GP1 公告](https://www.kioxia.com/en-jp/business/news/2026/20260804-1.html) · [路线图/仿真](https://americas.kioxia.com/en-us/insights/super-high-iops-ssd-202604.html)

## 4. 带宽、容量、IOPS 和尾延迟如何算

```text
每秒读负载 = Σ(事件率 × 平均有用字节 × 端点读放大)
每秒写负载 = Σ(事件率 × 去重唯一字节 × 副本/EC × 宿主写放大)
盘原始容量 ≥ [唯一数据率 × 保留时长 + 其他活数据 + staging/重建空间] × 保护放大 / 可用水位
IOPS ≈ 物理字节率 / 平均实际请求字节；队列深度 Q ≈ IOPS × 平均完成时间
B_eff ≤ min(Σ盘持续带宽, PCIe 端点/上行, 网络有效切面, CPU/GPU 接收端, Q×请求大小/延迟)
恢复/加载纯搬运下界 ≥ 体量 / B_eff；RTO 还含最慢分片、校验、重分片、进程及 warmup
host DWPD = 每日实际写入驱动器的 host 字节 / 安装盘的额定用户容量
```

带宽统一按**单向有效**。1 Gb/s=0.125 GB/s；PCIe Gen5 x16 的约 63.0 GB/s 单向是编码后、协议开销前的上限，不能用双向和 126；Gen5 x4 约 15.75 GB/s。四块盘各 14 GB/s 不会自动让每张 GPU 都得到 56 GB/s，交换上行、root complex、NUMA、跨 socket、内存拷贝、共享 NIC 和 writer 都可能收窄。对照 [Micron 9650](https://www.micron.com/products/storage/ssd/data-center-ssd/9650-ssd) 28 GB/s 顺读规格，或 Kioxia CM7 的顺读规格，必须写清块大小、稳态、QD、读写比例。同样 10M IOPS，若假设平均单 IO 50 μs，需要约 500 在途；QD1 只约 20k IOPS。**这个 50 μs 只是算例，不是 GP1 时延。**

容量按不同故障域计算，运行水位需同时覆盖 compaction、GC、EC 重建和峰值。平均带宽只管长期队列不一直涨；P95/P99 要在混合读写、cache GC、节点故障和足够预热后量。SSD 设备内部 NAND WAF 会影响磨损；如果厂商 DWPD 是 host 写账，先用真实 host 写与额定值比，不再乘 NAND WAF 双重扣除。应用合并、对象重写、宿主端冗余都可使 host 写放大，应该实计。

## 5. 算例 A：文本训练吞吐不一定压盘，checkpoint 可能压穿写寿命

**数据读取。** 假设全作业 1,220 万 token/s，盘面 int32 tokens，唯一读约 **48.8 MB/s**；同样 200T token 的总容量却约 **800 TB**，不含原始文本、索引、多版本。CPU 预处理、shuffle 小读、TP/DP 误重复、压缩解码或多模态数据会改结论。最先查 `samples/s × 单样本实盘 bytes` 和实际共享 FS 热点，不拿影像基准套纯文本。[MegaScale](https://arxiv.org/html/2402.15627) 有按 TP 避免重复读、先存 pinned host 内存并后台写的实例。

**Checkpoint。** 假设 10T 参数，本快照只含 BF16 2 B 与 FP32 Muon 单动量 4 B，唯一数据 **60 TB**；没保存 master、梯度等，真实格式若有这些另加。平均分给 128 台唯一写入主机，每台 468.75 GB。每台两块 15.36 TB 盘，两盘持续顺写标称各 7 GB/s，端点按 70% 取 9.8 GB/s，理想本地落盘 **47.8 s**。这不等于训练卡停 47.8 s：串行是停这么久量级，异步是先从 GPU 建一致快照再慢慢刷；flush 队列不能无限积压。[CM7-R 规格](https://americas.kioxia.com/en-us/business/ssd/enterprise-ssd/cm7-r.html)

- 每 5 分钟 60 TB 一次，向共享层持续写至少 **200 GB/s**；要求一次在 60 秒内全局持久，需要 **1 TB/s** 的更新数据有效吞吐，均未计冗余。
- 本地“两份”每台只占 **0.938 TB**，看似很小；每台却写 **135 TB/日**，两盘合计 30.72 TB，约 **4.39 host DWPD**。两块 1 DWPD 盘容量够、速率够，却不满足该写强度下的名义耐久。若每小时刷一次是约 **0.37 DWPD**；取更长间隔、更多写密集盘、分层 RPO 或按恢复验证后的增量，勿把写放大量藏到光鲜容量下。
- 本地快速点、跨机架耐久点应区分。NVMe RAID0 适合作可重建镜像/本地 staging，不适合作唯一 checkpoint。目录有文件不等于可恢复，manifest 需要提交并校验整组分片；隔离测试节点与机架故障。分别报恢复可继续训练的 RTO，以及重跑后追到中断前进度的总时间；RPO 还要看已持久提交的 checkpoint 年龄，而非最近一次返回训练的时间。

校准一下量级：[MLPerf Storage v3 / Azure Managed Lustre](https://learn.microsoft.com/en-us/azure/azure-managed-lustre/mlperf-storage-v3-results#checkpointing-results) 1250B 配置写 642.2 GiB/s、24.63 s，读 489.6 GiB/s、32.27 s；405B 配置写 457.0 GiB/s、11.76 s，读 438.1 GiB/s、12.39 s。**集群存储/fsync/读是实测，发 I/O 的训练进程是基准模拟，不能称完整训练恢复时间。** 数字用各报告的原始字节/速率定义，不用名义 1250B×固定参数字节反推。若慢分片压线，优先排查共享网络与请求同步波峰；[Megatron Bridge](https://docs.nvidia.com/nemo/megatron-bridge/latest/training/checkpointing.html) 的全局/本地检查点与复制是参考，不是任意配置保证跨机架。

## 6. 算例 B：多轮推理为什么值得把 KV 放 SSD

KV 缓存是可重算状态，媒体不是服务的全部。关键比较：
`复用收益 = 重算时间 −（排队 + metadata + 不可隐藏的数据取回 + unpack/scatter + 版本检查）`。若按层 prefetch，直接 I/O 只加快数据段；第一层等待、最慢读 rank 或恢复故障仍可能把 TTFT 推过 SLO。统计 **delivered hits**，不要让“找到缓存了却没及时交付”的请求计成有效命中；无命中请求不能替 SSD 命中平摊尾延迟。对活跃 decode 的每层历史 KV 逐 token 反复读 SSD，是完全不同的高频路径，通常不可行。

### 可复算的盘和网络预算

- DeepSeek-V4.1-Flash [报告](https://arxiv.org/html/2609.19969v1) 的压缩全局 KV 约 **890 B/token**，不含另外的 SWA。128 Ki token 是 **116.654 MB**。对照 70B 类 GQA 假设：80 层×8 KV 头×128 维×K/V 两份×BF16 2 B = **320 KiB/token**，128 Ki token 就是 **40 GiB**。量级差由架构/压缩决定，不由总参数决定。
- 假设每秒 **100 次**命中 128 Ki token 的完整 SSD prefix，DS 逻辑读 **11.67 GB/s**；存储/应用读放大 1.3× 后 **15.17 GB/s**。若平均 128 KiB I/O，约 **11.6 万 IOPS**；若平均 4 KiB，要约 **370 万 IOPS**。同一字节率，不同布局的盘/CPU 账完全不同。假设每请求能独占 20 GB/s，纯读下界 DS **5.83 ms**，对照模型 **2.15 s**，均不含排队、最慢 rank、网络、多层回灌或并发分享。
- 若同为 100 请求/s，每请求唯一新增需持久 8 Ki token，写约 **0.729 GB/s**，即日写 **63.0 TB 逻辑**。留 72h 是 **189.0 TB**；10+2 EC、80% 水位，则约 **283.5 TB raw**，尚未计快照重建、元数据与写缓存。变短 TTL 可减容量，但通常不改同样生成下的新增写率，也可能损失命中。

同一读预算若过单一链路，100 GbE 标称只有 12.5 GB/s，连 15.17 GB/s 平均需求都过不了；200 GbE 的 25 GB/s 是线速，仍不能证明尾延迟。如果 16 个恢复同时到达，整个批次留给存储的有效数据传输窗口仅 25 ms，1.3× 读取之后要求切面约 **97 GB/s**。不是每秒平均 15.17 GB/s 的流量变了，而是要赶上的 deadline 变了。硬件候选也要同时满足容量：283.5 TB 至少需 10×30.73 TB 的字节容量，但单条 10+2 stripe 还需要至少 12 个合格的片位置及相应故障域，不能把十块盘当完整的 10+2 容灾承诺。运营后要量实际同时需恢复多少条，再考虑错峰、预取、单请求回读与重算选择。

### 公开结果有哪三种证据

| 工作 | 结果 | 应怎么读 |
|---|---|---|
| DeepSeek 生产 [DeepInfer Q&A](https://github.com/deepseek-ai/DeepInfer/blob/main/doc/inference_deployment_qa.md) | 推荐 KV 存储节点 20×30.73 TB、≥40 GB/s 读和 ≥5 GB/s 写；约 14.4 TB **逻辑 SSD/GPU**，10+2 EC；agent TTL 3 天、chat 7 天 | 不是每卡物理背 14.4 TB。72 卡是约 1.04 PB 逻辑池份额量级；全局 main/indexer 持久、SWA 在主机 DRAM。生产读为 3FS→host shared memory，再用 NIC GDR 向 GPU 逐层重叠；不是“一跳 SSD 直达 GPU”。decode 不做主动 KV offload，结束写回以复用 |
| FlatCake v2 [论文](https://arxiv.org/html/2610.38355v2) | 4×B200 运行 DS-V4-Flash-0731；实验台本地 DRAM→GPU 46–48 GiB/s，SSD GDS→GPU 19.3，远端 SSD owner+RDMA 6.3；Claude Code trace 扫 0.2–0.6 QPS，delivered hit 维持 91.6%，SSD 对照在负载上升时降至 71.1% | 用布局、最小化取回、直接路径和执行重叠保证命中可交付；19.3 是具体拓扑微基准，依赖当地 8 块 PM9A3 RAID0，不是一块盘或逐卡可累加值。v2 read amp 约 1× 对其他机制 1.24–2.07×，指取回/真正消费字节，不是 NAND 写放大 |
| MoRI UMBP [vLLM 文章](https://vllm-project.github.io/2026/11/23/skip-the-dram-tier.html) | 16×MI355X、Kimi K3、等 1.8 TB 池和 48/70/96 会话，含 input/cache/output 的总吞吐差 ≤1%；另一 K2.6 128K 单请求 DRAM 0.45 s / NVMe 0.84 s / 重算 7.7 s | 共享池“跳过 DRAM 容量层”不等于无 DRAM：还用了 64 GB 写缓存和 16 GiB 读 staging；HBM 承担多数命中。另一组机器的 96 会话对照中，无写缓冲 NVMe 比全 DRAM 池吞吐低 6.7%，P90 TTFT 为 94.56s 对 67.20s。文中更大盘池 5.1× 不是介质本身更快 |

还有一个值得防的反例：[Google GKE + LMCache](https://cloud.google.com/blog/topics/developers-practitioners/boosting-llm-performance-with-tiered-kv-cache-on-google-kubernetes-engine) 8×H100/70B 的 50K 共享 prompt 场景，合适工作集下用 SSD/DRAM 平均 TTFT 下降 68%；工作集撑大后同一 50K 场景**平均 TTFT 反而高 48%**，虽 input throughput 仍上升。相同高吞吐可以掩盖服务变慢。更容易部署的顺序是 HBM 热前缀→DRAM 常复用→NVMe 冷复用；仅当读放大、取回 deadline 和写寿命通过才扩大 SSD 层。

## 7. 算例 C：为什么权重和 optimizer 流式卸载一般只作备选

**在线热权重。** 70B BF16 约 140 GB，假定单卡只留 64 GB 权重空间，每次单请求 decode 的稠密路径至少需从盘取 76 GB。单盘理想 14 GB/s 下至少 **5.43 s/token**；即便盘足够、单向 PCIe Gen5 x16 满 63 GB/s，也最多 **0.83 tok/s**，20 tok/s 需要 **1.52 TB/s** 只给这部分权重。批 64 可以让同一读复用给客户端，改善聚合输出，但不把单个请求的这一读步变快；冷加载一次 1.5 TB 权重，在端点实测 50 GB/s 的假设下至少 30s，则是合理用盘场景。[FlexGen](https://proceedings.mlr.press/v202/sheng23a/sheng23a.pdf) 的 OPT-175B/T4 + DRAM/SSD 历史实验，非压缩批 256 是 0.69 **聚合**生成 tok/s，验证容量换吞吐的代价，并非现代在线部署目标。

**稀疏、可预取例外。** [SlackTier](https://arxiv.org/html/2611.13413v1) 用 4×H200、DS-V4.1-1017，把约 203 GB 只读 Engram 表搬到 NVMe；一行随机小读，考核 IOPS 和层间余裕，不是扫描 200 GB 权重。论文特定测试中，两表单 SSD 无缓存时批128的平均步时增加 6.4%（agent）；四盘+小 HBM 行缓存的优化相对原路径每输出 token 额外开销最高约 1.4%，腾出的 DRAM 给 host KV 后另有二阶收益。不是 DeepSeek 已用 SSD 代替所有 Engram DRAM，也不能套给热 MoE GEMM。

**Optimizer 每步落盘很重。** 假设 70B Adam 跨 64 ranks，8 ranks/节点，完整 FP32 master+m+v 每步读写，两方向各 **105 GB/节点**。若有效读/写 50/25 GB/s，理想完全重叠的 I/O 下限 4.2s、串行 6.3s；按 10s/步，每节点日写约 907 TB，8×3.84 TB 则 **29.5 host DWPD**。这甚至没算参数和梯度额外 I/O。 [ZeRO-Infinity](https://arxiv.org/abs/2104.07857) / [DeepSpeed](https://deepspeed.readthedocs.io/en/latest/zero3.html) 的可行性来自分片、tile 预取回写、host cache、CPU optimizer 与足够大 compute window；SSD 存字节而不负责算更新。**先用 HBM 分片、DRAM 卸载或更少更新状态，再对 NVMe 保留真正跨不过容量闸门的场景。**

![三类算例：checkpoint、KV 复用和热权重的不同容量及带宽瓶颈]({{ '/assets/gpu-ssd-sizing-cases.svg' | relative_url }})

## 8. 一张可执行的验收单

1. **定义工作量，按负载分账。** 冷启动 bytes/版本，训练真实样本 bytes/s，checkpoint 可恢复唯一 bytes，推理 KV 每 token bytes 与有效 hit/s，optimizer 每步 host read/write。标明十进制或二进制、取平均还是尾分位，是每 GPU、每节点还是整个存储集群。
2. **量两条链路。** 对同一批请求做 local/remote、buffered/direct、cold/warm 交叉对照；按生产块大小、并发、读写比例测盘、PCIe、NIC、主机与 GPU。报告实际 direct 数、有效负载、读放大、GC/故障降级，不能只截图 FIO 顺序读标称。
3. **用用户能感受到的 SLO 结算。** 推理用 cold/hot/SSD-hit 分桶 TTFT 与 TPOT、缓存未按时交付/重算率；训练用 GPU 可用率和恢复至同一步的时间；按请求保留版本与权限，不能跨权重、租户、适配器或 KV 格式复用。
4. **最后才做采购。** 用「中间层几 TB 能保住多少复用」「在突发期间有多少 GB/s/IOPS」「单盘一年写多少」反推盘数与可持久层，并留坏盘/存储服务器/机架降级余量。能重建的东西本地缓存，不能丢的东西做真实冗余；SSD 只应该出现在它能赶在计算需要之前把字节送到的地方。
