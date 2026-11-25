---
layout: post
title: "混元 Hy4 vs Hy4 Flash：旗舰多花的钱买到了什么？从智能差距、推理架构到开放权重许可"
date: 2026-11-25T18:02:00+08:00
summary: "对照两款正式版权重与配置、腾讯同场评测和 Vals AI 独立评测。量化 Flash 在日常任务与长程智能上的取舍，拆解 KV Cache、LatentMoE 和 Engram，并细读 Tencent Hy License 1.0 的商用门槛。"
section: explainer
label: "模型架构与智能评测"
tags: [混元, 模型评测, MoE, 推理系统, 开放权重, 许可证]
demo: false
sources:
  - title: "腾讯混元：Hy4 正式版模型卡与规格"
    url: "https://huggingface.co/tencent/Hy4"
  - title: "腾讯混元：Hy4 Flash 模型卡、基座和任务评测"
    url: "https://huggingface.co/tencent/Hy4-flash"
  - title: "腾讯混元：Hy4 Flash 官方发布"
    url: "https://www.tencent.com/tencent-launches-hy4-flash-to-power-high-speed-cost-efficient-ai-deployment-for-everyday-workflows/"
  - title: "Vals AI：Vals Index 同一版榜单与方法"
    url: "https://www.vals.ai/benchmarks/vals_index"
  - title: "Vals AI：Hy4 测试记录"
    url: "https://www.vals.ai/models/tencent_hy4"
  - title: "Vals AI：Hy4 Flash 测试记录"
    url: "https://www.vals.ai/models/tencent_hy4-flash"
  - title: "vLLM：Hy4 Flash 部署配方"
    url: "https://recipes.vllm.ai/tencent/Hy4-flash"
  - title: "腾讯混元：Hy4 权重许可证"
    url: "https://github.com/Tencent-Hunyuan/Hy4/blob/main/LICENSE"
  - title: "腾讯混元：Hy4 Flash 权重许可证"
    url: "https://github.com/Tencent-Hunyuan/Hy4-flash/blob/main/LICENSE"
  - title: "腾讯云 TokenHub：中国站模型目录价"
    url: "https://cloud.tencent.com/product/tokenhub"
---

**Flash 可以当默认模型，但不应当成旗舰的无损低价版。** 两者在短代码题、文本理解和结构清晰的文档任务上差距可以很小；到了要连续调用工具、验证结果、在失败后换路径的任务，差距会迅速放大。最清楚的例子：腾讯基座评测里 MBPP-plus 仅差 **0.3 分**，但 Vals AI 的 Terminal-Bench 4.0 差 **24.24 个百分点**。同一个 Vals Index 榜单上，旗舰 **57.87%**、Flash **49.16%**；该评测记录的单测成本则为 **$1.72 对 $0.07**。真正值得部署的是按任务路由，让贵模型接住难样本，而不是为每个 token 都买旗舰。

这里的 Hy4 专指 **11 月 4 日发布、11 月 20 日开放权重的正式旗舰**，不指 Hy4 Preview；Flash 为 **11 月 16 日发布、11 月 18 日开放权重**的版本。两者均有指令版、官方 FP8 和预训练基座。[前篇六款模型对比]({{ '/2026/11/18/hunyuan-hy4-deepseek-glm-kimi/' | relative_url }})记录的是 11 月 18 日当时的权重可见状态，这次以正式权重与配置为准。

## 1. 智能差距：不是所有任务都差同样多

### 基座：容易生成像样的代码，和能稳定完成工程任务，是两回事

