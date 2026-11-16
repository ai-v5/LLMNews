---
title: "AI 日报｜MLPerf 加入 397B GRPO，Rubin HPC 亮相，昇腾推理补齐 MoE 与 KV 路径"
date: 2026-11-17T05:37:00+08:00
summary: "MLPerf 开始测大型模型的工具调用后训练；Rubin HPC 面向科学仿真；开源推理更新聚焦量化正确性、KV 搬运和显存容量。"
section: daily
label: "AI 动态"
tags: [MLPerf, Rubin, MoE, vLLM, 昇腾]
demo: false
sources:
  - title: "MLCommons：MLPerf Training v6.1"
    url: "https://mlcommons.org/2026/11/mlperf-training-v6-1-results/"
  - title: "NVIDIA：Rubin HPC"
    url: "https://blogs.nvidia.com/blog/rubin-hpc/"
  - title: "OpenAI：Science at the Frontier"
    url: "https://openai.com/index/science-at-the-frontier/"
  - title: "SGLang：昇腾 MoE 路线图"
    url: "https://github.com/sgl-project/sglang/issues/50795"
  - title: "SGLang：整数 W4A8 MoE 补偿修复"
    url: "https://github.com/sgl-project/sglang/pull/40880"
  - title: "vLLM：Mooncake 数组提交接口"
    url: "https://github.com/vllm-project/vllm/pull/67656"
  - title: "vLLM-Ascend：P/D 双边 DCP"
    url: "https://github.com/vllm-project/vllm-ascend/pull/21622"
  - title: "vLLM-Ascend：Qwen PLE 权重卸载"
    url: "https://github.com/vllm-project/vllm-ascend/pull/21751"
---

资料截至 **11 月 17 日 05:37（北京时间）**。官网只标日期的发布沿用原站日期；PR 时间换算为北京时间。

## 1. MLPerf Training v6.1 纳入 397B 模型的 GRPO 后训练

**11 月 16 日，**MLCommons 发布训练榜，新增两项：使用 Yambda 数据的注意力式推荐任务 DLRMv4-HSTU，以及 Qwen3.5-397B 的 GRPO 后训练任务，涉及工具调用等软件工程能力。该轮共有 153 个系统提交、250 项测试结果，首次出现 NVIDIA Rubin 和 Google TPUv7（Ironwood）。[MLCommons 公告](https://mlcommons.org/2026/11/mlperf-training-v6-1-results/) · [结果表](https://results.mlcommons.org/training)

**为什么重要：**GRPO 把生成、训练更新与任务评估都带进性能问题，不能只拿预训练 MFU 推断后训练效率。读榜时，应先对齐任务、达标条件、加速器数量和系统可用性类别，再比较时间。

## 2. NVIDIA 公布面向科学计算的 Rubin HPC

**11 月 16 日，**NVIDIA 在 SC26 公布 Rubin HPC，官方列出单 GPU 超过 5 万个 CUDA 核心、面向稀疏数据搬运的加速能力和第七代 NVLink，预计 **2028 年**可用。它面向仿真、工程和分析，不是今天可采购的通用训练 SKU。[NVIDIA 原文](https://blogs.nvidia.com/blog/rubin-hpc/)

**为什么重要：**如果科学 Agent 不断调用仿真求解器，瓶颈可能在稀疏访存、数据搬运和跨 GPU 同步，而非模型 token 生成。CUDA 核心数不能直接换算成 LLM 训练速度；现阶段应看目标求解器的实测。

## 3. OpenAI 公开科研人员使用 ChatGPT 的试点研究

**11 月 16 日，**OpenAI 发布对 1,819 位试点科研人员、超过 58 万条科学类消息的分析，另有 251 人参与问卷。受访者估计，在没有 AI 的情况下完成同质工作需约 1.9 倍时间。这个数字是自报估计，不是随机对照或实际节省工时。[OpenAI 报告](https://openai.com/index/science-at-the-frontier/)

**为什么重要：**它能帮助识别哪些环节已有真实使用，例如读文献、写代码和分析证据；不能仅凭用量或自评认定科研发现变快。值得测的是包含核验和返工在内的完整任务耗时。

## 4. SGLang 昇腾 MoE：路线图拆开量化格式，整数 W4A8 修复进入主线

**11 月 16 日 22:20 发布路线图；17 日 04:19 合入修复。**路线图把整数 INT4/INT8 与 MXFP 分开，MXFP W4A4 列为离线 ModelSlim 已合入、在线量化仍在推进。另一个已合入的整数 W4A8 修复，让 MoE TP 各 rank 只累加自身 K 分片对应的补偿项。此前在 910B2 上的 TP8/EP1 和 TP16/EP1 冒烟对照支持该诊断，不是最终提交的全模型精度或吞吐基准。[路线图](https://github.com/sgl-project/sglang/issues/50795) · [修复 PR](https://github.com/sgl-project/sglang/pull/40880)

**为什么重要：**W4A8 只是位宽；格式、量化发生位置、后端及 TP/EP 组合都要单独确认。路线图中的 A5 MegaMoE 依赖 A3 工作，950 DeepEP V2.5 是拟评估项，不是已交付能力。

## 5. vLLM Mooncake 改用数组提交 KV 传输描述符

**11 月 16 日 20:40 合入。**vLLM 在支持新 API 的 Mooncake 引擎上直接提交连续数组，减少 Python 列表装箱和逐项转换，仍保留一次批量拷贝，老引擎可走原接口。作者在 8 张 H20、Qwen3-32B 的合成 PD 实验中报告 KV 传输带宽提升 **10.4%–17.7%**；这是该组测试的传输指标，不是链路物理带宽或模型吞吐的同比提升。[vLLM PR](https://github.com/vllm-project/vllm/pull/67656)

**为什么重要：**如果提交前的 CPU 开销已成为瓶颈，先细分描述符构造、提交与传输本体，可能比升级互联更快定位问题。另篇今日解读讨论的是 Mooncake Pull 故障恢复，和这条正常路径优化不是同一实验。

## 6. vLLM-Ascend Mooncake Push 支持 P/D 两端使用不同 DCP 布局

**11 月 16 日 21:23 合入。**Push 路径把准备好的 token 区间按 P/D 两侧的分片和块表做对应。作者用 16 张 A3 对 DeepSeek V3.1 做了 P 侧 TP8/DCP4、D 侧 TP8/DCP2 的有限验证；当时运行环境还用了 PR 之外的兼容改动。没有可归因的吞吐比较，也不意味着 DeepSeek V4.1 Engram 已支持这个组合。[vLLM-Ascend PR](https://github.com/vllm-project/vllm-ascend/pull/21622)

**为什么重要：**P 和 D 可以各自选择更合适的上下文并行布局，不必为了传输强行对齐。真正选型仍要测高并发下 KV 搬运、尾延迟和不同块布局的正确性。

## 7. Qwen PLE 表可放到主机内存，按 TP 分片共享

**11 月 16 日 23:32 合入。**vLLM-Ascend 把 Qwen PLE 的 BF16 表放进 CANN 注册的主机内存，经 Triton UVA 按需查询；符合条件的节点内进程共享同一个 TP 分片。**47.684 GiB** 是作者计算的单 worker 表大小，不是卸载前后实测的峰值显存差。最终清理修复未在作者的设备冒烟环境重新部署。[vLLM-Ascend PR](https://github.com/vllm-project/vllm-ascend/pull/21751)

**为什么重要：**方案把常驻权重的设备容量成本换成主机容量和访问开销。除了看能多装多少 KV，应在实际访问局部性下对比尾延迟、主机内存占用与故障清理。
