---
title: "AI 日报：DeepSeek Harness 接入代码审阅，Kimi B300 基准遇到首 token 门槛"
date: 2026-11-23T05:31:00+08:00
summary: "DeepSeek Harness alpha 增加任务时间线和审阅；Kimi K3.1 Pro 的 B300 配方更新后，高并发点仍需核验首 token 延迟。另看 Inkling 小矩阵、DFlash2 启动兼容，以及 SGLang 的视频冷启动和 KV 传输。"
section: daily
label: "AI 动态"
tags: [DeepSeek, Kimi, B300, vLLM, SGLang, 推理性能]
demo: false
sources:
  - title: "DeepSeek Harness 0.2.3-alpha.1 发布说明"
    url: "https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.3-alpha.1"
  - title: "vLLM #69264：Kimi B300 PD 配方"
    url: "https://github.com/vllm-project/vllm/pull/69264"
  - title: "vLLM #69168：Inkling 小 M 矩阵核"
    url: "https://github.com/vllm-project/vllm/pull/69168"
  - title: "vLLM #68827：DFlash2 anchor-first 布局"
    url: "https://github.com/vllm-project/vllm/pull/68827"
  - title: "SGLang #52225：MiniMax-H3 视觉塔预热"
    url: "https://github.com/sgl-project/sglang/pull/52225"
  - title: "SGLang #46460：MooncakeTransport"
    url: "https://github.com/sgl-project/sglang/pull/46460"
---

资料核验截至北京时间 2026 年 11 月 23 日 05:31，以下是前 24 小时内的正式公开预览发布或上游合入。合入主线不等于已进入稳定版或公开容器。

## 1. DeepSeek Harness 把任务阻塞和代码审阅放进客户端

**11 月 22 日 11:19，alpha.1 发布。** [DeepSeek Harness 发布说明](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.3-alpha.1)列出实验性任务时间线、GitHub PR 审阅页面、GitLab 的审阅和合并，以及可选的 Linear、Notion、腾讯文档、飞书、企业微信、腾讯会议、钉钉连接器。当天 19:00 的 [alpha.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.3-alpha.2)发布说明只列出 Node.js 要求调整，不应视作又一次功能发布。

**为什么关注：** 审阅与任务状态开始成为运行时功能，不必把等待审阅、阻塞和子任务进展都塞进聊天摘要。这些是可观察性和工作流能力，不是模型在代码任务上变聪明的证据。接入前更值得测的是：是否能定位一个真实阻塞、恢复后任务状态是否一致、能否把审阅与合并授权分开。alpha 不等于稳定版。

## 2. Kimi K3.1 Pro 的 B300 配方进主线，但最高并发不是可用吞吐

