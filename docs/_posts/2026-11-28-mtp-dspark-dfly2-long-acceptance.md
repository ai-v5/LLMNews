---
layout: post
title: "MTP、DSpark、DFly2：投机解码要一轮接受 32 个 Token，还差什么？"
date: 2026-11-28T08:35:00+08:00
summary: "从 DeepSeek V3 的单步 MTP、DSpark 的半自回归与验算预算，到 DFly2 复用目标模型的稀疏 KV。用同口径数据和前缀存活模型，推导 16、32、64 token 接受长度的算法与系统门槛。"
section: explainer
label: "推理系统解读"
tags: [投机解码, MTP, DSpark, DFly2, 长上下文, 推理性能]
demo: false
sources:
  - title: "DeepSeek-V3 Technical Report，§2.2 / §5.4.3"
    url: "https://arxiv.org/abs/2412.19437"
  - title: "DSpark 技术报告，架构、调度与线上对照"
    url: "https://arxiv.org/html/2607.05147v1"
  - title: "Tencent Hy DFly2 技术报告，v1"
    url: "https://arxiv.org/html/2611.34776v1"
  - title: "AngelSpec 开源训练实现和 draft 权重入口"
    url: "https://github.com/Tencent/AngelSpec"
  - title: "DFlash 原始论文"
    url: "https://arxiv.org/abs/2602.06036"
  - title: "Speculative Decoding 原始论文"
    url: "https://proceedings.mlr.press/v202/leviathan23a.html"
---

DFly2 论文的「128K」是输入上下文长度。它每轮仍只提议 **5 个**候选；表中均值还把目标模型补出的 1 个 token 算进去。跑得动 128K 上下文，和一次验算平均通过 32 个 draft token，是两个不同的突破。前者要减少 draft 对历史 KV 的重复存取；后者必须同时延长预测可靠性、压低验算成本，并在高并发下仍能兑现收益。

这三代方法分别解决了不同问题：**MTP 让同一个模型学会向前多看一步；DSpark 把昂贵的预测改成块并行，再用廉价串行修正和动态预算；DFly2 让 draft 直接复用目标已算出的稀疏位置及 KV。** 本文以公开论文和实现为依据，未来 16–64 token 的数字是模型推导，不是实测。

## 1. 先统一口径：提议、验算、接受、提交

一轮 decode 先从已确认前缀出发，draft 提议 K 个 token。引擎可以只把前 V 个交给目标验算。目标用因果 mask 在一次 forward 中打分，但只能提交从头连续通过的 A 个 draft token；第一个失败以后，后面的 logits 是在错误前缀上算的，不能直接保留。通常还提交 1 个目标 token：拒绝点做修正，或全部通过后补出下一 token。不计 EOS、停止串、工具停点及输出截断，提交长度 τ = A + 1。

| 指标 | 测量什么 |
|---|---|
| K / V | draft 生成多少、目标实际验多少；另记 kernel padding 后物理执行多少行 |
| A / τ | A 是连续接受的 draft 数；τ 是最终提交数。报告必须标是否含目标补发 |
| S(j) | 第 j 个候选仍属于有效连续前缀的概率；比只报平均值更能看清长尾 |
| TPOT / 系统 goodput | 单用户输出速度 vs 在 TTFT/TPOT 等约束内交付的总 token 或请求；两者都要看 |

