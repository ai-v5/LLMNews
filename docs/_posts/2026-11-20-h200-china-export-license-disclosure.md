---
title: "美国公开 H200 对华许可明细：87.99 万颗获批，为什么不是 87.99 万张卡到货？"
date: 2026-11-20T17:00:00+08:00
summary: "美国众议院披露的是截至 5 月 11 日的许可快照。逐行复核显示，344.42 万颗申请中有 87.99 万颗获批，覆盖 NVIDIA H200 和 AMD MI325X；这 21 条在表中均为获批未发货。"
section: explainer
label: "算力与出口管制"
tags: [H200, AMD, AI算力, 出口管制]
demo: false
sources:
  - title: "美国众议院外交事务委员会：11 月 19 日披露公告"
    url: "https://foreignaffairs.house.gov/news/press-releases/chairman-brian-mast-exercises-legislative-authority-to-publicly-release-ai-chip-license-information-for-china"
  - title: "众议院外交事务委员会：两页官方摘要"
    url: "https://democrats-foreignaffairs.house.gov/wp-content/uploads/2026/11/11.19.26-ECRA-Information-Disclosure-HFAC-Summary.pdf"
  - title: "BIS 许可决定：四页逐项明细"
    url: "https://democrats-foreignaffairs.house.gov/wp-content/uploads/2026/11/11.19.26-ECRA-Information-Disclosure-of-BIS-License-Decisions.pdf"
  - title: "1 月 15 日《联邦公报》：先进计算芯片许可审查政策"
    url: "https://www.govinfo.gov/app/details/FR-2026-01-15/2026-00789"
  - title: "11 月 19 日《联邦公报》：另行发布的临时最终规则"
    url: "https://www.govinfo.gov/content/pkg/FR-2026-11-19/pdf/2026-23529.pdf"
---

