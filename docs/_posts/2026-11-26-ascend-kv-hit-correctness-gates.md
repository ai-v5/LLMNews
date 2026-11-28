---
layout: post
title: "KV 明明命中了，为什么模型还会答错？vLLM-Ascend 的三道正确性闸门"
date: 2026-11-26T05:30:00+08:00
last_modified_at: "2026-11-26"
summary: "从 AscendStore 的分组前缀恢复、Mooncake 的 PP 分段重排，到 PCP 下的滑窗回放，拆解三个独立修复，给出把有效命中与正确结果一起计入 goodput 的验收表。"
section: explainer
label: "推理系统与缓存正确性"
tags: [vLLM-Ascend, AscendStore, Mooncake, KV缓存, PCP, PD分离]
demo: false
sources:
  - title: "vLLM-Ascend #21167：AscendStore 细粒度前缀恢复"
    url: "https://github.com/vllm-project/vllm-ascend/pull/21167"
  - title: "vLLM-Ascend #18476：Mooncake 缓存组选择与 PP 重排"
    url: "https://github.com/vllm-project/vllm-ascend/pull/18476"
  - title: "vLLM-Ascend #22453：PCP 下的前缀命中回放"
    url: "https://github.com/vllm-project/vllm-ascend/pull/22453"
  - title: "PCP 的独立 A2 复验与 padding 说明"
    url: "https://github.com/vllm-project/vllm-ascend/pull/22453#issuecomment-7011095432"
---

一个缓存系统可以报告命中，连接器可以收到字节，HTTP 也可以返回 200，模型却可能给出错误答案，甚至一个有效 token 都没生成。**命中只是找到了候选，正确复用还需要三个条件：恢复的是同一段前缀，恢复到接收端可读的布局，再按正确的并行计划消费。**

截至北京时间 **11 月 26 日 05:30**，过去 24 小时内，vLLM-Ascend 有三项独立变更进入主干，分别说明这三个条件为何不能互相替代。它们来自不同模型、拓扑和实验，不是同一套配置的联合验证，也不能据此判断某个既有稳定版已全部包含修复。

