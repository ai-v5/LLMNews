---
layout: post
title: "AI 日报 11/27：Nemotron 文档解析提速，MoE 推理按阶段重排路由"
date: 2026-11-27T05:34:28+08:00
summary: "五条公开进展：NVIDIA 为 Nemotron Parse 开放数据和 DFlash2，昇腾测试 DeepSeek V4.1 的紧凑 KV 布局，两篇论文分别重排 MoE 路由和流水线推理，Libtt 展示四卡 RL 闭环。"
section: daily
label: "AI 动态"
tags: [Nemotron, DeepSeek, 昇腾, MoE, 强化学习, 推理系统]
demo: false
sources:
  - title: "NVIDIA：Nemotron 3.5 Parse 数据、训练配方和 DFlash2"
    url: "https://huggingface.co/blog/nvidia/building-on-nemotron-35-parse-open-data-fine-tunin"
  - title: "vLLM Ascend PR #23397：DeepSeek V4.1 Flash KV 布局"
    url: "https://github.com/vllm-project/vllm-ascend/pull/23397"
  - title: "RankCast v1"
    url: "https://arxiv.org/html/2611.33542v1"
  - title: "PipeAxes v1"
    url: "https://arxiv.org/html/2611.34615v1#S7"
  - title: "Libtt v1：Miles 强化学习实验"
    url: "https://arxiv.org/pdf/2611.34273v1#page=18"
---

资料复核截至北京时间 **11 月 27 日 05:34**，统计此前 24 小时内的公开进展。预印本按首次公开公告日期，工程 PR 读作贡献者报告，不等同于合入或生产可用。

## 1. NVIDIA 为 Nemotron 3.5 Parse 放出合成数据、微调配方和 DFlash2

**11 月 26 日，NVIDIA 发布配套资料。这是对既有文档解析模型的补充，并非新发一代权重。** 在作者的开发 checkpoint 对照里，加入 GRPO 后，重复检测命中的输出从 126 页降至 29 页，达到 9,000 token 上限的从 185 页降至 35 页；总体分数从 66.24 到 71.38。最终发布模型与这对消融 checkpoint 分开看。

