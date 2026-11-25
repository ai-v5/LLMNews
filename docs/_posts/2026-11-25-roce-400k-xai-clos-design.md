---
layout: post
title: "40 万张 GPU 怎么接进 RoCE：从 xAI Colossus II 到一套可复算的组网设计"
date: 2026-11-25T16:36:00+08:00
summary: "核对 Colossus 的公开证据，给出 400,032 张 GB300 的双平面三层 Clos 端口账本，并对照国内外实装案例，区分多平面与多轨，推演高基数两层、跨楼切面、PXN 和故障验收。"
section: explainer
label: "AI 集群组网"
tags: [RoCEv2, Spectrum-X, Colossus, PXN, Clos, GB300, AI集群]
demo: false
sources:
  - title: "NVIDIA：第一代 Colossus 的 100K Spectrum-X fabric"
    url: "https://nvidianews.nvidia.com/news/spectrum-x-ethernet-networking-xai-colossus/"
  - title: "SpaceX 公开申报：Colossus II 位置与上线批次"
    url: "https://www.sec.gov/Archives/edgar/data/1181412/000162828026042639/spaceexplorationtechnologi.htm"
  - title: "NVIDIA：GB300 NVL72 双平面网络参考架构"
    url: "https://docs.nvidia.com/enterprise-reference-architectures/nvl72-ai-factory/latest/network-logical-architecture.html"
  - title: "NVIDIA：Spectrum-X 多平面、HyperScale 负载与故障"
    url: "https://developer.nvidia.com/blog/giga-scale-ai-ethernet-evolution-spectrum-x-ethernet-rewrites-rules/"
  - title: "Meta：训练 RoCE 的网络与传输经验"
    url: "https://engineering.fb.com/wp-content/uploads/2024/08/sigcomm24-final246.pdf"
  - title: "OpenAI：MRC 的生产部署与多路径"
    url: "https://openai.com/index/mrc-supercomputer-networking/"
---

**我的建议：如果是 40 万卡资产池，按训练作业的通信边界给跨楼网络配带宽；如果合同明确要求 40 万卡能做全域高带宽通信，就按 1:1 切面设计，另验收实际路由、尾延迟和故障降级。** 这两个目标都能叫“40 万卡集群”，但交换机、光纤和训练调度不是一套规格。

下面给出两份互相独立的答案。第一份是**马斯克的集群公开到了哪一步**。第二份是**不拿推测冒充实装**，用可核对的 GB300 NIC 和交换机端口，构造覆盖 400,032 卡的后端网，按轨直达、跨轨由通信栈完成；同时列出 100K/200K 扩容方法，以及为什么某些设计确实能压到两层。前篇[RoCEv2、veRoCE 与 UBG 的协议对照]({{ '/2026/11/22/ai-scale-out-rocev2-veroce-ubg/' | relative_url }})解释协议，本篇解决如何把端点、链路和作业拼成系统。

## 一、Colossus II：能证实到哪一层

