---
title: "AI 集群 Scale-out 深度拆解：RoCEv2、veRoCE 与 UBG 如何传包、控流和恢复"
date: 2026-11-22T14:18:32+08:00
summary: "从 9001 字节 RDMA Write 算到线上开销，拆解 RoCEv2、字节 veRoCE 和华为 UBG 的包头、流控、多路径与故障恢复，并给出同预算集群验收方法。"
section: explainer
label: "AI 集群互联"
tags: [Scale-out, RoCEv2, veRoCE, UBG, RDMA, AI集群]
demo: false
sources:
  - title: "IBTA InfiniBand Architecture Specification"
    url: "https://infinibandta.org/ibta-specification/"
  - title: "火山引擎 veRoCE 协议原文"
    url: "https://volc-developer.tos-cn-beijing.volces.com/course/1765958096125_beb86bae351fa165dba84add1c01d92a.pdf"
  - title: "华为 UBG / SF9300 发布"
    url: "https://www.huawei.com/cn/news/2026/9/hc-ai-infra-aiwan-campus"
  - title: "IANA 端口登记"
    url: "https://www.iana.org/assignments/service-names-port-numbers?search=479"
---

同样是 800G，为什么跑单流 RDMA 能接近线速，一上 MoE All-to-All 就在交换机排队，甚至只闪断一条链路就拖住整个训练步？因为端口速率只回答“能发多快”，不回答三个更关键的问题：**包在多条路上怎么分，丢一包要补多少，哪一层负责让正在跑的 collective 继续。**

**结论先行：** RoCEv2 是标准化线协议和供应链基线。字节跳动 veRoCE 把端侧的乱序接收、选择重传和按路径控速打开，能复用一部分现有以太网底座，但不是只改交换机参数。华为 UBG 关注跨超节点的原生 UB 端点与高扇出专用交换；公开资料能确认软件接入、产品定位和若干厂商指标，却不足以还原 SF9300 的线上位图或重传状态机。三者不处在完全相同的层级，不能只拿一张“最大卡数”表排胜负。

## 1. 先分清：卡间总线、训练后端网和上层接口

