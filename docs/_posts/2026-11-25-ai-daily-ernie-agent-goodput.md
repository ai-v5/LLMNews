---
layout: post
title: "AI 日报：文心开放 280B 权重，Agent 评测别只看跑完的任务"
date: 2026-11-25T05:34:00+08:00
summary: "文心 5.5 Flash Preview 开放三种权重；MASSys 量化负载下的交付流失；两组实验拆开 PD 配比与稀疏索引带宽；Kimi 形状 MoE 算子给出同轮微基准；火山方舟部分旧模型到达下线节点。"
section: daily
label: "模型、推理与部署"
tags: [文心, 智能体, 推理系统, SLO, 稀疏注意力, MoE]
demo: false
sources:
  - title: "百度：ERNIE 5.5 Flash Preview 权重与许可"
    url: "https://huggingface.co/baidu/ERNIE-5.5-Flash-Preview"
  - title: "百度与 vLLM：11 月 24 日发布支持与技术说明"
    url: "https://vllm.ai/blog/2026-11-24-ernie-5-5-flash-preview"
  - title: "MASSys：论文 v1"
    url: "https://arxiv.org/html/2611.28671v1"
  - title: "SGLang 推理拆分对照：论文 v1"
    url: "https://arxiv.org/html/2611.29104v1#S5"
  - title: "IndexerStage：论文 v1"
    url: "https://arxiv.org/html/2611.28625v1"
  - title: "GC-MoE K3：论文 v1"
    url: "https://arxiv.org/html/2611.30542v1#S5"
  - title: "火山方舟：模型下线公告"
    url: "https://docs.volcengine.com/docs/ark/model-deprecation-notice?lang=zh"
---

**文心 5.5 Flash Preview 开放的是后训练权重，1M 上下文仍需单独做显存预算。** 今天几组推理系统实验也给出同一个提醒：看系统能交付多少任务，不能拿卡忙不忙、热门算子的加速比，或者已经跑完的任务分数代替。

覆盖 **北京时间 11 月 24 日 05:34 至 11 月 25 日 05:34**。论文以本窗口内的 arXiv 公告为准，作者提交日期可能更早；产品迁移按公告所列生效节点列入，不把旧公告当作新发布。

## 1. 文心 5.5 Flash Preview 开放 280B/14B 权重：支持 1M 不代表常见机型能跑满

