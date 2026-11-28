---
layout: post
title: "AI 日报｜950DT 的 64K Prefill、MI355X 的 KV 容量拐点，verl 分片同步权重"
date: 2026-11-28T05:34:00+08:00
last_modified_at: "2026-11-28"
summary: "SGLang 合入两种阶段不同的上下文并行方案；verl 用分片 NIXL 缩短大模型权重同步；昇腾有两处带实测的 decode 改动，以及 Kimi K3.1 的 DFLASH 功能进展。"
section: daily
label: "AI 动态"
tags: [昇腾, AMD, SGLang, vLLM, verl, 推理系统, 强化学习]
demo: false
sources:
  - title: "SGLang #51185：GLM-5.3-Flash 交错 Prefill CP"
    url: "https://github.com/sgl-project/sglang/pull/51185"
  - title: "verl #8395：sharded NIXL"
    url: "https://github.com/verl-project/verl/pull/8395"
  - title: "SGLang #53486：MI355X 的 GLM-5.3 DCP4 配方"
    url: "https://github.com/sgl-project/sglang/pull/53486"
  - title: "vLLM Ascend #20345：GDN 元数据复用"
    url: "https://github.com/vllm-project/vllm-ascend/pull/20345"
  - title: "vLLM Ascend #21782：DSA 小批次投影派发"
    url: "https://github.com/vllm-project/vllm-ascend/pull/21782"
  - title: "SGLang #52518：Kimi K3.1 DFLASH 昇腾路径"
    url: "https://github.com/sgl-project/sglang/pull/52518"
---

资料窗口：**北京时间 11 月 27 日 05:34 至 11 月 28 日 05:34**。下文时间为北京时间，工程动态以公开仓库合入时间为准；数据为贡献者或文档报告，并非独立复测。

## 1. 8 张 950DT：GLM-5.3-Flash 的 64K Prefill 输入吞吐升 11.44%

