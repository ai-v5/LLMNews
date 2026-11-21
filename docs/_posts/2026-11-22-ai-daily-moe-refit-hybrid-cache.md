---
title: "每日 AI 新闻｜MoE 权重同步提速，Qwen Flash-Next 训练与混合缓存有新实测"
date: 2026-11-22T05:37:00+08:00
summary: "Megatron 合并专家权重传输，TorchTitan 给出 Flash-Next 的图回放训练配方；昇腾 DSA 缓存分片、Blackwell 动态 EP 与 Qwen Code 也有新进展。"
section: daily
label: "AI 动态"
tags: [MoE, 强化学习, 训练系统, 昇腾, Blackwell, 智能体]
demo: false
sources:
  - title: "Megatron-LM #8606：按投影族打包 MoE 权重重分片"
    url: "https://github.com/NVIDIA/Megatron-LM/pull/8606"
  - title: "TorchTitan #6052：PLE 固定槽位"
    url: "https://github.com/pytorch/torchtitan/pull/6052"
  - title: "TorchTitan #6053：Flash-Next 训练配方"
    url: "https://github.com/pytorch/torchtitan/pull/6053"
  - title: "vLLM Ascend #22181：稀疏注意力 DCP"
    url: "https://github.com/vllm-project/vllm-ascend/pull/22181"
  - title: "TensorRT-LLM #22363：DeepSeek 动态 EP"
    url: "https://github.com/NVIDIA/TensorRT-LLM/pull/22363"
  - title: "TorchTitan #6172：混合注意力状态检查点"
    url: "https://github.com/pytorch/torchtitan/pull/6172"
  - title: "TorchTitan #6261：统一 KV 和状态内存池"
    url: "https://github.com/pytorch/torchtitan/pull/6261"
  - title: "vLLM #69028：Inkling 2 Mini"
    url: "https://github.com/vllm-project/vllm/pull/69028"
  - title: "llama.cpp b12600：Inkling 2 Mini"
    url: "https://github.com/ggml-org/llama.cpp/releases/tag/b12600"
  - title: "Qwen Code v0.28.3"
    url: "https://github.com/QwenLM/qwen-code/releases/tag/v0.28.3"
---

> 观察窗口（北京时间）：截至 11 月 22 日 05:37，向前 24 小时。PR 以合入时间计，版本以公开发布时刻计。文中硬件数字均为上游作者报告，并非本站独立复测。合入 main 不等于进入已安装的发行版。

今天最值得区分三个数字：**权重拷贝耗时、能容纳的上下文、完成一批 rollout 的时间**。它们分别对应通信粒度、缓存布局和调度效率；任何一个改善都不直接等于 RL 单步变快。

## 1. Megatron：权重不减，按投影族打包让机柜内同步快 2.27×

