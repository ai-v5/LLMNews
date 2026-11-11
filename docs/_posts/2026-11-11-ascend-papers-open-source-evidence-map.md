---
title: "昇腾究竟被谁用到了：论文实测与开源项目的证据地图"
date: 2026-11-11T21:30:00+08:00
summary: "从大模型训练、强化学习、多模态到推理与系统研究，按原始论文、实际代码和支持声明分层核查昇腾使用情况，并解释 torch_npu 检索能发现什么、又会漏掉什么。"
section: explainer
label: "昇腾生态调查"
tags: [昇腾, Ascend, 910B, torch_npu, 训练, 推理, 开源]
demo: false
sources:
  - title: "PanGu-α 原始论文"
    url: "https://arxiv.org/abs/2104.12369"
  - title: "CodeGeeX 原始论文"
    url: "https://arxiv.org/html/2303.17568"
  - title: "Intern Lumina U2 技术报告"
    url: "https://arxiv.org/html/2610.20818v1"
  - title: "Ascend Extension for PyTorch"
    url: "https://github.com/Ascend/pytorch"
  - title: "vLLM Ascend 官方项目"
    url: "https://github.com/vllm-project/vllm-ascend"
---

**资料核查截止：2026 年 11 月 11 日。** 本文调查公开论文、技术报告、官方文档和开源实现，覆盖历史与近期材料，并非仅筛选最近 24 小时。文中的实验结果均来自作者报告，本站未持有相关集群，也未复跑训练或性能测试。项目代码优先固定到提交版本；动态文档可能在此后变化。

“用了昇腾”至少包含四种不同情况：模型真的在昇腾上训练过；论文只在昇腾上做了一项算子或推理实验；开源项目实现了可选昇腾后端；厂商或社区提供了移植指南。把这四种情况混成一个名单，会夸大生态，也会错过真正有价值的工程进展。

本次调查得到的核心判断是：**公开证据已覆盖大模型训练、后训练、推理服务、多模态和底层系统，而且使用者不止华为；但“有适配”“有实测”和“已经规模化生产使用”仍须逐项区分。** 训练端可追溯到 PanGu-α、CodeGeeX，并延伸到运营商、互联网公司、科研机构的项目；软件端则同时存在 PyTorch 的 `torch_npu` 路线、MindSpore 路线以及直接调用 CANN 的 C++ 路线。

读这份名单时，最值得关注的不是条目总数，而是每条证据回答了多少问题：**谁在用、在哪个阶段用、用哪种芯片、规模多大、证据是论文实验还是仓库代码、有哪些未验证边界。**


读者可同时下载[结构化证据清单（JSON）]({{ '/assets/data/2026-11-11-ascend-evidence-map.json' | relative_url }})。清单保留分类、核验范围与来源，条目数量不代表独立使用者数量。

## 一 先确定什么才算证据

### 证据等级

| 等级 | 纳入条件 | 能够说明什么 | 不能自动说明什么 |
|---|---|---|---|
| A 实验或实际运行 | 原始论文、技术报告、官方实验记录明确写出昇腾与实验场景 | 作者确实报告在该硬件上运行过指定工作 | 本站独立复现、全模型生命周期都用昇腾、普遍性能优势 |
| B 可执行实现 | 上游或明确身份的适配仓库中有实际设备、分布式或算子调用 | 项目存在昇腾执行路径 | 所有功能、模型、版本与卡型均可用 |
| C 支持声明 | 官方安装指南、兼容列表、路线图或迁移文档 | 维护方声明的支持范围 | 已完成论文实验或生产部署 |
| D 待核线索 | 搜索摘要、转载、未核实型号的 NPU、存在冲突的材料 | 值得继续追查 | 计入“已确认使用”的结论 |

同一条目可以同时具备 A 与 B，表中按最直接的证据记录。**A 是作者公开的实验报告，不等于独立第三方认证。** “上游项目”也不等于适配工作由该项目原始团队独立完成，昇腾团队与社区贡献者可能共同参与。

### 关键词怎样消歧

- `Ascend`、`昇腾` 通常足以确认平台，但仍须排除参考文献、相关工作或未来计划中的提及。
- `910`、`910B` 必须与芯片、实验平台或 CANN 上下文相连，不能把型号相近的字符串、表格编号或其他设备当证据。原文只写 Ascend NPU 时，本文保留“未披露 SKU”，不自行升级为 910B。
- `NPU` 是设备类别，不是华为商标。Intel NPU、NVIDIA DLA、手机端 NPU 都可能出现在搜索结果中。XSched 同一份实验资料就同时包含多种 NPU，只有明确标为 Ascend 的实验属于本调查。
- `import torch_npu` 是高价值的发现线索。还要继续看它是否位于运行路径，是否配套 `torch.npu`、HCCL、`npu_fusion_attention` 等调用，以及是否只是可选依赖检测、测试桩或第三方 fork。
- 没有 `torch_npu` 不能据此排除昇腾。MindSpore、Paddle 自定义设备，以及 llama.cpp 的 CANN/AscendC/ACLNN 后端，都可以绕开这个 Python 包。
- 即使是 PyTorch 路线，新版 TorchNPU 也可自动注册，缺少显式导入不是可靠的负证据；应结合依赖清单、设备分支和后端注册继续核查。

## 二 论文与报告中的实际使用

下表将“原始模型训练”“继续预训练或后训练”“推理与系统实验”分开。机构栏仅描述论文署名或项目主体，不代表所有贡献、资金和设备来源；“非华为主体”也不等于已经完成独立的跨厂商公平基准。

### 大模型与多模态训练

