---
title: "TensorRT-LLM 1.3.0：Rubin 的 MoE 开始显式管 die，RL 更新不能只测权重拷贝"
date: 2026-11-21T05:33:00+08:00
summary: "Rubin SM107 还是预览，NVFP4 MoE 的 die 本地化、权重更新的请求边界，以及旧 TensorRT engine 的硬迁移才是这次升级值得分开验证的三件事。"
section: explainer
label: "推理与强化学习系统"
tags: [NVIDIA, TensorRT-LLM, Rubin, MoE, 低精度, 强化学习]
demo: false
sources:
  - title: "NVIDIA：TensorRT-LLM v1.3.0 Release"
    url: "https://github.com/NVIDIA/TensorRT-LLM/releases/tag/v1.3.0"
  - title: "NVIDIA：旧 TensorRT 后端迁移指南（v1.3.0）"
    url: "https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/v1.3.0/docs/source/legacy/tensorrt-backend-removal.md"
  - title: "NVIDIA：AsyncLLM 接口（v1.3.0）"
    url: "https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/v1.3.0/tensorrt_llm/_torch/async_llm.py"
  - title: "NVIDIA：RL 权重更新实现（v1.3.0）"
    url: "https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/v1.3.0/tensorrt_llm/llmapi/rlhf_utils.py"
  - title: "NVIDIA：在途请求权重更新测试（v1.3.0）"
    url: "https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/v1.3.0/tests/unittest/_torch/ray_orchestrator/multi_gpu/test_inflight_weight_update.py"
---

资料核验截至北京时间 2026 年 11 月 21 日 05:33。