**发生了什么。** 11 月 21 日 08:27，[Megatron-LM #8606](https://github.com/NVIDIA/Megatron-LM/pull/8606) 合入。训练池给推理池更新权重时，把满足布局条件的同类专家投影集中成 EP 分片张量，替代按专家逐个发起 NCCL M2N 重分片。可连续读取时用视图，必要时暂存或散写；不支持的专家布局仍走逐专家路径。

| Nemotron-3-Ultra BF16，作者测试 | NCCL send/recv | 旧 M2N | 打包 M2N |
|---|---:|---:|---:|
| 单 GB200 NVL72 机柜，8 节点，2,248 GB 逻辑数据 | 4,597 ms | 1,602 ms | 706 ms |
| 单机柜，16 节点，4.50 TB | 3,410 ms | 3,210 ms | 1,302 ms |
| 双机柜，32 节点，8.99 TB | 32,042 ms | 35,891 ms | 22,615 ms |

**为什么值得关注。** 两个 M2N 对照都已启用拆分通信器，主要差别是传输粒度。第三行训练和推理各占一柜，数据经过 InfiniBand；同布局内新路径快 1.59×，不能从第一行与第三行的差异反推跨柜带宽，权重体量和副本数也变了。作者验证目标权重张量指纹与 send/recv 一致，但未测旧请求中途切版本的正确性，也不是 RL 端到端耗时。

## 2. TorchTitan：Flash-Next 的哈希嵌入表不再全量聚合，固定槽位换来图回放

**发生了什么。** 11 月 21 日 16:42–16:45，TorchTitan 合入 [模型与行分片 #6046](https://github.com/pytorch/torchtitan/pull/6046)、[固定槽位 #6052](https://github.com/pytorch/torchtitan/pull/6052) 和[训练配方 #6053](https://github.com/pytorch/torchtitan/pull/6053) 等五项改动。Qwen3.8-Flash-Next 的额外哈希嵌入表有约 51.2B 参数，BF16 约 95.37 GiB。表按 DP 行所有权分片，不参与主模型的 FSDP 全表 all-gather。每卡发查表 ID、取回向量，反向把梯度发回所有者。固定槽位继续在设备侧去重，并消除每批把动态 split 读回 CPU 的同步。

**为什么值得关注。** 每卡 16K packed token 时，DP16 固定槽位相对旧路径最坏 distinct-ID 数是 1.03×；DP64 推导为 4.10×，不是实测流量，也不是相对旧路径的实际流量。16 张 GB300 的另一个 30 步微调配方里，自然路由是 378.6–379.0 TFLOP/s/GPU、峰值 243.59 GiB；416.4 是强制均匀路由的诊断值。两者都不是 256 卡实测或收敛结果。给超节点建模时，把嵌入查表通信与 MoE 派发分开记账。

## 3. 昇腾 DSA：在 Decode 组分摊历史 KV，容量和时延分别算

**发生了什么。** 11 月 21 日 14:58，[vLLM Ascend #22181](https://github.com/vllm-project/vllm-ascend/pull/22181) 合入稀疏注意力 DCP 改动：各 rank 保留本地查询，跨 DCP 组收集该步引用的主注意力与索引器历史。没有本地查询的 rank 也须参加相应集合通信。MLA 的 DSpark draft 用自己的缓存；不等于所有 draft 路径都支持同样的并行。

**为什么值得关注。** 在作者的 64 张 A5、32P+32D 测试中，按单引擎启动时逻辑 token 容量口径，P 侧实际 DCP 从 1 到 8 后是约 114 万→530 万（4.65×）；不是物理 HBM 放大，也不是稳态吞吐。独立长输入冷请求对照里，约 128K 的服务端 TTFT 增约 1.5%、输入吞吐降约 1.5%。容量收益可以明显大于时延代价，但生产要另测热前缀、索引器通信和排队；不要把多项优化组合的成绩归给 DCP 一项。

## 4. Blackwell 动态 EP：用更多权重常驻换小批 Decode 少等一个慢 rank

**发生了什么。** 11 月 21 日 12:41，[TensorRT-LLM #22363](https://github.com/NVIDIA/TensorRT-LLM/pull/22363) 合入 DeepSeek-V4.1 NVFP4 的小批、试验性动态 EP 路径。MoE TP/EP 受限，两侧 EP 都保留全套 routed experts 的本地 TP 分片，运行时可把一部分专家计算移到另一侧，不改变 top-k 专家和权重，也不临时搬运专家权重。实现平衡的是本步**不同专家数**，不是每个专家收到的 token 行数。

**为什么值得关注。** 作者早期 GB300 对照在 Attention TP8、MoE TP4/EP2、6 行 Decode 下，报告动态路由让两个 EP 半组的用时差约 2.8→0.7 μs，每个 MoE 半层省约 1.44 μs；不是吞吐翻倍，也不是最终发布版验证。按公开模型形状、FP4 权重加块 scale 估算，在这个拓扑仅 routed expert 权重就会额外占约 35.6 GiB/rank，未含模型其他层或暂存。要看省掉的尾部时间能否抵偿 HBM，而不是只数 GPU 峰值。

## 5. TorchTitan：混合注意力要同时给 KV 和递归状态定预算

**发生了什么。** 11 月 21 日 15:53，[#6172](https://github.com/pytorch/torchtitan/pull/6172) 合入 64-token 状态检查点与 overlap 调度。一个 150-token 重复 prompt 可以恢复到第 128 token，而非全部重算；但原来能从 200 精确恢复的下一轮，新路径可能只恢复到 192。单 GB300、Qwen3.5-9B 的 32 prompt × 8 sample 测试，全部完成时间中位数 15.22→11.50 s，同时每活跃请求从 3 到 5 个状态槽，默认并发上限 512→428。

**为什么值得关注。** 同日 14:45 合入的 [#6261](https://github.com/pytorch/torchtitan/pull/6261) 是独立的内存池实验。统一分配相对默认静态切分，在单 GB300 的长输入测试中 819→771 s，短输入却 234→248 s；专门调过的静态长输入方案还能做到 739 s。统一池减少对固定比例的依赖，不是所有负载更快。两项改动没有公开联合测量，不能把收益相乘。

## 6. Inkling 2 Mini 进入两套推理引擎：循环层共享权重，不共享每轮状态

**发生了什么。** 11 月 22 日 00:19，[vLLM #69028](https://github.com/vllm-project/vllm/pull/69028) 合入 Inkling 2 Mini 支持；11 月 21 日 07:30 发布的 [llama.cpp b12600](https://github.com/ggml-org/llama.cpp/releases/tag/b12600) 也加入该模型。vLLM 支持固定三轮循环、逐轮保留独立 KV 与卷积状态、DSpark 推测解码；还接入了可变循环的研究权重。这里新增的是引擎支持，不是模型首次公开。

**为什么值得关注。** 重复访问同一组权重不意味着只计一份运行态缓存。vLLM 作者在 TP1、约 51K 上下文、开启 DSpark 时测到，1/8/32/64 个请求的验证步分别耗时 5.87/10.40/21.16/35.02 ms。它既不是端到端服务时延，也没有给出匹配的无推测解码基线。评估循环模型时应按层访问次数计状态，再查看可接受 token 的吞吐。

## 7. Qwen Code：让已绑定的会话接手 PR 变化

**发生了什么。** 11 月 21 日 09:45，[Qwen Code v0.28.3](https://github.com/QwenLM/qwen-code/releases/tag/v0.28.3) 发布。已绑定并被跟踪的 PR 在 CI 失败、冲突或 head 改变时，可以[私下唤醒 Managed Session](https://github.com/QwenLM/qwen-code/pull/17665)，不会因为这次唤醒自动发公共评论。此版同时新增[无界面后台工作流](https://github.com/QwenLM/qwen-code/pull/17809)和跨会话产物库。

**为什么值得关注。** 这是把工程事件接回已有任务的运行时改动，不是模型变聪明。评估此类 Agent 更适合看事件是否正确绑定、重复唤醒率、产物可追溯性，以及需审批的操作有没有越界，不能用单轮代码评分代替。
