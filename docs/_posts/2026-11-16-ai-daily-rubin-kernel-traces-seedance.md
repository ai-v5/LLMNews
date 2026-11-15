---
title: "每日AI新闻｜Rubin 上的 GLM 专用路径、GPU 算子追踪与 Seedance Flash 接入"
date: 2026-11-16T05:30:00+08:00
summary: "TensorRT-LLM 面向 Rubin 加入 GLM-5.2 高吞吐路径，SGLang 可记录算子内部事件；另看 ROCm 上的 DeepSeek 优化、llama.cpp、AutoGPT 与视频 API。"
section: daily
label: "AI 动态"
tags: [推理系统, Agent, 多模态, 开源]
demo: false
sources:
  - title: "TensorRT-LLM #21585"
    url: "https://github.com/NVIDIA/TensorRT-LLM/pull/21585"
  - title: "vLLM #67377：ROCm MXFP8 路径"
    url: "https://github.com/vllm-project/vllm/pull/67377"
  - title: "SGLang #50374"
    url: "https://github.com/sgl-project/sglang/pull/50374"
  - title: "llama.cpp #31904"
    url: "https://github.com/ggml-org/llama.cpp/pull/31904"
  - title: "AutoGPT Platform beta v0.11.3"
    url: "https://github.com/Significant-Gravitas/AutoGPT/releases/tag/autogpt-platform-beta-v0.11.3"
  - title: "BytePlus ModelArk：Dreamina Seedance 2.5 系列"
    url: "https://docs.byteplus.com/en/docs/ModelArk/seedance-2-5"
---

**资料截止：北京时间 2026 年 11 月 16 日 05:36。** 回看此前 24 小时。仓库更新按主线合入时间，软件按版本公开时间，文档更新另行标示。主线有代码不等于稳定包已发布，作者测得的数据也不等于独立复测。

## 1. TensorRT-LLM：给 Rubin 上的 GLM-5.2 单独做一条高吞吐路径

**发生了什么：**11 月 15 日 12:20（北京时间），TensorRT-LLM 合入 GLM-5.2 NVFP4 的 Rubin 高吞吐专用实现。PR 列出 28、32、36 卡三个配置：prefill 实例用 TP4/EP4，decode 实例用 TP16/EP16，配合 attention DP、NVFP4 KV cache 和 MTP。改动包括模型加载与 attention、MoE、推测解码等执行路径，并非只新增配置文件。[合入记录](https://github.com/NVIDIA/TensorRT-LLM/pull/21585)

**为什么关注：**高吞吐方案要同时决定 P/D 的并行组、KV 表示和推测长度。这里合入的是专用路径，不是可直接引用的通用性能：性能验证还依赖未合入的 [Mooncake 实验草稿](https://github.com/NVIDIA/TensorRT-LLM/pull/21586)，并对接受的草稿 token 数使用了固定设置。实际自由采样的吞吐仍需另测。

## 2. vLLM：DeepSeek-V4.1-Flash 在 ROCm 上换了两类算子路径

**发生了什么：**11 月 15 日 09:46 和 20:56（北京时间），vLLM 分别合入针对 MI355X 的 AITER FlyDSL MXFP8 GEMM 路径，以及 gfx950 上把 mHC 接缝从两次 Triton 启动换成一次 HIP Mega-MHC 的改动。前者的作者离线加权计时里，所测 dense GEMM 的 prefill 用时从 189.8 降至 106.7 ms/step；后者的单接缝微基准改善 16%–41%，但每组 3 次的服务对照未测出超出波动的整体增益。[MXFP8 PR](https://github.com/vllm-project/vllm/pull/67377) · [Mega-MHC PR](https://github.com/vllm-project/vllm/pull/65992)

**为什么关注：**同一模型的不同改动，可能分别减少计算时间和启动开销。二者不能直接相加，更不能拿最快的局部比例代表整机。后续值得看相同权重、上下文和并发下的端到端吞吐、交互速度与显存。

## 3. SGLang：把 GPU 算子内部的停顿导出成时间线

**发生了什么：**11 月 16 日 00:41（北京时间），SGLang 合入 JIT 算子的调试追踪，可在 warp 内标记阶段，观察驻留 warp 和线程块更替，导出到 Perfetto。它提供 NVIDIA IKET 和内核内读取时钟的两条路径；前者需要可选组件及受支持硬件。[SGLang #50374](https://github.com/sgl-project/sglang/pull/50374)

**为什么关注：**看到总耗时变长，只知道哪个算子慢；内部事件能进一步区分算子启动后是哪一段在等。插桩会扰动原程序，作者所测 IKET 开销随设置约为 0.5%–10%。应把它用于定位，再在关闭追踪时测最终性能。

## 4. llama.cpp：Ripple 接入 DFlash2，本地语音转写也扩展了模型支持

**发生了什么：**11 月 15 日 19:36（北京时间），llama.cpp 合入 Ricursive Ripple-65B-Preview 的 DFlash2 推测解码适配；11 月 16 日 04:25 又为多模态模块加入 Boson Higgs Audio v3 STT 和微软 VibeVoice-ASR-HF 支持。这里是推理引擎适配，不是这些模型首次发布。[DFlash2 合入](https://github.com/ggml-org/llama.cpp/pull/31904) · [语音转写合入](https://github.com/ggml-org/llama.cpp/pull/32329)

**为什么关注：**消费级设备不必只靠降低模型精度提速，也可以让辅助模型提出草稿，再由目标模型验证。DFlash2 PR 给出 M5 Max、特定 GGUF 量化、温度 0、单流的一组结果：11.9→36.5 token/s。配置和任务会影响接受率；这不是多并发、长提示或其他设备的保证。语音方向则扩展了本地转写选项，本文不对转写质量或实时性下结论。

## 5. AutoGPT Platform：新增本地电脑执行目标

**发生了什么：**11 月 15 日 16:59（北京时间），AutoGPT 发布名为 Platform beta v0.11.3 的版本，列出远程 Local PC 执行目标、原生移动端服务基础和排程修正。发布说明称修复了多项私下报告的问题，并表示会在生产修复上线后再公布公告；截至本次核对，不从版本说明推断问题细节或影响等级。[官方 release](https://github.com/Significant-Gravitas/AutoGPT/releases/tag/autogpt-platform-beta-v0.11.3)

**为什么关注：**工作流从托管沙箱走向个人设备后，执行位置、文件权限和审计记录就成了部署的一部分。移动端服务基础不等于完整客户端已向所有用户开放。

## 6. BytePlus 补入 Dreamina Seedance 2.5 Flash 的 API 文档

**发生了什么：**标注 11 月 15 日更新的 BytePlus 文档列出 `dreamina-seedance-2-5-flash-261115`，支持文生视频、首尾帧与多模态参考，以及编辑和延长；规格表列出 480p/720p、4–30 秒。文档未标具体更新时间的时区，本文记录为产品文档更新，不把它当作模型首次公布，也未验证账号能否立即调用。[官方教程](https://docs.byteplus.com/en/docs/ModelArk/seedance-2-5) · [官方模型目录](https://ai.byteplus.com/ark/region%3Aap-southeast-1/docs/model-list)

**为什么关注：**参考素材、编辑、延长都有明确接口，比单看模型名更能判断是否可接入生产。Flash 与完整版的分辨率和功能边界不同；真正换用前，要用相同输入比较耗时、可用率和返工次数。