**有这件事。美国众议院外交事务委员会在美国当地时间 11 月 19 日，公开了美国商务部工业与安全局（BIS）处理 H200 和 MI325X 对华相关出口许可的记录。新的是明细公开，不是当天新批了近 88 万颗，也不是中国企业已经买到、收到或上线了这些芯片。** 公告由委员会发出，决定由 BIS 作出；两者不是同一个动作。[委员会公告](https://foreignaffairs.house.gov/news/press-releases/chairman-brian-mast-exercises-legislative-authority-to-publicly-release-ai-chip-license-information-for-china) · [11 月 19 日委员会会议说明](https://democrats-foreignaffairs.house.gov/2026/11/meeks-delivers-remarks-during-hfac-disclosure-of-bis-licenses-of-nvidia-amd-chips-to-china/)

## 原文的四张账：申请、退回、拒绝和批准未出货

[两页委员会摘要](https://democrats-foreignaffairs.house.gov/wp-content/uploads/2026/11/11.19.26-ECRA-Information-Disclosure-HFAC-Summary.pdf)给出总量；[四页 BIS 决定表](https://democrats-foreignaffairs.house.gov/wp-content/uploads/2026/11/11.19.26-ECRA-Information-Disclosure-of-BIS-License-Decisions.pdf)还能逐条核对出口方、数据中心运营方或最终收货方、芯片数量、状态和最终地点。表中日期是**提交日**，状态截点是 **2026 年 5 月 11 日**。按附件可见的 54 条记录加总，结果与摘要总量一致：

| 5 月 11 日表列状态 | 记录数 | 颗数 | 应当怎么读 |
| --- | ---: | ---: | --- |
| 获批、尚未发货 | 21 | 879,868 | BIS 已批准相关交易；表中未记录这些条目发货 |
| 退回未作决定（RWA） | 9 | 1,888,950 | 未签发许可，不等于实质性拒绝 |
| 已提交 | 23 | 600,342 | 表中没列批准，也没列拒绝 |
| 拒绝 | 1 | 75,000 | 与 RWA 单列 |
| 合计 | 54 | 3,444,160 | 公开明细所覆盖的申请量 |

[BIS 对 RWA 的官方说明](https://www.bis.gov/media/documents/snapr-faqs.pdf)列举了申请方主动取消、未及时补交信息等情形，公开表未披露每一项退回原因。87.99 万除以 344.42 万约为 **25.55%**，是这张快照中**按芯片颗数**计算的已批占比，不是案件通过率，也不是出货率。不能把其余 74.45% 一律叫作“被拒”，更不能把申请量当成去重后的采购订单。

## 哪些公司在表里？先分出口方，再看最终地点

下表只统计 21 条已批记录中的部分企业。型号口径按摘要定义，明细按出口方归类；公开表没有逐条披露板型、服务器整机配置或交付规模。

| 企业或集团 | NVIDIA 项 | AMD 项 | 合计获批颗数 |
| --- | ---: | ---: | ---: |
| 腾讯及列明子公司 | 75,000 | 75,000 | 150,000 |
| 字节跳动及列明子公司 | 75,000 | 75,000 | 150,000 |
| 滴滴 | 24,780 | 75,000 | 99,780 |
| 阿里巴巴 | 75,000 | 0 | 75,000 |
| 快手 | 0 | 75,000 | 75,000 |
| 百度 | 43,000 | 0 | 43,000 |
| 京东 | 41,300 | 0 | 41,300 |
| 比亚迪 | 4,000 | 0 | 4,000 |
| **全部 21 条** | **579,868（17 条）** | **300,000（4 条）** | **879,868** |

三个容易被转述带偏的地方：

1. **腾讯的 44.5 万不是批准量。** 委员会说，另有一笔 NVIDIA 为腾讯提交的 445,000 颗 H200 申请，未完整反映在 5 月 11 日摘要中。不能把它加到 15 万颗已批数，也不能假设它与表内条目完全不重叠。15 万颗已批中只有 7.5 万在 NVIDIA 栏。
2. **中国企业不等于中国境内部署。** 摘要按企业所在地、总部或最终母公司界定“中国企业”。例如阿里及子公司的 948,950 颗申请量中，有两条最终地点为马来西亚，状态均为 RWA。表末另述两张联想获批许可，涵盖包括 H200 在内的芯片，但用途是境外服务器制造和研发，不授权运往中国地点。
3. **名单、角色和违规结论是三回事。** 委员会把许可记录与它所引用的 2026 年 6 月 1260H 名单对照，用于提出监管问题。该名单日期晚于表的 5 月快照，名单也不能直接等同于 BIS 实体清单或某笔交易的违规认定。同理，申请材料列为可能安装服务器的企业，不等于最终收货方，更不证明发生了转流。

## 规则原文怎么读：逐案审查不是免许可

[2026 年 1 月 15 日生效的 BIS 最终规则](https://www.govinfo.gov/content/pkg/FR-2026-01-15/pdf/2026-00789.pdf)把从美国出口、面向中国或澳门最终用户、满足门槛及文件条件的相应申请，从原则上拒绝改为逐案审查。门槛是 **TPP 低于 21,000、总 DRAM 带宽低于 6,500 GB/s**，两条同时满足。TPP 是法规技术指标，不是模型实测 FLOPS、MFU 或 tokens/s。

- **供应与产能。** 申请方需证明不延误美国用户订单，不挤占原本用于美国终端用户的同级或更先进晶圆代工能力；规则还要求证明相关对中国及澳门出口累计 TPP 不超过规定窗口内同款产品对美国终端用户已出货累计 TPP 的 50%。这个比例不是采购单的通用批准率。
- **最终用户、用途与远程访问。** 规则要求相关筛查、物理安全和声明，并对 IaaS 的部分远程用户及用途设有附加条件。达到两个芯片技术门槛，只是进入这套审查的条件之一。
- **发货前验证。** 获批后，从美国出口的相关批次仍须经合格的美国第三方实验室验证技术规格。许可是一道关口，不替代后续出货、进口与验收。

同一美国日期还有**另一份文件**：[11 月 19 日生效的 BIS 临时最终规则](https://www.govinfo.gov/content/pkg/FR-2026-11-19/pdf/2026-23529.pdf)。它在修订后的 §742.6 里保留上述中国／澳门合资格出口的逐案审查门槛，同时在 §744.24 另设数据中心最终用途限制，覆盖满足规定的单一或互联数据中心向特定总部或最终母公司所在地的企业提供合计超过 1,200 万 TPP 的访问场景。这里的 **1,200 万是聚合 TPP，不是芯片数量**，也不是 1 月的单芯片门槛。国会披露的 5 月存档不能代替对 11 月新规则与具体交易的判断。

## 对算力供给意味着什么？

**美国许可、厂商发货、目的地到货、集群可用，是四个不同的里程碑。** 5 月表格里的未发货不能外推成 11 月仍然零出货。反过来，NVIDIA 在 11 月财报电话会上表示，上一季度对华销售了 24 亿美元获许可的 Hopper 数据中心产品，但当时已不再向中国发运这类产品。公司下一季指引也没有计入中国数据中心计算收入。收入不是 H200 颗数；停止出货这个表态也不能反推历史许可被全面撤销，或证明 AMD 的交付状况。[NVIDIA 财报](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Third-Quarter-Fiscal-2027/) · [路透社对财报电话会的报道](https://www.reuters.com/world/china/nvidia-stops-shipping-us-approved-ai-chips-china-2026-11-18/)

做训练或推理容量规划，应把**已获许可但未锁定交付的数量**放在情景分析里，而不是基线。基线至少要有分批交付和验收凭据，再确认 SKU、节点间互联、供电散热、软件栈及可用机时。例如 [NVIDIA 的 HGX H200 规格](https://docs.nvidia.com/enterprise-reference-architectures/hgx-ai-factory-h100-h200-b200/latest/components.html)是单卡 141 GB HBM3e、4.8 TB/s；它们有助于估算长上下文和低批量解码，但同一张卡在推理里贡献多少 tokens/s、在训练里能否形成大规模同步池，还取决于并行方式、网络拓扑和端到端效率。**这次披露能量化美国曾批准多大规模的潜在供应，不能量化中国市场已新增多少可调度算力。**