**11 月 23 日 00:25，[vLLM #69264](https://github.com/vllm-project/vllm/pull/69264)合入。** B300 的 Dynamo + vLLM 分离式配方固定了镜像和 Dynamo 版本，并对不同并发点采用不同 P/D 副本及 draft token 配置。按 InferenceX 作者报告，[已完成的旧 sweep](https://github.com/SemiAnalysisAI/InferenceX/actions/runs/44931328829)中，48、96、660 客户端的 P90 TTFT 分别为 **1.07、3.84、10.72 秒**。48 和 96 都是 1P3D，但 draft token 数从 5 改为 4；660 是另一套 4P5D。不能把整条曲线当作只改并发的实验。

[InferenceX #5175](https://github.com/SemiAnalysisAI/InferenceX/pull/5175)的新修订把 4P5D 测点从 660 改到 600；作者另外报告了 7.04 秒，但对应[新 sweep 测点](https://github.com/SemiAnalysisAI/InferenceX/actions/runs/45060814796/job/137326484028)截至核验时仍排队，旧 sweep 不覆盖它。**不同并发的 10.72 和 7.04 秒不能算同负载加速。** 评估服务容量时，先按 TTFT 和 TPOT 筛出达标点，再比较有效输出与 GPU 数；不要把输入、命中的缓存 token 和模型实际生成的 token 混称输出吞吐。

## 3. Inkling-2-Mini：5090 的微秒级算子改善，整机 ITL 只降约 7.5%

**11 月 22 日 08:09，[vLLM #69168](https://github.com/vllm-project/vllm/pull/69168)合入。** RTX 5090 上，短卷积投影在 M=8、N=32 时由 **13.9 降到 2.0 µs**。窄输出给不了足够并行 tile，Split-K 让多个 CTA 算出 FP32 部分和，再按固定切分顺序归并。这说的是归并顺序，不是与未切分路径逐位等价，也不是 Tensor Core 内部累加位宽的证据。

端到端是三个改动一起测，包括 loop blend 和 Q/K/V 合并。作者使用 Inkling-2-Mini + DSpark、合成负载、并发 1，两个 fresh-server 对照的平均 ITL **10.70 → 9.89／9.91 ms**。这是延迟，不是全模型 7 倍。GB10 审阅者另测到同形状短卷积 **15.1 → 2.6 µs**，没有匹配的整机 ITL 实验。选型时应把热点形状分布、kernel 和 end-to-end 分开看。

## 4. DFlash2 的 anchor-first 草稿终于能走主线启动路径

**11 月 23 日 00:07，[vLLM #68827](https://github.com/vllm-project/vllm/pull/68827)合入。** 旧路径曾拒绝 checkpoint 声明 `sample_from_anchor: true`；更新后，运行时从配置区分 anchor-first 的 K 个查询与普通布局的 K+1 个查询，并用统一宽度处理 KV lookahead 与相应卷积分块。作者在公开的 Qwen3.8-27B-DFlash2-Exp 草稿配置上报告启动后 acceptance length 6.03；另一个普通布局草稿的 128 个对照输出完全一致。

**为什么关注：** 这是模型产物与运行时的布局、分配约定打通，不是同一模型更快的 A/B，也不能用接受长度推导整体 decode 提速。部署时先验证“什么 checkpoint 能正确启动”，再在相同工作负载下比较验证成本、TPOT 与接受长度。

## 5. MiniMax-H3：把第一条视频请求的编译成本搬到启动阶段

**11 月 23 日 02:37–02:39，SGLang 三项改动合入。** [视觉塔预热 #52225](https://github.com/sgl-project/sglang/pull/52225)把部分 cuDNN JIT 提前到 ready 之前。两张 B300、编码器 TP2、空编译缓存的单次对照，首个 16:9 关键帧请求的**文本编码阶段**从 **7.182 → 2.676 秒**，FL2VA 的进程启动至健康则从 **190.38 → 204.85 秒**。[另一项 Triton 改动 #52224](https://github.com/sgl-project/sglang/pull/52224)减少形状变化带来的重编译，但新 top-k bucket 仍会触发编译。

[双分区部署 #52023](https://github.com/sgl-project/sglang/pull/52023)允许 FL2VA 和 Ref2VA 在一个服务共享文本编码器与两个 VAE，两个 DiT 仍各需约 61.73 GiB 权重；显存不足时可能随请求切换搬运。部署验收要同时记三项：启动到健康、首请求分阶段延迟、混合流量下的权重切换。单阶段 7.182 → 2.676 秒不是整段视频提速。

## 6. SGLang 抽出 MooncakeTransport，节省的是一部分 CPU 计划开销

**11 月 22 日 17:43，[SGLang #46460](https://github.com/sgl-project/sglang/pull/46460)合入。** 重构把 Mooncake 的缓冲区注册、计划执行和生命周期整理进公共 Transport 接口，不改变线上协议或线格式。作者早期版本的 CPU mock 在 72 层、每层 2,048 页组时，传输计划中位耗时 **46 → 10 ms**；每层只有 16 组时反而 **0.28 → 0.33 ms**。两张 H100 的 Qwen3-8B 1P1D 对照吞吐基本持平，高并发点为 **8.90 req/s → 8.90 req/s**。性能数字早于最终 rebase；未验证昇腾端到端。

**为什么关注：** KV 切得细时，主机的页表准备和注册寿命可能比 RDMA 本身更值得优化。但 CPU mock 不能代替真实传输测试；应同时观察碎片程度、计划耗时、TTFT 和失败后缓冲区能否安全回收。

相关阅读：[vLLM 的两次前缀缓存修复]({{ '/2026/11/23/vllm-kv-contiguous-prefix-offload/' | relative_url }})。这是另一条路径：已经写进 CPU 或磁盘的 KV，未必能在下一次请求中组成连续前缀。