训练后端 Scale-out 接住跨超节点的 DP 梯度归约、EP token dispatch/combine、CP 的 KV/状态交换，也可能承担 PD 分离的 KV 搬运、RL 权重刷新。Scale-up 内部追求高带宽、低延迟和紧耦合，跨界后更容易遇到多跳、跨故障域、拥塞与带宽割；把 EP 留在域内、跨域跑 DP，并不能证明跨域也适合大 EP。生产上还可把日志、数据、checkpoint 等前端流量和后端集体通信分面。Meta 的公开训练案例即区分前后端，并在 AI Zone 内与跨 Zone 采用不同的容量假设。[Meta SIGCOMM 2024](https://engineering.fb.com/wp-content/uploads/2024/08/sigcomm24-final246.pdf)

| 比较对象 | 实际是什么 | 两端和交换机怎么选 | 证据边界 |
|---|---|---|---|
| RoCEv2 | IB transport over UDP/IP，通常在 L3 Ethernet Clos | RoCE RNIC/SuperNIC、以太网交换机；PFC/ECN/队列及路径能力依设备协同 | 线协议可核；包级喷洒、重排、选择重传不能一概假定 |
| 字节 veRoCE | verbs 兼容、线协议不同的 RDMA transport | 两端都要支持并协商相应 profile；源端散列可用标准 ECMP，交换侧喷洒和裁剪另需支持 | 有公开技术 PDF；各卡 SKU、profile、量产部署与异厂商互通仍需逐项举证 |
| 华为 UBG | Unified Bus Gateway，跨超节点设备原生 URMA 路径和配套交换产品 | NPU 原生端点（EID）、软件栈及 SF9300 同类设备的配套；不是普通 RoCE RNIC 自动识别 | 有 CANN 接口、开源补丁和产品披露；未找到完整的产品级 wire spec、可独立复现实测 |

这里的 veRoCE 不等于华为云 EFI 的 [vRoCE](https://support.huaweicloud.com/usermanual-ecs/ecs_03_4503.html)，也不等于 VOQ：VOQ 是交换机输入端按目标出口等维度分队列的调度方式，可以改善队首阻塞，不是端点线协议。[Cisco VOQ 说明](https://www.cisco.com/c/en/us/solutions/collateral/silicon-one/silicon-one-wp.html)

## 2. RoCEv2：一条 9001 B RDMA 写请求如何在线上走完

应用向 SQ 投递 Work Request，NIC 根据 QP 上下文决定是发 SEND、WRITE、READ 还是 atomic。WRITE 由发送端带远端地址和 rkey；SEND 要接收端准备接收 WQE；READ 先发请求，再由响应端返回数据。连接型 RC 的可靠性由两端 RDMA transport 实现，不是 UDP 保证的。RoCEv1 是二层 Ethernet 封装，EtherType 0x8915；RoCEv2 路由用 IP/UDP，标准目的端口 4791，源端口通常可提供 ECMP 熵。[IBTA 规范](https://infinibandta.org/ibta-specification/) · [IANA 登记](https://www.iana.org/assignments/service-names-port-numbers?search=479)

```text
Ethernet [可选 VLAN] | IPv4/IPv6 | UDP | BTH | 依 opcode 的扩展头
                     | RDMA 数据 | Pad | ICRC | Ethernet FCS
```

BTH 12 B 含 opcode、pad 计数、目的 QPN 和 PSN（后两者各 24 bit）等。RETH 16 B 含远端 VA 8 B、rkey 4 B、消息总长 4 B；不为每个分片重复发。ACK 的 AETH 4 B 报告 syndrome / MSN。下面用 RC WRITE、不带 immediate、IPv4 无选项、无 VLAN、RDMA path MTU 4096 B。IP MTU 至少要 4156 B，不能把 4096 B RDMA 数据上限当作 L3 MTU。[Microchip RoCE IP 指南](https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/ip_cores/directcores/roce_ug.pdf) · [Linux RXE opcode 表](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_opcode.c)

| 包 | opcode / PSN | 负载 + pad | IP 总长 | Ethernet 帧含 FCS | 线时等价字节 |
|---|---|---:|---:|---:|---:|
| First | 0x06 / s | 4096 + 0 | 4156 | 4174 | 4194 |
| Middle | 0x07 / s+1 | 4096 + 0 | 4140 | 4158 | 4178 |
| Last | 0x08 / s+2 | 809 + 3 | 856 | 874 | 894 |

基础开销 Ethernet 14 + IPv4 20 + UDP 8 + BTH 12 + ICRC 4 + FCS 4 = 62 B，首包另加 RETH；每帧线时另计前导码/SFD 8 B 与 IFG 12 B。正向序列化效率 **9001 / 9266 = 97.14%**；400GbE 十进制 50 GB/s 乘此得约 48.57 GB/s 理想上界。它不是实测，不算 PHY/FEC、拥塞、重传、PCIe、DMA、反向 ACK 或其他流。一个示意性的累计 ACK（0x11＋AETH）约 66 B 帧、86 B 线时，不代表每个数据包都发 ACK。

**两个 CRC，两种职责。** Ethernet FCS 是链路层校验；ICRC 覆盖归一化的 IP/UDP/BTH、扩展头、负载及 pad，不包括 Ethernet/VLAN/FCS 和 ICRC 本身。TTL、IP 的 ECN 所在字段等按约定掩码计算，正常路由和 ECN 改标不会使 ICRC 失败；源/目的 IP 和 UDP 端口不属于这种掩码。ICRC 不是安全认证。[Linux RXE ICRC 实现](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_icrc.c)

**ACK 还不等于“远端 GPU 用到了数据”。** 普通 WRITE 不产生远端 receive CQE；需要通知时可用 WRITE_WITH_IMM 等约定并配接收 WQE。应用端的完成语义、GPUDirect 内存可见性及 CUDA 同步必须另行验证，不可把网络 ACK 当应用确认。[GPUDirect RDMA 指南：内存顺序](https://docs.nvidia.com/cuda/gpudirect-rdma/)

## 3. 流控、拥塞控制、可靠性、路由是四个控制环

| 控制环 | 感知 / 反馈 | 动作与边界 |
|---|---|---|
| PFC | 相邻设备队列压力 → 802.1Qbb 按优先级 PAUSE | 止住上游该优先级；不是逐流控速。需按线速、传播、反馈延迟和最大帧留 headroom。拥塞可蔓延到共享优先级；错误依赖会让 pause 长时间持续，watchdog 与降级策略要另验 |
| ECN/CNP | 交换机把能 ECN 的 IP 包标 CE → 接收 NIC 发 CNP | 发送 NIC 降注入；DCQCN 是常见源端速率调节，不是规范唯一算法。ECN 阈值和回路过慢会挤到 PFC/丢包，过激也会压低吞吐 |
| RC 可靠性 | PSN、ACK/NAK、重试/超时 | 基础实现如 RXE 遇序列缺口丢乱序包并发 sequence NAK，可能从缺口重发一串；实作升级可不同。ACK 丢失、NAK 丢失或拥堵会让恢复落到更慢的定时器 |
| ECMP / 自适应路由 | 五元组、QP 熵、队列/链路等 | 决定包走哪条路，不保证可恢复。静态 ECMP 稳定但大流可能碰撞；flowlet 要有空隙；包级分流改善均衡但放大乱序和接收状态需求 |

[PFC 说明](https://networking-docs.nvidia.com/doca/sdk/flow-control) · [RoCEv2 ECN/CNP](https://enterprise-support.nvidia.com/s/article/understanding-rocev2-congestion-management) · [DCQCN 原论文](https://conferences.sigcomm.org/sigcomm/2015/pdf/papers/p523.pdf) · [RXE 相应实现](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_resp.c)

要做工程预算，可以先算端口 BDP：800 Gb/s = 100 GB/s 单向；若闭环反馈时间 **假设**为 20 µs，发送端在得到信息前最多还可塞入约 2 MB。这不是 PFC headroom 配置值（逐跳与端到端反馈时间不同），也没有考虑多入一出。64 个 rank 同时向热点 expert 发包时，决定尾部的是热点出口的突发量、环路响应及等待，平均带宽可能几乎不变。Meta 在具体规模下展示增加 QP、扩展 ECMP hash 及流量工程的价值，也报告过激 ECN 对部分 collective 不利。以“PFC 一定开/一定关”替代噪声、负载和缓冲实测不可靠。

## 4. veRoCE：乱序不等于丢包，丢一包也不应重传一串

[火山引擎协议 PDF，§3、§5、§7–8](https://volc-developer.tos-cn-beijing.volces.com/course/1765958096125_beb86bae351fa165dba84add1c01d92a.pdf) 是本节依据。2025 年 12 月 v2.0.4 PDF 把 4794 写为候选；[IANA 2026-03-06 登记](https://www.iana.org/assignments/service-names-port-numbers?search=479) 确认 UDP **4794**。按 §9，连接管理的 REQ/REP/RTU 仍用 RoCEv2 的 4791，通过原 CM Vendor ID 字段协商；成功后 veRoCE 数据与确认走 4794，否则走 RoCEv2 回退。标准端口登记不是 IETF/IBTA 标准，也不是旧网卡能直接解新包的证据。

- **包头怎么改。** 保留 Ethernet/IP/UDP 和 BTH 的基本布局，重定义或扩展部分标记、opcode 和扩展头。MSNETH 带消息序号；POETH 带消息内包序位让接收端定位数据；RQETH 给需接收队列匹配的操作标识接收侧消息序。MSNETH、POETH 与 RQETH 在 §3 各占 4 B；SACKETH 为 20 B：24 bit 起始 PSN、8 bit 有效位长和 128 bit 位图。位图用于判断要补哪些包，不等于累计完成确认。每方向独立区分请求类包与 READ response/AtomicAck 的 24 bit PSN 空间，不能把所有包用一条 PSN 线读。头随 opcode/profile 变化，不能照抄上节 RoCE 字节数：例如 §5.4.1.3 的直接放置 WRITE，**每包**带着指向该包目标子区间的 RETH，普通 RoCE 只在 First/Only 带 RETH。把地址放回每个包，多付头部字节，换来不依赖 First 先到。
- **如何边收边补。** 假设包 s、s+2 已收，s+1 还没到。接收端记录空洞和已收窗口；能依据包序定位时，不必把 s+2 原样堆在交换机等事后排序。SACK 允许发送端只修 s+1，而不是顺带再打一遍 s+2 以后。延迟到达和真正丢失在一开始难区分，快速重传可能误判，因此 Lazy SACK、窗口、重传去重设计与超时兜底仍重要。128 bit SACK 位图不是所有硬件接收重排窗口的上限；超出实际窗口可以被静默丢弃。以上面的 800G、20 µs 假设计，2 MB 约是 488 个 4 KiB 包的在途量；真正需要的乱序窗口还取决于各路径速率与到达时差、QP 数及 NIC 缓存，不能拿 ACK 报告的 128 位来替代。
- **为什么有两种多路径。** 源 NIC 主动变 UDP 源端口时，普通 ECMP 可散到不同路径，端点知道用过哪条路径，可做连接级或按路径拥塞管理；若交换机自己喷洒、端点不掌握路径身份，协议文档的这条模式只能做连接级控制。FCC 允许速率或窗口设计，RTT 探针、ECN/CNP、ACK 合并分别承担反馈与确认，不是“既逐包喷洒便天然逐路径控速”。
- **裁剪不是丢包免疫。** 支持 trimming 的交换机在拥塞时裁掉负载、保留可识别的头并按规范更新完整性字段，把仍可识别的标记送到支持它的接收端；接收端用 Drop NAK 报具体 PSN。破纤、路径黑洞、裁剪反馈也丢、窗口耗尽，不能靠同一机制消除。
- **开发者要关注完成语义。** §10.1 明确，DDP 的远端 WRITE/SEND 和本端 READ 不能依赖内存数据按包顺序可见，看到最后一个字节不是完成。错误 CQE 也不保证后续消息没有写入。消费端用 CQE 和适当的设备同步；跨消息重叠写且强依赖顺序时，按规范用 fence。verbs 兼容不意味着原有的隐式先后关系成立。
- **硬件按 profile 验。** P0 是 RoCEv2 基线；P1 的 veRoCE 必选项集中在 WRITE 及相应操作，P2 增强选择确认/重传、DDP、多路径、按路径控制、裁剪端点等，P3 扩到 READ/SEND/atomic、共享接收队列和 UD 等。表里的可选不等于不支持，反之不能把最高 profile 的能力下放给所有 NIC。检查固件、驱动/provider、GPU/NPU Direct DMA、各操作码、PFC 配置、交换机 LB/裁剪及失败回退。一个 [xsc 驱动上游邮件](https://lists.openwall.net/netdev/2026/11/04/494) 提供不同 QP 模式的实现线索，不证明合入、跨厂卡互通或量产规模。

[火山引擎官方资料入口](https://developer.volcengine.com/resource/7584346532149723178) 与[发布解读](https://developer.volcengine.com/articles/7641550136838520868)披露其场景下训练 +11.2%、All-to-All +48.4%、2% 丢包条件下仍达网卡带宽 95.7%。这三个数字来自不同口径；没有相同拓扑、流量、随机/突发丢包分布、运行方差与尾部数据，不能横拿来对标 UBG 或推定故障作业不重启。

## 5. UBG：先确认数据面，再谈“百万卡”

华为 [HC 2026 计算架构发布](https://www.huawei.com/cn/news/2026/9/hc-lingqu-agent-ai) 把柜内/跨柜 UB 与跨超节点的 UBG 分开。[CANN HIXL 补丁](https://gitcode.com/cann/hixl/pull/612) 明确写 **Unified Bus Gateway**、A5 原生 URMA 端点和 EID；官方 [HIXL 手册](https://www.hiascend.com/doc_center/source/en/CANNCommunityEdition/910/commlib/hixlug/llmcrv2_42_25.html) 给出 `protocol: ubg`、设备侧 placement 及 128 bit 十六进制 comm ID 样例，另有 UBoE / RoCE 样例。后续 [HIXL 改名记录](https://gitcode.com/cann/hixl/pull/818)将外部选项改为 `ub_rtp`，内部 hcomm 仍可见 UBG；配置以安装版本为准。它证明 API 形状，不证明每个包有 128 bit EID 字段或包布局等同 comm ID。URMA 是软件访问模型；Jetty、TP 等是公开端点抽象，但不是可以与 RoCE QPN、PSN 等长替换的字段。

- **UBC/原生 UB、UBoE、UBG 不是一个名字。** 超节点内 UB/UBC 用于 Scale-up 通道；UBoE 是把 UnifiedBus 承载在以太网上，华为 [2025 官方说明](https://www.huawei.com/en/news/2025/9/hc-xu-keynote-speech)称可用已有 Ethernet 交换设备。UBG 是本节的跨超节点方案，CANN 中也见 `UB_RTP/UBG` 代码路径；[UB-Mesh](https://arxiv.org/abs/2503.20377)是层次化拓扑设计，不能当成这台交换机的端口图或报文格式。一套 [vLLM Ascend PD 异构配线](https://github.com/vllm-project/vllm-ascend/blob/main/docs/source/tutorials/features/pd_disaggregation_mooncake_multi_node.md)说明同超节点默认内部通路，跨域参数面按配套硬件选 UBG/UBoE/RoCE；这不是同一个包跨三种网络无缝通行。同端点配置限制与某型号交换机双模式也不是一回事。[IANA 4792 所登记的 IP Routable Unified Bus](https://www.iana.org/assignments/service-names-port-numbers?search=479) 不构成 UBG 使用该端口的证据。
- **端口与出货。** [SF9300 发布](https://www.huawei.com/cn/news/2026/9/hc-ai-infra-aiwan-campus)点名搭配昇腾 A5/A6，公开方案为两级、多平面；[数据中心网络发布](https://e.huawei.com/cn/news/2026/solutions/enterprise-network/xinghe-intelligent-data-center-network)披露约 30% 组网投资优化和约 40% 端到端时延优化，属于厂商指定对照，不是标准提供的幅度。至多 1024 radix 是高扇出与百万卡架构宣称，不能从中倒推 SF9300 单 ASIC 有 1024 个 800G 口，更不能倒推出百万卡量产、全二分带宽或全故障域训练效率。发布同页的 176×1.6T、约 280T 和 2 µs 是**另一台跨柜 Scale-up 设备**；[CloudMatrix384 论文](https://arxiv.org/html/2506.12708v2#S3.SS2)的公开实装是 UB Scale-up 加 RoCE Scale-out，不能类推成 UBG 装机统计。
- **公开到哪、停在哪。** 发布提到 LLR，宣称对瞬态链路闪断做微秒级恢复、无丢包；这是指定链路故障范围，不能推出网卡/ToR/整个平面故障透明。[hcomm 实现记录](https://gitcode.com/cann/hcomm/pull/3968)可见 QoS/Jetty 参数，但不能据此写出 UBG credit 单位、ECN 或 PFC 等价性、拥塞控制算法、乱序位图、重传窗口及计时器。截至资料范围，没有核验到可用于独立实现的 SF9300 承载位级包头或多厂互通报告。华为早期 [UB 技术论文](https://www-file.huawei.com/admin/asset/v1/pro/view/6ca306adab0a4852bacffce25f5573ec.pdf)讨论 EID 与拥塞机制，不能当作 2026 具体 SKU 的 wire specification。

## 6. 同场技术：开放规范、参考架构和品牌不是一个维度

| 技术 | 可核实的增量 | 不应混为一谈 |
|---|---|---|
| NVIDIA Spectrum-X | Spectrum 交换与 SuperNIC/端侧重排协调，做包级自适应路由、拥塞管理和遥测 | 配套软硬件能力，不是所有 RoCEv2 网卡开开关即可实现。[原厂架构](https://developer.nvidia.com/blog/optimize-large-scale-ai-workloads-with-nvidia-spectrum-x/) |
| UEC / UET | 截至截稿公开规范 **1.1**；端到端传输可做喷洒、可调顺序语义、裁剪等，1.1 加本地 Scale-up profile、CSIG 等 | UET 与 RoCE 是不同传输（UDP 4793），开放规范不自动等于已有异厂商全部互通。[版本史](https://ultraethernet.org/specification-history/) · [1.1 发布](https://ultraethernet.org/ultra-ethernet-consortium-releases-specification-1-1-advancing-ai-and-hpc-networking/) |
| InfiniBand | 独立 fabric 和 RDMA transport 生态，按虚通道的逐跳流控，配套自适应路由和部分网内集合通信 | 不能写成 Ethernet PFC。SHARP 支持范围取决于交换器/软件及 collective 类型。[Quantum-X800](https://www.nvidia.com/en-us/networking/products/infiniband/quantum-x800/) |
| OCP MRC / MetaRoCE | 前者是公开多路径规范；后者是 Meta 明确描述的独立传输设计 | 都不自动等于 veRoCE 或通用 RoCE 的模式开关。[OCP MRC 1.0](https://www.opencompute.org/documents/ocp-mrc-1-0-pdf) · [MetaRoCE](https://engineering.fb.com/2026/08/24/networking-traffic/metaroce-rdma-transport-ai-ethernet/) |

从影响力看，RoCEv2 赢在跨供应商采购、Linux/verbs/诊断工具积累和公开大规模生产经验。veRoCE 的影响力证据是火山业务测试、协议公开、端口登记和第三方驱动线索，还不足以把各厂生态都算进去。UBG 的优势假设是 NPU 原生数据路径和大扇出算网一体，证据更集中于同生态集成。开放性至少分公开 API、公开 wire spec、能跨厂实测三关，任何一关不能替代另外两关。

## 7. 容灾到底救哪一层？从首个坏包跟到训练步

把恢复时间分解为故障检测、流量改道、端侧修复和上层恢复，几段可能重叠，不能简单相加，更不能只报最快一段。

| 故障 | 被救的对象 | 应测什么 |
|---|---|---|
| 误码 / 单链路短闪断 | PHY/FEC、链路级重放或端到端选择重传 | 一次失链造成多少包、多少重放字节、第一笔正确完成与尾部停顿 |
| 一个 spine/uplink 下线、链路降速 | ECMP/AR 或 NIC 路径重新映射；剩余切面变窄 | 重映射之后还剩多少**方向容量**、是否 PFC 扩散、有没有路径黑洞及长尾 |
| 一个端口/整 NIC/ToR/平面失败 | 要求物理独立的 rail，NIC/驱动、内存注册、QP 与 CCL 配合 | 同一个通信操作能否继续，不行是否需要重建 communicator；只有故障链路微秒恢复不足以证明 |
| rank、进程、NPU/主机故障，站点失效 | Elastic runtime、业务幂等、checkpoint/重调度 | 丢多少步、重新入组多久、检验数据正确，区别于网络层容灾 |

这里的恢复不能用 ACK 或端口灯代替。应报告**首笔校验正确的 post-fault 操作时间**、进入幸存链路基准吞吐 90% 且持续稳定的时间、训练步 wall time 的 p95/p99/p99.9、abort/restart 比例、完成结果校验。按实际设备及通信库版本验证；[NCCL 文档](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html#nccl-ib-timeout) 的 ACK timeout 为 4.096 µs × 2^timeout，只是定时器定义，不是路径 RTT，也不是任意协议的容灾承诺。

## 8. 组网与选型：算端口，再测有效带宽、有效 EP 规模和好步率

**先算最紧的割。** 对一批操作，理想下界至少是 max（最大发送节点字节/单向发送容量，最大接收节点字节/单向接收容量，最忙的任意方向 fabric cut 字节/该方向总容量）。发送/接收可以同时发生，不能把双向总字节粗暴除以单向带宽，也不能用 full-duplex 标称值掩盖单侧热点。举例：一个 64×800G leaf 以 32 下联、32 上联运行，对上/下各 3.2 TB/s 单向，理想 1:1；48 下联、16 上联则是 3:1，跨 leaf 均匀热点就要争 1.6 TB/s，而不是每下联都可一直取 100 GB/s。若 16 上联失一条，跨 leaf 切面变为 1.5 TB/s，拥塞分布不保证同比例。高 radix 能减少级数，但也要算光模块、线缆、独立供电、维护 blast radius 与闲置备用容量。

**双向不能直接当有效负载。** 一条 800GbE 全双工理论为单向 **100 GB/s**、TX+RX **200 GB/s**，未扣协议、数据移动、重传。举例，一个对称通信目标若要每卡 **190 GB/s 双向有效负载**，即使方向完全均衡，也要至少 95% 的线速利用率；若负载近似上面的 97.14% 包效率，则可供双向应用数据的理想上限约 194.3 GB/s，尚未扣别的损耗。**300 GB/s 双向**不可能由一条 800G 满足。若多个 NPU 共用一台 NIC，还得先算注入拓扑、PCIe/设备内通路、各 rank 在哪个 rail。

**做两组正交对照，而不是分别挑最好看的数字。**

1. **同线速、同拓扑、同语义：** 固定每卡/每方向注入、网卡与 GPU/NPU 绑定、交换芯片/跳数、链路 MTU、节点数、oversubscription、CCL 算法和协议运行版本、数据类型、梯度/路由分布与负载。允许供应商提出优化配置，再单列成本相同的量产对照。某协议不能在这里同拓扑运行就诚实标注不是纯协议对照。
2. **同整机组网预算：** 纳入 NIC 及交换端口、光模块、布线、功耗、备用域；在相同训练或推理 SLO 下比较规模，而不是拿不同数量的 NIC 宣称协议快几倍。
3. **从小到大、从干净到脏：** 先测单流/多流、固定速率 incast、乱序和长短流混合，再测 EP 64/128/256/512 的不等长 A2Av、CP ring、DP SR/AR、H-FSDP 参数预取，最后叠加 KV 搬运、RL refit、后台负载。回放专家偏斜而不是只跑均匀 A2A；存下每 rank 完成时间与偏斜分布。
4. **逐项拔掉冗余的实验室验收：** 同样的故障时点和工作量，分开测短闪断、一路 spine、一个 host rail、ToR 和 rank。记录重传、SACK、NAK、CNP、ECN 标记率、PFC pause duration、队列峰值、端口速率/丢弃、RNIC/NPU 重排窗口、checkpoint/abort。报告峰值和 p99，而不是故障前后的均值。控制面、数据面和应用可恢复性分别签字。
5. **统一指标账本：** 每卡有用 bytes/s、交换口线上 bytes/s（各方向）、collective 完成时间 CCT、通信暴露到关键路径的时间、step MFU、符合 SLO 且校验正确的好步数/小时。NCCL bus bandwidth 是 collective 归一化估计，不等于端口 TX+RX 实测。可用 [UEC Collective Benchmark 1.0](https://ultraethernet.org/wp-content/uploads/sites/20/2026/10/UEC-Performance-Spec-v1.0.pdf) 的 CCT 和方向化利用率口径；它没有替你覆盖并行 collectives、后台或故障，须另补。

我的选型顺序：**跨厂可采购、可运维优先，就以 RoCEv2 做可验证的基线；已有以太网、同步大流哈希撞车或偶发丢包拖尾明显，就在现网预算下 A/B 验证 veRoCE 换来的尾延迟；若主要使用昇腾并计划把更多 EP/CP 跨超节点，才优先拿 UBG 与现有 RoCE/UBoE 路径做同负载对照。** 最后签收的不是技术名或宣传 radix，而是“哪一种故障之后，多少 rank、多久能完成下一次正确且符合时限的 collective”。

本文截至 2026 年 11 月 22 日，公开资料核验与示例计算，不包含自建集群测试。所有厂商指标和示例上界都不是跨平台性能承诺。
