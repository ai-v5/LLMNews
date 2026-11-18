---
title: "SenseNova-Loop 的部署账：9B 权重，不等于 9B 计算，也不等于一份 KV"
date: 2026-11-19T07:30:00+08:00
summary: "官方 AWQ/GGUF 已发布。拆开共享权重、重复执行、长上下文缓存与后端支持，解释为什么 4-bit 权重不是 4-bit 全链路，512K 上限也不是 512K 部署实测。"
section: explainer
label: "模型部署与缓存"
tags: [SenseNova, 循环模型, KV缓存, 量化, 推理性能]
demo: false
sources:
  - title: "SenseNova-Loop 正式模型卡"
    url: "https://huggingface.co/sensenova/SenseNova-Loop-9B"
  - title: "官方 AWQ 模型卡与提交历史"
    url: "https://huggingface.co/sensenova/SenseNova-Loop-9B-AWQ/commits/main"
  - title: "官方 GGUF 模型卡"
    url: "https://huggingface.co/sensenova/SenseNova-Loop-9B-GGUF"
  - title: "vLLM 原生支持 PR"
    url: "https://github.com/vllm-project/vllm/pull/64832"
---

**最重要的判断：Loop 把参数存储与执行深度解耦，不会自动把计算、访存和缓存都压缩到普通 9B 模型的水平。** 低精度权重让它更容易装进显存；是否更快、是否能在长上下文下保持并发，则是另一组问题。

