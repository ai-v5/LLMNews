---
layout: post
title: "950DT 上的百万 token KV 命中，为什么还是超时？"
date: 2026-11-28T05:29:00+08:00
last_modified_at: "2026-11-28"
summary: "拆解 GLM-5.3 HiSparse 的外部缓存恢复：256 MiB 分批把最大单次 GET 从 40.30 秒压到 1.39 秒，而整轮读取仍约 40 秒。三组试验分别回答了租约、传输和请求完成的问题。"
section: explainer
label: "推理系统解读"
tags: [昇腾, GLM, KV Cache, 长上下文, vLLM, 存储]
demo: false
sources:
  - title: "vLLM Ascend #23442：修复、硬件回归和 SDK 对照"
    url: "https://github.com/vllm-project/vllm-ascend/pull/23442"
  - title: "固定版本 84894c1：GET 拆批实现"
    url: "https://github.com/vllm-project/vllm-ascend/commit/84894c1de06566d3571b0ada71f6760f0fa33cdd"
  - title: "HiSparse 外部池接入 #21924"
    url: "https://github.com/vllm-project/vllm-ascend/pull/21924"
---

**外部 KV 命中以后，推理引擎还要把数据取回来。** vLLM Ascend 的一组 950DT 测试把这段路径的问题暴露得很清楚：GLM-5.3 复用接近 100 万 token 的历史前缀时，Device 端的一次批量读取超过了 MemCache 的 10 秒读租约，最终请求返回 HTTP 500。11 月 27 日合入的 [#23442](https://github.com/vllm-project/vllm-ascend/pull/23442) 把这批读取拆成多个调用，降低的是**最长一次操作的时长**。作为对照，把租约放宽到 60 秒做 SDK 测试，整轮读取前后都在 40 秒左右。

本文依据截至北京时间 **2026-11-28 05:29** 的公开 PR、固定提交与作者测试，不是独立上机复现。

## 1. 被卡住的不是命中判断，而是读取租约

这个案例来自单机 8 张 950DT、TP8、Prefill 和 Decode 同部署的 HiSparse 路径。对 GLM-5.3，外部池的恢复涉及两类数据：送往 **Device 的 C8 Indexer 数据**，以及送往 **Host 的 Source 数据**。两者落点不同，不能把其中一张测速表等同于整个模型恢复。路径背景见 [#21924](https://github.com/vllm-project/vllm-ascend/pull/21924)。

MemCache 对两类批量 GET 都使用读租约。此前 Host GET 已按 256 MiB 的字节预算分批，但 Device GET 没套用这条规则。接近百万 token 时，一个 rank 把 8,183 个 Device key 交给单次 GET，调用在租约到期后失败，SDK 报 `-3106`。只盯前缀命中率，容易把这样一个请求归到“缓存可用”，却看不到它在恢复中途失败。

[合入代码](https://github.com/vllm-project/vllm-ascend/commit/84894c1de06566d3571b0ada71f6760f0fa33cdd)把相同的字节预算用于这条已注册的 HiSparse 读取路径，并保留各批次 SDK 状态。它按整 key 分组，不把单个超预算 key 切开。所以 **256 MiB 是通常的组批预算，不是对任何单次传输大小或延迟的绝对保证**。这个边界决定了生产监控除了看批量上限，还得看最大的单 key。

## 2. 三个试验，三个不同的结论

| 证据 | 条件 | 能说明什么 |
| --- | --- | --- |
| 10 秒租约的 SDK 诊断 | 八个 rank；单批与拆批比较 | 单批读在八个 rank 均失败，拆批成功；直接验证这次租约问题 |
| 60 秒租约的 SDK 对照 | 8,183 个合成 key/rank；每个方案三轮，交替顺序 | 让原单批也能跑完，比较最长单次 GET 和整轮墙钟时间 |
| 模型级外部前缀重放 | W4A4C8 MXFP4、MTP3、Decode Graph；测试树还带独立的 Resident DMA 改动 | 验证特定 checkout 的请求完成和外部前缀恢复；没有提供客户端 TTFT 或并发容量曲线 |

作者的 [60 秒租约对照](https://github.com/vllm-project/vllm-ascend/pull/23442)中，一个 Device rank 完成 10.04 GiB 逻辑读取，Host 则是 50.55 GiB/rank，两组独立测试。整轮的计时从第一个 rank 发起首个 GET 到最后一个 rank 完成末次 GET。

| 目标 | 单批/分批预算 | 每 rank 调用数 | 整轮中位数 | 最大单次 GET |
| --- | ---: | ---: | ---: | ---: |
| Device | 单批 | 1 | 40.18 s | 40.30 s |
| Device | 256 MiB | 41 | 40.28 s | 1.39 s |
| Device | 512 MiB | 21 | 39.59 s | 2.51 s |
| Device | 1 GiB | 11 | 39.65 s | 4.74 s |
| Host | 单批 | 1 | 41.49 s | 41.84 s |
| Host | 256 MiB | 205 | 41.56 s | 0.52 s |

Device 用 256 MiB 分批后，最大单次调用约缩短 **29 倍**，整轮中位数反而多了 **0.10 秒**。更大的 512 MiB 批次在这组数据里只节约 0.69 秒整轮时间，却多用了 1.12 秒的最长单次调用预算。在没有额外竞争请求的这几轮里，选择 256 MiB 的收益主要是租约余量。不能拿这几轮最大值保证生产 P99，也不能把 Host 和 Device 两张独立测得的墙钟时间直接相加。

模型级重放另有三个长度点：16,384、131,072 和 1,047,552 输入 token。最大的请求从外部恢复 **1,047,424 token**，在本地计算 **128 token** 的尾段，输出 **1,024 token**。三个长度点的重放均无本地前缀命中。这里要分清：作者的模型测试树另带 [#23336 的 Resident DMA 改动](https://github.com/vllm-project/vllm-ascend/pull/23336)，这个 PR 已关闭且未合入；[#23442 所在提交的 HiSparse backend](https://github.com/vllm-project/vllm-ascend/blob/84894c1de06566d3571b0ada71f6760f0fa33cdd/vllm_ascend/hisparse/backend.py#L198) 有另一处显式 H2D 恢复逻辑。因此，不能从 #23336 未合入推断主线缺少 H2D，也不能把组合测试直接记为某个发布镜像已通过百万 token 验收。

## 3. 建模要有三块秒表

**第一块：单次操作的租约。** 设每个批次的显露时长为 `t_call`，服务关心的是各 rank、各批次的最慢调用能否在租约内完成。用 `调用总时长 / 调用次数` 代替最慢调用，会掩盖热 rank、拥塞和大 key。以 10 秒租约为例，1.39 秒是该受控测试中的样本最大值；在实际负载下，要按 size bucket 记录调用尾部、超时比例与重试流量。

**第二块：整个前缀恢复的关键路径。** 建模时把 Device Indexer、Host Source、后续搬运和等待分别记账，再用实际依赖关系求关键路径。对单个串行读取流，可以先估算 `数据量 / 有效带宽 + 批次数 × 固定开销`，但带宽项必须用同并发、同路径测得的口径。SDK 对照里的字节数是逻辑读负载，不是独占链路流量，也不是网络端口带宽。一个请求需要多个 rank 都到齐时，还得观察最慢 rank，而非所有 rank 的均值。

**第三块：用户首 token。** 客户端看到的是排队、缓存查找和恢复、未缓存尾段 prefill，以及首 token 生成和传输的关键路径。即便每次读取都在租约内，恢复也可能比本地重算更慢；如果恢复和计算能重叠，比较的则是两条路径各自显露的时间。本文证据解决的是第一块，并为第二块提供了 SDK 样本，**尚未回答第三块的性能盈亏**。

## 4. 下一轮测试怎么做

| 要回答的问题 | 最少要对比什么 |
| --- | --- |
| 同一批次预算能否扛住并发？ | 固定镜像与模型，扫并发和长度；分别看 Host/Device 的 P99、最大 key、-3106 错误、重试与完成率 |
| 外部命中到底省不省时间？ | 同请求顺序比较冷 prefill、强制外部恢复和本地热命中；同一时钟记录客户端 TTFT、恢复墙钟、排队及本地重算 token |
| 失败后能否正确完成？ | 清掉本地缓存、保留外部池，记录各 rank 状态；检查失败、重试或回退后 token/logprob 与参考运行的一致性 |
| 哪条链路值得升级？ | 对齐 Host Source/H2D 与 Device Indexer 的时间线，测它们各自因重叠而隐藏的部分，再看哪段决定客户端尾延迟 |

如果只能多加一个指标，我会在“命中率”旁加上 **外部命中且在首 token SLO 内正确完成的请求率**。把完全重算成功、外部恢复成功和外部恢复失败后回退分开统计，才能判断应该继续压低单次调用尾部、提高总读取带宽，还是对某些请求直接重算。

延伸阅读：[昇腾 KV 命中后的正确性检查](/LLMNews/2026/11/26/ascend-kv-hit-correctness-gates/) · [GPU 接 SSD：大模型场景与规格估算](/LLMNews/2026/11/24/gpu-ssd-llm-storage-sizing/)。