NVIDIA 的 [TensorRT-LLM v1.3.0](https://github.com/NVIDIA/TensorRT-LLM/releases/tag/v1.3.0) 于 **2026 年 11 月 20 日 10:45（北京时间）**正式公开，标签对应提交 `c66df86`。这个版本最值得拆开的不是“支持更多模型”，而是三条变化：**MoE 的数据摆放开始考虑 Rubin GPU 内的 die，RL rollout 的权重更新开始进入请求调度，旧 TensorRT engine 路径则不再可用。** 三者都可能影响选型，但各自需要不同的验收。

## 一、Rubin 的 Preview 不等于所有组合可用

发布说明给 Vera Rubin 标注 **SM107 Preview**，并明确列出 DeepSeek-V4 与 Kimi K3。模型“能加载”、指定量化和 kernel “确实被选中”、生产负载“达到相同 SLO”是三道不同的门槛。不能把 Blackwell 上一款模型的 MTP / NVFP4 配方自动移植到 Rubin，也不能把预览当成生产支持承诺。

版本已经列出两个值得进验收的问题：Kimi-K3 NVFP4 的 tokenizer 可能在打包的 Transformers 版本下加载失败；P/D 分离运行 DSpark 时，draft KV 不转给 generation worker，可能降低接受率，聚合部署不受此问题影响。前者是启动正确性，后者是在相同模型下改变有效生成成本；两者都不是提高 GPU 算力能解决的。 [版本说明](https://github.com/NVIDIA/TensorRT-LLM/releases/tag/v1.3.0)

## 二、MoE 不止是位宽，还要看权重落在哪个 die

### 先区分三个层次

| 变化 | 动的是哪一段 | 不应据此推断 |
|:--|:--|:--|
| Rubin NVFP4 MoE 的 locality domain（uGPU） | NVIDIA 将其描述为让该路径的内存访问留在对应 GPU die，默认启用，可用 `DISABLE_LOCALITY_DOMAINS=1` 做消融。 | 不是所有算子都走本地 HBM；不是 EP 的 dispatch / combine 不再通信；不是所有 shape 都快。 |
| MXFP8 W8A8 linear / MoE | 权重和激活用于计算的格式；发布说明以 MiniMax-M3 checkpoint 为例。 | 不代表模型各层、KV、累加或通信都统一为 FP8。 |
| Marlin W4A16 NVFP4 | 用 4-bit 权重存储支持 Hopper/Ada 部署，激活按 16-bit 路径。 | 能读 NVFP4 权重，不等于用原生 W4A4 峰值。 |
| NVFP4 冷页压缩 | 低精度用于部分冷 KV 页存放，仍须手动开启；活动 GPU KV dtype 不随此开关改变。 | 不是每 token 的 QK/PV 都以 FP4 跑，更不能直接给整网 KV 容量套 4×。 |

不同后端和通信实现也应分开记录：v1.3.0 增加了多个 MoE 计算后端及 NCCL-EP 后端，`CUTEDSL_FC12` 被标成 Rubin 专用。但**已加入备选后端，不等于指定模型或形状默认选中它**。看实测应同时记录 W/A/KV、实际 kernel 名、scale 方案、专家分片与传输精度。 [版本说明](https://github.com/NVIDIA/TensorRT-LLM/releases/tag/v1.3.0)

**工程判断：** 用一组固定真实路由，分别在低并发 decode 和高吞吐 prefill 跑 die-local 路径开/关。不要只报 GPU 总 HBM 吞吐：还要拆专家 GEMM、dispatch / combine、跨 die 流量、每 rank 活跃专家数和 token 数。一个 die 内部更省流量，仍可能因热门专家让最慢 rank 等得更久。以固定 TTFT/ITL 门槛的合格输出吞吐判定净收益，不能从 release notes 推导倍率。

## 三、RL rollout 的重点：定义哪一批 token 属于哪版策略

v1.3.0 公告增加在途权重更新和 MoE Router Replay。后者可以返回 token 级专家路由，不是返回一份完整、可重演的 rollout；采样配置、策略版本、token/logprob 仍要另外保留。

本版的 [AsyncLLM 源码](https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/v1.3.0/tensorrt_llm/_torch/async_llm.py) 将 RL 接口绑定 Ray 编排。默认 [WorkerExtension](https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/v1.3.0/tensorrt_llm/llmapi/rlhf_utils.py) 从进程间共享句柄装入权重，更新动作使用等待请求排空的控制路径；另有显式的非排空方式。[版本内测试](https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/v1.3.0/tests/unittest/_torch/ray_orchestrator/multi_gpu/test_inflight_weight_update.py) 用定制 worker、TP=2 的单层 TinyLlama 检查：更新前提交的请求可结束，更新后新请求的 logits 对得上 Hugging Face 参考。测试**关闭了 KV 块复用**，不证明开着前缀复用时旧权重产生的缓存必定被安全隔离，也没有验证更新前的请求从头到尾只采用同一策略版本。非排空也不等于没有暂停或重计算成本。

实际验收应把两个方案分开：**严格版本边界**可排空旧策略请求再切换，**允许在途更新**则要测暂停、重算及丢弃比例，并为 KV 和轨迹验证权重版本。固定 prompts、生成长度分布与 trainer/rollout 拓扑，逐段计时：

1. trainer 完成参数导出到 rollout 副本可取；
2. 跨进程或跨机传输、重分片、量化及加载；
3. 临界区内暂停、缓存失效或重算；
4. 全部 rank 的新版本验证及首个合格 rollout 返回。

最终比较 **合格 rollout tokens / 整个更新周期**、p95 更新停顿、策略滞后，以及到等质量目标所需的加速器小时。不要用 IPC 拷贝时长或稳定期 decode TPS 代替整个周期，也不能把单机 IPC 接口当成已验证的跨机权重分发。

## 四、旧 engine 是硬迁移，不是换一个启动参数

[迁移指南](https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/v1.3.0/docs/source/legacy/tensorrt-backend-removal.md)写得很明确：**PyTorch 成为 TensorRT-LLM 唯一执行后端**。旧 TensorRT engine 的构建、转换和使用流程，包括 `trtllm-build`、`TrtLlmArgs`、`trtllm-bench --engine_dir`，不能沿用。旧 C++ Executor 和运行时 API 也被移除；Triton 集成只保留 `llmapi` 模型。这里移除的是 TensorRT-LLM 的 engine 后端，不是说 NVIDIA TensorRT 产品消失，也不是说新的 PyTorch 路径不再使用定制 CUDA kernel。新部署从受支持的 checkpoint 加载，不再依赖旧 engine 制品。

迁移建议先保留可回滚的旧服务，再用同 checkpoint 做影子对照。先核对模型与 tokenizer、输出/logprobs、工具接口契约，再测冷启动、显存、长上下文与 SLO goodput。发布说明还指出显式 CLI 参数现在优先于 YAML，P/D 的 KV 传输默认超时变为 60 秒。参数不变、实际生效配置变了，会让所谓的版本 A/B 失去意义。 [版本说明](https://github.com/NVIDIA/TensorRT-LLM/releases/tag/v1.3.0)

**我的判断：** 对已有部署最先处理的是旧 engine 兼容性。对新采购或跨平台优化，最有价值的是把 die 本地性当独立的性能变量。做 RL 的团队则应优先验证权重版本边界：一次更新后跑得更快，但得到的轨迹不能按训练规则使用，就没有净收益。