下表是[腾讯两款 Base 的同表 few-shot 结果](https://huggingface.co/tencent/Hy4-flash#pretrained-model-capability)。百分点差为 Hy4 − Flash。它测的是对应基座在指定提示和评分下的表现，不是聊天版、Agent 或带检索的生产成绩。

| 代表测试 | Shots | Hy4 Base | Flash Base | 差值 |
|---|---:|---:|---:|---:|
| MBPP-plus 短程序 | 3 | 74.0 | 73.7 | +0.3 |
| U-MATH | 5 | 71.6 | 69.8 | +1.8 |
| MMLU-Pro | 5 | 73.9 | 71.1 | +2.8 |
| SuperGPQA | 5 | 62.7 | 57.8 | +4.9 |
| MMMU-Pro（Standard，10 选项） | 4 | 59.6 | 52.0 | +7.6 |
| 中文 SimpleQA | 5 | 83.9 | 74.6 | +9.3 |
| SimpleQA | 5 | 57.2 | 37.5 | +19.7 |

**差额分布比均分有用。** Flash 保住了不少局部模式和题意清晰的推理能力，但闭卷事实问答和部分图文联合推理更容易露出差距。SimpleQA 的差距提示 Flash 在事实型任务更适合配检索、逐条核对证据；不能由此推出有检索时也差 19.7 点。腾讯内部代码与 Agent 验证集的 bits-per-byte 是 **0.185 对 0.198**（越低越好，Flash 高约 **7.0%**），说明即便短代码题接近，两者对这批序列的概率建模仍不同；内部数据未公开，且 BPB 不能换算成 Agent 成功率。腾讯也提示，基座偶尔不遵守 few-shot 的输出格式，可能影响个别分数。

### 指令版：长程终端、税务和法律长文的差距，比单次表格编辑明显

下表为[同一版 Vals Index 榜单](https://www.vals.ai/benchmarks/vals_index)及其[旗舰](https://www.vals.ai/models/tencent_hy4)、[Flash](https://www.vals.ai/models/tencent_hy4-flash)测试记录，取 11 月 21 日榜单口径，不混用首发稿里的历史分数。两个条目的默认 API 供应商说明不同，模型在各子测试也可能使用不同服务设定；这是第三方测到的产品级结果，不是同硬件、同权重精度、同推理预算的消融。

| 测试 | Hy4 | Flash | 差值 |
|---|---:|---:|---:|
| Vals Index（行业加权） | 57.87% | 49.16% | **+8.71 pp** |
| Terminal-Bench 4.0（终端任务） | 39.39% | 15.15% | **+24.24 pp** |
| Tax Agent Bench | 34.40% | 23.25% | +11.15 pp |
| Vibe Code Bench v1.1.1 | 68.88% | 61.58% | +7.30 pp |
| HLAB-Vals-1.1（长程法律交付） | 12.50% | 5.42% | +7.08 pp |
| Finance Agent v2.1 | 64.70% | 60.81% | +3.89 pp |
| Excel Modeling v1.1 | 66.18% | 62.97% | +3.21 pp |
| Legal Research Bench | 41.35% | 38.46% | +2.89 pp |

榜单同页记录：每个测试 **$1.72 / $0.07**，约 **24.6×** 成本差；时长 **51:31 / 16:59**，约 **3.0×**；tokens/test **17.49m / 9.26m**，约 **1.9×**。这些是 Vals 评测聚合口径，不能当作普通 API 请求的输出长度、单流 decode 速度或 GPU 性能。同榜单按金融、代码、法律、税务等权重汇总，也不是普适 IQ，多个小差值还受抽样误差影响。

为什么长程任务容易拉开？一个直观模型是：如果 10 个依赖步骤都必须成功，单步 95% 对 90% 在独立示意下会放大成 60% 对 35%。实际步骤并不独立，Agent 还能观察反馈、自我纠错，但这解释了为什么「短题会写」无法外推为「能改完仓库并处理构建失败」。旗舰对高价值任务的收益，应看**约束遵守、错误恢复、验收通过**，不要只评最后一段话。

### 腾讯自己同场测，也看到了长程终端差距

[Flash 模型卡附录原图](https://huggingface.co/tencent/Hy4-flash/blob/main/assets/benchmark.png)披露了两款指令版在同一套公开题上的结果。旗舰与 Flash 各用自己最高的可用思考档，不代表相同 token 预算。以下是几个差距有辨识度的项目：

| 腾讯同场测试 | Hy4 | Flash | 领先分值 |
|---|---:|---:|---:|
| Terminal-Bench 4.0（Claude Code harness） | 44.4 | 19.2 | +25.2 |
| ProgramBench（接近完成的评分口径） | 30.0 | 16.0 | +14.0 |
| DeepSWE v1.1（mini-SWE-agent） | 74.9 | 64.6 | +10.3 |
| OSWorld 2.1（Full，允许部分得分） | 78.9 | 68.1 | +10.8 |
| AutomationBench v1.0.6 | 56.2 | 52.2 | +4.0 |
| HLE-Full（可用工具） | 59.1 | 55.2 | +3.9 |
| MMMU-Pro（指令版） | 78.6 | 75.8 | +2.8 |

最有说服力的是 **Terminal-Bench 4.0 在腾讯与 Vals 两套系统中分别差 25.2 和 24.24 点**。绝对分数不一样，方向和量级相近；它们是**两个评测执行方**，却仍是**同一题集**，不算跨数据集的两次独立复现。腾讯内部办公也有反例：相对可控的 Markdown 协作 **57.7 / 56.9**，而要求保持原文结构、不引入旁损的 Word 编辑 **97.2 / 46.2**。因此连「办公」也不能统一走 Flash，关键是失败是否可低成本发现和修复。基座的 MMMU-Pro 差 7.6，指令版表中差 2.8，显示实际交付还取决于后训练与评测设定，不能在缺乏消融时把缩小的差距都算给蒸馏。

### 腾讯内部日常办公数据：Flash 胜 Preview，不胜正式旗舰

[腾讯 WorkIndex](https://huggingface.co/tencent/Hy4-flash#task-performance-and-cost)覆盖 PPT、文档、表格、音视频处理等 WorkBuddy 工作流：**正式 Hy4 51.4、Flash 42.1、Hy4 Preview 39.7**。所以「Flash 比 Hy4 更强」是把 Preview 和正式版混了；正确说法是 Flash 在这套任务上超过旧 Preview，仍低于现旗舰 **9.3 分**。腾讯正文报 Flash 平均每任务成本约为旗舰的 **1/20**；同卡成本图显示约 **¥5.7 / ¥0.2**，并标注 **24.5×**。官方文本与图的口径或舍入不完全等同，只宜描述为约二十倍量级的特定样本成本差，不能当价目表或 SLA。卡中另有 85 位内部用户、259 个任务的盲测：Flash 满意度 2.79/4、Haiku 5.5 为 2.81/4；这是不同对手、不同评分尺度，不用于推导 Hy4 与 Flash 的精确差值。

## 2. 架构：Flash 把模型预算花在了哪里？

| 项目 | Hy4 | Hy4 Flash |
|---|---|---|
| 参数 | 语言主干 770B，文本激活 49B；ViT 1.23B、DFly2 3.3B 另列 | 155.5B 主干（不含 Engram、ViT、DFly2），Engram 约 63.5B；文本激活 11.3B；ViT 0.43B、DFly2 0.85B |
| 层数 / 隐宽 | 78 / 6,144 | 42 / 3,072 |
| 专家 | 77 层 MoE，256 选 8 + 1 共享，专家中间维 2,048 | 41 层 MoE，512 选 16 + 1 共享；路由专家潜维 1,536，中间维 1,536 |
| 注意力 | Gated DSA + 跨层复用索引，MLA；稀疏评分选 Top-2,048 | 12 层 IndexPool 稀疏 + 30 层 512-token 滑窗；配置每 4 个 token 聚一组，最多选 512 组；主注意力仍最多读 2,048 token |
| 视觉 | 模型卡含文本、图像和视频理解；40 层 ViT | 首要接口描述为文本和图像输入；27 层 ViT。某部署是否启用视频，须按服务和 recipe 实测，不用产品的音视频工作流倒推原生端点能力 |
| 共性 | 1,048,576 token 上下文、4 路 iHC、120,832 词表；两者都用 DFly2 复用目标模型 KV 与索引做推测解码 | 同左 |

来源：[Hy4 规格与配置](https://huggingface.co/tencent/Hy4/blob/main/config.json)、[Flash 规格与配置](https://huggingface.co/tencent/Hy4-flash/blob/main/config.json)。Flash 首发新闻用 **224B / 12B**，开放权重模型卡用 **约 220B / 12B**；模型卡分项约为 219.8B（另有细小未单列组件和舍入），两处并未给出 4B 差值的完整对账，不用它推断删了哪些权重。旗舰的 770B 是剔除视觉、适配器与 drafter 的语言主干，不能直接与 Flash 220B 的含 Engram 口径相除后称作「纯计算缩小比」。

**LatentMoE：专家多了，矩阵反而小了。** 用三张门控 FFN 矩阵记每个 routed expert 为 `3 × 输入维 × 中间维`。仅算每 token 实际选择的路由专家，单层 Flash/旗舰是 `(16 × 1,536 × 1,536)/(8 × 6,144 × 2,048) = 37.5%`；再乘 41/77，整主干的这部分算子量约为 **20.0%**。这不是整个模型的 FLOPs：不含潜空间投影、shared expert、Attention、router、Engram 以及视觉。两者路由比例都是 **1/32**，也不能据此说 All-to-All 一样。在「每个 token-expert 独立发一份、无目的地去重、按所示维度交换」的示意中，Flash 每 token 每层扇出载荷的维度单位是 `16×1,536`，旗舰是 `8×6,144`，约一半；块大小、目的地合并、路由偏斜、EP 拓扑和投影放置才决定真实 P99 与线上字节数。

**Engram：把局部模式移到可查表的参数里。** Flash 在四个层位查询 2-gram、3-gram 的哈希 embedding。表容量大，不会在每个 token 上像 dense 层那样读完；约 63.5B 若按 BF16 存储就是约 **127 GB**。按四层、每层两组 768 维查表，不计映射及后续算子，原始向量约 **12 KiB/token**。如果表放主存，瓶颈可能转成 NUMA、随机 gather 和 GPU 传输，而不是主干矩阵算力；12 KiB 是逻辑向量大小，不是 PCIe 实测。哈希局部记忆也不等于外部事实检索，更不能由这两款模型的对比单独估算 Engram 的贡献。腾讯说还做了来自 Hy4 的蒸馏，以及以缩短输出为目标的 RL；厂商说的平均输出减半不等于每个任务必然缩短 50%，也无法把差距单独归因给某一项架构改动。

**混合注意力：1M 是可寻址长度，不是每层都具有 1M 的直接访问。** 旗舰每层用稀疏访问远程 token；Flash 把这种直接访问集中在 12 层，其余 30 层只看当前及前 511 个 token。跨层传播仍能把远处信息传下来，但长证据互相依赖、证据位置分散、误导项密集的输入，值得单测，不应从 1M 规格断言两者长文效果一致。

## 3. 推理系统：用权重文件和 KV 容量把账算开

### KV 的「约 1/6」从哪来？

只算 MLA 主 KV 的逻辑 payload：每 token、每层存 512 个 latent 与 64 个额外 RoPE 元素，假设 BF16，故 **1,152 B**。设长度为 `L`，不把 Top-2,048 误当作历史存储上限。

- Hy4：约 `78 × L × 1,152 B`。
- Flash：约 `[12 × L + 30 × min(L,512)] × 1,152 B`。假设后端对 SWA 真正回收窗口外页，稀疏层按 token 保留候选主 KV。
- **1,048,576 token**、单序列：约 **87.75 GiB / 13.52 GiB**，Flash 为 **15.4%（约 1/6.49）**；**2,048 token** 时比值是 **25.0%**，不宜把 1/6 套到短上下文。

这只是解释量级的估计，与腾讯宣称的 **约 1/6** 接近，并非复现厂商测量。未包含 indexer cache、压缩组状态、页表、FP8/量化 scale、对齐或不同 TP 后端的复制；IndexCache 的索引复用不等于主 KV 跨层共用。SWA 是否真的环形回收，决定容量公式能否兑现。decode 的 cache 读取量由被选槽位和实际 kernel 决定，也不能把容量比直接变成 HBM 带宽比或 TTFT 比。

### 四套权重的落盘大小

按四个 Hugging Face 公开目录汇总根目录 **.safetensors** 文件大小，不含模型卡、配置、tokenizer 或运行时分配；GB 为十进制。

| 指令版 | BF16 | FP8 |
|---|---:|---:|
| Hy4 | [1,548.93 GB，245 个分片](https://huggingface.co/tencent/Hy4/tree/main) | [786.31 GB，245 个分片](https://huggingface.co/tencent/Hy4-FP8/tree/main) |
| Flash | [440.52 GB，148 个分片](https://huggingface.co/tencent/Hy4-flash/tree/main) | [287.07 GB，148 个分片](https://huggingface.co/tencent/Hy4-flash-FP8/tree/main) |

因此 Flash 是旗舰约 **28.4% 的 BF16 文件、36.5% 的 FP8 文件**；FP8 口径下优势缩小，与 Flash Engram 仍保持非 FP8 等因素相符，不应把整个 FP8 文件当作每权重恰好 1 byte。两个 FP8 配置均有 128×128 权重块，但旗舰采用 compressed-tensors 配置，Flash 使用 e4m3 动态激活方案并有不转换模块；后端须按各自实现加载。只看容量，旗舰 FP8 文件已大于 8×80 GB；Flash 的 [vLLM 配方](https://recipes.vllm.ai/tencent/Hy4-flash)默认把 Engram 放 CPU RAM，因此下载大小也不是硬性的 GPU 驻留下限。还要分别查最大并发 KV、图执行工作区、视觉输入、EP 负载、主存带宽与各卡峰值。配方的启动长度示例也可能远短于 1M。

[腾讯称 Flash 超过 150 tokens/s](https://www.tencent.com/tencent-launches-hy4-flash-to-power-high-speed-cost-efficient-ai-deployment-for-everyday-workflows/)，口径对应 megakernel、4-bit 和 DFly 叠加的优化路径；公开文本未给出可复核的匹配并发、上下文长度和完整机器配置。不把它当官方 BF16/FP8 权重在任意节点上的吞吐，也不拿单流读数当卡均吞吐。上线压测应拆成 TTFT、TPOT、请求完成 P95、每轮平均接受的 draft token、有效请求吞吐、单位合格任务的 GPU 秒与成本。压测至少覆盖短问答、长前缀、工具串行及读图，区分冷缓存、热缓存和升档后的前缀重建。

## 4. 怎样部署才真省钱：按合格交付定价

[TokenHub 广州刊例价](https://cloud.tencent.com/product/tokenhub)，按每百万 tokens（不含限时折扣）：

| 计费项 | Hy4 | Flash | 旗舰价 / Flash 价 |
|---|---:|---:|---:|
| 未命中输入 | ¥6 | ¥0.5 | 12× |
| 输出 | ¥18 | ¥2 | 9× |
| 命中缓存输入 | ¥0.30 | ¥0.02 | 15× |

任务价还随输出、迭代轮数、工具外部费用、失败重试、人工审核和重建缓存变化。例如 **100K 输入、10K 输出、未命中缓存**，只算 token：旗舰 **¥0.78**，Flash **¥0.07**。若所有任务先用 Flash、20% 不合格再完整跑旗舰，期望模型账单是 **¥0.226/任务**，比直接用旗舰省约 **71%**；对升档样本会额外付一次 Flash 的延迟。这个例子假定费用固定且不含工具、并发、人工、前缀复用；**不能把 20% 当作实测回退率**。质量验收是否可靠，比这个成本比更重要。

推荐路由：

- **Flash 直出**：有明确模板的摘要、文档整理、初版 PPT、短代码助手、可检索并核证的问答。用格式、执行器或原文引用做廉价验收。
- **Flash → Hy4**：表格与财务推演、跨文档比对、长文 Agent。报表公式有冲突、引用无法对齐、工具反复出错或没有通过自动验证时升档。交给旗舰的是必要原材料与验证记录，不把失败答案当先验事实。
- **Hy4 起跑**：跨模块代码修改、难以定义廉价验收的高价值长程任务、一次失败就带来高额人工或风险的场景。金融、税务和法律等仍由人复核；榜单差距不是专业背书。

做生产 A/B 时用同一批任务、同一工具、同一输入、同一策略档位，配对记录成功、升档、误放行和 P95，并画两条曲线：在同质量门槛下的合格任务成本，以及在同成本预算下的合格交付率。不能用榜单总体准确率推算「Flash 失败的那批，旗舰一定能救回多少」；应直接测这个条件成功率。

## 5. Tencent Hy License 1.0：可商用，但有两个容易踩错的阈值

我逐字比对了 [Hy4 LICENSE](https://github.com/Tencent-Hunyuan/Hy4/blob/main/LICENSE) 和 [Hy4 Flash LICENSE](https://github.com/Tencent-Hunyuan/Hy4-flash/blob/main/LICENSE)，两个官方 GitHub 文件内容相同。它以 Apache 2.0 为底稿，但新增第 10 节；因此适宜叫 **开放权重、带大型 MaaS 附加条款**。不能把 [Hy4 Preview 的 Apache 2.0](https://github.com/Tencent-Hunyuan/Hy4-preview/blob/main/LICENSE)外推给这两款。以下是原文解读，不替代个案法律意见。

| 场景 | 怎么读条款 |
|---|---|
| 自部署，内部研发、推理、微调 | 第 10.3 节豁免 10.2，但要**仅作内部用途**，且原作品、衍生作品及其输出均未向第三方提供。对外发报告或生成物时不能直接援引这项内部例外；这也不自动等于需要另签，仍应看是否落入 MaaS 等条件。 |
| 嵌入产品 | 只在具体功能或工作流里提供能力，终端用户不能获得通用模型访问，是第 10.1 节列的 MaaS 排除情形。单纯转发给独立运营的第三方模型服务也被排除；若自己托管并对外开放通用推理/微调，不能借「代理」名称套这项排除。 |
| 自营通用 API / 远程微调 | 向第三方提供远程推理或微调、让其提交输入或设定参数/训练数据，属于第 10.1 节所述 MaaS 范围。若你运营 MaaS 业务且命中下列**任一**门槛，依据第 10.2 节，使用或继续使用前要取得腾讯单独书面许可，邮件也可以。 |
| 镜像、交付量化权重、分发微调模型 | 第 4 节要求随附许可、显著标注改动、保留适用的著作权/专利/商标/归属信息，以及存在时附适用的 NOTICE。可以给自己的修改设条款，但不能移除、限制或与第 10 节冲突；下游也继续受它约束。第 6 节并不授权用腾讯商标给产品背书。 |
| 蒸馏和合成数据 | 第 1 节明确把微调、量化、蒸馏、合并、剪枝等改出的模型权重列入衍生作品。**没有一条把所有模型输出一概禁止商用或禁止拿来训练**；但「从零训练另一模型，只用 Hy4 API 输出来做教师数据」是否属于衍生权重，原文未给出清楚分界。产品发布前让法务核对，必要时索取书面澄清，同时核对 API 平台自己的服务协议；不能直接套自托管权重的条款。 |

两个**或**门槛：

1. **任意连续 12 个月，全球累计总收入超过 5,000 万美元或等值币种。** 算的是收入，不是利润；不要求这笔收入来自 Hy4。许可中 Legal Entity 含控制、受控制、共同控制的实体，不能默认只看签约的一个子公司，也不要按单一自然年算。
2. **拟使用模型的产品或服务，在任何自然月超过 1 亿月活。** 看产品或服务口径，不是只数 Hy4 功能的调用人数。两项均写的是「超过」，不是「大于等于」，但不要在采购决策里只靠卡阈值。

最典型的误判是「我们的 API 还没挣钱，所以不用另签」：若运营 MaaS 的法律实体已命中集团层面收入阈值，和这款 API 自身营收为零并不矛盾。另一个是「我们有一亿月活，所以任何自用必然要签」：第 10 节还要先看 MaaS 范围、专用功能排除及纯内部使用的条件。签约或二次分发前留存实际下载版本的 LICENSE，并由合规团队核查集团边界、用户定义和上线形态。

## 结论

这两款模型最有价值的差异在于**长程高难任务要用多少预算才能交付**。Flash 用更薄的主干、潜空间专家、局部查表和滑窗，把日常任务做到了可大量调用的价位；旗舰更值得保留给错误可累积、需要全局证据或必须自我纠错的工作。工程上用任务级合格率来选路由，采购上则先看权重的部署边界，再看是否属于许可证定义中的 MaaS。这三件事分别需要评测、容量模型和许可证原文，不能由一个总榜、一个激活参数数值或一句「已开源」代替。