贪心解码可以逐位比 argmax。随机采样要求更强：标准验算在已通过的前缀下，从 q 提议 x，以 min(1, p(x)/q(x)) 接受；失败时从归一化的 max(p−q,0) 重采样。p 是目标分布，q 是**真正生成候选的条件分布**。单位置接受概率等于 1−TV(p,q)，不是 top-1 命中率。只要验算和回退正确，draft 可以很弱，输出分布仍能保持；不代表同一随机种子逐 token 相同，也不涵盖不同量化或不一致的采样/精度实现。[标准 speculative sampling](https://proceedings.mlr.press/v202/leviathan23a.html)

## 2. MTP、DSpark 和 DFly2 的架构，究竟差在哪

![V3 式 MTP 做浅预测；DSpark 块并行、轻量串行修正并控制实际验算量；DFly2 复用目标稀疏索引和 KV。]({{ '/assets/specdecode-draft-paths.svg' | relative_url }})

*图解：按三份公开报告重绘，讲的是草稿侧机制；三者均需目标验算。* [查看原图]({{ '/assets/specdecode-draft-paths.svg' | relative_url }})。

| 方法 | 如何生成候选 | draft 从哪里取上下文 | 最适合解决的问题 |
|---|---|---|---|
| DeepSeek V3 式 MTP | 主干 hidden + 前一 token embedding，附加 Transformer 沿因果链预测；V3 常用 1 个额外候选 | 主干当前表征输入附加模块，历史状态依实现 | 简单的一步投机；额外目标也用于改善主干训练 |
| DFlash | anchor + 多个 mask，轻量骨干一次并行铺开多个位置 | 多层目标 hidden 投影到 draft 自己的 KV；原版看全前缀 | 摊薄多步提议的骨干开销 |
| DSpark | 重的 Transformer 并行，轻的低秩 Markov head 逐 token 修正；另有置信度头 | 也是多层 hidden 注入 draft KV；官方 V4.1 的三层 draft 用滑窗，而非重读整段历史 | 让同一草稿块内部更一致，并按负载给验算预算 |
| DFly2 | 三层小 MoE 块并行，slot 内有轻量顺序修正 | 复用目标已缓存的 KV latent 和选好的索引；额外注入 anchor 对应的末层 hidden | 长上下文下同时保留远端可达性、压住 draft KV 容量和读取 |

**MTP 是一类训练目标，不是一种固定推理算法。** [Gloeckle 等](https://arxiv.org/abs/2404.19737)研究独立多头；DeepSeek V3 则把每个深度串起来，用共享 embedding/LM head，训练时给定真实上一个 token，再预测后一个。原报告的「预测两个」是主干 1 个加 MTP 额外 1 个，不是额外提议 2 个；第二个 token 接受率 85–90%，报告约 1.8× TPS。这个浅路径省的是目标 forward 次数。即使把一个模块递归用来多提几步，也多出草稿因果链，并遭遇训练真前缀与线上 draft 自生成前缀的分布偏移；不能把 85–90% 当完整长块各位保证。[V3 §2.2、§5.4.3](https://arxiv.org/html/2412.19437v2)

**DFlash 并行的是重计算，不是让 verifier 跳过因果依赖。** 典型实现从目标多个层取 hidden，投影进 draft 层的 KV，用 anchor 和 mask 跑一次小模型。这样可以把数次小 forward 换成一次块 forward，但各位置基础预测没有消费同轮已采样的前一个候选；若第 1 位选择了变量名、数字或工具参数的不同分支，后面可能继续沿另一分支生成。**DFlash 2 与 DFly2 是不同项目**；DFlash 2 也在处理块内依赖，不能把原版 DFlash 的表现外推给所有后继。[DFlash](https://arxiv.org/abs/2602.06036) · [DFlash 2](https://inco.ai/blog/dflash2/)

**DSpark 给块内依赖做低成本建模，再控制目标实际要验多少。** 骨干先为多个候选位置产生 base logits，低秩 Markov 修正根据前一已采样 token 改变当前 logits。这条小串行链不重复跑整个 Transformer。训练冻结主干，通过交叉熵、分布匹配和置信度损失优化 draft；生产路径用条件置信估计各个位置的前缀存活概率。简单成本模型里，把更多候选放进目标批次的收益是多接受几个 token，代价是目标每秒能跑的验算轮数下降；DSpark 按整个 batch 分配位置，而不是人人固定验五个。论文专门证明不能事后偷看候选再决定是否把该候选送验，否则随机采样有选择偏差；论文里的线上实现用前两轮的置信信息确定全批容量，再按当前前缀累计置信度排序分配；这样选全局预算时不回看当前提议结果。真实 kernel 台阶、padding 与长序列不均衡都会改变成本曲线。[DSpark §§3、5 与附录 A](https://arxiv.org/html/2607.05147v1)

**DFly2 共享两样东西，单共享一样不够。** 只共用目标 KV、却仍扫完整前缀，draft 计算和带宽会随 L 增长；只共享 top-k 索引、仍保有 draft KV，则长上下文容量和 Prefill 投影还在。DFly2 让每个 draft 层与一个目标稀疏 attention 层配对，读取上一轮验算在 **anchor 前一行** 已选出的索引，以及目标已有的 KV latent；同一 draft 层各候选位共用这组索引。不把后面的真实验证结果提前喂给 draft。训练用冻结的目标 indexer 重算；线上读取已算过的结果。目标自身仍需运行 indexer 和 verifier；消失的是 draft 对整个历史的额外索引、持久 context KV 和 Prefill 构建。局部工作区、权重、PD 传输的一份 anchor hidden 仍存在。[DFly2 §§3–4](https://arxiv.org/html/2611.34776v1)

- **DeepSeek V4.1 Flash**：三层配对索引 28/32/36，512 个远端候选位置 + 128 个近窗位置 + 6 个块内位置，论文的读取预算 646。**GLM-5.3-Flash** 的 Top-512 是每组 4 个位置，共 2,054；**Hy4 flash** 的 Top-2048 也是 2,054。这里是各 draft 层的预算，不能把 Top-512 一律理解成 512 个 KV token 或用作整机字节数。
- **为什么复用上一行有效？** DS-V4.1 Flash 的短块实验里，用上一行 Top-512 去覆盖各候选位置自己会选中的 Top-512，按 index score 权重衡量平均约 0.80；加两行历史可到约 0.86，合并多层与历史能更高，但接受串只小幅改善。这是**索引分数覆盖率**，不是 Attention softmax 质量、准确率或接受率。只测了当前短块；不能假定第 32、64 位还有同样覆盖。
- **共享又不等于复制整个目标。** 三层 draft 由配对层初始化 attention 和部分专家，另外注入末层 hidden 缓解 KV 中没有最新输出语义的问题；slot 修正除了看前一个候选，还可读共享上下文与已生成的块内前缀。训练用按位置加权的目标分布蒸馏。论文三套 draft 的参数量 6B–14B、每 token 激活 0.4B–1.1B，不能把 6B–14B 当每 token 计算量，也不能忽略权重常驻和专家派发。
- **开源状态**：腾讯 11 月 26 日公开报告、训练实现和 [DS-V4.1-Flash B6 权重](https://huggingface.co/AngelSlim/DS-V4.1-Flash-DFly2-B6)、[GLM-5.3-Flash B6](https://huggingface.co/AngelSlim/GLM-5.3-Flash-DFly2-B6)、[Hy4-flash B6](https://huggingface.co/AngelSlim/Hy4-flash-DFly2-B6)。B6 是 anchor 加 5 个 draft 槽。核对了 [AngelSpec 固定提交的 DeepSeek 配置](https://github.com/Tencent/AngelSpec/blob/9f11dd0450c44ec5a0a7c18eb35f8a8565fb52ee/angelspec/config/dfly2_dsv41_flash_draft_config.json) 中的配对层、Top-512、128 窗和 slot0 融合。能下载权重、能训练，不保证任意 checkpoint 或任意 vLLM／SGLang／硬件的发布镜像可直接运行；共享的 KV 布局、压缩、paging、索引含义都必须匹配。

腾讯第一代 [DFly／AngelSpec](https://arxiv.org/abs/2607.25852) 已有块生成、轻量串行修正及 batch 级验算资源分配。DFly2 新的关键不只是调度，而是把 draft 设计改成原生稀疏 target 的消费者。DeepSeek 官方 [V4.1-Flash-1017](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017) 使用 DSpark；权重命名若含 `mtp` 并不说明它仍是 V3 式 MTP。也不要把 DSpark 研究版、DFly2 论文中同配方重训的 DSpark，以及官方部署的 DSpark 当成同一个 checkpoint。

## 3. 同口径实测：DFly2 为什么速度能涨得比接受长度多

以下是 [DFly2 v1 表 6–7](https://arxiv.org/html/2611.34776v1) 的**三类任务组均值**。每格为 DFlash → DSpark → DFly2，含目标补发。H20、TP8 接受长度测量，2K chat／不思考，三个 draft 均为作者同配方重训的约等规模三层模型，K=5；不是拿原厂 DeepSeek 线上 checkpoint 直接跑。表中 T=0 便于对比；各任务的随机采样结果见论文，不能把贪心结果当高温 RL rollout。

| 目标模型 | 通用 τ，T=0 | 长上下文 τ，T=0 | Agentic τ，T=0 |
|---|---:|---:|---:|
| DeepSeek V4.1 Flash | 3.65 → 3.81 → **4.12** | 3.40 → 3.23 → **3.74** | 3.55 → 3.35 → **4.06** |
| GLM-5.3-Flash | 3.43 → 3.68 → **3.96** | 2.86 → 3.05 → **3.85** | 2.95 → 3.10 → **4.03** |
| Hy4 flash | 3.58 → 3.81 → **3.96** | 1.63 → 3.20 → **3.63** | 2.00 → 3.16 → **4.11** |

Hy4 flash 长上下文中原版全历史 DFlash 的 1.63 不能代表局部版 DFlash：同窗 DFlash† 是 3.13。对 DS-V4.1 Flash 的 CodeSpan 64K，随机采样时分别 3.13、2.92、3.59。对 GLM 128K LongSWE，分别 2.64、2.79、3.52。输入很长时，DFly2 相对更稳；但这里实际每轮多提交的是零点几到约一个 token，远非 32。

- **单请求，含不含 Prefill 结果不一样。** DS-V4.1 Flash 的 agentic 组，DFlash 对无投机为 **2.78× decode / 0.90× 端到端**，DSpark 为 **2.61× / 1.44×**，DFly2 为 **3.10× / 1.50×**。DFlash 的额外 Prefill 成本会吃掉 decode 收益；DFly2 在个别任务的端到端也不一定最快，例如 GLM 的 MemAgent 是 0.98×，仍略低于不投机。[表 9](https://arxiv.org/html/2611.34776v1)
- **高并发，必须按相同单用户速度读。** DS-V4.1 Flash 图 7 对比同配方 DSpark：短文本 +28%，CodeSpan 64K +62%，SWE 64K +81% 系统输出吞吐。短文本是 1P1D，两个 64K 场景用 8P1D，每实例 DP8×TP1/EP8，贪心、长场景并发 1–32。是曲线等用户速度点，不是相同并发、单 kernel、或每 GPU 通用提升。快的原因既有较长的接受串，也有更薄的 draft context 和服务容量；现有数据不能把 +81% 准确归因给某一个改动。
- **容量可以反推，但要分清理论和实测。** 论文表 2 的 BF16、随 L 增长的 KV：DS-V4.1 Flash 4.4 KiB/token；三层自有全历史 draft 再加 3.4 KiB/token。64 Ki tokens 下按配置算，后者约多 **217.6 MiB/请求**；没有分页碎片、rank 切分和量化口径，不是单卡实际显存。论文的 1.73× 是在 32K 固定 KV 池下，对全历史自有 KV 的**并发容量估计**；对 DSpark 式滑窗并不会再自动增加 73%。
- **DSpark 自己的线上对照是另外一组证据。** DeepSeek 在 V4 Preview 的真实流量里用 DSpark-5 对当时 MTP-1：V4 Flash 在 80 tok/s/user 时总吞吐 +51%，V4 Pro 在 35 tok/s/user 时 +52%；更高交互门槛的夸张倍数伴随 MTP 基线接近其容量边界。它验证的是整个系统的线上曲线，不是只给 Markov head 计收益；不能跟 DFly2 的 +62%／+81% 相乘。[DSpark 图 7](https://arxiv.org/html/2607.05147v1)

## 4. 为什么把 5 改成 64 不行：前缀存活是乘法

![每位条件通过率恒为 95% 时，第 16、32、64 位的前缀存活率约 44.0%、19.4%、3.75%。K=64 平均接受 18.29 个草稿，不含目标补发。]({{ '/assets/specdecode-prefix-survival.svg' | relative_url }})

*图解：按下文的恒定条件通过率模型计算，不是论文实测。* [查看原图]({{ '/assets/specdecode-prefix-survival.svg' | relative_url }})。

设 qⱼ 为**已经通过前 j−1 位**时，第 j 位通过的条件概率，暂不考虑预算剪裁。S(j) = q₁×…×qⱼ，平均接受的 draft 数 E[A] = S(1)+…+S(K)。这个连乘是条件概率链式法则，不需假设各位置独立。下面用每位条件概率都相同的玩具例子，隔离 K 的影响；平均值**不含 target 补发**。

| 每位条件通过率 | K=5 平均 A | K=16 | K=32 | K=64 | 64 位全部通过 |
|---|---:|---:|---:|---:|---:|
| 90% | 3.69 | 7.33 | 8.69 | 8.99 | 0.12% |
| 95% | 4.30 | 10.64 | 15.32 | 18.29 | 3.75% |
| 97% | 4.57 | 12.47 | 20.13 | 27.73 | 14.24% |
| 99% | 4.85 | 14.71 | 27.23 | 46.97 | 52.56% |

两个推论。第一，90% 在 K=5 看起来已很好，拉到 64 却仍约 9 个，剩下 55 个大多是无效验算。第二，即使每位 99%，用 K=32 平均也只接受 27.23。若想让**一半轮次完整通过** 32／64／128 位，等效每位条件通过率要分别达到 **97.86%／98.92%／99.46%**。这和「平均接受 32」不是同一个目标。平均要 32，可以用更长候选且有足够高的存活曲线，如 K=64、平坦的 98% 在这个模型里给约 35.55；真实任务的后半位通常不是平的，工具调用边界还会强制打断。

**单轮目标太难时，更现实的是混合服务。** 状态稳定、源文本可复制、代码补齐、结构化 JSON 的低熵片段可给较长深度；开自由回答、新一轮工具结果、推理分叉时主动缩回。无损 verifier 不会因为代码“写得也对”而多接受一位；要么让 q 更接近 p，要么用经过证明的另一种 verifier，或明确改变质量合约。

## 5. 真正拉到 16–64，四道门槛要同时过

**一：用自己的草稿前缀训练，直接盯住存活，而非只看逐位 CE。** Teacher forcing 看的是正确前缀，线上后半段消费的是 draft 自生成的前缀；应在目标同版本、同温度、同 top-p 与约束下采样草稿，用目标蒸馏或针对期望接受长度做训练。层级方案可以并行铺 8–16 位，再用很窄的因果修正、稀疏重取或验证少量分支；不能把 64 次串行 LM-head、跨卡路由或小 GEMM 都塞进原来的短轮预算。优先在 8、16、32 位报告 S(j) 和条件 qⱼ，再查尾部是词表分布、长程检索还是错误分支。低熵片段也可以用可复制的原文、仓库片段或受约束的语法分支当便宜提议；对照目标必须使用同一约束，验算仍不能省略。现有 [D-REAL](https://arxiv.org/abs/2611.10432) 在 Qwen3-8B、DSpark／DFlash 2 上把目标改成单轮期望接受长度，报告最多约 +0.23 token、最高 +9.4% 服务吞吐；不是 32 token 已实现。[受控复测](https://arxiv.org/abs/2610.24993v3) 也显示统一训练/推理配置会缩小性能差距，昂贵的 token 依赖并非总划算。

**二：长块必须动态刷新“读哪里”，但不重复扫整个历史。** DFly2 的五位共用索引适合局部主题稳定时。如果第 24 位转向新文件、引用旧函数或切换数学分支，上一行 Top-k 可能完全不够。优先做按子块用量增减或刷新索引、近窗保底、按层合并目标已算的索引、对低置信位置才额外检索；再看能否异步把选中页备好。对 dense target，没有可直接借用的稀疏选择，跨过这道门要用 [LongSpark](https://arxiv.org/abs/2609.37029) 一类固定全局摘要、局部窗口、边界 hidden，或模型本身提供压缩上下文。只要这些近似只在 draft 侧，精确 verifier 仍能保输出分布；如果在 target 侧换成近似 top-k，就必须重新定义参考目标。

**三：让目标 verifier 把长块当小型 Prefill 做，但保留确切的提交语义。** 通常目标前向次数减少，而每轮处理的行数增加。高并发时目标的 GEMM/MoE/attention/索引/LM-head 可能先饱和。用 ragged pack，把不同请求的实际 V 扁平化，避免统一 pad 到 64；为同一前缀的多行共用 KV tile，融合 sparse gather、去重和目标验算；用分页 scratch、版本化 KV 和事务式提交，拒绝点后的 KV、压缩池、滚动窗口、Mamba/GDN 等递归态与 RNG 都要正确回退。树形提议可覆盖多条分支，但分支数不能指数长；同一 token budget 下要比较多分支是否比单长串更好。[ICLR Block Verification](https://proceedings.iclr.cc/paper_files/paper/2025/file/3e710b42b1a9ed898f607ec0f4fcc971-Paper-Conference.pdf) 展示了不按原逐 token 规则验算、仍能保持目标分布的路径；它的修正机制是算法的一部分，不等于允许跳过不匹配 token 或省掉同一批目标打分。多分支、动态截断、约束采样都要各自证明或回归分布。

**四：把候选 token 写进资源调度账，先保护 p99。** 粗略视角是一轮成本除以提交量：TPOT ≈ (T_draft + T_verify + T_commit + T_sched)/E[τ]；这里各项取曝光时间，重叠时看关键路径而不是相加所有流耗时。系统侧分子是同轮所有请求的提交 token。一个简化判断：当前总提交期望 G、轮时延 C，额外验一位带来存活收益 s 和增量成本 ΔC，则仅当 s > G×ΔC/C 时才提高瞬时吞吐；队列、设备和 SLO 会再约束。例：G=100、C=10 ms，额外一位若多花 0.1 ms，需要 s>1，必不划算；若同一个 tile 的空行只多 0.01 ms，门槛是 s>0.1。把预校准的 GPU/NPU shape 台阶、EP 最大 rank、KV 读流量及队列反馈放进预算，比硬设每请求 32 更有用。

### 硬件上最先撞哪一道墙？

用一个**形状示意**说明：32 个 active 请求，K 实际全验，连同每请求一行目标工作，K=5 时约 192 行，K=32 时 1,056 行，K=64 时 2,080 行，分别是第一种的 **5.5×／10.8×**。这是逻辑 verifier 行数，不等于 step 时延倍数。若不提前削减，在上表 95% 的假设下，K=64 平均只提交 19.29 个 token，约 65 个目标行换 19.29 个提交，约 3.37 行/提交；K=5 则是 6/5.30≈1.13。低并发的权重复用可以抵消部分行开销，高负载下不能指望同样的抵消。低并发原本读权重受限时，更多行能提升 GEMM 利用率；高 batch 时就可能转到矩阵算力、稀疏 KV gather、Top-k、LM head 和专家 all-to-all。草稿块还会放大不同请求长度与专家热点，最慢 rank、跨机流量和 rollback scratch 峰值比均值更早暴露问题。**NPU 实现要测实际物理 padding、稀疏页带宽、EP 尾部和 graph bucket 切换；H20 论文的吞吐数字不能拿来填 950DT 或 GB300。** [vLLM Ascend 的公开投机文档](https://docs.vllm.ai/projects/ascend/en/v0.30.0/user_guide/feature_guide/speculative_decoding.html) 同样指出 batch size × draft 深度过大时 TPOT 会逆转；这不是该版本已支持 DFly2 的证明。

## 6. 我会怎么验收一个声称“接受 32”的系统

| 试验 | 固定／扫参 | 要拿到的证据 |
|---|---|---|
| 算法上限 | 同 target/checkpoint、采样策略；K=1/5/8/16/32/64，区分代码、推理、开放聊天和工具输出 | 分别报提议 K、实际 V、有效 A、提交 τ、S(8/16/32/64)，以及拒绝原因；禁止只报成功全收的轮次 |
| 长上下文 | 长度 4K/32K/128K；固定冷启动、热缓存、PD 配比与 KV 预算。对照短窗、仅 KV Share、KV+Index Share、动态刷新 | draft 读多少物理页、占多少持久显存、prefill 重算/搬运多少；验证增量收益能否覆盖更大的稀疏 gather |
| 集群收益 | 同硬件卡数、target 量化与 serving engine；从低并发到入队过载，固定 RL 采样温度／截断和 max output | TTFT、TPOT、p99、SLO goodput、tokens/卡秒；RL 再看完成有效轨迹/卡小时、工具时间和 rollout 尾部。不要用无工具的纯 decode 峰值代表整作业 |
| 无损和稳定 | Greedy token 一致性；随机采样检查小分布精确性、长规模分布回归、停点和约束；注入拒绝、EOS、换页和抢占 | 检查已提交 KV/递归状态与 target-only 基线，验证 sampler、logprobs、回退与版本兼容；避免误把采样波动解释成质量变化 |

**我的判断：** DFly2 最可能被广泛采用的思想，是让 draft 和 verifier 共享目标已经付费获得的上下文状态。它解决的是「长输入时多猜几个仍划算」。要走到「混合负载平均接受 16、32 甚至 64 个 draft token」，应先攻逐段可靠性和成本感知的 ragged 验算，别先把固定 K 调大。下一步真正有说服力的结果，不是某个代码样本一轮通过几十位，而是在公开的混合、带工具、长上下文负载上，同时给出**前缀存活曲线和同 SLO、同卡数的 goodput**。