推理端，单 H200、BF16、相同 2,078 页的单次解析流程中，以 Parse 3.5 关闭投机为基线，DFlash2 在并发 1 和 512 分别带来 **7.62× 和 1.52×** 页吞吐。32 token 草稿设置平均接收约 14 个草稿 token。高度结构化的长输出给了投机解码空间，但低并发倍数不能当作饱和吞吐倍数。选型应同时数正确解析页/s、结构校验失败和尾延迟。[NVIDIA 发布说明及方法](https://huggingface.co/blog/nvidia/building-on-nemotron-35-parse-open-data-fine-tunin)

## 2. 昇腾 KV 排布测试：DeepSeek V4.1 Flash 多接了请求，单路 decode 未变快

**11 月 26 日，vLLM Ascend 公开 PR #23397。** 贡献者在 8 张 910B3、TP4 × DP2、EP8 上测 DeepSeek-V4.1-Flash-1017-W4A8。KV 为 BF16，每 worker 人为限制到 256 MiB；并发 8，轮换 16K 前缀，每个请求生成 32 token。相同 fork 修订上的对照显示，新布局将历史 KV 每 block ID 的预留从 540,928 B 降到 369,280 B，滑窗组的每 ID 层数也改变，实际容量收益随两类状态占比而变。

| 轮换前缀，两轮合计 | 原布局 | Block-outer |
| --- | ---: | ---: |
| 总输出吞吐 | 6.45 tok/s | 7.81 tok/s |
| P95 TTFT | 32.35 s | 26.10 s |
| 平均 TPOT | 373 ms | 411 ms |

作者记录峰值执行并发从 4 到 6，平均排队少约 7 秒。**这组数据更支持“容量和排队改善”，不支持“decode 算子快 21%”。** 单固定前缀近全命中的对照两轮结果不一致。另一项约 128K 容量数字是不同 KV 预算下的估算；端到端 P/D、A3 和任务质量没有相应实测。接入时需测真实预算和前缀局部性，并在固定 TTFT/TPOT 门槛下重算有效吞吐。[PR #23397 与实验版本](https://github.com/vllm-project/vllm-ascend/pull/23397)

## 3. RankCast：Prefill 平衡 token，Decode 平衡活跃专家

**11 月 26 日，arXiv cs.DC 公告发布 RankCast v1。** 作者在 SGLang、DeepEP 上验证阶段感知路由：保留路由器最确定的一部分专家，其他槽位从候选中选择。Prefill 优先分摊最忙 EP rank 的 token；中等批量 decode 优先减少该 rank 需要读取的不同专家数。它动的是 token 的专家选择，和只重排专家副本而保留原路由的方案不能混为一谈。

作者在 Qwen3-235B-A22B EP8 和 Qwen3.5-397B-A17B EP16 实验中报告，最忙 rank 的 prefill 超额负载减少超过 75%，输入吞吐最高提升 19%，decode TPOT 最多下降 10%，报告的质量损失低于 1 个百分点。都是论文配置内结果。启用前应复测路由改写比例、任务分组质量、通信 metadata 开销，以及 decode 从带宽受限转到计算受限时的交叉点。[RankCast v1](https://arxiv.org/abs/2611.33542)

## 4. PipeAxes 把 PP 推理里的算子批宽、层切片和网络发包解耦

**11 月 26 日，arXiv cs.DC 公告发布 PipeAxes v1。** 常规 token chunk 同时决定 prefill 批宽、连续占用计算的时间以及跨 stage 激活搬运粒度。PipeAxes 用较宽批次计算，但每次只推进几个层，让 decode 有机会插入；网络分组独立选大小，论文还在跨节点路径评估了 INT4 激活传输。

在双 RTX 4090、Qwen3-8B BF16、PP2、6.45 请求/s 的同一请求回放，PipeAxes 有 **135/188** 个请求同时满足 TTFT、TPOT 和单请求 P95 ITL 门槛；固定 512+Express 是 112/188，原生 vLLM V2 是 14/188。总输出分别为 472.3、464.3、495.6 tok/s，原生的总 tok/s 最高，但达标请求最少。这个反差值得纳入 PP 验收。论文另有受控 TCP 弱网测试，不是 RoCE/NVLink 生产集群验证。[PipeAxes v1 §7，表 1](https://arxiv.org/html/2611.34615v1#S7)

## 5. Libtt：四张 Tenstorrent Blackhole 芯片跑通小模型 GRPO 闭环

**11 月 26 日，arXiv cs.DC 公告发布 Libtt v1。** 作者用 Miles 在四张 Blackhole 上跑 Qwen3-0.6B，两张 FSDP2 训练、两张 TP 生成。三次不同 seed 各完成 90 步，GSM8K 测试贪心准确率从 58% 升到平均 73.3%，每步包括权重刷新。1,024 token 是评测输出上限，论文没有公布实际训练轨迹长度，分布式 checkpoint 恢复尚未验证。

对应的公开布局文档显示，32×32 tile 可能使扁平参数/梯度缓冲和含单例维的 logits 占用放大 32 倍。编译器与运行时对满足对齐和算子条件的形状使用紧凑表示。这个小模型已经需要审计物理张量分配，再往长序列或大模型外推，不能只拿逻辑模型大小算容量。[Libtt 论文 §9.5](https://arxiv.org/pdf/2611.34273v1#page=18) · [固定版本物理布局实现说明](https://github.com/pcmoritz/libtt/blob/2c68912a946f557de33ca6d14f2a4e5f0669a66c/docs/physical-layouts.md)

论文公告日期可在 [arXiv cs.DC 列表](https://arxiv.org/list/cs.DC/recent) 查看。另见今日独立解读：[MoLT 如何把参数量、训练 token 与 FLOPs 分开算]({{ '/2026/11/27/molt-token-vs-flop-efficiency/' | relative_url }})。
