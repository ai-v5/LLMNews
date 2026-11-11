---
title: "AlphaGenome 2：能预测更多细胞状态，怎样判断输出的证据等级"
date: 2026-11-12T05:39:00+08:00
summary: "AlphaGenome 2 把细胞条件变成显式输入，也把更多未测实验变成可预测的输出。真正使用它时，既要看指定基准上的提升，也要逐条检查输出是否有相应的训练观测与验证支持。"
section: explainer
label: "基因组 AI"
tags: [AlphaGenome, 单细胞, 科学AI, 模型评估]
demo: false
sources:
  - title: "Google DeepMind：AlphaGenome 2 官方公告"
    url: "https://deepmind.google/blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/"
  - title: "AlphaGenome 2 原始论文"
    url: "https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/alphagenome-2.pdf"
  - title: "官方指南：Navigating imputed tracks"
    url: "https://www.alphagenomedocs.com/user_guides/imputation.html"
  - title: "官方指南：Migrating from AlphaGenome 1"
    url: "https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/docs/source/user_guides/ag1_vs_ag2.md"
  - title: "官方教程：Choosing a condition"
    url: "https://www.alphagenomedocs.com/colabs/v2/choosing_a_condition.html"
  - title: "官方 FAQ"
    url: "https://www.alphagenomedocs.com/faqs.html"
  - title: "AlphaGenome 2 客户端源码与许可"
    url: "https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/README.md"
---

同一段 DNA，在不同细胞里可能发挥不同作用。研究一个变异时，除了问“改了哪个字母”，还要问“在哪种细胞、什么状态下观察”。AlphaGenome 2 把后一个问题变成了模型的显式输入。

