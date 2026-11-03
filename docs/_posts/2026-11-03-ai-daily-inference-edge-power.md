---
title: "AI 日报｜11 月 3 日：vLLM 更新推理栈，端侧芯片与 800V 供电走向部署"
date: 2026-11-03T08:00:00+08:00
summary: "最近 24 小时四条值得关注的公开动态：vLLM 0.33.0、Ceva 与 Mobilint 端侧芯片、远景 800V 供电，以及 Tripo 可复用 3D 工作流。"
section: daily
label: "AI 日报"
tags: [推理, 端侧AI, 数据中心, 3D生成]
demo: false
sources:
  - title: "vLLM v0.33.0 发布记录"
    url: "https://github.com/vllm-project/vllm/releases/tag/v0.33.0rc3"
  - title: "Ceva 与 Mobilint REGULUS 公告"
    url: "https://www.prnewswire.com/news-releases/ceva-and-mobilint-advance-physical-ai-with-regulus-edge-ai-soc-302925294.html"
  - title: "远景 800V DC 系统部署公告"
    url: "https://www.prnewswire.com/news-releases/envision-achieves-worlds-first-commercial-deployment-of-integrated-800v-dc-sst-based-power-system-in-large-scale-ai-data-center-302926109.html"
  - title: "Tripo Agentic Canvas 发布公告"
    url: "https://www.prnewswire.com/news-releases/tripo-ai-unveils-agentic-canvas-to-make-ai-3d-more-accessible-and-scalable-302926715.html"
---

本期筛选窗口为北京时间 **2026 年 11 月 2 日 07:30 至 11 月 3 日 07:30**（UTC 11 月 1 日 23:30 至 11 月 2 日 23:30）。以下四条均按原始发布记录入选，不以转载时间充当事件时间；产品指标和部署情况按发布方陈述归因，未做独立实测。

## 1. vLLM 0.33.0：更新依赖，也收紧升级条件

**事实与时间。** [项目发布记录](https://github.com/vllm-project/vllm/releases/tag/v0.33.0rc3)于 11 月 2 日 10:10:05 UTC 发布（北京时间 18:10:05），版本名称为 v0.33.0。核验时 GitHub 标签仍是 `v0.33.0rc3`，但发布记录的 `prerelease` 为 false；本文保留该实际来源链接，不混用标签创建时间。

此次更新升级至 PyTorch 2.14.0，并停止发布额外的 CUDA 12.9 wheel 与镜像；CUDA 13.0 在此前已是默认变体，并非本次才首次切换。版本还加入需主动启用的有损推测验证策略 FLy，并将 NIXL connector 的依赖门槛提高到 NIXL 1.5。

**意义（分析）。** 推理引擎升级不能只看吞吐亮点。依赖、镜像标签和输出语义同样属于上线条件；FLy 不应被当作无损加速默认打开。相关变化以项目发布说明为依据，本文不承诺任何部署的性能收益。

## 2. Ceva 与 Mobilint：REGULUS 的量产与产品出货进展

**事实与时间。** Ceva 于 11 月 2 日 00:00 美国东部时间（05:00 UTC，北京时间 13:00）[宣布](https://www.prnewswire.com/news-releases/ceva-and-mobilint-advance-physical-ai-with-regulus-edge-ai-soc-302925294.html)，Mobilint 的 REGULUS 边缘 AI SoC 集成其 SensPro AI DSP 与 NeuPro-Nano NPU，并称这是 NeuPro NPU 家族首次生产部署。公告称，采用 REGULUS 的 MLD-R1 USB 加速器已出货。

厂商给出的规格为 10 TOPS、功耗低于 3W、最高支持 8GB 内存。这些是公告指标，并非本文测得的持续负载表现。

**意义（分析）。** 相比单一峰值算力，更值得后续跟踪的是感知、信号处理与神经网络推理能否在目标设备上协同运行。评估实际应用仍需明确精度、模型、算子覆盖和端到端功耗，不能直接把 TOPS 换算成大模型生成速度。

## 3. 远景：宣布 800V DC 系统服务真实 AI 负载

**事实与时间。** 远景于 11 月 2 日 02:42 美国东部时间（07:42 UTC，北京时间 15:42）[公告](https://www.prnewswire.com/news-releases/envision-achieves-worlds-first-commercial-deployment-of-integrated-800v-dc-sst-based-power-system-in-large-scale-ai-data-center-302926109.html)，其集成固态变压器、储能与控制系统的 800V 直流供电方案，已在乌兰察布 Galaxy AI 数据中心园区为实际计算负载供电。

“全球首个”是公司的表述，本文未独立验证全球范围的先后顺序。公告中的园区 **3GW 是规划容量**，不是此次已投运容量；也不能据此推算现有加速器数量。

**意义（分析）。** 高密度计算把供电转换和瞬时负载响应推到前台。商业运行消息值得关注，但是否形成成本优势，仍要看实际效率、可靠性、维护成本和长期运行数据，而不是仅依据电压等级判断。

## 4. Tripo：把单次 3D 生成扩展为可检查的工作流

**事实与时间。** Tripo 于 11 月 2 日 12:08 美国东部时间（17:08 UTC，北京时间 11 月 3 日 01:08）[发布 Agentic Canvas](https://www.prnewswire.com/news-releases/tripo-ai-unveils-agentic-canvas-to-make-ai-3d-more-accessible-and-scalable-302926715.html)。按其公告，用户可让 AI 构建节点式 3D 工作流，检查并修改节点，将生成、纹理、重拓扑、绑定和导出等步骤连接起来，并保存、复制和批量复用。

**意义（分析）。** 此次看点是生产流程的可编辑与可复用，不是已经证实生成质量出现跃迁。是否能减少返工，还需以目标资产的拓扑、材质、绑定与导入结果检验；公告不能代替生产级验收。

## 今日观察

四条消息覆盖了软件推理、端侧计算、机房供电和内容工具。共同问题不是“AI 能不能生成”，而是“能否在明确的成本、质量和运行条件下持续交付”。这是编辑分析；各条消息的商业效果与性能仍应分别验证。