**11 月 24 日。** [百度与 vLLM 的首日支持说明](https://vllm.ai/blog/2026-11-24-ernie-5-5-flash-preview)与[模型卡](https://huggingface.co/baidu/ERNIE-5.5-Flash-Preview)确认：此前先提供 API 的 Preview 现在有可下载权重，Preview 使用 Apache 2.0，早先的 Base 仍使用自己的许可。总参数 280B、每 token 激活 14B；默认包为 MXFP4 路由专家加其余 FP8，也有 FP8 与 BF16 包，均带 DSpark 草稿头。这仍是后训练过程中的预览版本。14B 是激活参数口径，不是装载权重的口径。

43 层里，37 层 HCA 每 128 token 压成一个历史条目并保留 128-token 滑窗，另外六层 MLA-DSA 从完整历史中选择 top-2048。用 1,048,576 token 做结构估算，忽略滑窗、索引与对齐，六层 DSA 占全部保留历史条目的约 95%；**这不是字节占比**，因为各层表示可能不同。更不能拿 2048 代替历史长度算显存。[官方部署代码](https://github.com/baidu/vLLM-ERNIE#serve)的四卡 Preview 示例设 128K；其 8×80 GB、FP8 示例称可到 256K、不能到 1M。做选型应分别核算权重、常驻 KV 与索引、长 prefill 的临时空间。

## 2. MASSys：同一套 Agent，压力上来后，评测分数和按时交付可以分叉

**11 月 24 日 arXiv 公告。** [MASSys v1](https://arxiv.org/html/2611.28671v1)用多 Agent 真实工作流重放，比较不同 serving 栈。在两张 H200 的三组配对种子上，总提交强度由 0.05 增至 0.10 作业/秒，五个后端在共同 **30 分钟到达窗口内**的完成比例平均下降约 **32–40 个百分点**。这是窗口内完成率，不是每个任务有 30 分钟的独立截止，更不能据此断定每小时完成数下降。

例子：一个 ResearchBench 种子里，Continuum/vLLM-Omni 产生可评分结果的任务从 22/22 变为 23/40；已评分任务的平均余弦分 0.777→0.785，看起来没坏，按所有提交折算则为 0.777→0.451。两组提交不是同一批任务，不能把差值解读成模型质量上升或下降；这说明只给幸存样本打分会漏掉交付流失。做 Agent 服务，应一起报提交数、按时可评分数、存活任务延迟和得分。把方法迁移到 Agentic RL 时，另统计真正进入训练的完整、合格且未过期的轨迹组，不把服务失败当成模型得了零奖励。

## 3. 同样四张卡，50% 忙和 99.7% 忙都能严重掉请求

**11 月 24 日 arXiv 公告。** [SGLang 五种架构对照](https://arxiv.org/html/2611.29104v1#S5)把 Qwen3-8B 放在同一台四卡 A100-40GB 主机，固定请求重放。在 32K 输入、32 token 输出上限、0.8 req/s 的压力点，固定 TP2 prefill + TP2 decode 失败率 **92.92%**，GPU 均值却只有 **50.1%**；统一 TP4 失败 **89.58%**，GPU 均值 **99.7%**、调度队列峰值 145。四个单卡副本的 P95 端到端是 **4.732 s**。换到 0.4 req/s，PP4 又把 P95 首 token 时间从单卡副本布局的 3.806 s 降至 1.554 s。

这不是 PD 分离孰优孰劣的普遍结论：小模型能装进单卡，且实验只测静态切分。可迁移的是诊断方法：看 prefill 和 decode 各自的队列是否持续增长，加上交接 KV 开销和同时满足两类时延目标的请求/秒，再决定是改配比、加并发副本还是减少并行通信。

## 4. IndexerStage：把索引挪出 HBM，会产生另一条逐步取数的带宽预算

**11 月 24 日 arXiv 公告。** [IndexerStage v1](https://arxiv.org/html/2611.28625v1)指出，DSA 选完 top-k 才只读取选中的 latent KV，但用于选位置的 Indexer-K 仍需扫描全部可见历史。原型按层串流已封页的 Indexer-K，用共享暂存区复用本地 HBM，而不是让所有层的历史索引同时常驻；调度器还检查链路能否逐层及时交付。

论文用 **16 张执行 H800 加 16 张作背板和搬运的 H800**，走 NVLink/NVSwitch，并非 SSD 实验。相对主机内存背板的 HiSparse，16K–64K 的静态 decode 吞吐为 1.08–1.14×；固定 latent-KV 背板路径后，64K 下扩大批次仍得 1.10×，而固定 batch 24 开串流的每输出 token 时间反增 2.42%。结论是：容量释放有价值，但需要批次收益覆盖逐层搬运成本。比较每卡吞吐或部署成本时必须算上背板 GPU，不能只数执行卡。这也不是文心所用 FlashIndexer 的同一项实现。

## 5. GC-MoE K3：把瓶颈拆到 GPU 内的角色，比直接套吞吐倍数更有用

**11 月 24 日 arXiv 公告。** [GC-MoE K3 v1](https://arxiv.org/html/2611.30542v1#S5)用 CUDA Green Contexts 将 dispatch 和专家计算划给不同 SM 分区，再用每 token 所需专家所属 rank 的就绪信号驱动收尾。GB200 上 24 个 EP8/16/32 的合成形状，完整 MoE FFN 子层对**同轮** SGLang-style 参考实现的时延比均值为 **1.1324×**；EP32 每 rank 两 token 时是 1.2222×，到 128 token 时只有 1.0413×。

这是单层 CUDA Graph 重放，指标为各 rank 中位时延的最大值，不是整模型 decode、真实路由偏斜或尾时延；论文提供的历史 vLLM 对照也不是同一软件环境。算子优化值不值得进生产，先量完整 decode 步有多少时间在这个子层，尤其是低并发和 rank 负载不均时。

## 6. 火山方舟部分旧模型到下线节点：推荐迁移和自动替换未必是同一 SKU

**11 月 24 日 14:00，北京时间。** [方舟第十批下线公告](https://docs.volcengine.com/docs/ark/model-deprecation-notice?lang=zh)列出服务下线生效节点。比如 `deepseek-v4-pro-260425` 的主动迁移推荐为 `deepseek-v4-1-flash-261017`，表中的自动替代却是 `deepseek-v4-1-flash-economy-261017`，仅适用于公告所述的可自动迁移接入点。直传旧模型 ID 的逻辑不能假定平台会重定向。另有个别 SKU 的下线日期不同；这是方舟平台特定版本的生命周期变化，不是 DeepSeek 全线下线，也没有实际调用过客户接入点来验证迁移。

**另读：** [Loop-PP 专题]({{ '/2026/11/25/loop-pp-recurrent-training/' | relative_url }})从训练侧拆解另一个容易读错的数字：共享权重为什么省显存，但循环仍会在流水线留下新的等待。
