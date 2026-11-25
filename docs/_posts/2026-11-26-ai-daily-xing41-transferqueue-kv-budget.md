---
layout: post
title: "AI 日报：星辰 4.1 补齐原生权重，TransferQueue 改写控制面，GB200 基准重测 KV 容量"
date: 2026-11-26T05:31:00+08:00
summary: "Xing4.1-Preview 新增 MindSpore 原生权重；TransferQueue 合入可选 Rust 控制器；InferenceX 排除额外主机 DRAM 后重测 MiniMax；昇腾尝试细粒度 TP；百炼发布决策模型，Claude Code 接入远程 Skills。"
section: daily
label: "AI 动态"
tags: [星辰, 昇腾, TransferQueue, GB200, KV Cache, 智能体]
demo: false
sources:
  - title: "Xing4.1-Preview：MindSpore 原生权重提交"
    url: "https://huggingface.co/XingChen-AGI/Xing4.1-Preview-MindSpore/tree/3cea0634dc6e8509ddb4ab6182245280ba104ebb"
  - title: "FlagOS：Xing4.1-Preview 多芯片适配"
    url: "https://flagos.csdn.net/6b064e4040858c2d881db546.html"
  - title: "TransferQueue #223：可选 Rust 控制器"
    url: "https://github.com/Ascend/TransferQueue/pull/223"
  - title: "InferenceX #5226：移除额外 DRAM 并重测"
    url: "https://github.com/SemiAnalysisAI/InferenceX/pull/5226"
  - title: "vLLM-Ascend #21624：Kimi 细粒度 TP"
    url: "https://github.com/vllm-project/vllm-ascend/pull/21624"
  - title: "阿里云百炼：11 月 25 日北京地域模型发布记录"
    url: "https://help.aliyun.com/en/model-studio/newly-released-models"
  - title: "Claude Code v2.1.332 发布记录"
    url: "https://github.com/anthropics/claude-code/releases/tag/v2.1.332"
---

资料核验截至北京时间 **2026 年 11 月 26 日 05:31**，覆盖此前 24 小时的公开发布与上游合入。下文时间均为北京时间；厂商只给发布日期的条目不补具体时刻。源码合入不等于已进入稳定包，原作者测试与基准记录也不等于本刊复测。

## 1. Xing4.1-Preview 补齐 MindSpore 原生权重，适配测试暴露首 token 权衡

