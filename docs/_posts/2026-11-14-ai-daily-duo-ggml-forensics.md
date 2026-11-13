---
title: "AI 日报｜Duo 开放双工交互模型，ggml 1.0 发布，权重取证开始接受代码检验"
date: 2026-11-14T05:36:00+08:00
summary: "本期精选 3 条：Duo 公开模型和流式部署分支；ggml 1.0 带来多后端优化与兼容性变化；两份公开代码让模型权重取证更容易复查，但不能直接证明完整训练硬件。"
section: daily
label: "AI 动态"
tags: [多模态, 开源, 推理系统, 模型取证]
demo: false
sources:
  - title: "inclusionAI/Duo"
    url: "https://github.com/inclusionAI/Duo"
  - title: "ggml v1.0.0"
    url: "https://github.com/ggml-org/ggml/releases/tag/v1.0.0"
  - title: "checkpoint-forensics"
    url: "https://github.com/macrogrants/checkpoint-forensics"
  - title: "checkpoint-forensics-repro"
    url: "https://github.com/peterjliu/checkpoint-forensics-repro"
---

本期资料截止 **北京时间 2026 年 11 月 14 日 05:36（UTC 11 月 13 日 21:36）**，观察窗口为此前 24 小时。只收录能核实原始发布时间、且有实质信息的变化，本期共 3 条。

## 1. Duo 公开模型与部署代码：让 AI 一边听看，一边回应

**发生了什么：** inclusionAI 公开了 Duo。项目希望把交互从“你说完、我再答”变成持续接收声音和画面、同时决定是否回应的过程，也支持对话中的打断。

这次公开材料不只有演示：仓库列出了 Duo 1.0 的基础、蒸馏、量化权重，以及 1.2 基础权重。主分支提供离线研究流程，另有 vLLM-Omni 和 SGLang-Omni 流式部署分支。仓库首个提交时间为 **UTC 11 月 13 日 09:13:02，即北京时间 17:13:02**；README 的发布记录也标注 11 月 13 日。[原始仓库](https://github.com/inclusionAI/Duo)

**为什么值得看：** 真正自然的语音和视频交互，难点不只是回答速度。模型还要判断什么时候接话、什么时候继续听，以及自己说话时新输入该怎样影响后续输出。Duo 将这件事分成负责交互意图的 Intent 和负责生成媒体的 Realization，并用统一时间线约束信息流。这比单纯把一个聊天模型接上语音合成，更接近在建一套持续交互系统。

**别误读：** 官方把当前版本定位为研究预览。离线参考流程仍包含 ASR 文本环节；README 将更直接的视觉交互列入后续版本。公开部署分支也不等于已经证明任意硬件、任意并发下都能低延迟运行。本期没有自行测量响应延迟或打断成功率。

## 2. ggml 1.0 发布：性能优化之外，升级兼容性也要检查

**发生了什么：** ggml 发布 **v1.0.0**，GitHub Release 时间为 **UTC 11 月 13 日 08:34:21，即北京时间 16:34:21**。

这次发布汇总了多种后端的改进：CUDA 的少行量化矩阵乘和融合计算、Metal 的 MoE 路由融合、Vulkan 的预填充 FlashAttention，以及 SYCL、OpenCL、WebGPU、Hexagon 等路径上的工作。核心调度也会避免上传没有被实际读取的输入。[官方发布说明](https://github.com/ggml-org/ggml/releases/tag/v1.0.0)

**为什么值得看：** 本地推理的“快”，往往不是某个大算子单独跑得快，而是少搬一些数据、少发起一些小计算，并让不同硬件都走上合适的实现。ggml 的价值仍在于把这些细节装进可以复用的底层库。

**升级提醒：** 这不是只有提速、没有代价的版本。发布说明明确移除了过时公共 API 和旧的 `DIAG_MASK` 操作，并调整 RPC 协议以拒绝不兼容对端。依赖旧接口、自己维护后端或使用远端推理节点的项目，应先核对接口与两端版本。发布说明汇总的优化不代表每个模型都得到同样增益，也不能把这些此前陆续合入的变化说成今天才首次实现。

## 3. 模型权重取证有了两份公开代码：从“听作者说”走向“自己能查”

**发生了什么：** Will DePue 相关报告的作者代码，以及 Peter J. Liu 的独立复现仓库，已公开可读。

- 作者仓库首提交：**UTC 11 月 13 日 05:52:03，北京时间 13:52:03**。
- 独立复现首提交：**UTC 11 月 12 日 23:20:02，北京时间 11 月 13 日 07:20:02**。

作者仓库提供若干模型的权重行样本、固定版本与哈希校验，以及 CPU 回放和 GPU 检查脚本。独立复现则用 CPU 模拟随机数在张量中的排列，报告了多组布局匹配和部分种子搜索结果。[作者代码](https://github.com/macrogrants/checkpoint-forensics) · [独立复现](https://github.com/peterjliu/checkpoint-forensics-repro)

**方法一句话：** 模型的一些权重可能还留着初始化时的随机数。随机数本身和它们被填进张量的位置，可以用来检验“是否符合某种初始化实现”。

**为什么重要：** 公开代码让争议有了更具体的检验对象：样本从哪来、版本是否固定、换个种子是否仍能匹配、另一种布局能否解释数据。这比只展示一个很高的相关系数有用得多。

**证据边界没有消失：** 两个仓库都不等于完整复现了报告的所有结论。作者仓库明确说明，起始权重的线索不能说明后续训练在哪里进行；独立仓库也明确没有验证硬件型号映射、NVIDIA 与 AMD 的数值区别、训练卡数和成本。**初始化模式吻合，不等于完整训练全过程已经被证明。** 本期核查的是公开材料与代码说明，并未重新下载模型、运行全套实验。详细方法和限制见[本站解读]({{ '/2026/11/13/checkpoint-forensics-hardware-attribution/' | relative_url }})。

## 今天的共同线索

这三条消息都在让“能看见的结果”变成“能拿来检验的东西”：Duo 给出交互模型与部署入口，ggml 把底层优化打包成可升级版本，权重取证则开始接受公开代码层面的复查。

对使用者来说，更有价值的问题不是“名字听起来多厉害”，而是：**材料是否完整，条件是否说清，换一个环境还能不能成立。**

### 日期核查说明

本期没有把聚合网站的“今日收录”当成“今日发布”。例如 [Gemini 4 Hydrogen 的官方页面](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-hydrogen/)发布时间为 UTC 11 月 12 日 18:00；[Inkling 2 Small 的权重上传提交](https://huggingface.co/thinkingmachines/Inkling-2-Small/commit/78cb6c0ef68e1f089b77e78cfd94783d05b5c41b)为当日 19:53，均早于本期窗口起点，因此没有作为本期新发布消息重复收录。