**11 月 27 日 19:13**，[SGLang #51185](https://github.com/sgl-project/sglang/pull/51185) 合入交错 Prefill Context Parallelism；20:08 [回移到昇腾维护分支](https://github.com/Ascend/sglang/pull/1492)，不是发布镜像。实测基于单机 8 张 950DT，W8A8 MXFP8、BF16 KV、TP8/EP8，eager prefill、decode graph、开启 MTP。并发 8、128 请求，每请求 65,536 输入并只生成 1 token：PCP 关闭→CP8，平均首 token 延迟 **31.43→28.20 s**，P99 **33.40→31.59 s**，总输入吞吐 **16,337.51→18,207.02 tok/s**。

**为什么重要：** 这是同卡数的 Prefill A/B。交错分配让各 rank 分担 query 计算，但 KPool 的 key 和 gate 仍要跨 rank 收集并重排，索引和未池化尾段仍被复制。不能把显存或通信量简单除以 8。它给了一个 64K 负载的校准点，不是 decode、P/D 分离或其他长度的结论。

## 2. verl：235B 权重同步 21.7→6.35 秒，小模型却不一定划算

**11 月 27 日 11:06**，[verl #8395](https://github.com/verl-project/verl/pull/8395) 合入分片 NIXL 权重同步。区别是让训练 rank 从自身拥有的切片并发发送到目标 rollout rank，不再依赖单一 rank 串行搬运完整权重流。在 8 卡 B300 节点组成的 RoCE 环境，Qwen3-235B-A22B 的 16→16 卡独立同步测得 NCCL **21.7 s**、原 NIXL **21.1 s**、分片 NIXL **6.35 s**。作者取第 2–4 次同步均值，测试时关闭了切片校验；它不是带合入版校验的完整系统实测。

**为什么重要：** 不换同类传输库也能受益，关键是把发送负载分给真正拥有权重的 rank。不过 30B-A3B 的小规模 GRPO 中，`update_weights` 中位数从 **9.4→7.5 s**；0.6B 则是 **3.3→6.1 s**。配置 RL 资源时，要把同步的固定成本与切片字节量分开，并测它有多少落在完整训练迭代关键路径上。该 PR 的实测 vLLM 版本为 0.24，不代表当前固定的 0.32 已获得同样速度。

## 3. MI355X：GLM-5.3 的 Decode CP，缓存吃紧后才占上风

**11 月 27 日 15:40**，[SGLang #53486](https://github.com/sgl-project/sglang/pull/53486) 合入 **GLM-5.3（非 Flash）** 的 FP8 高并发配方，平台为 8 张 MI355X。它把 Decode KV 分散到 DCP4，公开对照报告 GPU KV 池 **3.28M→10.5M token**，AgentX 前缀命中 **93%→96.9%**。在 [InferenceX 作者的一小时对照](https://github.com/SemiAnalysisAI/InferenceX/pull/5168) 中，C16 的旧配方本地复现与 DCP4 比较，总输入加输出吞吐 **8,173→9,369 tok/s/GPU**，按 P90 token 间隔换算的用户出字速度 **45.4→59.9 tok/s**（约 **22.0→16.7 ms**）。C24 的 DCP4 达 **13,304 tok/s/GPU**，用户出字速度反而回到 **39.7 tok/s**。C8/C10 下，测试的 DCP4 表现低于之前的 DCP1 配方。

**为什么重要：** decode 每步多付出的代价，可能被避免驱逐与重算的收益抵消，低负载时则未必。这里是包含 HiCache、prefill graph 与调度差异的整套配方对比，采用了合成的推测接受设定，不是 DCP 单变量实验，也不能把 C16 当作其他机器的通用阈值。[已上线 cookbook](https://docs.sglang.io/cookbook/autoregressive/GLM/GLM-5.3#mi355x-fp8-high-concurrency-deployment-with-dcp4) 有另一组 DCP4 数字，不与上面的同组对照混算。

## 4. 昇腾 A3：验证轮数没变，GDN 元数据复用让每轮更快

**11 月 27 日 22:08**，[vLLM Ascend #20345](https://github.com/vllm-project/vllm-ascend/pull/20345) 合入 Model Runner V2 的 GDN 元数据复用：兼容缓存组共用请求布局，各组仍绑定自己的物理状态索引；启用状态 checkpoint 的组独立构建。Qwen3.5-9B BF16 在单张 A3、DFlash 7 个草稿、16K 输入/256 输出下，平均 TPOT 在 C1 **5.787→3.829 ms**，C4 **6.941→4.836 ms**。另一次带计数的 C1 测试里，两边都执行 34 轮目标模型推理，完整构建 **816→34**，其余 **782 次**成为组内更新。

**为什么重要：** 端到端 decode 既取决于每一轮产出多少 token，也取决于每一轮要做多少重复准备。十组配对输出逐 token 一致是窄范围验证。24 倍是完整构建次数之比，不是元数据耗时降了 24 倍，也不能直接映射到其他硬件或模型。

## 5. 910B：DeepSeek-V4.1-Flash 的小矩阵走不同算子，TPOT 降约 4.2%

**11 月 27 日 19:57**，[vLLM Ascend #21782](https://github.com/vllm-project/vllm-ascend/pull/21782) 合入 DSA 输出投影分流：`wo_a` 未量化、仅一个本地组、至多 128 个 token 行时，使用普通二维 matmul。910B、1017 W4A8、TP8/DP1、C6、关闭 MTP，使用 46.5K 前缀与 3.5K 随机输入，每组两次，平均 TPOT 约 **31.28→29.96 ms**，总输出吞吐约 **+3.5%**。

**为什么重要：** PR 性能要绑定到实际派发。模型整体是 W4A8，不代表这个投影权重已经量化。若低 TP 部署在每 rank 放多个本地组，则不命中新分支，不能套用这组数据。

## 6. Kimi K3.1 DFLASH：有四节点功能验证，速度仍待公布

**11 月 27 日 15:32**，[SGLang #52518](https://github.com/sgl-project/sglang/pull/52518) 合入 Kimi K3.1 DFLASH 的昇腾适配，包括 draft 侧滑窗 MLA，以及空闲 DP rank 的目标模型验证图处理。作者报告四节点 TP64、Kimi K3.1 Pro W4A8 的 GSM8K **198/200**。PR 未报告吞吐或延迟，也没有同配置关闭 DFLASH 的精度对照。

**为什么重要：** 可以据此跟进可运行配置，但不能据此估算每秒输出、每轮接受数或节省的卡数。下一步应固定模型与采样，在相同负载下记录目标验证步时、接受长度、TPOT 和尾延迟。

**配套解读：** [950DT 上的百万 token KV 命中，为什么还是超时？](/LLMNews/2026/11/28/950dt-kv-read-lease/) 把单次读租约、整个恢复时间和客户端首 token 延迟分开测。