本文的新增事件是 **11 月 18 日官方 AWQ 与 GGUF 权重公开**，不是把 17 日正式模型发布重报一次。HF 历史显示，AWQ 权重及 MTP 草稿于 18 日 08:53 UTC 加入，GGUF 于 09:28 UTC 加入；AWQ 卡片在 20:52 UTC 又把部署路径明确指向 LightLLM 的专用分支。依据为公开模型卡、提交记录与后端 PR；本文没有运行模型，也不提供自测吞吐。[AWQ 历史](https://huggingface.co/sensenova/SenseNova-Loop-9B-AWQ/commits/main)、[GGUF 历史](https://huggingface.co/sensenova/SenseNova-Loop-9B-GGUF/commits/main)。

## 一、先分清三种“大小”

正式模型约 9B 独立参数，32 个物理 decoder 层；中间 [4, 28) 的 24 层执行两遍，因而一次前向实际经过 56 次层计算。厂商另给出约 14.6B 的推理等效参数口径。后者不是 14.6B 独立权重，也不是相同硬件上的延迟比。每四层采用三层线性注意力、一层全注意力；循环区还包含双流 mHC。[正式模型卡](https://huggingface.co/sensenova/SenseNova-Loop-9B)。

| 应该计量什么 | Loop 带来的变化 | 不能据此声称什么 |
| --- | --- | --- |
| 独立权重字节 | 两次执行可指向同一份参数，减少重复存储 | 每 token 只读取这些参数一次 |
| 实际算子执行次数与 FLOPs | 共享层仍要重新计算 | 9B 参数必然具有普通 9B 的延迟 |
| 每次访问的注意力/循环状态 | 同一层的不同访问接收不同隐藏状态 | 权重共享就能合并两次访问的 KV |
| 整个请求的成本 | 还包含 prefill、输出长度、草稿验证、工具等待 | 单个 decode token 更快就意味着任务更便宜 |

这是从结构出发的分析，不是额外的性能实测。尤其不要把 56/32 直接写成端到端时间倍数：embedding、视觉编码器、输出头、算子融合与调度都不按这个比例缩放。

## 二、共享 W，为什么不能共享 KV？

用一层的线性投影作示意：第一遍的键是 `K₁ = h₁Wₖ`，第二遍是 `K₂ = h₂Wₖ`。共享的是 `Wₖ`；经过前一轮计算以后，`h₂` 通常已不同，因此不能用同一份历史 K/V 替换两次逻辑访问的状态。

这个判断不仅是形式推导。[vLLM #64832](https://github.com/vllm-project/vllm/pull/64832) 明确为每次 loop visit 保留独立 attention/recurrent state，并在权重处理完成后再绑定共享参数。所以它还有一个容易漏掉的工程差别：**加载阶段权重峰值可能高于稳态权重占用**。拿模型文件大小预测启动能否成功，会漏掉这部分。

按公开的层模式推导，56 次访问中有 14 次全注意力、42 次线性注意力。若按 32 个物理层只分配 8 份全注意力缓存，就把应计的 14 份误写成 8 份，低估约 42.9%。这不是 mHC 双流再乘二：残差流数量与 KV head 数、逻辑缓存槽是不同概念。

### 一个可以复算、但带前提的容量模型

[Preview 的公开配置](https://huggingface.co/sensenova/SenseNova-Loop-9B-Preview/blob/main/config.json)给出 4 个 KV heads、head dimension 256。**若正式版及目标后端沿用这些维度，并按 14 次访问独立存储**，单条 262,144-token 序列的全注意力缓存净载荷为：

```text
M_KV = 14 × 2(K、V) × 4(KV heads) × 256(head dim)
       × 262144(tokens) × 每元素字节数
```

| 缓存元素精度 | 条件计算的全注意力 KV 净载荷 |
| --- | ---: |
| BF16 | 14 GiB |
| 8-bit | 7 GiB |
| 4-bit | 3.5 GiB |

这里不含 scale、分页碎片、权重、42 次线性注意力访问的 recurrent/conv state、视觉和 MTP 开销以及运行时 buffer。它不是正式版某后端的实测容量，不能直接推出“某张卡可跑几路”。本文未取得 gated 正式 BF16 配置文件，因而保留此前提，而不是把 Preview 的配置冒充正式文件。

## 三、KV 从 8-bit 变 4-bit，总显存不会减半

厂商给出的低内存表，是 **W4 固定时的预计最低 GPU 内存**，并非同硬件、同后端、同并发的运行曲线：[官方容量说明](https://huggingface.co/sensenova/SenseNova-Loop-9B#low-memory-deployment)。

| 上下文 | W4 + KV8，官方估算 | W4 + KV4，官方估算 | 按表复算的总量下降 |
| --- | ---: | ---: | ---: |
| 64K | 约 10 GiB | 约 9 GiB | 约 10% |
| 128K | 约 12 GiB | 约 10 GiB | 约 16.7% |
| 256K | 约 15 GiB | 约 12 GiB | 约 20% |

总量还含不会随着 KV bit-width 减半的项目。因此即使理想 KV payload 减半，总显存也只下降其中一部分。表中的约 4.9 **GB** 权重数字也不要未经换算当作 GiB。

这些容量点止于 256K；模型声明的 512K 上下文上限不等于已经给出了 512K 部署实测。更不能把表里的最小内存预算直接当成高并发服务配置。批量增大后，权重可摊薄，但每序列状态与缓存仍需增长。

## 四、当前能用什么，和已经证明什么，是两回事

| 路径 | 当前公开证据 | 尚未得到证明的部分 |
| --- | --- | --- |
| 官方 AWQ | 4-bit 权重，包含量化 embedding/output head；附可选 MTP 草稿。卡片最新指向 LightLLM `sensenovaloop_awq` 分支、单卡文本服务示例 | AWQ 相对 BF16 的独立质量消融；该示例的多模态、KV4 或 256K 性能 |
| 官方 GGUF | 提供多种量化格式；快速开始指定 OpenSenseNova 的 llama.cpp fork，示例上下文为 4096 | 任意上游版本开箱兼容；该示例代表 256K 或 512K 实测 |
| vLLM PR #64832 | Preview 的未量化文本路径，独立 visit 状态、共享权重处理和若干正确性检查 | 正式 AWQ、KV4、多模态已经进入稳定版 |

依据：[AWQ 卡片](https://huggingface.co/sensenova/SenseNova-Loop-9B-AWQ)、[GGUF 卡片](https://huggingface.co/sensenova/SenseNova-Loop-9B-GGUF)、[vLLM PR](https://github.com/vllm-project/vllm/pull/64832)。本次读取的 AWQ 卡片版本为 `64bd16e`，GGUF 为 `11c1210`；vLLM PR 仍为 open。

AWQ 页面明确说，展示的基准分数和 BF16 示例继承自基础模型卡。这些分数不能当成量化后精度不变的证据。类似地，正式版相对 Preview 的能力改善，也不是“多跑了一遍 loop”的消融，因为两者默认都为两遍。

## 五、怎样评估它的真实性价比？

以下是建议的实验设计，而非已完成的实验。先固定 checkpoint、后端 commit、硬件、输入输出长度和采样配置，再逐项改变变量：

1. **拆容量。** 分别记录加载峰值、prefill 峰值、decode 稳态占用；对 4K、64K、128K、256K 分组，用多点斜率估计每 token 缓存字节，不把预留池大小当成有效数据量。
2. **拆低精度。** 先固定 W4 比 KV8/KV4；再固定 KV 精度比 BF16/W4。否则无法知道收益来自权重、缓存还是换后端。同步跑长上下文检索、工具调用与图文质量测试。
3. **拆延迟和吞吐。** 固定并发测 p50/p95 TTFT、TPOT；再在相同延迟门槛下找最大并发和合格输出 tokens/s。单序列峰值与满卡吞吐不能混成一个“快了几倍”。
4. **拆重复计算。** 记录 GEMM、注意力、mHC、量化转换与 launch 的时间比例，以及实际 HBM 读写。共享权重省的是容量；两次访问之间隔着整个循环块，不能假定所有权重一直留在片上缓存。
5. **单独开关 MTP。** 除吞吐外记录接受率、每步接受 token 数、草稿及验证成本；只比较最终接受的 token，不把草稿 token 当作交付吞吐。

对于带工具的 agent，再补上同任务集、同成功判据下的 **成功任务数/GPU 小时** 与每个成功任务的端到端时间。省显存如果能提高合格并发，是实用收益；如果代价是更长尾延迟、更多失败重试，单看 tokens/s 会得出错误结论。

## 结论

SenseNova-Loop 的价值主张是用较少独立参数承载更深计算。11 月 18 日的量化权重与后端说明，让部署路径更具体了，但还没有替代同口径的质量、吞吐与长上下文实验。评价它应坚持四本账：**独立权重容量、实际执行工作量、每访问缓存状态、成功任务成本**。只有把它们分开，才能判断“装得下”是否真的转化成“跑得快、跑得准、服务得更多”。
