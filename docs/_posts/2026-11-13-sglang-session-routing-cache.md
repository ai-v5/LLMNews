---
title: "会话落在同一台引擎，为何仍然丢缓存？SGLang 的 DP 粘性路由提案"
date: 2026-11-13T05:33:00+08:00
summary: "从一个尚未合入的调度补丁，看多轮推理的真正局部性边界：引擎不等于缓存域，命中率也不等于用户延迟。"
section: explainer
label: "推理系统解读"
tags: [SGLang, 推理, PrefixCache, 调度, 数据并行]
demo: false
sources:
  - title: "SGLang PR #50180"
    url: "https://github.com/sgl-project/sglang/pull/50180"
  - title: "所分析版本的 DP controller"
    url: "https://github.com/sgl-project/sglang/blob/419c827ef355eee022f34b843ded0e498d096e1c/python/sglang/srt/managers/data_parallel_controller.py"
  - title: "对应版本单元测试"
    url: "https://github.com/sgl-project/sglang/blob/419c827ef355eee022f34b843ded0e498d096e1c/test/registered/unit/managers/test_data_parallel_controller.py"
---

## 先说结论：路由边界必须对齐缓存边界

多轮对话的上一轮历史已经算过，下轮请求却又把它算一遍，原因不一定是 KV cache 容量不够。还可能是：**请求被送到了同一引擎内的另一个缓存域。**