| 公开证据 | 能推出什么 | 不能推出什么 |
|---|---|---|
| [NVIDIA，2024-10-28](https://nvidianews.nvidia.com/news/spectrum-x-ethernet-networking-xai-colossus/) | **第一代** Colossus 早期 100K Hopper 的 RDMA 后端用 Spectrum-X、SN5600、BlueField-3；公告明确说三层，称特定运行中有 95% 数据吞吐 | 不是独立实测、不是 MFU，也不能把代际、层数或 NIC 原样套到 II |
| [xAI Colossus 页面](https://x.ai/colossus)与[2026 年 5 月公告](https://x.ai/news/anthropic-compute-partnership) | 前者说扩到 200K 互联规模；后者说 Colossus I 超过 220K，包含 H100、H200 和 GB200 | 两者时间和 GPU 构成口径不同；都没交代最大的同步作业用了多少卡 |
| [SpaceX 公开申报](https://www.sec.gov/Archives/edgar/data/1181412/000162828026042639/spaceexplorationtechnologi.htm)，正文第 132 页附近 | II 涵盖 Memphis / Southaven；披露先后上线约 110K GB200、110K GB300，另有至少 220K GB300 当时属于下一期。申报中 Anthropic 跨 I/II 的约 325K 是服务容量 | 这几种数字不能相加倒推某张无阻塞网，也不能推出每期恰好一张物理 fabric |
| [马斯克 2026-09-25 的原帖](https://x.com/elonmusk/status/2103329761690865846)（核对公开嵌入数据） | 他当时给 II 的口径是 **110K GB200 + 440K GB300**；后续批次是该帖当时的计划 | 这是负责人表述，不是独立盘点；未给出单作业规模、光纤路线、分轨、故障域或东西向带宽 |
| [xAI 融资公告](https://x.ai/news/series-e) | I + II 曾披露超过 100 万 **H100 等效** | 等效算力不能换成实体卡数、交换机数量或网口 |

**最有证据支撑的 II 架构推断**：NVL72 柜内用 NVLink/NVSwitch；柜外是按批交付、按区域铺设的高速后端网，配独立存储/管理网络；高频通信先留在 NVL/近邻域，跨批次或站点的互联承担流量预算更清楚的阶段。**RoCE/Spectrum-X 是有前代实证、也有 GB300 公开产品支持的候选。** 还找不到能证明二代具体交换机型号、两层还是三层、同一批的 rail 映射、站点间是否有端到端 RoCE，或是否开启 PXN 的竣工资料。所谓“中央交换”即使存在，也可能是一组 spine/核心域，不能按一台 ASIC 理解。下一节是可施工验证的候选设计，不是把这些未知项填成事实。

## 二、先定哪些卡能互通：4 条独立 rail，每轨 2 个 plane

以单一代同构 GB300 为基准，避免把实际机房可能混装的 GB200 和 GB300 设为同一个 800G 模板。[NVIDIA DGX 规格](https://docs.nvidia.com/dgx/dgxgb200-user-guide/hardware.html)列出 GB200 tray 为 4×400G NIC，GB300 tray 为 4×800G NIC；GB300 每柜 18 tray、每 tray 4 GPU。其[企业参考架构](https://docs.nvidia.com/enterprise-reference-architectures/nvl72-ai-factory/latest/network-logical-architecture.html)给出 800G 拆 2×400G、每张 GPU 两条 plane 接入，并以 tray 内 GPU 位置编 rail。这是下面的接入模板；该小规模参考架构不构成对 40 万卡的认证。

**本文按端点可达性用词：** 多平面（multi-plane）是在**同一个互联域**上为**同一批端点**提供多张并行网络。域内任意两端可以互通，只是报文或流分到不同 plane；它们不因 plane 被分成不同卡组。本文所说的多轨默认指独立多轨（isolated multi-rail），把端点按 GPU/NIC 位置划进不同的直达域；同轨可直接走 RDMA，跨轨需要先经 NVLink/PXN 等能力转接到同轨 NIC，或另用显式网关/共享骨干。厂商的 *rail-optimized* 仅说明同位置/同轨优先，**不自动证明轨间隔离**；若同一 plane 的 spine 允许轨间 IP 转发，就属于保留跨轨直达的 rail-optimized 网络。

- **Rail 按 GPU/NIC 位置分**：每台 4 GPU tray 有 rail 0–3。每条 rail 跨所有 tray，供同位置 NIC 互达。不是给整个机柜仅配四个网口，也不是单个进程自然得到四个 NIC 的带宽。
- **Plane 按同一 rail 的并行路径分**：每个 NIC 的 800G 拆 A/B 各 400G。基线将 A/B 的交换机、配线架和跨区光路独立；同一 NIC、光模块、tray 和 compute rack 仍有共因故障。物理上得到 **8 张 rail-plane**，每张覆盖全部 tray，但**每条只覆盖每 tray 的一个 GPU 位置**。每轨内，两张 plane 都覆盖同一批卡；全场没有一张让 400,032 卡两两直接 RDMA 的统一平面。
- **端到端语义先二选一**：独立 PF/GID 的软件多平面要明确 NCCL/插件发现、平面绑定和重建行为；硬件多平面由验证过的 ConnectX-8、固件、DOCA xPlane、交换机 NOS 配套，逻辑设备和 IP 布局按指定栈生成，不能将两种路径混配。[NVIDIA 多平面支持矩阵](https://docs.nvidia.com/networking/display/kubernetes2670/spectrum-x/spectrum-x.html)列出了 GB300 的这两种模式。拓扑算术不依赖某种负载均衡，实装验收依赖。
- **任意 GPU 互通的边界**：同 rail 两端经交换机直接互达；不同位置间可通过 tray 内 NVLink 转到对齐的 NIC/代理，或由库做同位置分片再在 NVL 域汇集。没有任何跨 rail 的裸 RoCE IP 路由作为隐式兜底。跨 rail 裸 QP 的应用要显式代理、走经测试的共同网络，或另选共享 fabric。
- **管理、存储与训练数据面物理分开**：BMC/OOB、镜像与数据读、checkpoint、网络路由控制各有优先级/独立路径。不要让存储写风暴触发训练队列的 PFC；前端和存储另按吞吐、持久化、故障域做 BOM。

## 三、一套 400,032 卡的三层 Clos，把每根链路算清

**目标**：同园区 50 个 cell，所有相同 rail 的端点连通；正常态在每个 rail-plane 内按 400G 端点做 1:1 切面，无需假设一台巨型中央交换机。每个 cell 设计容量 2,048 tray。采用 [Spectrum-4 SN5610 级 64×800GbE](https://networking-docs.nvidia.com/sn5000hw/specifications)，[硬件手册支持 800→2×400、4×200](https://networking-docs.nvidia.com/sn5000hw/cable-installation)；采购以当前合格 SKU 和固件矩阵为准，不拿早期 SN5600 的料号默认可买。

- **整柜**：5,556 柜；44 个 cell 每个 111 柜，6 个 cell 每个 112 柜。每 cell 1,998 或 2,016 tray（7,992 或 8,064 GPU），合计 100,008 tray、400,032 卡。每条 rail-plane 接 100,008 个 400G 端点。
- **单 rail-plane 布线**：第 `p` 个 cell 内有叶交换机 `L[p,l]`、汇聚 `A[p,i]` 各 32 台，`l,i=0..31`。核心 32 组，每组 32 台 `C[i,j]`。不同索引 `i` 的核心组彼此不直接连接。端点按 tray 序号每 64 个落一台 leaf；尾部留空，不用把半柜算成整柜。
- **连法**：每个 `L[p,l]` 对 cell 内每个 `A[p,i]` 一根 800G；每个 `A[p,i]` 对同组全部 `C[i,j]` 各一根 800G。核心一台连 50 个 cell 的同索引汇聚，每 cell 一个 800G 端口，余 14 个可用于尚未部署的 cell，不是本地冗余速率。
- **路径**：同 leaf 经过 1 台；同 cell 跨 leaf 为 L→A→L（3 台）；跨 cell 为 L→A→C→A→L（5 台）。跨 cell 每对 leaf 正常有 32×32=1,024 条拓扑候选路径，实际逐跳 ECMP 组最多 32，而非一个 1,024-way ECMP 组。

![40 万卡三层 Clos 的一张 rail-plane 模板]({{ '/assets/roce-400k-clos.svg' | relative_url }})

| 角色 | 每台真实接口分配 | 每 rail-plane | 4 rail × 2 plane |
|---|---|---:|---:|
| Leaf | 32 个 800G 笼位拆成 64×400G 给 tray，另外 32×800G 给汇聚。**64 个物理端口、96 个逻辑接口** | 1,600 | 12,800 |
| Aggregation | 32×800G 下接 leaf，32×800G 上接 core | 1,600 | 12,800 |
| Core | 50×800G，每 cell 一个，剩 14×800G | 1,024 | 8,192 |
| **合计** | 不含备件、存储网、OOB、跨城 DCI | **4,224** | **33,792** |
| 400G NIC→Leaf | 端点实际接通数，含 breakout 子链路 | 100,008 | 800,064 |
| 800G Leaf→Aggregation | 一根逻辑线两端各占一个端口 | 51,200 | 409,600 |
| 800G Aggregation→Core | 同上 | 51,200 | 409,600 |

### 3.1 为什么端口不超售，以及“无阻塞”到底保证什么

所有速率均按**单向线速**，不把 TX 和 RX 相加。一个满 leaf：64×400G 下联 = 32×800G 上联 = **25.6 Tb/s**；一个 cell、一张 rail-plane 的北向切面是 **819.2 Tb/s**，满部署最重的 2,016×400G=806.4 Tb/s。八张合计每 cell 北向 **6.5536 Pb/s**。全场卡端口合计 **320.0256 Pb/s ≈ 40.0032 PB/s** 单向注入，不是实测、更不是某一条楼间链路拥有这个带宽。若 25 个 cell 切对 25 个，拓扑跨半场单向可排布上界 163.84 Pb/s，最轻的一半只接 1998×25 个 tray，满发也只有 159.84 Pb/s，实际作业流量矩阵还会进一步限制。

还可以作一项比“端口和差”更强的检查。对某一张 rail-plane，考虑每个端点最多提供及接收一个 400G 单元的任意单播置换。把不同 leaf 之间的需求视作源/目的 leaf 二分多重图，最大度数 ≤64；拆为 64 个匹配，每两色共用一个 `i`，该 leaf 到对应汇聚每方向最多两个 400G 单元。接着固定 `i`，以 cell 为顶点，跨 cell 的最大度数仍 ≤64；再拆为 64 个匹配，每两色走同一个 `j`。于是每条汇聚→核心同样每方向不过两个单元。同 cell 需求留在汇聚；同 leaf 留在本机。**所以正常态路径可重排、对置换存在 1:1 布线解。** 默认逐流哈希、一次随机同步 incast、队列峰值、传输重试和运行中的自适应调度都不由这个证明保证。要把线速变成吞吐，需要实测多个同发作业的流量矩阵、端口散布和 tail。

### 3.2 L3 精确路由、规模与扩容方法

这里的“三层”是交换拓扑；转发层协议在每层都是 IP/L3，RoCEv2 不要求一个跨 40 万卡的大二层广播域。采用 [RFC 7938 风格 eBGP](https://datatracker.ietf.org/doc/html/rfc7938)，按 rail-plane 隔离 RIB/VRF，邻接用链路地址，主机路由源地址/GID 强绑定接入，控制平面链路和端点地址分配分开。**软件平面模式的算例**：预留 `10.64.0.0/11`，切 8 个 /14；每张 fabric 有 64 个 /20 cell block，每 cell 32 个 /25 leaf block，可放 64 端点加 gateway；实际前缀应由 IPAM 生成并处理冲突。硬件 PLB 若抽象为单逻辑 NIC，按厂商 profile 验证 GID 与 plane，不强用这个寻址。

控制面要规定传递方向，不让故障后的数据走 “先下降再上升” 的迂回：leaf 前缀精确传播到上联，核心只从本组 cell 面得到其可达 leaf 路由；同 cell 优先本地 A 路径，远端走组内 core；跨组和跨 plane 不转发。尤其**不能让汇聚在本地某条叶链路故障后继续无条件宣告整个 cell**；用精确叶前缀（50×32=1,600 个/rail-plane）和故障撤销，汇聚失去某本地 leaf 方向后不把该本地流量经 core 兜回同 cell。验证同价多路径、可见性、FIB/resilient hash、BFD/BGP 收敛、灰故障隔离和重启时的服务状态；必要时按选定 NOS 的 eBGP multipath/AS 策略实现，而不是把同一 AS 设到每层等它自动工作。不要把单条默认路由当作下一层所有目的地都能到。

| 目标卡数 | 整柜实际卡数 | cell | 核心每 cell/每台并行链数 | Leaf + Agg | Core | 后端交换机合计 |
|---:|---:|---:|---:|---:|---:|---:|
| 100,000 | 100,008 | 13 | 4 | 6,656 | 2,048 | **8,704** |
| 200,000 | 200,016 | 25 | 2 | 12,800 | 4,096 | **16,896** |
| 400,000 | 400,032 | 50 | 1 | 25,600 | 8,192 | **33,792** |
| 400,000，北向约 2:1 | 400,032 | 50 | 1（每汇聚上联 16 台） | 25,600 | 4,096 | **29,696** |
| 400,000，北向约 4:1 | 400,032 | 50 | 1（每汇聚只上联 8 台） | 25,600 | 2,048 | **27,648** |

10/20 万前两行是**各自建成**的省核心方案，物理并行链路要用单独的路由邻接/可证明的散列方案，不能因同邻居而只在一个口上搬流。想无重布线一路扩到 40 万，就采用末态核心索引法从第一天预留，包括当前 cell 所需的 32 根北向链，接受早期闲端口；或者把加 core、移链路和验证做成可回退的分波项目。千万别把表里的三行误当不需要重新配线的连续拓扑。

## 四、两层什么时候真的成立？三套方案如何选择

设相同速率的有效逻辑 radix 为 S，leaf 端口一半下联、一半上联，全部 leaf 对 spine 组全连；**每 rail-plane 两层端点上限为 S²/2**。四个位置 rail 是四批同形端点，双平面是同一批端点的复用。如果 64×800G 全拆成 128×400G，S=128，最多 8,192 tray/rail，四条 rail 对应 **32,768 GPU**；增加同规模的 plane 主要改善带宽/故障，不会增加同一 plane 可接的 tray 数。

但更高 radix 会改变结论。公开 [Spectrum-6 SN6600 系列](https://networking-docs.nvidia.com/sn6000hw/nvidia-interconnect-for-spectrum-6-based-ethernet-switches)支持 512×200GbE 有效扇出；[NVIDIA 多平面材料](https://developer.nvidia.com/blog/giga-scale-ai-ethernet-evolution-spectrum-x-ethernet-rewrites-rules/)给出 800G 拆四张 200G plane，并展示了更高端口速率的 Rubin 512K 架构示意。**借用其原理而非复用 Rubin 图上的数量**：令 GB300 每 GPU 4×200G，4 rail×4 plane 共 16 张 fabric。每张：叶交换机 391 台，各 256×200G 下联、256×200G 上联；spine 256 台，各使用 391 个 200G 端口。叶到每台 spine 一个 200G 接口。每张能接 100,008 tray，最大理论 131,072，四 rail 不重复算 plane。这里把每轨 100,008 张卡的两层直达域复制到四个 GPU 位置。**若需求改成全场 400,032 卡两两原生 RoCE 直达**，这份 512 口、四条独立 rail 方案不合格。不能把四条 rail 的卡数当作同一两层 RDMA 域；要改成全域共享可达，并重新论证交换机有效基数、切面和布线。

| 40 万卡候选 | 交换台数 | 端点物理子链 | 交换间逻辑链 | 适用条件 |
|---|---:|---:|---:|---|
| 三层 2×400，近 1:1 | 33,792 | 800,064×400G | 819,200×800G | 需要可类比现有 64×800G 部件，且要求园区范围 1:1 切面 |
| 三层 2×400，L3 约 4:1 | 27,648 | 800,064×400G | 512,000×800G | 高频 EP 不大规模跨 cell，按 job 布局和测量定价 |
| 两层 4×200，近 1:1 | 10,352 | 1,600,128×200G | 1,601,536×200G | 512 扇出、四平面 NIC/光学配线、256 路 ECMP、驱动与固件组合均通过验证 |

两层方案的 200G 是逻辑链，不等于一根独立外皮或一个独立光模块。要把并行纤芯拆到 256 台不同 spine，需要实际的 1:4/1:8 分光线束/无源配线规划（按 lane 一一映射，不做功率分光广播），同一个多通道光模块的关联故障也要计入。**盒子更少不等于线更少**。单 rail-plane 391 个 leaf 覆盖 50 个 cell，其 spine 端口地理集中问题更尖锐；若光预算、模块供应或 ECMP 宽度不达标，不能订货后再指望固件补上。两层物料更适合新建且能集中布纤的园区，三层是更易分区上线的保守基线，4:1 则是为了符合通信本来就分层的训练负载。

模型和账本：[Python 复算与端口断言]({{ '/assets/data/roce-400k-clos-model.py' | relative_url }})、[三层 CSV]({{ '/assets/data/roce-400k-clos-main.csv' | relative_url }})、[两层 CSV]({{ '/assets/data/roce-400k-clos-shallow.csv' | relative_url }})。脚本检查端点和端口，**不是**包级仿真。

### 4.1 业界已经怎么组：两层多平面与十万卡证据对照

不同公司披露的“规模”至少有四种：**已投入运行的算力池、同一个训练后端网可达的端点数、最大同步作业实跑卡数，以及设计/可交付上限**。同一家也可能同时使用两层 Ethernet、多层跨楼网络和 InfiniBand；不能按公司只贴一种拓扑标签。

| 案例 | 可确认的规模与组网 | 证据边界 |
|---|---|---|
| **微软 Fairwater / OpenAI / Oracle Abilene** | 微软公开 Fairwater 站内两层 Ethernet，800 Gb/s/GPU；多个站点另走专用 AI WAN。OpenAI 确认 MRC 已部署在 Fairwater 和 Abilene。论文表 1 给出匿名生产网的 GB200 + ConnectX-8 **4×200G**、**8×100G** 两层配置，并报告 **50K、75K 卡同步预训练**故障案例。 | **131,072** 是论文两层拓扑容量算例。不要把匿名作业指认到某栋楼、把设计上限写成单作业卡数，或把这套网络套到 Azure 所有 GPU 集群。[微软 Fairwater](https://blogs.microsoft.com/blog/2025/11/12/infinite-scale-the-architecture-behind-the-azure-ai-superfactory/) · [OpenAI 生产部署](https://openai.com/index/mrc-supercomputer-networking/) · [MRC 论文](https://arxiv.org/html/2605.04333v1#S5) |
| **Meta 129K H100 / Prometheus** | Meta 披露曾用 5 栋楼建成 **129K H100** 单集群。更新的 Prometheus 由数十万 GPU 组成，单楼多层 Ethernet fabric 最多 **20,736 卡**，用 DSF 或 NSF；楼间用深缓存的 BAG，跨度 **2 到 100+ km**。 | 集群规模不等于同一作业。Prometheus 公布可并行跑多个数万卡作业，并按模型副本分层，把最敏感的通信尽量放在副本内，再给跨楼同步单独配带宽。[129K 历史披露](https://engineering.fb.com/2025/09/29/data-infrastructure/metas-infrastructure-evolution-and-the-advent-of-ai/) · [Prometheus](https://engineering.fb.com/2026/10/19/data-center-engineering/inside-prometheus-meta-gigawatt-scale-supercluster/) |
| **NVIDIA DGX B300 / Rubin** | DGX B300 SuperPOD 正式参考架构为 **512 节点 / 4,096 GPU**，两层 leaf–spine、rail 对齐、每 GPU 双平面 2×400G；B300 文档明确同一平面可经 spine 跨轨。厂商另展示了 512K Rubin 架构。 | 这是参考设计和更大规模的架构图，不是 512K 卡单作业验收数据。[DGX B300](https://docs.nvidia.com/dgx-superpod/reference-architecture/scalable-infrastructure-b300/latest/network-fabrics.html) · [512K Rubin 设计图](https://developer.nvidia.com/blog/giga-scale-ai-ethernet-evolution-spectrum-x-ethernet-rewrites-rules/) |
| **阿里云 HPN / 电信韶关真武** | HPN 论文披露已部署的 **15K GPU／Pod**：两层、双 ToR、rail 对齐、双平面。该版不同 Pod 之间另加 Core，**15:1** 超售，以 PP 为典型跨 Pod 通信。韶关真武另有万卡上线公告，采用卡间 RoCE 与双平面多轨。 | HPN 的北向配比只适用于那一版负载假设，不能照搬到广域 EP。真武是另一套加速卡与项目，十万是扩容规划，不是该公告所证实的上线规模。[HPN 论文](https://rmiao.github.io/assets/pdf/sigcomm24-hpn.pdf) · [阿里云上线公告](https://ue.aliyun.com/news/20260407) · [双平面多轨报道](https://www.cnr.cn/gd/xgyxgd/20260405/t20260405_527574164.shtml) |
| **腾讯星脉** | 腾讯产品文档称支持单集群 **10 万+ GPU 组网**，星脉披露多轨 RDMA 与 TCCL 协同。 | 产品支持上限；未披露该规模的竣工配线、每轨端点、交换层数或同规模同步作业日志。[IHN 产品文档](https://cloud.tencent.com/document/product/1779/110321) · [星脉 2.0](https://developer.cloud.tencent.com/article/2433459) |
| **字节跳动** | MegaScale 有 **12,288 GPU、175B、55.2% MFU** 的训练基准。火山引擎另公开 veRoCE 的多路径、选择重传与拥控设计。 | 两条证据不能拼成“12,288 卡用 veRoCE”或“已用 veRoCE 跑十万卡单作业”。[MegaScale](https://www.usenix.org/conference/nsdi24/presentation/jiang-ziheng) · [火山引擎 veRoCE 原文](https://volc-developer.tos-cn-beijing.volces.com/course/1765958096125_beb86bae351fa165dba84add1c01d92a.pdf) |
| **百度昆仑芯 / 中科曙光** | 百度披露 P800 **3.2 万卡**点亮并规模化使用；十万卡是交付能力。曙光披露郑州上线十万卡级资源池，网络为 scaleFabric 类 IB 原生 RDMA。 | 国产加速卡/资源池不等于十万 GPU 两层 RoCE；不据此推断单作业。[百度 3.2 万卡](https://cloud.baidu.com/news/news_312c7a72-b32c-4b45-a3fb-da21e99562fc) · [百度交付口径](https://cloud.baidu.com/news/news_49a6cfa4-2785-4d74-b564-bfba65c16647) · [曙光半年报](https://static.cninfo.com.cn/finalpage/2026-08-26/1225507613.PDF) |

协议也要按项目区分。例如，微软还披露过一个不同的 Azure GB300 集群，柜外是 [800G Quantum-X800 InfiniBand 全胖树](https://azure.microsoft.com/en-us/blog/microsoft-azure-delivers-the-first-large-scale-cluster-with-nvidia-gb300-nvl72-for-openai-workloads/)。AWS [Rainier 的 50 万+](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Fourth-Quarter-Results/default.aspx)是 Trainium2，Google [Ironwood](https://cloud.google.com/blog/products/compute/inside-the-Ironwood-tpu-codesigned-ai-stack)则用 TPU ICI 与光路交换连接多个 cube；两者可作系统思路对照，不计入 GPU RoCE 样本。

**对两层设计最有用的启发是故障粒度。** MRC 在 50K 卡作业里报告过 leaf 侧光模块闪断，作业吞吐短时约降 25%，但没重启；论文也明确说，若故障发生在 **NIC 端共用光模块**、四条子链一起掉，QP 仍可能失败。四个 plane 不能当四个完全独立的光模块。传统 RoCE 逐流 ECMP、Spectrum-X NIC 的 PLB、MRC 的逐包多路径、NCCL 的 PXN 是四件事：**PXN 可经本地 GPU 转接到对齐的 NIC，并在适用时聚合消息；它不代替跨平面调度和重传。** 工程上我会用 Fairwater 式浅网验证同园区大范围 EP；多楼、多站则先按 Meta/HPN 划分模型副本和高频通信域，再用跨界实测给北向定速，而不是按资产量给每栋楼配相同超售。


## 五、光纤距离、防拥塞与反压必须一起设计

**园区假设不是 xAI 现场距离。** 一种实际布置是 5 个机房区各 10 cell；就近放 leaf/汇聚，每连续 64 个 tray 端点可跨相邻数柜（柜内不一定有交换机），A/B 走不同铜/光配线与配电。一张 plane 的核心按 `j` 分 4 个物理配线/电力域，每域 8 个 j，另一 plane 不共用这些故障域。按每段**实际布放**而非地图直线核查：支持配对的短距 DAC/AEC 用在数米内，叶到邻近汇聚优先 ≤500 m DR 类，跨楼到 core 选可验证的 2 km FR 类或明确的长距链路。800G（单端口）与 2×400G（两独立链接）模块外观看起来可以相同，**对端 lane、调制、FEC、介质和 DOM 全部要匹配**。[NVIDIA 光连接选型](https://www.nvidia.com/en-us/networking/interconnect/)和[ConnectX-8 认证链路](https://networking-docs.nvidia.com/connectx8fwrn/40.51.1002/validated-and-supported-cables-and-switches)只给部件起点，不替代逐链插损、回损、连接器/熔接、FEC 门限与余量。用 [Supermicro GB300 柜 132–140 kW](https://www.supermicro.com/datasheet/datasheet_SuperCluster_GB300_NVL72.pdf)做工程量级，5,556 柜的**计算柜**约 733–778 MW，不含网络/备用/CDU/PUE 或负载差异；这是另一条独立的项目可行性门槛。

光传播单程约 **5 μs/km**。单段 2 km 的传播 RTT 约 20 μs；800 Gb/s 下，光传播往返期间可在途约 **2 MB/链路/方向的反压裕量估算**。PFC 要算单跳的最坏有效响应时间，而不是把整条端到端 RTT 填进单端口；还需包括检测、发送 pause、对侧反应、帧序列化、MTU 和内部管线。32 个这样的长链仅传播项就是 64 MB 量级，不能拿交换机总 buffer 逐口重复承诺，也不能把它充当厂商最终门限。跨多公里无认可的 headroom 与 QoS 时，我会在 cell/园区边界终止短域 PFC，用明确带宽的 DCI、经验证的可恢复拥塞机制与作业分层去跨区。50 个 cell 即使在同区域，长程链路更适合单独工程；**若现场没有能满足 1:1 跨区光纤槽位与预算的走线，照搬三层 33,792 台并不可施工。**

### 如果真像 Colossus II 那样跨站点，另一份 BOM 怎么算

这里不能把园区图上的 50 个 cell 画一条跨城光纤就算完。**可实施的两站版本**：每站 25 个 cell、2,778 柜、200,016 卡，分别用上表 16,896 台的配置建完整本地 RoCE（两站合计 33,792 台）。两站之间不用转发同一优先级的 PFC，也不宣告 RoCE 端点前缀。普通训练作业完全在站内；确需跨站的阶段，由作业框架站内归约/分片后，把显式批量数据交给独立长距传输端点，例如有背压、分片、校验与重试的 TCP 通道；跨站 AllReduce 要在两端将数据合并并确认 epoch，不能把普通 NCCL RoCE QP 直接接过去。若要求 RDMA 型跨站传输，则单独验收光层、封装、丢包重传和通信库，不能默认标准 RC 满足。

示例明确限定 DCI 的规模：**两条不共管道、不共边界机房的路径组，每组 512 个 400G 客户侧通道**。每站每组 16 个 32×400G WAN 侧口的边界单元，每个单元另有不低于 12.8 Tb/s 的本地汇聚接口；两站这一级共 64 个边界单元。对端路由/光传输以每组 204.8 Tb/s 客户侧线速验收；正常双组为 409.6 Tb/s、任一组失效剩 204.8 Tb/s。波分、光层线路速率和设备数按现场长度、放大段、光纤对和采购的转发器核算，不能把 512 个客户口等同于 512 对跨城裸纤。例如要在单组失效后仍维持 **102.4 Tb/s 有效负载**，这相当于剩余线速 50%；一批 128 个作业各每 4 秒向对端发送 400 GB 压缩/分片后数据，时间均值正好是 102.4 Tb/s/方向，但同步冲击还需错峰与保序，入口、边界网关及收端也都需超过该速率。把 128 个作业理解成计量单位，不是已验证的并发上限。若单个作业需跨区大范围 EP 或更短窗口，其流量级别完全不同；两站版**不**满足 40 万任意卡线速的条件，只满足站内完整与有明确带宽门槛的跨站协作。实际 xAI 跨站端口数和速率未披露。

### 5.1 四个控制环，分清它们的对象

| 机制 | 反馈对象与时间尺度 | 在工程里负责什么 | 不负责什么 |
|---|---|---|---|
| **逐流 ECMP / Flowlet** | 典型按 L3/L4 哈希，一条流（或 flowlet）固定路径 | 保持顺序，提供基础路径冗余；部署比逐包简洁 | 不能保证少数 elephant QP 均匀。flowlet 要有可分隔空隙，长突发不一定有 |
| **交换机逐包自适应 / 端侧 plane 选择** | 出口队列、每 plane 可用性与拥塞状态 | 分散 ECMP 组内热点，且应主动避开降速/故障 plane | 不能增大同一个接收者的 NIC；必须支持乱序放置/重排，不给普通 RoCE RC 盲目喷包 |
| **ECN / CNP / 端侧速率** | IP CE 标记→接收 NIC 发 CNP→发送 NIC 对连接/QP 等控速；至少经历反馈路径 | 抑制持续拥塞，减少 PFC 发生与公平性失控；应按实际控制算法与反馈带宽验证 | 流量真正只有一个目的出口时，不可能靠选路“创造”带宽；也不代替重传 |
| **PFC 逐跳反压** | 无损优先级 ingress headroom；802.1Q PFC 暂停对端相应优先级 | 在短域做突发保护；XOFF 留足反应时间，XON 有滞回 | 暂停的是端口+优先级，不是单流。会拖住同队列的无辜流、传播或死锁；不应靠它维持持续大规模过载 |
| **RC 可靠性、任务恢复** | PSN 顺序、重传/超时、QP 状态；再到 NCCL/作业 | 区分暂时丢包、链路切换、QP 重建、节点换卡、checkpoint 恢复 | ECMP/BFD 收敛不等于旧 QP 或 collective 继续，更不等于 DC 间零回滚 |

RoCEv2 的抓包链是 Ethernet → IP DSCP/ECN → UDP 4791 → RDMA BTH（含 QPN、PSN）等；交换机 PFC 帧不经路由跨域传播，但一个拥塞点可在每一跳依赖上游 ingress 反复重新施加 pause。[IANA](https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xhtml?search=4791)、[DCQCN 论文](https://www.microsoft.com/en-us/research/publication/congestion-control-large-scale-rdma-deployments/)与[Cumulus QoS/Headroom 文档](https://docs.nvidia.com/networking-ethernet-software/cumulus-linux/Layer-1-and-Switch-Ports/Quality-of-Service/)分别对应线协议、端侧控速与逐跳防溢出。定好 DSCP→内部 TC→PFC priority 映射，保持 ECN 位跨 L3/隧道的一致性；为 CNP/控制流保留小而有保障的队列，别让反馈和被暂停的大流同堵一处。PFC watchdog 的触发、恢复和丢弃行为由 NOS/SKU 定义，应做连锁停顿和恢复注入测试，而不是设置一个“通用毫秒数”。向上再向下的路径规则缩小环路风险，但仍需检查共享缓冲、重路由与优先级映射构成的实际队列依赖图。

**别把三个环境混用。** (1) 普通 RoCEv2 用 ECMP、按 QP 多流、ECN/DCQCN 与经验证的短域 PFC；(2) Spectrum-X 自适应逐包、端侧直接放置和拥塞控制属于配套实现，固定软件版本后对照验证；(3) [UET](https://ultraethernet.org/wp-content/uploads/sites/20/2026/01/UE-Specification-1.0.2-1.pdf)、[OpenAI MRC](https://arxiv.org/html/2605.04333v1)或 Meta 的 DSF/NSF 有自己的包/排序、端侧或交换侧机制。它们可以给本方案提供对照思路，不是打开一个“RoCE HDR”开关就能叠加。Meta [SIGCOMM 生产研究](https://engineering.fb.com/wp-content/uploads/2024/08/sigcomm24-final246.pdf)在其接收端发起集合通信和深缓存条件下曾撤下 DCQCN；不是建议在任意 40 万卡 all-to-all 网络上关拥控。

### 5.2 对应三类实际 traffic，决定北向是否值得买满

1. **向量化 AllReduce / ReduceScatter / AllGather**：把 TP/CP 中高频、大 payload、强同步路径尽量放进 NVL72/近域。在 NVL 内先 reduce-scatter，再用匹配 rail 做跨域数据并行，最后域内 all-gather。用真实 rank 日志判断哪些字节穿过 cell；Ring 里每 rank 约发 `2(P−1)S/P` 字节（S 为每 rank 输入大小、单向），不等于每一位都出 cell。跨楼桶需要 stagger/pacing，不能每个作业在同一个时刻把大桶故意对齐。
2. **MoE Dispatch/Combine**：收集层 × step × 源/目的的物理 bytes，包括量化元信息、padding 与路由不均。一个简化对称例：宽 4096、BF16、Top-8、每卡 50,000 输入 token/s，10% 的专家路由命中跨 cell，dispatch+combine 外发期均约 `2×8192×8×0.1×50000=6.55` GB/s/卡；跨 cell 比例若变为 50%，则 **32.77 GB/s**，超过 4:1 共享的约 25 GB/s/卡名义预算。这里只算 activation 复制，没计与 CP/DP 同发和热点。小 batch/LL 看 p99 加上实际完成 token；大 batch/HT 看每卡端口和跨 cell 切面。若分层去重是一目的域一份，必须量到 distinct destination 与真实二次转发，不按 Top-K 乘法硬扣。
3. **同一个目的 rank 的 incast**：8 个发送端各 400G 同时对一个 400G 接口灌 10 μs，即使整个 Clos 空闲，出口超额在流量真正同时到达时仍可积累 `(8−1)×50 GB/s×10 μs=3.5` MB。也正因此要做调度/credit 或收端协调、队列与 ECN 验证；添加 spine、ECMP 更随机、PFC 更激进都不能消除端口的容量不等式。

量化超售判据：从 trace 取每 cell 双向分开、每 rail-plane 的 P99 峰窗 offered load，窗口至少覆盖一个通信阶段和会重叠的后台 traffic。若将 4:1 配置北向限制在 70% 预留，八张合计每 cell 约 **1.147 Pb/s** 可调度，按最重 8,064 卡平均 **17.8 GB/s/卡** 单向，仍须每条 rail-plane 分开满足。若北向超过阈值，优先调整 EP/CP/副本映射；仍不满足就升到 2:1 或 1:1。2:1 的变体每汇聚 16 个北向口，共 614,400 根 800G 交换间链路。70% 是示例运营保护线，不是所有系统的固定最佳值。Meta [Prometheus 工程说明](https://engineering.fb.com/2026/02/09/data-center-engineering/building-prometheus-how-backend-aggregation-enables-gigawatt-scale-ai-clusters/)的典型 4.5:1 是另一套实际分层和流量配比，给了证据方向，不给 Colossus 的配比。

## 六、PXN 用在哪里，什么时候不该开

**PXN（PCI × NVLink）是 NCCL 的发送路径优化，不是 RoCE 协议，也不是 plane 的负载均衡器。** 正常拓扑相近时，直接是 G0→本地 NIC0→同 rail 对端；所谓 PXN 是 G0→本地 NVLink 上的 G3→靠近 G3 的 NIC3→匹配 rail→远端，数据路径不靠主机 DRAM 中转。NCCL 在特定规则支持下还能把多个本地 GPU 的消息在代理侧聚起来，从而少走跨轨链路或改善消息聚合。[NVIDIA NCCL 原理](https://developer.nvidia.com/blog/doubling-all2all-performance-with-nvidia-collective-communication-library-2-12/)

- Rail 对齐的 DP ring/tree 先建立直达基线；不为了“40 万卡”强制每轮 PXN。切换去远侧路径只在确实能减少外部跨轨、避免慢 PCIe 根复杂路径或得到聚合收益时值得。额外 NVLink/HBM 读写、代理 GPU copy/SM 等代价要一起量，尤其当 NVLink 同时跑 TP/专家转发。
- 任意专家位次的 all-to-all 需要明确组内代理或分层实现；PXN 可以是一种路径，但**不能把任意跨 rail 原生 QP、或者整个 NVL72 跨 tray 的任何 NIC 都假定为已支持**。验证进程/节点视野、GPU/NIC 距离、NVLink 可达、库/插件路径和路由前缀。DeepEP、NCCL-EP/GIN 的设备发起或分层方案要按所用后端单独验证，不能从传统 NCCL 的结果反推。
- 在固定版本以同样通信组、注册、缓冲和 rank 映射比较默认与 `NCCL_PXN_DISABLE=1`，用 `NCCL_CROSS_NIC` 管 ring/tree 的跨 NIC 策略，用 `NCCL_IB_QPS_PER_CONNECTION` 测 ECMP 熵，不把这三个参数当成同一开关。对多 QP 做 1/2/4/8 分档测。在一台交换机、32 条候选、理想独立均匀哈希的例子里，8/32 个同时活跃 QP 平均只撞中约 7.18/20.41 条路径，这也不等于被占路径负载均衡。还要考虑 NIC QP/CQ 容量、消息分割和 p99，不做 100K tray 全互联预建 QP。公开 [NCCL 参数](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html)和[用户缓冲注册约束](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/usage/bufferreg.html)明确普通网络用户缓冲注册与 PXN 路径不兼容；这不等于 PXN 中转路径不存在自己的 GDR。开跑前确认真正加载的 transport、peer GID、GPU/NIC/plane 活跃计数。
- **故障区别**：plane A 的一个口坏，同一 NIC 的 plane B 可用时走 B；整个 NIC 或共享光模块坏，两条子链可一起掉。把旧 QP 透明迁移、走邻 GPU NIC 的新连接、重新建组、整作业 checkpoint 恢复分别验收，不能统一说“PXN 会帮忙容灾”。

## 七、故障要算到哪台设备、哪个作业，才能叫可行

| 单次故障 | 三层 40 万主方案剩余能力（理想容量，不是作业速度） | 必须验证的后果 |
|---|---|---|
| leaf→agg 一根 800G 断 | 该 leaf/rail-plane 上联 32→31（少 3.125%） | 活跃流有无长尾、BGP 撤销与硬件重分布是否同向收敛 |
| 一台 agg 断 | 该 cell/rail-plane 所有 leaf 上联 32→31，北向也掉 32 根，即该 rail-plane cell 切面 −3.125% | 本 cell 某些源流是否集中到单剩余路径；不允许借别的 cell 回绕 |
| 一台 core 断 | 每个 cell 在该 rail-plane 少 1/1,024 北向线（0.098%），但对应 agg 自身上联少 1/32 | 全域流迁移可能放大远大于 0.098% 的 tail；观察最差 agg/端点 |
| 一个 core 机房/配电域断 | 指定 plane 内按布局掉每组 8/32 core（25% 北向）；另一 plane 物理独立 | 只有两 plane 能按残余速率平衡才接近合并 −12.5%；同域 ACC/冷却关联另计 |
| 一台 leaf 或一条 400G 子链故障 | 受影响端点最多 64 个，单 GPU 同 NIC 另一平面还 400G | 当前 QP 是否幸存取决于选定栈；不能拿“全场平均不到 1%”遮盖单端点折半 |
| NIC 两子口共因坏 / 柜级断电 / 整 cell 不可用 | 单 GPU 的该 HCA 可能归零 / 整柜 72 卡不在线 / 多达 8,064 卡不在线 | 这是端点不可达，不是路由负载问题；按作业网格换 spare、重建/恢复，不能许诺通信连续 |

1:1 主方案 leaf 在满端点下**掉一根不再 1:1**；若要求关键负载在单损仍不降速，要限制受影响 leaf 下接至最多 62 个 400G 端点（实际可用量与重度流量分布再验），或增加物理容量/真正冗余；双 plane 也不是 2×400G 任丢一边还等于 800G。对单 plane 保护的作业，在正常期如果每 GPU 要超过 400G，就不要承诺全 plane 故障后保持速率。供电、线道、核心组散开且记录 SRLG（共因失效组），从设备的“有路径”升级到实际作业的降级 SLA。

## 八、把设计交给集成团队之前的验收清单

| 关卡 | 执行办法 | 合格证据 |
|---|---|---|
| **物理与端口验收** | 导出 rack/tray/NIC/plane→leaf 笼位/子口→agg→core 拓扑；验收每一根 fiber lane、距离、插损、极性、FEC、光模块温度 | 端到端 LLDP/DOM 与设计一致，误码及丢包在约定范围；链路降速/高纠错能被派修 |
| **阶梯实测** | 4–16 台→一组 leaf→单 cell（近 8K）→两 cell→首个多机房块，最后才全站；每阶段先跑隔离双向线速，再跑匹配负载 | 400/800G 各方向有效 payload、延迟分位数、最差端点以及完整 TCP/BGP/PFC 计数；保护站内单平面与跨域差异 |
| **流量与真实训练** | 小包 RDMA RR、大包单流/多 QP、等负载 bisection、拥塞接收者、实际 AllReduce/AllGather/EP routing replay，再做真实训推长跑混载 | 逐流速率公平、队列深度/PFC 活动时长、ECN/CNP/retransmit、乱序/重发、各 rank 关键路径和整步 P95/P99；公开 algBW、busBW 与端口方向的分母 |
| **容灾与控制面** | 断单链、慢链、FEC 灰化、整交换机、同光缆组、核心区、plane、NIC、柜，且在 collective 进行时测试 | 分层记录检测→路径切换→QP/communicator→首个有用训练步→追平断点；分别判定不中断降速与恢复类故障 |
| **编排和寿命** | Job scheduler 感知 NVLink 域、rail、cell、楼、电力；先选同构卡与最少跨域的 rank 映射；分 plane/分 cell 滚动升级 | 阶段性回退方案，长跑吞吐、有效训练 step 比率、停机恢复时间和持久化故障域可追溯；按角色设置可复建备件 |

我会把验收目标写成**“指定 workload/调度、指定坏件集合、最差 rank 和好步率”**，而不是“交换机都能线速”。公开设备和端口图能证明上述参考拓扑在正常态可构造；项目要做到可签字，还必须在目标 NIC/NOS、光学和供配电条件下完成硬件与作业测试。相反，如果招标文件只承诺“装机 40 万张”，那最应该追问的是：**最大单作业多少卡、跨几个 cell、跨区切面多少、失去一条 plane 后还承诺什么？** 这四个答案，比单写两层或三层有用得多。