| 工作与公开版本 | 团队或来源 | 明确的昇腾使用 | 证据与边界 |
|---|---|---|---|
| PanGu-α，2021 | 华为与鹏城等联合团队 | 2,048 颗 Ascend 910，最大 200B 语言模型训练 | A；[原始论文](https://arxiv.org/abs/2104.12369)。是原始 910，不能改写成 910B |
| PanGu-Σ，2023 | 华为主导 | 1.085T 参数稀疏模型，512 颗 Ascend 910，训练 329B tokens | A；[v1 论文](https://arxiv.org/html/2303.10845v1)。继承 PanGu-α 并扩展为稀疏模型，不是完全从零初始化；总参数不等于每 token 激活量 |
| CodeGeeX，KDD 2023，训练于 2022 | 清华、智谱主导，含华为合作者 | 13B 代码模型，1,536 颗 Ascend 910、192 节点；850B tokens，约两个月 | A；[v2 §2.3 与表 2/3](https://arxiv.org/html/2303.17568v2)。原始实现为 MindSpore 1.7，公开 PyTorch 版本不能反推原训练栈 |
| FRAME，ACL Findings 2025 | 美团、北大、北航、清华 | 3B 预训练实验使用 512 颗 910B，每模型超过 180 小时；1.3B 实验使用 96 颗 | A；[附录 B.1](https://aclanthology.org/2025.findings-acl.1040.pdf)。不同大小实验的训练预算应分别读，不能混算 |
| Haidass-143M-v1 / 1.5，2026 | DALabCommunity | v1 模型卡报告 64 颗 910B，从零训练约 100B tokens；v1.5 报告约 400B tokens 与 MindSpeed-LLM | A，作者模型卡；[v1](https://huggingface.co/DALabCommunity/Haidass-143M-v1)、[1.5](https://huggingface.co/DALabCommunity/Haidass1.5-143M)。不是同行评审论文，不能将 v1 卡数直接沿用到 v1.5 |
| Pangu Ultra，2025 | 华为主导 | 135B dense 模型，8,192 颗 Ascend NPU，13.2T tokens | A；[v1 报告](https://arxiv.org/html/2504.07866v1)。本文保留 NPU 平台粒度，不补写 910B |
| Pangu Ultra MoE，2025 | 华为主导 | 718B MoE 模型，约 6K 颗 Ascend NPU 训练 | A；[v1 报告](https://arxiv.org/html/2505.04519v1)。与上一报告分属不同公开材料，不把型号推断当论文原文 |
| TeleChat2 / 2.5 / T1，2025 | 中国电信团队 | 报告 Atlas 900 A2、最多 8,000 颗 Ascend NPU 的训练集群 | A；[报告](https://arxiv.org/html/2507.18013v1)。正文未直接写 910B；集群规模也不等于每个实验都使用全部设备 |
| TeleChat3-MoE，2025 | 中国电信与华为等联合团队 | 从 105B 到超过 1T 的 MoE 家族，报告 Ascend 集群端到端训练 | A；[报告](https://arxiv.org/html/2512.24157v1)。不自动认定为 910B，也不列为完全无华为参与 |
| JIUTIAN-139MoE，2024 | 中国移动九天 | 原报告明确 A800 向 910B 迁移，并继续训练 | A，阶段细节不完整；[§2.5](https://www.modelscope.cn/models/JiuTian-AI/JIUTIAN-139MoE-chat/resolve/master/JIUTIAN-139MOE%20TECHNICAL%20REPORT.pdf)。未拆清 910B 阶段卡数、token 数和时长，不能写成“896 张 910B 训练两个月” |
| Open-Sora-Plan v1.5.0 | 北大 YuanGroup / LanguageBind 社区 | 四个图像阶段分别 512/384/256/256 颗 910B；五个视频阶段均为 512 颗 910B | A；[官方版本报告](https://huggingface.co/LanguageBind/Open-Sora-Plan-v1.5.0/blob/main/Report-V1.5.0.md)。8.5B 视频生成模型，使用 MindSpeed-MM；不把其他版本硬件混入 v1.5 |
| Intern Lumina U2，2026-10，v1 | 上海 AI 实验室主导，含高校与华为作者 | 五个训练阶段均为 1,024 颗 910B，并提供昇腾推理、评估路径 | A；[§5.2 与附录 D](https://arxiv.org/html/2610.20818v1)。基于 LLaDA2.0-mini，不能写成语言基模全程从零预训练；1,024 是训练卡数，不是每次推理所需卡数 |
| DiC，CVPR 2025，v2 | 北大、北邮、华为 | DiC-XL / H 图像扩散模型在 8 颗 910B 上训练 | A；[§4.1](https://arxiv.org/html/2501.00603v2)。吞吐测试使用单张 A100，不能当作 910B 推理速度 |
| MindVL，2025-09，v1 | 华为 | MindVL-8B / 32B 在千卡规模 910B 集群训练 | A；[§2、§4.2.2](https://arxiv.org/html/2509.11662v1)。千卡不能改写成精确 1,024 卡；使用既有 Qwen2.5ViT 与 Qwen3 / DeepSeek V3 语言底模，不是语言模型从零训练 |
| BitCPM-CANN，2026 模型卡 | OpenBMB | 基于 Megatron-LM、MindSpeed 和 910B 的分布式量化感知训练，覆盖 0.5B / 1B / 3B / 8B | A，作者模型卡；[官方说明](https://huggingface.co/openbmb/BitCPM-CANN-8B)。另有 16 卡 910C 吞吐报告，不能归入 910B；发布权重是 fake-quantized 浮点格式 |
| OSUM-Pangu，2026-03，v1 | 西北工业大学 ASLP | 基于 openPangu 7B，训练与推理均使用 Ascend | A；[报告](https://arxiv.org/html/2603.10862v1)。未取得明确 910 SKU，不能归入已确认 910B 清单 |
| Spark-Audio 1.0，2026-10，v1 | 科大讯飞 | 报告音频模型训练使用国产平台，明确包括 910B 与海光 BW1000 | A；[报告](https://arxiv.org/html/2610.31292v1)。未拆分两种芯片的逐阶段份额，不能称“纯 910B 全程训练” |

这些记录已经足以回答“是否只有华为自己的模型使用昇腾”：不是。FRAME 的预训练研究、讯飞的后训练、京东的推理报告，来自不同业务主体。但与华为联合发表的 CodeGeeX、Intern Lumina U2 等仍应如实标明合作关系，不能为了突出第三方采纳而删去合作者。

### 继续训练 强化学习与任务研究

| 工作与公开版本 | 团队或来源 | 明确的昇腾使用 | 证据与边界 |
|---|---|---|---|
| Spark-Prover-X1，v3 | 科大讯飞研究院 | 7B 模型继续预训练 512 颗 910B；Prover SFT 256 颗；Formalizer SFT 128 颗；GRPO 320 颗 | A；[§4.2](https://arxiv.org/html/2511.13043v3)。这是已有数学底模上的 CPT、SFT、RL，不能称为从零训练基础 LLM |
| SummOrchestra / Beyond Overlap Metrics，ACL Findings 2026 | 浙江师范、华为与多所高校联合 | 8 颗 910B 64GB，在 Qwen2.5 / Qwen3 的对话摘要模型上开展 SFT 后 GRPO | A；[§4.1](https://aclanthology.org/2026.findings-acl.1161.pdf)。硬件结论限作者自训练模型，不能把外部 GPT teacher / judge 的运行硬件也算入 |
| verl Async RL Training Tuning Guide，2026-10-26 | verl 官方工程报告 | 在 910B 上调优 Qwen3-30B、Qwen3.5-35B、Qwen3-Omni 等异步 RL 资源配比与流水 | A，工程报告；[原文](https://verl-project.github.io/posts/2026-10-23-async-rl-training-tuning/)。完整 run 配置未披露，局部收益不能推广到所有任务；URL 日期不等于页面发布日期 |
| MindSpeed RL，2025-07，v1 | 昇腾官方训练系统 | 16 颗 Ascend NPU 的端到端对比；671B MoE 扩展到 384 颗，每颗 128GB | A；[实验设置](https://arxiv.org/html/2507.19017v1)。报告未明确 910 SKU；不能把全部实验都写成 384 卡。项目当前维护状态另见下文 |
| Pangu Embedded，2025-05，v1 | 华为主导 | 7B 模型 GRPO；policy 训练与推理使用 1,024 颗 Ascend NPU，另 256 颗用于 reference model | A；[§2.6](https://arxiv.org/html/2505.22375v1)。未明确 910 SKU；不能把两组资源合并成 policy 单项 1,280 卡 |
| Attention Editing，2026-04，v1 | 招商银行 AI 实验室 | 在 910B 集群将 Qwen3 注意力结构改造成 MLA / GateSWA 并蒸馏；另有单张 910B 推理实验 | A；[§5.2、§6.2](https://arxiv.org/html/2604.05688v1)。未披露训练卡数；图 4 明确使用 H800，故不能照抄“全部实验都在 910B” |
| Enhancing Cross-Lingual Emotion Detection with Data Augmentation and Token-Label Mapping，WASSA 2024 | 中国电信云团队 | 8 颗 910B、每颗 64GB，开展跨语言情绪识别与触发词检测微调 | A；[§4](https://aclanthology.org/2024.wassa-1.53.pdf)。这是 XLM-R 等任务模型实验，不是大语言模型预训练 |
| Decoding Matters，EMNLP 2024 | 中科大、新加坡国立大学、华为联合 | 推荐解码研究，在六个数据集实验，报告单颗 910B 32GB | A；[§6.1](https://aclanthology.org/2024.emnlp-main.589.pdf)。研究对象为推荐解码，不应写成通用 LLM 集群训练 |
| ECHO-LLaMA，EMNLP Industry 2025 | 华为多伦多 Ascend 团队、滑铁卢大学 | LLaMA 共享 KV 架构转换及训练性能，对照 V100 和 910B | A；[论文](https://aclanthology.org/2025.emnlp-industry.156.pdf)。包含短步数性能基准，不代表大型 LLM 完整从零训练 |

这里最重要的区分是训练阶段。**在同一张卡上做一次 LoRA、跑一轮 GRPO，以及从随机初始化训练一个基础模型，都是真实使用，却回答不同的问题。** Spark-Prover-X1 的价值在于公开了多个后训练阶段的硬件规模；Attention Editing 则说明企业用户正在昇腾上做模型结构改造，而不仅是运行别人已发布的权重。

### 推理 系统与非 LLM 工作负载

| 工作与公开版本 | 平台与用途 | 可追溯证据 | 解释边界 |
|---|---|---|---|
| xLLM Technical Report，2025-10，v1；京东与高校联合 | 910B / 910C 推理服务；DeepSeek-R1 分别使用 16 颗 910B 或 8 颗 910C，报告京东业务部署 | A；[§5](https://arxiv.org/html/2510.14686v1) | 报告中的框架加速来自指定软件版本、模型与 SLO，不能换算成昇腾对 NVIDIA 的芯片优劣 |
| Serving Large Language Models on Huawei CloudMatrix384，2025，v3；华为与 SiliconFlow | 系统含 384 个文中称 Ascend 910 的双 die NPU；§5.1 这组实验分配 256 个，其中 prefill 96、decode 160 | A；[§5.1、表 2](https://arxiv.org/html/2506.12708v3) | 保留正文型号，不将“910”解释为 910B 或 2019 原始款。384 是系统容量，非该实验用卡数；Perfect EPLB 为理想预测项 |
| 大模型服务 Field Study，2026-07，v1 | 16 设备 Ascend 910 系统，CANN / vLLM-Ascend，MoE 与多模态推理 | A，作者现场报告；[论文摘要](https://arxiv.org/abs/2607.08215) | 单作者报告，未明确 B/C 子型号；不与多方独立可复现基准视为同等可信度 |
| THOR，AAAI 2021 | 8 / 256 颗 Ascend 910 上的 ResNet-50 训练与二阶优化研究 | A；[会议原文](https://ojs.aaai.org/index.php/AAAI/article/view/16867) | 属视觉训练和优化器研究，不是 LLM 证据 |
| APOLLO，MLSys 2022 | §6.4 在 Ascend 910 上开展 BERT、PanGu-α 2.6B 训练，含 64 / 128 卡设置 | A；[会议论文](https://proceedings.mlsys.org/paper_files/paper/2022/file/e175e8a86d28d935be4f43719651f86d-Paper.pdf) | §6.6 的推理实验是 GPU，不能把整篇实验都归于昇腾 |
| RazorAttention，ICLR 2025 | 附录 A.3 使用 8 颗 910B 对 GLM-9B-1M 做 128K / 256K 长上下文推理 | A；[会议论文](https://proceedings.iclr.cc/paper_files/paper/2025/file/2a98af4fea6a24b73af7b588ca95f755-Paper-Conference.pdf) | 属 KV 缓存与推理优化，不证明 GLM 原始训练硬件 |
| XSched，OSDI 2025 | Ascend 910b、CANN 8.0.0，抢占式调度实验 | A+B；[固定版实验材料](https://github.com/XpuOS/xsched-artifacts/blob/e5ed1086200798ff1a81ea160d6aca30555bd1a2/README.md) | Ascend 对应原 artifact fig7、论文终稿 Figure 9；其余 Intel NPU3720 / NVIDIA DLA 实验不得算作昇腾 |
| Automatically Planning Optimal Parallel Strategy for Large Language Models，2024-12 / arXiv 2501 | 两台服务器、16 颗 910b 64GB，以 ModelLink 对 Baichuan2 / Qwen / Aquila2 配置做训练 profiling | A；[实验设置](https://arxiv.org/html/2501.00254v1) | 包含模拟估计，也有实际设备测量；结论受测试模型与层数配置限制 |
| Segmented Operations using Matrix Multiplications，2025 | 在 910B 上实现并测试 segmented scan / sum，覆盖合成与 LLM 数据 | A；[正式摘要](https://arxiv.org/abs/2506.23906) | 是算子算法实验，不是完整 LLM 训练 |
| NeutronSparse，2026 预印本 | 910B 上的 SpMM 稀疏矩阵乘，协调异构计算引擎 | A；[正式摘要](https://arxiv.org/abs/2606.22482) | 与 MindSpore 及 GPU 库比较需保留配置；页面标注 SIGMOD 2027 不等于该会议已经举行 |
| AcOrch，2026 公开预印本 | 910B 上的 CPU–NPU 协同采样式 GNN 训练 | A；[正式摘要](https://arxiv.org/abs/2606.01161) | 属图学习，与 MindSporeGL 比较；Frontiers of Computer Science 的 2027 标记是期刊卷期，此处按 2026 年公开预印本记录 |
| AgenticCANN，2026 | 在 910B 上评测生成的 Ascend C 算子，涵盖六种算子与五类模式 | A；[正式摘要](https://arxiv.org/abs/2607.26661) | 被生成算子在昇腾执行，不代表生成它的 Agent / LLM 在昇腾训练 |
| W4A16 Mixed-Precision Matrix Multiplication on Decoupled Architecture，2026 | Ascend 910 上的 INT4 解量化、FP16 GEMM、Split-K 内核 benchmark | A；[正式摘要](https://arxiv.org/abs/2601.16536) | 已核对摘要未明确 B/C 子型号；内核收益不能直接换成端到端服务收益 |
| Hermes，USENIX ATC 2025 | Ascend 训练性能分析与优化系统，报告 2022–2024 年生产案例 | A；[会议资料](https://www.usenix.org/conference/atc25/presentation/zhou) | 135 个案例、40 个客户为作者报告，本轮未核得具体 910 SKU |
| Squeezing Operator Performance Potential for the Ascend Architecture，ASPLOS 2025 | Ascend 算子性能分析，含 MobileNetV3、PanGu 100B 等工作负载 | A；[作者论文 PDF](https://grace-liu.github.io/static/papers/25-ASPLOS-ascend.pdf) | 已确认平台，未确认具体 910 SKU；不强行归为 910B |
| DataHelix，2026-11 | 8 颗 910B，11 类视频与多模态训练负载的输入数据调度 | A；[论文](https://arxiv.org/abs/2611.09411) | 证明输入流水线的系统实验，不等于这些基础模型都在昇腾上完成全量预训练 |
| Ascend to Science，2026-07，v1；鹏城实验室 | 分实验使用 910A / 910B / 910C，涉及 HPL-MxP、低秩 SVD、GEMM、量子仿真与蒙特卡洛 | A；[论文与实验附录](https://arxiv.org/html/2607.20120v1) | 非 LLM 科学计算；各代硬件、精度与比较基线不同，不宜合成一个通用加速比 |
| Tensor Yard，2021；华为与莫斯科大学联合 | Ascend 310 上的 ResNet 推理与张量分解优化 | A；[原文](https://arxiv.org/html/2108.04029v1) | 是 310 推理，不是 910 系列训练；保留它可避免把昇腾生态缩成大模型训练卡 |

系统论文带来的信息往往比“支持哪些模型”的列表更有解释力：有的解决算子布局，有的解决通信与调度，有的解决 KV 缓存或输入等待。它们揭示了实际使用昇腾时花时间的地方，也提醒我们不能只按峰值算力判断迁移成本。

## 三 开源项目的昇腾执行路径

下面的“主线”指核查时的上游默认分支，不代表所有内容都已进入稳定发行版。**存在 CI 配置与最近一次硬件 CI 已通过，是两回事。** 本文核查到配置时只记录配置存在，不声称已经检查全部运行结果。

### 训练框架与设备基础设施

| 项目与归属 | 具体实现或文档证据 | 等级 | 支持范围应怎样读 |
|---|---|---|---|
| DeepSpeed，deepspeedai 上游 | [NPU 安装与验证指南](https://github.com/deepspeedai/DeepSpeed/blob/b9100c541ac1b8e25148bc8000d1ad45c4c095db/docs/_tutorials/accelerator-setup-guide.md)，配套 NPU Accelerator / op_builder | B+C | 指南明确在 Atlas 300T A2 验证；从 v0.12.6 起支持自动识别。不是全部 CUDA 算子均等价可用 |
| Accelerate，Hugging Face 上游 | [设备与分布式状态](https://github.com/huggingface/accelerate/blob/f47439c1fb24721ea71ab98f9b512726b5a97828/src/accelerate/state.py)、NPU 启动参数和大模型派发 | B | 不是仅有一个 import；仍需核对实际训练策略和依赖版本 |
| Transformers，Hugging Face 上游 | [NPU FlashAttention 集成](https://github.com/huggingface/transformers/blob/a72a1c385297bfaf1c8a07b5f4e689a315b90b77/src/transformers/integrations/npu_flash_attention.py)，实际调用 NPU attention | B | 证明特定 attention 执行路径，不等于模型库全覆盖 |
| Diffusers，Hugging Face 上游 | [attention_processor](https://github.com/huggingface/diffusers/blob/0905b667fe3f37f43b6ef9c6e05ad20636206938/src/diffusers/models/attention_processor.py) 使用 `torch_npu.npu_fusion_attention`；DreamBooth 示例有 NPU 分支 | B | 扩散模型也进入昇腾适配范围；未逐模型核验硬件 CI |
| LlamaFactory，hiyouga 上游 | [v1 NPU 指南](https://github.com/hiyouga/LlamaFactory/blob/f28b1b45ae175b55778a78ebe49961b03a684ac0/docs/zh/multi-backend/npu/index.md)、融合 RMSNorm / RoPE / SwiGLU / MoE 实现 | B+C | 当前 v1 文档列 SFT、LoRA、DPO、RM 等支持，QLoRA 不支持；旧 README 的另一分支方案不能与 v1 混写 |
| ms-swift，ModelScope 上游 | [固定版 NPU 文档](https://github.com/modelscope/ms-swift/blob/4c21511f00d610e88bbc186d86dc7b7269b5a4ab/docs/source_en/BestPractices/NPU-support.md) 明确 8×910B3 64GB 验证及具体组合 | B+C | 覆盖 CPT/SFT/DPO/RM/GRPO/PPO 等路径。该文档对 QLoRA、Liger、SGLang 的限制是本项目集成范围，不是那些上游项目的全局结论 |
| ColossalAI，hpcaitech 上游 | [NpuAccelerator](https://github.com/hpcaitech/ColossalAI/blob/da8f5c2dd56f97d3d23d3d222b114e1a3d4710f5/colossalai/accelerator/npu_accelerator.py) 导入 `torch_npu`、设置 HCCL，并调用 `torch.npu` | B | 另有 `npu_fusion_attention` 实现；未确认每个 booster、插件、模型的硬件验证 |
| Ray，ray-project 上游 | [NPU 资源管理器](https://github.com/ray-project/ray/blob/16aa1bb8588e0729ba2ecb37b0a4e191b091ed53/python/ray/_private/accelerators/npu.py) 与调度文档 | B | 证明设备发现、资源与调度支持，不能单独证明某个 LLM 在昇腾训练成功 |
| PaddleCustomDevice，PaddlePaddle 上游 | [Ascend 自定义设备后端](https://github.com/PaddlePaddle/PaddleCustomDevice/blob/d0e25eef753eadf23a2ab4a5d90de4fcca123c74/backends/npu/README.md)，`paddle_custom_npu` 与运行示例 | B+C | 当前文档明确 910B，910A 指向 release/2.6；不依赖 `torch_npu` |
| MindSpore Transformers / MindFormers，MindSpore 生态 | [2.0.0 安装指南](https://www.mindspore.cn/mindformers/docs/en/stable/installation.html) 与[架构文档](https://www.mindspore.cn/mindformers/docs/en/r1.3.0/start/overview.html) | C，框架路线明确 | 预训练、微调、推理和评估；2.0.0 安装页列 Atlas A2/A3 及配套依赖，不将旧版本与新版本矩阵混合 |

### 强化学习与后训练

| 项目与归属 | 具体实现或文档证据 | 等级 | 支持范围应怎样读 |
|---|---|---|---|
| verl，verl-project 上游 | [Ascend 工作流配置](https://github.com/verl-project/verl/blob/81464bb6d35cbb43962be42b0088a591e7020f21/.github/workflows/model_ascend.yml)、[安装指南](https://github.com/verl-project/verl/blob/main/docs/ascend_tutorial/en/get_start/install_guidance.rst) | B+C | 存在训练后端与 vLLM/SGLang rollout 组合；不代表每个组合都已通过本次核查，版本依赖冲突也需处理 |
| ROLL，Alibaba 上游 | [NpuPlatform](https://github.com/alibaba/ROLL/blob/7c0ded3d621ad4f45fb4d6675914de5eae8918eb/roll/platforms/npu.py) 与 [Ascend RLVR 指南](https://github.com/alibaba/ROLL/blob/7c0ded3d621ad4f45fb4d6675914de5eae8918eb/docs_roll/docs/User%20Guides/Hardware%20Support/ascend_npu_rlvr.md) | B+C | 文档明确 Atlas 900 A2 PODc / 910B1 与 A3 产品，需按硬件系列配镜像 |
| slime，THUDM 上游及配套适配 | [NPUAccelerator](https://github.com/THUDM/slime/blob/79aa41a884ab0bf65222c94418f6357d3c31192b/slime/utils/accelerator/npu.py)、[补丁说明](https://github.com/THUDM/slime/blob/79aa41a884ab0bf65222c94418f6357d3c31192b/docker/npu_patch/README.md) | B | 需要外部 ascend-slime、特定 SGLang 分支与 Megatron 补丁，不能写成所有工作流无补丁即插即用 |
| AReaL，areal-project 官方适配分支 | [NPUPlatform](https://github.com/areal-project/AReaL/blob/2262610b8c87abe355b98194afcb6d0846c57795/areal/infra/platforms/npu.py)、[固定版安装指南](https://github.com/areal-project/AReaL/blob/2262610b8c87abe355b98194afcb6d0846c57795/docs/en/tutorial/installation_npu.md) | B+C | 使用 ascend-v1.0.5 专用分支与 A2/A3 镜像；支持 vLLM-Ascend rollout 及 FSDP/Megatron 训练，该集成不支持 SGLang；不能当作 main 所有功能均已支持 |
| TRL，Hugging Face 上游 | [vLLM generation](https://github.com/huggingface/trl/blob/6a7764ac47291f290521e5e6f8ef1176d068281c/trl/generation/vllm_generation.py) 有 NPU cache、内存与 sleep mode 处理 | B，范围局部 | 有实际集成代码，但不能外推为所有 RL 算法均完成昇腾验证 |

RL 的适配不能只看训练器：rollout 引擎、权重同步、休眠/唤醒、显存复用、分布式通信都影响端到端流程。一个项目在 CUDA 上能完成 PPO 或 GRPO，并不意味着替换设备名称后全部可用；反过来，已有专门 NPU 代码也不应被简单归为“只有厂商 demo”。

### 推理服务与轻量部署

| 项目与归属 | 具体实现或文档证据 | 等级 | 支持范围应怎样读 |
|---|---|---|---|
| vLLM Ascend，vllm-project 社区插件 | [官方版本文档](https://docs.vllm.ai/projects/ascend/en/v0.23.0/)、[固定版 NPU LoRA 实现](https://github.com/vllm-project/vllm-ascend/blob/c251a6a5ed5cc10f7ec6daa5b87d410d731bf6fd/vllm_ascend/lora/punica_npu.py) | B+C | 是官方推荐的独立硬件插件，而非 vLLM 核心内置全部昇腾实现；不能把所有版本的支持矩阵叠加 |
| SGLang，sgl-project 上游 | [Ascend attention 后端](https://github.com/sgl-project/sglang/blob/23a45fd33921164fa440fd7c28cc63341259c28c/python/sglang/srt/hardware_backend/npu/attention/ascend_backend.py)、[A3 quickstart](https://github.com/sgl-project/sglang/blob/23a45fd33921164fa440fd7c28cc63341259c28c/docs/docs/hardware-platforms/ascend-npus/getting-started/quick_start.mdx) | B+C | 上游已有 NPU 路径，同时依赖独立的 sgl-kernel-npu；不能因 ms-swift 的集成限制而说 SGLang 不支持昇腾 |
| LMDeploy，InternLM 上游 | [Ascend PyTorchEngine 指南](https://github.com/InternLM/lmdeploy/blob/cf52797ec6890fb6fe99aee8c4768d209d5a720b/docs/en/get_started/ascend/get_started.md)、[模型矩阵](https://github.com/InternLM/lmdeploy/blob/cf52797ec6890fb6fe99aee8c4768d209d5a720b/docs/en/supported_models/supported_models.md) | B+C | 依赖 dlinfer-ascend，列 A2/A3/300I Duo；同版本 quickstart 与矩阵对 A3 模型范围不完全一致，部署前应确认具体组合 |
| llama.cpp，ggml-org 上游 | [CANN 后端文档](https://github.com/ggml-org/llama.cpp/blob/b8abe41a5081728f9f4c824ef810902a11ab7ffd/docs/backend/CANN.md)，直接使用 AscendC / ACLNN | B+C | 910B 与 310P 有明确支持项；310P 不支持 BF16，量化矩阵乘受限。硬件表中 910/910C 空白验证栏不能自动算通过 |
| sherpa-onnx，k2-fsa 上游 | [Ascend 模型、命令和运行输出](https://k2-fsa.github.io/sherpa/onnx/ascend/models.html) | B+C，语音推理路径 | 有 910B 模型部署资料；不代表这些语音模型原始训练使用昇腾 |

### 算子 编译器 视觉与语音

| 项目与归属 | 具体实现或文档证据 | 等级 | 支持范围应怎样读 |
|---|---|---|---|
| TileLang 主线，tile-ai | [固定版 README](https://github.com/tile-ai/tilelang/blob/348e8072a824e217caf6d09c70272a8a5661c25f/README.md) 与 [Ascend 后端](https://github.com/tile-ai/tilelang/blob/348e8072a824e217caf6d09c70272a8a5661c25f/tilelang/ascend/README.md) | B+C | 当前主线声明 Ascend 950 支持；不能据此把 A2/A3 独立后端的状态全部归入主线 |
| TileLang-Ascend，tile-ai 独立后端 | [固定版 README](https://github.com/tile-ai/tilelang-ascend/blob/4805777d691b0c586e647fc0f975fa4cc306c00e/README.md) 声明 A2/A3 测试与验证，提供 GEMM / attention 示例 | B+C | 与 TileLang 主线按仓库和硬件分开记录，不当成两个独立终端用户 |
| Liger-Kernel，LinkedIn 上游 | [Ascend 安装与后端](https://github.com/linkedin/Liger-Kernel/blob/42dc23c41dcaf1f95d858837aed5301fd4faa27a/README.md)、[backend 说明](https://github.com/linkedin/Liger-Kernel/blob/42dc23c41dcaf1f95d858837aed5301fd4faa27a/src/liger_kernel/ops/backends/README.md) | B+C | 有主线 Ascend 派发与 HCCL；CI badge 不等于本文检查过全部硬件测试 |
| FlagGems，flagos-ai 上游 | [Ascend 后端注册](https://github.com/flagos-ai/FlagGems/blob/4d3d9f70c9c92ae9adf004ed0202355fe26fd511/src/flag_gems/runtime/backend/_ascend/__init__.py)、[BMM 实现](https://github.com/flagos-ai/FlagGems/blob/4d3d9f70c9c92ae9adf004ed0202355fe26fd511/src/flag_gems/runtime/backend/_ascend/ops/bmm.py) | B | 有实际 Triton/CANN 算子执行路径及 NPU 派发；存在逐算子排除项，不代表完整模型或所有精度、形状均通过验证 |
| MMCV，OpenMMLab 上游 | [逐算子 Ascend 支持表](https://github.com/open-mmlab/mmcv/blob/d2111bda571f3b3eb53954af6f9cff25f34e626f/docs/en/understand_mmcv/ops.md)，配套 NPU C++ 实现 | B | 是算子级支持，不能套成所有 MMDetection / 3D 模型都已适配 |
| DIOPI，DeepLink 上游 | [Ascend 构建实现](https://github.com/DeepLink-org/DIOPI/blob/b179d61735ce26bcc6585f38d194455afe28d2dc/impl/ascend/CMakeLists.txt)、[Ascend NPU 实现](https://github.com/DeepLink-org/DIOPI/blob/b179d61735ce26bcc6585f38d194455afe28d2dc/impl/ascend_npu/CMakeLists.txt) | B | 属第三方适配层；未核查完整逐算子通过表 |
| timm / pytorch-image-models，Hugging Face 上游 | [NPU 分布式设备代码](https://github.com/huggingface/pytorch-image-models/blob/43b549bfe9d680bc94284cfd0b611152d18e97d7/timm/utils/distributed.py) | B | changelog 记录昇腾支持，不能将“should work”升格成全部模型验证 |
| WeNet，wenet-e2e 上游 | [AISHELL NPU 训练脚本](https://github.com/wenet-e2e/wenet/blob/be6ad97fdb512589df113042f7ff3a29d392fb38/examples/aishell/s0/run_npu.sh) 与 README 安装说明 | B+C | 是语音模型训练的实质入口；本文没有核对硬件 benchmark |
| CogAgent，zai-org 上游 | [微调文档](https://github.com/zai-org/CogAgent/blob/27498ca74268e05fdddd27f83c64671d50bc7146/finetune/README_en.md) 有 Atlas A2、`torch_npu`、`transfer_to_npu` 迁移步骤 | C，项目内示例 | 不等于持续硬件 CI，也不能据此推断原模型预训练平台 |
| ContentV，ByteDance 上游 | [demo.py](https://github.com/bytedance/ContentV/blob/8ad3ca206e4c9f0a29885de87476ce190a6c746d/demo.py) 有 `USE_ASCEND_NPU` 与实际迁移分支 | B，demo 范围 | 能证明代码提供昇腾入口，不能证明训练、数值一致性或生产规模 |
| FunASR，ModelScope 上游 | [Ascend 说明](https://github.com/modelscope/FunASR/blob/2b4a0623613013b2b59ae289b189768426006cfa/docs/ascend_npu.md) 记录贡献者在 310P3 上的局部运行；[部署矩阵](https://github.com/modelscope/FunASR/blob/2b4a0623613013b2b59ae289b189768426006cfa/docs/deployment_matrix_zh.md) 列限制 | B+C，局部兼容 | 原贡献者的运行报告与后续修订的 CPU 检查不同；FunASR-Nano 不应被写成已具备官方生产 NPU runtime |

### 华为基础生态单列

基础适配栈是生态能够运行的前提，但不能将每个组件都当成一家独立企业的采纳案例：

- **TorchNPU / Ascend Extension for PyTorch**：为 PyTorch 注册昇腾设备、算子、内存和分布式能力。官方 README 明确，自 2.5.1 起可自动注册，显式 `import torch_npu` 不再是必需条件，尽管仍推荐显式导入。因此，代码搜索必须补查依赖与设备注册，而不是只搜一行 import。[官方说明](https://github.com/Ascend/pytorch/blob/master/README.md)
- **MindSpeed 及 LLM、RL、MM 组件**：提供昇腾训练加速和特定模型流程。本文在 Open-Sora-Plan、Haidass 等实际项目中分别记录它们的使用，避免把一个底座的多个入口算成多个独立使用者。MindSpeed-RL 当前 README 说明，自 2026 年 4 月起暂停新增功能集成，保留现有优化与问题响应，并引导最新方案参考 verl，选型时须注意维护方向。[MindSpeed](https://github.com/Ascend/MindSpeed)、[MindSpeed-LLM](https://github.com/Ascend/MindSpeed-LLM)、[MindSpeed-RL](https://github.com/Ascend/MindSpeed-RL)
- **TorchAir**：昇腾图编译路线，属于执行栈，而非一份模型已训练完成的证据。[项目](https://github.com/Ascend/torchair)
- **MindSpore / MindFormers、MindIE 与 ModelZoo**：分别对应框架/大模型套件、推理与适配示例生态。[MindIE-LLM](https://github.com/Ascend/MindIE-LLM) 是其中的 LLM 推理引擎。一个模型出现在示例库，只能说明该版本提供了相应迁移或运行材料；原始作者使用什么训练硬件，仍应回到论文与报告核查。

从代码结构看，昇腾支持已经出现在多家非华为组织维护的上游仓库中，且覆盖设备发现、分布式、attention、MoE、推理服务等实际路径。更准确的结论是**主流开源栈中存在可审计的昇腾实现**，而不是“这些框架的全部功能都已与 CUDA 完全等价”。

## 四 不应混入强证据清单的材料

为便于继续补充，下面保留有价值的线索及排除理由，而不把“没有核完”写成“没有使用”。

| 条目或情况 | 本轮判断 | 原因与来源 |
|---|---|---|
| AcceLLM，2024 | 模拟评估，单独列出 | [摘要](https://arxiv.org/abs/2411.05555) 明确 simulated evaluations，包含 H100 与 910B2；不能作为纯实机评测证据 |
| UNIT，NeurIPS 2024 | 作者硬件声明存在内部冲突 | [正式论文附录 A.1](https://proceedings.neurips.cc/paper_files/paper/2024/file/dcfb4b195fe1ec750ef13312974b620e-Paper-Conference.pdf) 写 128×910B 64GB、150 小时，同时写 CUDA 11.7。保留声明与矛盾，不替作者解释，也不据此断言整项工作虚假 |
| Parallel Scan on Ascend AI Accelerators | 候选，未完成原文核查 | [OpenReview](https://openreview.net/forum?id=wPepcNWMhs) 的搜索线索涉及 910B，但本轮直接读取遇到浏览器验证，未将索引摘要当作已读全文 |
| AMLA、IndexSLM、A-IO、NPUMeter、AscQLUT | 待进一步核查 | [AMLA](https://arxiv.org/abs/2509.25224)、[IndexSLM](https://arxiv.org/abs/2607.09885)、[A-IO](https://arxiv.org/abs/2604.09752)、[NPUMeter](https://doi.org/10.1145/3820380)、[AscQLUT](https://www.sciencedirect.com/science/article/pii/S1383762126001578) 尚未完成与主表同等深度的核查，不据索引片段给出确定硬件结论 |
| Rethinking Expert Trajectory Utilization、RLKD | RL 候选，全文硬件待复核 | [ACL 条目](https://aclanthology.org/2026.acl-long.1528/) 的大文件读取超工具大小限制；[RLKD 原 PDF](https://ojs.aaai.org/index.php/AAAI/article/download/40710/44671) 遇反机器人拒绝。仅索引线索不足以升级为全文核查成功 |
| LMGL-WD | 候选，训练硬件与阶段待核 | [AAAI 原 PDF](https://ojs.aaai.org/index.php/AAAI/article/download/38577/42539) 本轮无法直接读取，不据线索确定设备配置；即使后续确认任务模型使用昇腾，也需区分任务训练与所用语言底模的原始预训练 |
| 大气与海洋模型迁移相关工作 | 候选，配置与实验范围待核 | [AAAI 原 PDF](https://ojs.aaai.org/index.php/AAAI/article/download/41497/45458) 本轮无法直接读取，暂不引用未经正文核实的硬件参数或性能比较 |
| MagicDrive-V2 | 兼容性线索，待核；不计入昇腾训练实测 | [ICCV 2025 补充材料](https://www.openaccess.thecvf.com/content/ICCV2025/supplemental/Gao_MagicDrive-V2_High-Resolution_Long_ICCV_2025_supplemental.pdf) 直接读取返回 403，本轮未完成主训练硬件与兼容性范围的原文复核 |
| AntAngelMed | 昇腾部署支持，非训练硬件证据 | [官方模型卡](https://huggingface.co/MedAIBase/AntAngelMed) 提供 8×64GB 910B 与 vLLM-Ascend 部署说明；不能推出原模型在 910B 训练或已在医院生产部署 |
| 原模型在昇腾的第三方复现 | 只归入该复现 | 第三方 MindSpore / NPU 移植，不能追溯改变原论文的硬件事实 |
| Qwen 等模型的 MindIE / vLLM-Ascend 指南 | 只证明指定部署路线 | 不能因此声称 Qwen 原始预训练使用昇腾，或模型仓自身实现了完整 NPU 后端 |
| OpenRLHF | 上游合入未确认，另有第三方适配线索 | [Ascend PR #605](https://github.com/OpenRLHF/OpenRLHF/pull/605) 已关闭且未合并；第三方 fork 应另核版本、运行路径和维护状态，不能算成上游默认支持 |

这一区分也适用于媒体新闻。“计划采用”“采购设备”“适配完成”“上线服务”是不同阶段。仅凭采购、路标或匿名消息，本文不把某家公司所有模型训练归入昇腾。

## 五 如何解读这张生态地图

### 已有真实采用 但不能从条目数推市场份额

公开材料同时出现厂商自研、联合研发、非华为主体的模型实验和开源上游适配，说明昇腾的使用并非局限在一个封闭模型栈。真正有分量的变化，是不同组织在不同阶段公开了可检查的硬件与软件配置。

但这些记录不能直接推算装机量、收入、市场份额或集群利用率。一个模型家族可能发表多份报告，一个后端可能服务多个上层框架，一篇论文还可能复用同一集群。**论文数量、仓库数量、用户数量和芯片数量是四个不同统计单位。** 本文不将它们相加。

### 软件链条比单个 import 更接近迁移难度

实际迁移通常跨越以下链条：设备运行时与内存、算子覆盖、自动微分、分布式通信、训练并行策略、权重格式与同步、推理调度，最后才是应用的质量和服务指标。

Intern Lumina U2 的附录 D 是一个具体例子：除了导入迁移模块，还处理 grouped matmul、MoE 反向、attention mask 语义和内存约束。`transfer_to_npu` 可以减少机械式设备替换，却不能自动保证算子语义、性能与数值一致性。该报告也说明，已有 CUDA 字符串不一定意味着最终仍跑在 GPU。[适配细节](https://arxiv.org/html/2610.20818v1)

相似地，llama.cpp 直接通过 CANN 使用昇腾，Paddle 采用自定义设备，MindSpore 有另一套执行栈。**以 `torch_npu` 为入口做搜索很有效，把它当唯一判据则会系统性漏检。**

### 上游集成正在扩大 版本组合仍决定能否落地

Transformers、Accelerate、Diffusers、DeepSpeed、Ray、SGLang、Liger 等仓库已有实际代码，是比单一宣传页面更可审计的信号。但用户部署的是一个具体组合：芯片子型号、驱动、固件、CANN、框架、适配包、模型、精度和分布式策略。任一维度变化，都可能改变结论。

本轮看到的几个真实边界很有代表性：LlamaFactory 新旧版本的 QLoRA 说明不同；ms-swift 的 Liger/SGLang 集成范围不等于上游支持范围；LMDeploy 同版本不同页面对 A3 模型范围有不一致；llama.cpp 的 310P 与 910B 精度路径不同。它们说明“支持昇腾”需要拆成可执行的配置清单，而不是一个永久的勾选框。

### 性能比较必须保留原来的分母

本次不制作一个跨论文的“昇腾对 GPU 加速倍数排行榜”，因为公开实验的比较对象并不统一：

- xLLM 的主要对比是在指定昇腾硬件上的不同服务框架，包含版本与 SLO 差异。
- CloudMatrix384 的系统容量、实际实验资源和理想负载均衡预测不是同一个量。
- Intern Lumina U2 的 NVIDIA 参考线训练预算较小，不是严格等预算硬件对照。
- DiC 在 910B 训练、A100 测吞吐；Attention Editing 同时包含 H800 与 910B 实验。
- 算子微基准、训练每步时间、端到端生成速度、服务 goodput、能耗与总成本，不能互相代替。

因此，引用性能数字时至少需要保留：模型和权重版本、精度、卡数、软件版本、输入输出长度、batch、延迟约束、比较基线，以及该数值是实测还是预测。缺一组关键条件，就应降低结论强度。

## 六 检索覆盖 方法与盲区

本次采用分主题、分来源的小批量查询，先用搜索引擎发现候选，再回到原始论文、会议附录、官方模型卡和仓库文件。代码检索不仅看 `import torch_npu`，还补查 `torch.npu`、`npu_fusion_attention`、HCCL、CANN、AscendC、ACLNN、NPU 后端目录、安装依赖及 CI 配置。对同一项目的镜像、fork 与上下游组件去重，不按搜索命中数量计数。

检索组合包括：

- 硬件词：`Ascend`、`昇腾`、`Ascend 910`、`910B`、`910C`、`NPU`，以及 Atlas / CANN 上下文。
- 任务词：pretraining、fine-tuning、inference、serving、RL、GRPO、multimodal、diffusion、GNN、operator、compiler、scheduling、HPC。
- 来源词与域名：arXiv、ACL Anthology、NeurIPS / ICLR / MLSys / USENIX 会议材料，GitHub、Hugging Face、ModelScope、Gitee / GitCode 及官方文档。
- 反向追溯：从已发现论文的实验设置、项目 README、适配指南与运行示例，核对实际硬件与相关实现。
- 分支与身份核查：跟踪仓库迁移、更名、官方专用分支与 release 分支；AReaL 的昇腾专用分支、FlagGems 的上游后端，是仅检查旧仓名或默认文件路径容易遗漏的例子。

查询遵守工具限额与访问限制，没有使用代理轮换、验证码破解或高频爬取来绕过限制。检索过程中未把聚合站、自动摘要页或搜索结果的抓取日期直接当作原始发表日期；这些页面只用于发现线索，核心结论尽量回到一手材料。

**这仍然不是穷尽性清单，也不是可以计算召回率的正式系统综述。** 公开搜索无法覆盖未发表的企业部署、私有仓库、所有论文附录、尚未建立索引的新提交，以及大量只在 GitCode/Gitee 或中文社区流传的材料。ONNX、TVM、JAX、传统 CV / 语音、小型学术任务与设备边缘应用，本轮也没有完成逐仓逐论文穷举。某些原文遇访问验证或下载失败，已保留为待核项，没有伪装成读过。

可继续补全的高价值方向是：逐条检查硬件 CI 的实际运行结果；补充公开训练日志和复现实验；把文档支持矩阵与已发行版本对应；为型号不明确的 Ascend 报告寻找作者明确披露；追踪候选论文的正式版本与勘误。新增材料应沿用同一规则：**记录证据的原话所能支持的范围，不把希望、适配或片段实验扩成完整部署事实。**

## 七 给读者的使用建议

如果关心“真实采用”，优先看 FRAME、CodeGeeX、Spark-Prover-X1、Open-Sora-Plan、Intern Lumina U2 与 xLLM 的逐阶段硬件证据。如果准备迁移项目，优先检查自身使用的框架与推理后端在特定版本的矩阵，而不是照搬别人模型的配置。如果做性能或采购评估，应在同一质量、延迟和成本约束下重跑自己的工作负载。

这张地图支持一个相对稳健的结论：**昇腾已经进入多个组织的真实训练与推理流程，开源软件支持也延伸到多个主流上游；它的成熟程度需要按任务、版本和硬件组合判断。** 继续扩大名单有价值，继续提高每条记录的证据质量更有价值。

**资料说明：** 全文链接均指向公开材料。论文年份或版本标注用于识别所依据的证据，不代表所有项目都在该年首次支持昇腾。未附固定提交的网页按核查日读取，后续可能更新；本站分析与作者性能声明已尽量分开表达。