11 月 12 日公开的 SGLang [PR #50180](https://github.com/sgl-project/sglang/pull/50180) 提议在 DP controller 内增加按会话 key 保持 rank 亲和性的策略。本文分析的是提案，不是已发布功能；它没有改变模型、Attention 算法或卡间通信。它的价值在于把调度对象从“这一条请求”向“会持续产生请求的一段会话”推进一步。

**资料范围与状态：**本次筛选窗口为 UTC 2026-11-11 21:33 至 2026-11-12 21:33。PR 创建于 UTC 11 月 12 日 20:33:15，最后一次元数据更新为 21:07:30；下文对应 head `419c827ef355eee022f34b843ded0e498d096e1c`。发布前复核时仍 open、未合入。本文未自行复现实机实验。

## 一、两层路由之间的“局部性断点”

考虑这样的部署：

```text
多轮会话
   ↓ 入口按会话固定到引擎 A
引擎 A 的 DP controller
   ├─ DP rank 0：独立缓存域
   ├─ DP rank 1：独立缓存域
   └─ 其他 ranks
```

入口只知道“引擎 A”，而实际可复用的历史位于某个 rank。若内部继续逐请求轮转，入口的粘性承诺就没有一直传到缓存所在处。这是两层各自合理的决策，组合后却不合理。

这里的 rank 是 DP 调度与缓存的逻辑域，不应简单理解为“每个 rank 就是一张独立 GPU”。TP、DP attention 等配置共同决定实际执行拓扑。**对性能建模而言，应先画缓存驻留和请求分派关系，再画卡数。**

## 二、补丁真正做了什么，没做什么

提议的开关是 `--load-balance-method follow_routing_key`；OpenAI 接口通过 `X-SMG-Routing-Key` header 传入 key，`/generate` 使用请求体的 `routing_key`。

从固定版本的 [controller 代码](https://github.com/sgl-project/sglang/blob/419c827ef355eee022f34b843ded0e498d096e1c/python/sglang/srt/managers/data_parallel_controller.py#L915-L930) 可看到以下顺序：

1. 外部明确指定 DP rank 时，优先遵循外部路由。
2. 有 routing key 且已记录的 rank 仍活跃，就继续发往那里，同时更新请求预算。
3. 新 key 或旧 rank 不再活跃时，按请求数负载重新选择。
4. 不带 key 的请求走请求数策略，不建立映射。

映射表容量为 65,536，存 key 的哈希，命中时更新最近使用次序。它不是一个 KV 搬运机制，也不是跨 rank 的全局缓存索引。记录被淘汰或 rank 失效后，重新分派可能损失缓存局部性，但请求不必因此失去执行路径。

一个很重要的细节是：**已有会话保持亲和性时，不再用当下负载推翻分配。**对应 [测试](https://github.com/sgl-project/sglang/blob/419c827ef355eee022f34b843ded0e498d096e1c/test/registered/unit/managers/test_data_parallel_controller.py) 明确覆盖了“该 rank 已经最忙仍然留在原 rank”的行为。因此这不是“缓存和负载兼得”的最优调度器，而是一条清晰、可解释的优先级规则。

## 三、作者实验说明了什么

[PR 实验说明](https://github.com/sgl-project/sglang/pull/50180) 使用四张 H200、Qwen3.6-35B-A3B-FP8、TP4/DP4 与 DP attention。64 个并发会话各做八轮；共享系统提示为 300 个词，每轮新增 220 个词，生成 64 tokens 的贪心回复并追加历史。以下为作者报告，非本站实测：

| 策略 | 第 2–8 轮 prompt token 缓存命中占比 | 整段运行耗时 |
|---|---:|---:|
| 轮转 | 54.1% | 43.8 秒 |
| 按请求数 | 52.4% | 51.9 秒 |
| 会话 key 亲和 | 83.6% | 34.5 秒 |

相对轮转，总耗时减少约 21.2%；等价的运行速率比约 1.27 倍。这里不是每个请求延迟都降低 21.2%，也不是 GPU 算力提高 27%。缺少重复实验分布、尾延迟与不同会话长度组合，不能外推为普遍收益。

## 四、为什么“命中更多”不保证“响应更快”

以下是分析模型，不是该 PR 给出的公式。对同一请求，比较两条路径：

- 留在原 rank：排队时间 + 使用已有前缀后的剩余计算。
- 去较空 rank：较短排队时间 + 缓存未命中带来的重算。

可以用一个决策不等式表达：

```text
留在原 rank 值得 ⇔ 节省的重算时间 > 额外排队时间
```

若系统支持跨域搬运 KV，还要在右侧或替代路径加入传输、格式转换与同步开销。此提案不做这些搬运，不能把高速互联带来的潜在能力算成已经实现的收益。

这也解释了为什么按“请求数最少”不一定表现最好：一个带很长历史的未命中请求，可能比几个短请求昂贵得多。请求数只是成本代理变量；token 数也不是完美代理，因为命中前缀与新增 token 的代价不同。

反过来，会话亲和也有失败场景：少数长会话持续产生高负载、某些 rank 的缓存被其他任务挤掉、会话停顿很久后恢复，或者映射还在但缓存已经不在。**“路由记得会话”与“缓存仍然保存历史”是两个不同的状态。**

## 五、工程上的下一步，不只是换一个默认参数

面向多轮 Agent 和长上下文服务，建议用下面的矩阵复核，而不是只跑统一长度的聊天循环：

| 维度 | 应观察的信号 |
|---|---|
| 短长会话混合、热点会话 | rank 间队列差异、p95/p99 首 token 延迟 |
| 不同 KV 容量与淘汰压力 | 映射命中但 prefix cache 未命中的比例 |
| 会话暂停、rank 故障与重启 | 重分派后的恢复代价，是否出现突发重算 |
| 连续批处理与混合输出长度 | 总吞吐和单会话响应是否同时改善 |
| 与 DP-aware 网关组合 | 两层路由是否一致，显式 rank 覆盖是否符合预期 |

从架构上看，更进一步的策略可以把亲和作为偏好而非绝对约束：只在原 rank 的额外等待超过估计重算代价时迁移。这是本文提出的后续方向，**不是现有补丁已实现的功能**。它需要可信的缓存驻留信号、队列估计和稳定的成本模型；复杂度本身也有维护与正确性成本。

## 六、CI 红灯的具体含义

不能只看 PR 描述里的红叉就断言代码测试失败。对当前 head 核查 [Base](https://github.com/sgl-project/sglang/actions/runs/43306943535)、[Extra](https://github.com/sgl-project/sglang/actions/runs/43306943135) 和 [AMD](https://github.com/sgl-project/sglang/actions/runs/43306943230) 工作流后，失败位置是 gate 的 `Require run-ci label (optional)`，后续主要测试被跳过，汇总任务随之失败。

这意味着当前公开 CI **不能提供完整通过证据**，但也不是已证明该调度逻辑在 GPU 测试中出错。作者报告的本地单元测试通过和公开 CI 的未执行状态应分别记录。性能表也没有明确绑定最终 force-push 后的精确 head，因此本文只将其当作作者对提案的实验报告，不作为最终提交的独立性能认证。

## 最后的判断

这个小补丁最值得带走的不是“快了多少”，而是一个部署审查问题：**我的入口路由、内部调度与 KV 缓存，是否使用同一个局部性边界？**

对 GPU 与 NPU 推理系统，这个问题都成立；但本次公开实验只涉及 H200，不能据此宣称昇腾上的收益或适配已经验证。先确认状态驻留在哪里，再决定如何调度，往往比先讨论卡间带宽或再加一层缓存更接近实际瓶颈。