Google DeepMind 于 **2026 年 11 月 11 日 15:00 UTC，即北京时间 23:00** 发布这一更新。资料核验截至**北京时间 2026 年 11 月 12 日 05:39**。本文依据官方公告、原始论文，以及 Python 客户端 2.0.0 对应的公开代码和文档，重点讨论如何理解和使用新增能力。**本文没有调用托管模型做实测，也没有独立复现论文基准。**[官方公告](https://deepmind.google/blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/)

## 把细胞状态变成可指定输入

原版 AlphaGenome 主要从 DNA 同时预测固定的一组实验轨道。AlphaGenome 2 接收 DNA 与目标条件，条件可以是组织、细胞类型或状态，并从网络早期就参与计算。用户也可提供自己的单细胞表达数据，让编码器生成条件表示，免去针对新数据集的微调。[官方公告](https://deepmind.google/blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/)

在接口中，这形成了两条路径：

- **参考条件**：用 `condition=` 选择模型支持的组织、细胞类型或细胞系。
- **表达条件化**：用 `cell_conditioning=` 提供人类 scRNA-seq 原始计数，再用 `cell_condition_name=` 命名这组细胞。

后一条路径仍需提供实测的单细胞表达数据，可以来自已有实验。“无需微调”省掉的是为新数据训练模型的步骤，并不意味着没有输入数据就能描述任意细胞状态。[条件选择教程](https://www.alphagenomedocs.com/colabs/v2/choosing_a_condition.html)

**我们的判断是，这会改变分析的基本单位：每条结果都应该同时带着变异、目标基因和细胞条件。**省略条件，会把一个有明确生物学背景的预测变成难以核查的泛泛判断。

## “接近翻倍”要连着指标和数据划分读

作者报告，在 TenK10K 单细胞 eQTL 基准上，因果候选识别的召回率在 **90% 精确率**处从 16% 升至 30%；效应方向任务在 **90% 方向准确率**处，保留比例从 23% 升至 43%。基线是经单细胞数据微调的 AG1。前一任务使用 6,346 个高后验纳入概率（PIP）的变异—基因关联及等量匹配对照，不能等同于临床确证的致病变异，也不能概括为“准确率翻倍”。[论文，第 4、35–36 页](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/alphagenome-2.pdf)

论文针对基因组区间、实验轨道、新数据集与变异任务采用不同划分。时间外推测试使用专门的留出模型；全基因组模型并非沿用同一留出设置。阅读时要确认“未见过”的是哪个维度，不能把所有数字合成一次同时跨新基因组、新细胞和新人群的验证。[论文，第 19–20、31–32 页](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/alphagenome-2.pdf)

## 最需要带进分析表格的，是三个证据标签

AlphaGenome 2 可以为某个条件输出未在该条件实际测量过的实验轨道。官方文档为每条轨道设置了 `imputation_mode`，用来区分其训练观测和推断依据。这里的“证据等级”是本文对这些类别用途的概括，不是逐变异准确概率、置信区间或临床证据分级。

| 标签 | 官方含义 | 解读时应保留的边界 |
| --- | --- | --- |
| `observed` | 该条件的这个实验通道在训练中有实测数据 | 当前输出仍是模型预测，并不代表这次变异效应又做过实验 |
| `imputed_supported` | 该条件未测此通道，但推断方向有信息支持并做过基准评估 | 可以用于形成假设，不能替代实际测量 |
| `imputed_exploratory` | 缺乏足够约束，相关外推没有得到基准验证 | 可能出现系统性误导，应作为探索线索 |

这些定义来自[官方填补轨道指南](https://www.alphagenomedocs.com/user_guides/imputation.html)。尤其要注意，`observed` 描述的是**训练数据覆盖情况**，不是本次预测的实验验证状态。

还有一个容易在界面中丢失的细节：`supported_conditions()` 按输出类型显示的是各通道中的最佳标签。假设某种细胞只测过 CTCF，TF 结合这一大类可能显示 `observed`，但同类其他未测转录因子仍属探索性预测。因此，最终筛选应查看每条结果自己的 `imputation_mode`，而不是只看条件列表中的汇总列。[官方说明](https://www.alphagenomedocs.com/user_guides/imputation.html#where-the-labels-appear)

**我们的分析：输出覆盖越广，结果的出处越不能省略。**如果报告只保留漂亮曲线和较大的效应分数，这三种依据会看起来像同一类结果。把标签保存在导出的表格、图注和候选列表里，是使用新能力的基本要求。

## 跨模态预测有方向，缺失数据也不等于零

官方文档没有把所有模态之间的填补视为同样可靠。可及性与基因表达可为彼此提供支持；组蛋白修饰与 CpG 甲基化的支持性推断需要可及性信息，只有基因表达并不够。未测的 TF 结合、剪接、CAGE 和三维接触图，则被列为探索性输出。用户表达条件化输入不对应一个训练参考条件，因此不会有轨道被标为 `observed`。[跨模态规则](https://www.alphagenomedocs.com/user_guides/imputation.html#cross-modality-rules)

文档还解释了两种比“模型可能出错”更具体的风险。

**第一，像真的剪接图，不一定含有足够的剪接证据。**常见 3′/5′ 单细胞计数没有跨越内部剪接连接，不能直接监督细胞特异的外显子使用。模型可以依据 DNA 基序给出合理的边界，但这不代表异构体比例得到验证。只有单细胞输入时，官方建议优先研究总转录效应，不把推断的外显子覆盖解释为已经验证的异构体使用。[剪接风险说明](https://www.alphagenomedocs.com/user_guides/imputation.html#splicing-effects-from-single-cell-assays-only)

**第二，一个 TF 的高结合预测，可能缺少“这个 TF 在这里表达”的前提。**TF ChIP 实验通常选择该转录因子表达的细胞；未测组合在训练损失中被遮罩，而非作为零信号负例。开放染色质上的匹配基序可能触发高分，即使目标细胞不表达这个 TF。官方因而建议额外核对相应表达证据。[TF 假阳性说明](https://www.alphagenomedocs.com/user_guides/imputation.html#false-positives-in-tf-chip-seq-for-unexpressed-transcription-factors)

这里共同的工程问题是：没有测量的组合，不能自动充当没有效应的组合。扩大模型输出范围时，也要扩大对这些空缺的说明。

## 真正接入 API，要改哪些步骤

根据官方迁移指南和客户端源码，一个稳妥的工作流可以分成四步。以下是接口阅读，不是本文已经运行成功的实验。

### 1. 先选生物条件，再请求预测

从 `alphagenome.models.v2` 导入客户端，先查 `supported_conditions()` 和 `observed_metadata()`。参考条件可以将组织和细胞类型的 ontology CURIE 合并。例如血液 CD14 阳性单核细胞使用 `UBERON:0000178_CL:0001054`。这类组合使“哪一种细胞、来自哪里”得到明确表达。[条件选择教程](https://www.alphagenomedocs.com/colabs/v2/choosing_a_condition.html)

`predict_interval`、`predict_variant` 和 `score_variant` 每次对应一个条件。跨组织比较需要循环调用，或给批量方法传入逐项匹配的条件。条件字符串的编码也只是结构检查；“格式合法”仍需和模型支持的条件目录核对。[迁移指南](https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/docs/source/user_guides/ag1_vs_ag2.md)

### 2. 用自己的细胞时，检查输入契约

表达条件化接收 `AnnData`，要求原始 UMI 计数和 Ensembl 基因 ID，不能把已经对数变换的表达矩阵当原始计数交进去。客户端会移除基因 ID 的版本后缀、检查重复 ID，并将计数序列化。调用方应在此之前核对自己的数据处理流程。[输入转换源码](https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/src/alphagenome/models/v2/gene_counts_condition.py)

当前客户端限制每次表达条件化最多 **256 个细胞**，且只支持人类输入；同时提供参考条件与表达条件也会报错。这个 256 是请求大小上限，不是“256 个细胞就一定足够”的生物学保证。官方 FAQ 明确提示，输入若明显偏离训练分布，模型可能无法捕捉其变化。[客户端验证代码](https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/src/alphagenome/models/v2/dna_client.py)、[FAQ](https://www.alphagenomedocs.com/faqs.html#condition-vs-cell-conditioning)

### 3. 读取结果时保留标签和分数含义

可用 `filter_to_observed()` 选择训练中有直接观测的轨道，也可在整理后的变异分数表中按 `imputation_mode` 保留支持性推断、排除探索性结果。这样的筛选减少了混用证据的风险，但并不把留下的预测变成临床结论。[填补轨道指南](https://www.alphagenomedocs.com/user_guides/imputation.html)

AG2 目前返回 `raw_score`，没有 AG1 的 `quantile_score`。不同模态、不同 scorer 的数值含义也不同，不能按同一量纲直接混合排序。我们的建议是把版本、条件、输出通道和 scorer 一起保存，避免用单一阈值横扫所有输出，更不能直接将原始分数解释为致病概率。[官方迁移说明](https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/docs/source/user_guides/ag1_vs_ag2.md#variant-scores)

### 4. 将请求规模和外推范围算入研究计划

按条件逐次预测意味着候选条件越多，请求量也越大。官方说明，实时模型预测更适合小规模分析，服务速率随需求变化；已有预计算图谱的查询速率更高。不要把一段可运行的示例直接理解为可无限扩展的全基因组服务承诺。[官方 README](https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/README.md)

API 接受某段合法 DNA，也不等于那类输入经过验证。FAQ 将其他物种、合成序列、大型结构变异以及大量 N 填充的序列列为未做基准的范围。[输入范围 FAQ](https://www.alphagenomedocs.com/faqs.html#arbitrary-sequences)

## 当前可以取得什么，仍需验证什么

发布时，AG2 提供非商业研究 API，商业研究处于私有预览。客户端仓库使用 Apache-2.0，示例和文档使用 CC BY 4.0。客户端开源不能转写为“模型权重开放且可随意商用”。[官方公告](https://deepmind.google/blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/)、[代码与用途声明](https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/README.md#terms)

官方 FAQ 将直接 API 输出与 Atlas 分数说明为非商业研究用途，并禁止用于训练其他机器学习模型或临床决策；README 另提示特定可下载工件存在例外，不能推广到所有输出。选择服务或数据前，应核对相应的[官方 FAQ](https://www.alphagenomedocs.com/faqs.html#terms-and-commercial)与[服务条款](https://alphagenome.google/terms)，不能只看客户端的软件许可证。

论文的 Code availability 说明，**AG2 模型源码和权重将于最终发表时提供**。因此，现阶段应按 API 已开放访问、AG2 权重尚未公开取得来描述；不要将旧版 AlphaGenome 的权重下载入口算到新模型头上。[论文，第 53 页](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/alphagenome-2.pdf)

至于科学用途，作者也承认条件表示来自观察性资料，尚不清楚能否预测基因敲除、过表达或动态状态转变的响应；本研究没有开展新的湿实验。[论文，第 14、52 页](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/alphagenome-2.pdf)

AlphaGenome 2 的实际价值，在于帮助研究者把候选变异、候选基因和可能相关的细胞条件连接起来，并据此安排下一步实验。模型给出的机制线索还需要独立证据检验。官方明确限制其用于科研，未验证或批准用于临床或诊断；任何个体诊断、用药或疗效保证都不在当前结果支持范围内。[论文，第 53 页](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/alphagenome-2.pdf)、[官方用途声明](https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/README.md#terms)

本文对官方文档作了中文概括与独立工程分析。文档和示例由 Google DeepMind 提供，版权归 Google LLC，许可为 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，客户端代码为 [Apache-2.0](https://github.com/google-deepmind/alphagenome/blob/f7b58d65f1dca93f9050086908b505a3304945fb/LICENSE)。代码阅读固定于提交 `f7b58d65f1dca93f9050086908b505a3304945fb`；本文未转载论文图表，也不将公开可读的论文视为已获开放再利用许可。