**11 月 25 日 09:13，官方模型仓库出现首个带权重的可见提交。** 该[固定修订](https://huggingface.co/XingChen-AGI/Xing4.1-Preview-MindSpore/tree/3cea0634dc6e8509ddb4ab6182245280ba104ebb)列出 **128 个 safetensors 分片，合计约 573.19 GB（533.82 GiB）**。此前可见修订没有这些分片，故新进展是原生格式文件上架，不是重报 11 月 23 日的权重公告，也不代表同时公开了恢复原训练所需的全量优化器、数据和运行时状态。

同日 [FlagOS 适配报告](https://flagos.csdn.net/6b064e4040858c2d881db546.html)给出一个可比较的例子：同为 8 卡 NVIDIA、vLLM 0.24.0、W8A8、并发 64、1K 输出，输入 4K/16K/32K 时，报告的输出吞吐提升 **6.8%/4.1%/1.7%**，平均每输出 token 时间下降 **8.6%/18.7%/20.9%**，但平均首 token 时间上升 **11.8%/21.5%/6.0%**。这是同一硬件下的整栈对照，不是某个融合算子的单项收益；其他适配使用的框架与权重精度也不完全一致。

**为什么关注：** 模型文件、可恢复训练状态与可交付推理服务是三种产物。服务侧应联合卡首 token 和逐 token 延迟门槛，不能从单项均值或跨芯片归一图直接推导有效吞吐、MFU 或成本。

## 2. TransferQueue 合入 Rust 控制器，同一队列先看元数据尾延迟

**11 月 25 日 10:44，[TransferQueue #223](https://github.com/Ascend/TransferQueue/pull/223)合入。** 新后端可选，Python 仍是默认。作者在单台主机上用 128 条 TCP ZMQ 连接、4,096 条活跃样本，控制器固定在 4 个物理核。索引跨度为 4,096 时，闭环元数据请求率 **1,917→65,819 RPC/s**；跨度为 262,144、活跃样本不变时，**158→66,786 RPC/s**。

另一个定速到达测试包含客户端排队。在稀疏索引配置下，满足 **计划到达至完成 P99 ≤25 ms** 且确认窗口无丢弃、错误或超时的最高试验速率是 **90→64,000 RPC/s**。这是特定元数据负载、索引与实现一起变动的结果，不能把提升全归因于 Rust，也不能等同于样本吞吐、GPU 通信带宽或训练加速。核验时 [最新稳定 Release](https://github.com/Ascend/TransferQueue/releases/tag/v0.1.12)仍为 v0.1.12。

**为什么关注：** 高并发 rollout 应分别测控制面 RPC 的排队、轨迹数据面的字节量，以及 learner 真正消费的样本数。只有知道每个有效样本组触发多少次请求，控制面的容量数字才能转化为系统预算。

## 3. InferenceX 重测 GB200：平均吞吐少变，首 token 尾部拉长

**截至 11 月 25 日 12:45，[重测](https://github.com/SemiAnalysisAI/InferenceX/actions/runs/45490780339)已标记成功；12:50，[配方修订 #5226](https://github.com/SemiAnalysisAI/InferenceX/pull/5226)合入。** 原 MiniMax-M3.1-Flash FP4 的 GB200 Dynamo-SGLang 分离式配方，在无推理 worker 的基础设施节点额外部署了 **600 GB** Mooncake KV 存储，不符合该项目的资源计入口径。调整后重新跑了五个分离式点。以下旧数据只作说明比较，不再是有效基准成绩。

五个配置匹配点中，平均 QPS 降 **0.46%–2.45%**，P95 TTFT 升 **12.42%–62.12%**。例如 2P、并发 480 的点，平均 QPS **21.95→21.61**，P95 TTFT **2.73→4.43 秒**。配方差异有记录，但不能保证两次运行的请求到达、机器和系统条件逐项相同，因此不把差值当成 DRAM 容量的因果曲线。[#1860 回填修订](https://github.com/SemiAnalysisAI/InferenceX-app/pull/1860)把重测标为追加回填，以保留九个未受影响的聚合式点，不应把它们也列作无效。

**为什么关注：** 外部 KV 池的容量、部署位置及是否计费，会影响一张图上哪些点过延迟门槛。如果门槛是 **每配置 P95 TTFT ≤4 秒**，2P 并发 480 从旧记录的达标变成重测不达标；这只是对配置分位数的判定，不是逐请求 goodput。

## 4. 昇腾 Kimi 细粒度 TP：权重走 DP 轴，KV 仍留在请求 owner

**11 月 25 日 21:24，[vLLM-Ascend #21624](https://github.com/vllm-project/vllm-ascend/pull/21624)合入。** 运行时可借 DP 轴分摊选定的 KDA 投影、共享专家等权重，卷积、递归状态和注意力/KV 仍留在请求 owner。分摊并不免费：需要交换输入、恢复投影分片和归约输出；被测布局的路由专家仍走独立的 EP64。Kimi 的 QKV/G 和共享专家路径要求原生 TP/PCP/DCP/PP 均为 1，并依赖分离式 decode 的图执行、重算调度及对应 offload 连接器。

作者按张量及量化 scale 计算，7 组目标权重在 localTP8 下由每卡 **64.862→8.108 GiB**，这是这些权重的分摊量，不是整模型缩小八倍。早期修订在八台 A5、64 NPU、等额 **33 GiB/卡** KV 预算、模拟 128K 前缀与 1,024 输出的 decode 测试中，对照为 DP8 TP8 DCP8，新配置为 DP64 TP1 localTP8：

| 客户端并发 | 对照→新配置：平均 TPOT | 对照→新配置：输出 tok/s |
|---:|---:|---:|
| 256 | 27.87→26.14 ms | 8,796→9,140 |
| 512 | 41.83→33.06 ms | 11,262→13,392 |

**为什么关注：** 用 **30 ms 平均 TPOT** 当门槛时，列出的两个点中，只有并发 256 在两组都达标；512 的吞吐差不是达标容量。这里同时改动 DP/TP/DCP，测试用合成投机接受长度和确定性路由，未验证完整 P→D 传输和真实任务质量，不宜将差异归因给 EP 或外推。

## 5. 阿里云百炼把分类、是非和评分做成独立决策入口

**11 月 25 日，北京地域[发布记录](https://help.aliyun.com/en/model-studio/newly-released-models)新增 `decision-model`。** [服务规格](https://help.aliyun.com/en/model-studio/decision-model-stable)描述为面向文本或图像的专用决策接口，可并行返回分类、是非或评分的概率与置信信息。这是专用结构化结果，并非通用生成接口的任意 JSON schema 输出，也不支持函数调用。上线记录的日期不等于所有地域同时上线。

**为什么关注：** 可将工单路由、轻量校验交给固定决策入口，把低置信度和高风险样本留给后续推理或人工。要不要替换通用 LLM，先在同一组真实决策上检查置信度校准、低置信度回退率和错误代价；可输出概率并不意味着概率已校准，也没有匹配的端到端提速证据。

## 6. Claude Code 把 MCP 服务端 Skills 接入 CLI，指南和授权仍是两回事

**11 月 25 日 09:32，[Claude Code v2.1.332](https://github.com/anthropics/claude-code/releases/tag/v2.1.332)发布。** 此版加入 MCP 服务端托管的 Skills（beta），在命令菜单用服务端名称区分；同时增加可拒绝技能或命令加载阶段内联 shell 指令的 `PreSkillShellCommand` hook。[Anthropic 的功能说明](https://claude.com/fr/resources/articles/skills-over-mcp-tasks-and-more)还区分了 Claude 的 Tasks、Elicitation 已普遍可用与文件上传后续推出，这些不是 CLI 此版全部新上线的功能。

**为什么关注：** 服务端开始提供工具的使用流程，客户端仍须单独决定哪些指南可信、哪些工具调用和外部写操作获得批准。将流程放进服务器可减少各客户端重复维护，但不等于这些流程获得了执行授权；工程上还应验证服务器版本变化、运行中等待用户以及权限拒绝后的状态恢复。

## 今日判断

今天最有价值的不是最大倍数，而是**资源账和验收口径**：把权重与请求状态的归属分开；把控制器 RPC 与训练样本分开；把计入的 DRAM 容量、平均吞吐和延迟达标点一起报告。另见今日[缓存命中的三道正确性闸门]({{ '/2026/11/26/ascend-kv-hit-correctness-gates/' | relative_url }})，补上只看吞吐容易漏掉的正确性验收。
