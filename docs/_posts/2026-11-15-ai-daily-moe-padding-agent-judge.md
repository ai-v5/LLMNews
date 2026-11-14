---
title: "每日 AI 新闻｜MoE 跳过填充行，浏览器智能体增加结果复核"
date: 2026-11-15T05:30:00+08:00
summary: "vLLM 减少 MoE 无效计算并补齐 DeepGEMM 预热；Browser Use 让运行结果更好诊断；跨 rank 预填充提案则展示了首 token 延迟与解码吞吐的取舍。"
section: daily
label: "每日AI新闻"
tags: [vLLM, MoE, DeepGEMM, 智能体, 推理系统]
demo: false
sources:
  - title: "vLLM #66799：grouped top-k 跳过 padding"
    url: "https://github.com/vllm-project/vllm/pull/66799"
  - title: "vLLM #64827：DeepGEMM 预热"
    url: "https://github.com/vllm-project/vllm/pull/64827"
  - title: "Browser Use 1.0.5 发布说明"
    url: "https://github.com/browser-use/browser-use/releases/tag/1.0.5"
  - title: "Browser Use #6403：评判器实验"
    url: "https://github.com/browser-use/browser-use/pull/6403"
  - title: "vLLM #67689：跨 rank 对齐 prefill 放行"
    url: "https://github.com/vllm-project/vllm/pull/67689"
  - title: "vLLM #67688：原始回放对照"
    url: "https://github.com/vllm-project/vllm/issues/67688"
---

**资料截止：北京时间 2026-11-15 05:30，覆盖此前 24 小时。** 本期选 4 条。两项 vLLM 改动已合入源码，一项浏览器智能体更新已发布，另有一项仍在审查的调度提案。

## 1. vLLM 让 MoE 路由跳过不对应真实 token 的行

**发生了什么。** 11 月 14 日 10:18，vLLM 合并 [#66799](https://github.com/vllm-project/vllm/pull/66799)。DP 对齐和 CUDA Graph 会给输入补齐形状。在适用的 grouped top-k 路由里，这些补齐行现在默认标为无效专家，模块化 MoE 内核可以略过它们。

**为什么值得关注。** 吞吐收益不一定来自更快的矩阵乘，也可以来自少做无效工作。作者的配对 ShareGPT 实验中，GLM-5.3 NVFP4 的 DP8+EP 配置吞吐提高约 5%–21%，MiMo-V2.6-Flash 的 DP4 配置在部分并发点提高约 5%–7%。这些是特定 CUDA 内核与部署的结果。DeepSeek-V3.2 在最高并发点的总收益处于波动范围内，其中一段解码反而变慢；DeepSeek-V4/V4.1 自有路由、ROCm AITER 等不受这项默认路径影响。

## 2. DeepSeek-V4/V4.1 的部分 DeepGEMM 编译提前到预热

**发生了什么。** 11 月 14 日 10:01，vLLM 合并 [#64827](https://github.com/vllm-project/vllm/pull/64827)，补上 DeepGEMM 版输出投影 einsum 和 mHC prenorm 等原先遗漏的预热路径，同时减少不可能在实际模型配置中用到的编译变体。

**为什么值得关注。** DP+EP 服务中，一个 rank 在真实请求上触发 JIT，其他 rank 也可能被拖住。把必要编译移到上线前，对扩容接流量和尾延迟都有意义；减少无用编译则避免把成本全挪到启动。在作者的 GB200 测试中，V4.1 的 prenorm 编译变体从 37 种减到 6 种，可接流量时间两次对照从 381/390 秒降到 310/320 秒。测试只清空 DeepGEMM 缓存，不是整个环境的完全冷启，也未覆盖 speculative decoding 的所有预热路径。

## 3. Browser Use 1.0.5 默认复核运行结果

**发生了什么。** 11 月 14 日 16:24，Browser Use 发布 [1.0.5](https://github.com/browser-use/browser-use/releases/tag/1.0.5)。每次运行可由评判模型结合执行轨迹、末尾截图与页面状态，给出是否完成、失败原因和站点操作注意事项；可以改评判标准或关闭。

**为什么值得关注。** 让智能体报告“为什么没办成”，比只返回执行轨迹更方便排查。开发者拿 13 次会话做测试，每次各评三遍：在五个有障碍的会话里，注意事项记录从 6/15 增至 15/15，但成功判定仍是 27/39。这是诊断覆盖改善，不是任务成功率提升。复核有额外模型调用，截图未脱敏，不能把它当成安全或独立验收保证。[评判改动和样本说明](https://github.com/browser-use/browser-use/pull/6403)

## 4. vLLM 提议让 MoE 的 DP rank 同步放行预填充

**发生了什么。** 11 月 15 日 03:41，[vLLM #67689](https://github.com/vllm-project/vllm/pull/67689) 公开，尚未合并。对启用了预填充间隔限制的 MoE 部署，若某个 DP rank 因过载提前放行，提案让其他 rank 下一步也放行，不再白等这个已经变长的同步步。

**为什么值得关注。** 这比单看某个 rank 的排队时间更接近系统瓶颈，也将代价推给了轻载 rank。在[作者用修改版 v0.32.0 的回放](https://github.com/vllm-project/vllm/issues/67688)中，4 张 B300 的长上下文突发回放中预填充吞吐提高 22%，冷请求中位 TTFT 从 9.8 秒降到 6.0 秒；持续偏斜下，轻载 rank 的单流中位解码速率约减半，合计生成吞吐约降 15%。这些不是当前 main 移植版的端到端数据，也不支持无条件启用。