| 北京时间 11 月 25 日 | 主干变更 | 确认的合入提交 |
| --- | --- | --- |
| 20:31:16 | AscendStore 细粒度前缀恢复 | [`a5df188`](https://github.com/vllm-project/vllm-ascend/commit/a5df1888be2e244e2178cef76c67859cdd9d4c8a) |
| 21:26:22 | Mooncake 缓存组选取与 PP 重排 | [`c19e26d`](https://github.com/vllm-project/vllm-ascend/commit/c19e26d320566fb0a2f204da8c2fc8ba38dd0e8c) |
| 21:40:02 | PCP 滑窗前缀回放 | [`0f63cfa`](https://github.com/vllm-project/vllm-ascend/commit/0f63cfa1a52225f301ffd4a335b8daa3028c283f) |

此前的[连续前缀 offload 解读]({{ '/2026/11/23/vllm-kv-contiguous-prefix-offload/' | relative_url }})关注怎样**留下更多可复用的连续前缀**；这次关注找到前缀后，怎样证明它**能被后续计算正确使用**。

## 第一关：逻辑命中位置，不等于物理页，也不等于每种状态都能从这里恢复

对同时具有 Attention 与 Mamba 类递归状态的模型，Attention 可以从物理页读取覆盖某段逻辑前缀的 K/V，递归状态却还需要正确的检查点。不能因为 Attention 命中较长前缀，就让整个请求从那里继续：另一组状态可能只在更早的位置可恢复。

[AscendStore #21167](https://github.com/vllm-project/vllm-ascend/pull/21167) 的 bulk 路径使用精确存储哈希键，借助 Core 的缓存管理器找各组共同可恢复的前缀，并把本地 HBM 已命中的前缀和推测回放纳入判断。加载路径带上各组末端 key：Attention 恢复物理页，Mamba 恢复精确检查点；为避免保存期间状态被提前释放，检查点块在 bulk save 完成前保持固定。对需要 EAGLE 回放的角色，Mamba 各组服从调度器共有的检查点边界。

因此，`--prefix-match-unit 64` 的 **64 是逻辑匹配粒度，不是每次传输恰好 64 token**。能匹配到页内位置，不等于物理页被切小，也不保证任意位置都有递归状态可用。

| Qwen3.5-35B-A3B；MRv2、MTP、APC；PMU=64 | 已验证的 HBM-only / external-only 恢复位置 | 双路径 64-token 续写 | 与 cold 精确一致的位置 |
| --- | --- | --- | --- |
| Memcache bulk、Mooncake bulk；混合部署 TP2/DP1 | 均为 2,112 / 2,176 / 2,240 | 三档均相同 | 2,176 / 2,240 |
| Memcache bulk、Mooncake bulk；P/D 每角色 TP2/DP1 | 均为 2,112 / 2,176 / 2,240 | 三档均相同 | 2,112 |

这是作者报告的指定请求检查。**两种缓存恢复彼此一致，不等于每个位置与 cold 逐 token 一致。** Mooncake 的公开 GPQA 跑测没有缓存命中，不能拿分数论证复用后的质量。未设置 PMU 时，Mooncake P/D 样本还在 HIXL 初始化阶段停止，不能补成一个可对照的固定粒度 P/D 数字。

## 第二关：收到的字节，不等于 Decode 已经按自己的布局读到了它

当 P（prefill）和 D（decode）使用不同 KV-head 分片，接收字节可能还处在传输布局，需要重新排列。[Mooncake #18476](https://github.com/vllm-project/vllm-ascend/pull/18476) 修了两处相互独立的接收端问题：

- **选对组。** 用已注册传输组的名字和索引，与本次层集合求交；不能只解析层号，不然单张量的 index cache 可能混到双张量 K/V 组，重编号的 draft cache 也可能被漏掉。
- **收齐段。** 同一请求、同一 CP 分片下，不同 P 的 PP stage 分别贡献不同层。旧代码覆盖待重排描述符，可能只留下最后一段；新代码在锁内累积，仍等全部拉取完成，再消费一次并保留失败清理。HTTP 成功因此不能替代验证：字节到了，但部分层没有重排，输出仍可能错。

公开复现是 **P TP4/PP4 → D TP2/PP1**，D 侧 DP16。**PP4→PP1 本身并不必然触发 KV-head 重排**；这里 TP/head 布局不同。作者 11 月 18 日的单次 A3 功能验证中，只修组选择时 12/20 请求正确，再加分段累积后 20/20 正确；冷缓存 P/D 和本地 prefill 配对检查 4/4 正确。11 月 25 日 rebase 后有 34 项定向 CPU 回归（含 PP4 的 24 种登记顺序），不是新跑了 NPU 性能。小样本回答的是“这类错误能否被抓住”，不是“线上的好请求率提高 40 个百分点”。

## 第三关：恢复正确页后，还要让各 PCP rank 执行同一个合法回放计划

DeepSeek-V4.1-Flash 的滑窗有界回放只重新执行部分历史。作者发现，启用 prefix cache 与 `--swa-bounded-replay` 后，PCP（prefill 上下文并行）大于 1 的某些 warm hit 只返回 EOS。冷请求和 PCP1 的同类条件不触发这条故障。[PCP #22453](https://github.com/vllm-project/vllm-ascend/pull/22453)。

根因不是“窗口太小”，而是**把全局留存 128 行与 rank 本地 padded 宽度约 30 行相比较**。二者所属范围不同。这个判断把 PCP8 的 hit 错误排除在紧凑回放之外，随后中段使用的是普通路径上的回放边界。最终修复对已有缓存、且确实需要裁剪的请求按全局条件选择紧凑回放；对冷请求，仍只在确实能省行的条件下采用这一路径。所有 rank 使用同一全局决策，而不是各自按局部宽度决定。

| 硬件验证 | 结果 | 边界 |
| --- | --- | --- |
| 作者：16×910B2C，TP1/DP2/PCP8/EP16 | 8K warm hit 不再 EOS，找回预期内容但标点异于 cold；32K warm 的 token ID 与 cold 一致 | 服务器设 1M 不等于测过 1M 输入，也没有吞吐结论 |
| 独立 reviewer：8×910B3，单引擎 PCP8/EP8，W4A8，15,092-token 定向请求 | 两次 warm hit 从 2/2 EOS-only 变 0/2；前后 cold ID 相同 | warm 不是每次都与 cold 逐 token 一致；单引擎排除 DP 改道混杂 |

**正确性修复也不等于零性能代价。** 现有 PCP 紧凑回放会将每 rank 补到全局保留宽度；reviewer 的示例中，中段 21–39 层从旧错路径约 30 行/rank 变为约 128 行/rank。这约 4.27× 只是该例的 nominal 形状变化，既不是有效 FLOPs 比，也不是整步或端到端时延比。候选优化是让 rank 对齐到其本地保留行数的全局最大值，而不是全局行数之和，但必须一起测新 collective、图形状适配和位置映射成本；这并未在本次合入实现。[reviewer 的范围说明](https://github.com/vllm-project/vllm-ascend/pull/22453#issuecomment-7011095432)。

## 上线时怎样验收：先过正确性，再把命中算进 goodput

这不是三条 PR 的联合基准。它们提示的上线方案是把实验沿数据生命周期拆开，**每次只改一个变量**，同时在每个模式保留同样的请求分母。

| 验收对象 | 建议做的对照 | 必须留的证据 |
| --- | --- | --- |
| 逻辑恢复 | 冷 / HBM-only / external-only；围绕 PMU 的 63/64/65 与物理页边界；MTP 开关分开 | 实际命中源、每组尾 key、共同恢复的 token 区间、递归检查点 |
| 布局交付 | 同 TP 与异 TP；多个合法 PP 到达次序；并发请求加 CP 分片 | 本次重排的组、层段与 shard，完成信号；可行时用规范布局的逐 rank checksum 对照 |
| 回放消费 | PCP1 与 PCP8；同一 warm 请求固定到实际缓存所在的引擎；逐个打开有界回放/MTP | 每 rank 的窗口位置、owner、有效/填充行数、原始 token ID、finish reason 与任务结果 |
| 端到端验收 | 固定模型权重、dtype、采样、输入/到达节奏、种子；支持时测确定性对照，否则测任务判据 | 每种模式的总尝试、验证命中、有效、无效和超时数；EOS-only 不能算作成功 |

建议主指标用 **合格请求 goodput = 内容正确且满足预设 TTFT/端到端时延 SLO 的请求数 ÷ 同一墙钟窗口**。把有效请求的 p95/p99 与全量请求的无效、错误和超时数一起展示，不能先过滤错误，再把剩下的低延迟说成服务能力。命中率、搬运字节和 HTTP 成功率仍值得记录，但分别只证明候选、传输和协议响应。

三道闸门的顺序可以直接进日志：**命中候选 → 同一逻辑前缀 → 可消费的目的布局 → 各 rank 一致回放 → 正确结果**。上一步的成功不是下一步的证据；把这几个状态分开，才知道慢在哪里、错在哪里，以及一次“命中”究竟值多少。
