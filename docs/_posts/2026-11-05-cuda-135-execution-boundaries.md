---
layout: post
title: "CUDA 13.5 深读：Rubin 进入 GA，推理系统还需要重验哪些执行边界"
date: 2026-11-05T05:50:00+08:00
summary: "CUDA 13.5 的重要性不止是 Vera Rubin 正式支持。资源分配、Tile 内跨卡通信、GPU 驻留控制量和图执行各有进展，也各有驱动、拓扑、形状与兼容限制。沿官方文档和固定版本代码，拆解哪些变化值得评估，哪些结论不能直接外推。"
section: explainer
label: "GPU 软件栈解读"
tags: [CUDA, NVIDIA, 推理系统, GPU, CUDA Graph, 编译器]
demo: false
sources:
  - title: "CUDA 13.5 官方发布解读"
    url: "https://developer.nvidia.com/blog/nvidia-cuda-13-5-brings-nvidia-vera-rubin-ga-support/"
  - title: "CUDA Toolkit 13.5 Release Notes"
    url: "https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html"
  - title: "MPS v3 interface"
    url: "https://docs.nvidia.com/deploy/mps/latest/mpsv3-interface.html"
  - title: "CUDA Tile IR programming model"
    url: "https://docs.nvidia.com/cuda/tile-ir/latest/sections/prog_model.html"
  - title: "CCCL v3.5.0 Release"
    url: "https://github.com/NVIDIA/cccl/releases/tag/v3.5.0"
  - title: "CCCL v3.5.0 batched Top-K API 与约束"
    url: "https://github.com/NVIDIA/cccl/blob/v3.5.0/cub/cub/device/device_batched_topk.cuh"
  - title: "cuda.core 1.2.0 Release Notes"
    url: "https://nvidia.github.io/cuda-python/cuda-core/1.2.0/release/1.2.0-notes.html"
---

北京时间 **2026 年 11 月 5 日 02:46:07**，NVIDIA 发布 CUDA 13.5 技术解读。该时间来自原始页面的 `article:published_time` 与 JSON-LD，两者一致；页面显示的日期为美国当地的 11 月 4 日。文章宣布 Vera Rubin 支持由早期开发阶段进入 GA，并介绍资源管理、Tile 编程、工具与库的配套变化。[官方文章](https://developer.nvidia.com/blog/nvidia-cuda-13-5-brings-nvidia-vera-rubin-ga-support/)

对推理系统团队，最有价值的问题是：**哪一层获得了新能力，原有的哪些执行假设因此需要重新验证？** 把这些变化笼统归结为“升级 CUDA 就更快”，会漏掉软件栈中真正决定收益和风险的条件。

本文依据 CUDA 13.5 发布资料、查阅时的官方接口文档，以及 CCCL v3.5.0 固定版本源码。下面的工程评估框架属于本文分析，不是 NVIDIA 已测得的业务收益；本文没有在 Rubin 或其他 GPU 上运行性能实验。

## 一、先区分四种“支持”，不要把兼容下限当成功能下限

CUDA 13.5 对应的驱动分支是 **R620**。发布说明明确区分：既有 CUDA 13.x 应用可在满足小版本兼容条件的 R580 及以上驱动运行；13.5 新功能和新启用平台则需要支持它们的 R620 或更新驱动。驱动也不随 Toolkit 自动捆绑安装，Linux 从 13.4、Windows 从 13.1 就已如此。[驱动兼容说明](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html#cuda-driver)

这里应当分开管理四个问题：

1. **平台支持：** 目标 GPU、操作系统和驱动组合是否被支持。
2. **程序可运行：** 编译产物是否能被当前驱动加载，既有接口是否满足兼容要求。
3. **功能可用：** 新 API、通信方式或编译路径是否满足更高的硬件与驱动条件。
4. **工作负载获益：** 应用实际调用到什么实现，它是否改善目标请求分布下的成本和时延。

这是一个逐层收紧的判断过程。容器中的 Toolkit 版本正确，不代表宿主机驱动提供了所有新功能；程序成功启动，也不能证明目标算子选择了新路径。生产验收至少要记录宿主驱动、GPU 架构、关键库版本、编译目标和实际运行路径，而非只保存一个镜像标签。

还要区分“新版本的组成部分”和“当天首次公开的技术”。本次配套介绍的 **CCCL 3.5.0 已于 10 月 7 日发布**，**cuda.core 1.2.0 的版本说明标注 9 月 2 日发布**。它们适合放进 CUDA 13.5 的整体升级评估，但不能重新包装成 11 月 4 日才出现的独立成果。[CCCL 发布记录](https://github.com/NVIDIA/cccl/releases/tag/v3.5.0)、[cuda.core 版本记录](https://nvidia.github.io/cuda-python/cuda-core/1.2.0/release/1.2.0-notes.html)

## 二、资源管理：保证多少，能借多少，何时归还，是三个不同问题

GPU 共享不只是把若干进程放在同一张卡上。在线推理、离线评估与后台任务通常具有不同的到达模式，资源分配同时要考虑最低服务能力和闲置容量利用率。

13.5 的 locality-domain 分区允许应用选择等量 SM，或者包含域内额外 SM。后一种方式提高可分配资源的覆盖度，但各域的 SM 数可能不同，需要查询实际分区容量后安排工作。[Runtime 资源接口](https://docs.nvidia.com/cuda/cuda-runtime-api/cuda_runtime_api/group__CUDART__EXECUTION__CONTEXT.html)

**本文分析：** 等量分区更容易做对称调度；不等量分区则要求调度器理解容量差别。如果仍给每个分区固定等量任务，最慢分区可能决定整批完成时间。增加可用 SM 是资源条件变化，不是同步任务自动加速的证明。

MPS v3 需要显式选择协议版本 3，v2 仍是默认接口；升级 Toolkit 不等于已经启用 v3。[启用条件](https://docs.nvidia.com/deploy/mps/latest/mpsv3-interface.html#enabling-mps-v3)

MPS v3 又提供了两种不同的调节方式：

- 时间片权重调整每个 server 的计算时间片长度，不保证相同百分比的 GPU 利用率。
- 静态 SM 分区可配置借用容量与出借容量；允许出借的分区必须**没有挂接客户端**，不是“客户端还在但暂时不忙”就能出借。借用和出借分别控制，默认关闭。

这些条件来自 [MPS v3 接口文档](https://docs.nvidia.com/deploy/mps/latest/mpsv3-interface.html#sm-partition-load-balancing)。因此，“设置 50% 权重”不应直接被运维系统解释成“买到了半张卡的确定吞吐”，而“可共享分区”也不能替代严格的独占容量承诺。

部署时还有两项不能省略的约束：**同一 server 的 locality domains 与静态 SM 分区互斥**；时间片设置也不是任意在线热调。全局 `compute-policy` 必须在创建任何 server 前设定，只要仍有 server 条目就不能修改。每个 server 的 `timeslice-pct` 只能在启动前，或没有任何挂接客户端时修改；任一 namespace 仍有客户端时，更新会被拒绝。[分区互斥条件](https://docs.nvidia.com/deploy/mps/latest/mpsv3-interface.html#locality-domains)、[设置变更条件](https://docs.nvidia.com/deploy/mps/latest/mpsv3-interface.html#changing-settings)

一个更有解释力的测试是让后台任务先使用额外容量，再让在线流量到来，观察回收过程中的尾延迟，而非只测两个服务稳定运行时的平均吞吐。还应覆盖客户端退出与重新挂接、批量突增、通信密集任务与计算密集任务混跑。**弹性收益通常发生在负载变化时，风险也应在负载变化时测。**

## 三、Tile 跨卡与 SIMT 互操作：融合边界前移，部署边界没有消失

CUDA Tile 的跨 GPU 内存访问区分单播和多播：单播依赖参与 GPU 的 NVLink 连接；多播还要求支持 NVLink SHARP 的 NVSwitch fabric。内存映射与指针建立必须在内核启动前完成。[Tile 跨 GPU 模型](https://docs.nvidia.com/cuda/tile-ir/latest/sections/prog_model.html#multi-gpu-communication)

这为把计算与跨卡操作放进更连续的执行路径提供了条件。其潜在收益，是减少阶段之间的启动、落回全局内存和调度交接。它不会消除数据传输量，也不会自动使任意 PCIe 多卡或跨机网络获得相同能力。

从算法设计看，融合有两面：生产者能更早把数据交给消费者，但它们的进度也会更紧密地相互依赖。比较实现时，应固定相同拓扑、数值语义与工作量，分别观察通信等待、资源占用和端到端完成时间。一个更少启动次数的内核，如果占用更多寄存器或使慢参与者拖住其他 GPU，并不必然更快。这是性能分析假设，仍需实测。

另一项变化是 **Tile 内调用 SIMT 库函数的预览支持**。它目前限于受支持 NVIDIA 库提供的函数，不支持任意用户自定义 device 函数；相关 bytecode 不能直接交给 driver JIT，需经相应工具与 tile 库编译链接为 cubin。官方还明确：13.5 的这类预览字节码不兼容未来 13.6 等版本，配套库独立发布，可能晚于 Toolkit。[互操作限制与兼容性](https://docs.nvidia.com/cuda/tile-ir/latest/sections/prog_model.html#simt-interoperability)

因此，Rubin 的 GA 与 Tile-SIMT 的 preview 是两个不同成熟度层级。适合的落地方式，是选择一个有清楚对照的算子试点，把工具链和库版本一并冻结，保留原路径。将预览接口当成长期稳定的插件 ABI，会把今天的优化成本变成下一次升级的迁移成本。

## 四、GPU 驻留控制量：减少的是一次往返，不是取消所有动态约束

CCCL 3.5 的 `cuda::args::deferred` 可以让归约操作直接读取设备内存中的元素数。例如，上一步筛选得到有效元素数量，下一步归约无需先把这个数量传回 CPU；捕获的图可以在不同 replay 中读取不同数量，而不因此更新或重新捕获图。[CCCL 3.5 发布说明](https://github.com/NVIDIA/cccl/releases/tag/v3.5.0)

它瞄准的是推理系统中常见的控制依赖：GPU 已经算出了下一步需要多少工作，CPU 却还要等待结果、组装参数再发回去。对于每个阶段都很短的流水线，这次往返可能比算术本身更显眼。

但“数量可以动态变化”不等于“图可以容纳无限形状”。缓冲区容量、参数上界、算法可接受范围仍然存在。一个实用的设计是把**已分配容量**与**本轮有效长度**分开：容量按可证明的上界准备，执行时只处理有效部分，并对越界显式处理。

这里的评估对象也应是整个流水线。假如省下了一次主机同步，却为了统一上界而分配过大的临时区，导致可并发请求变少，局部优化可能被系统级损失抵消。应同时记录 CPU 等待、GPU 空隙、临时存储峰值和目标并发下的完成时延。

## 五、Batched Top-K 的限制，决定它能否替换现有采样路径

官方发布解读把批量 Top-K 与 token 选择、稀疏注意力联系起来，但**具体 API 的约束比应用标签更重要**。

固定到 CCCL v3.5.0 的 `DeviceBatchedTopK`，其公开 API 文档将初始适用范围限定为一个 thread block 可处理的小 segment，需要编译期可知的大小上界，并受 shared memory 容量约束。接口检查还要求调用方显式接受非确定、无排序输出，tie-break 也不保证固定次序。[v3.5.0 API 文档与接口检查](https://github.com/NVIDIA/cccl/blob/v3.5.0/cub/cub/device/device_batched_topk.cuh)

这意味着，面向更大候选空间时，不能不检查形状就把旧 Top-K 调用机械替换成这个 API。可能需要分段候选选择再合并，也可能适合保留其他实现；这些属于调用方设计，而非该 API 已经替用户完成的工作。

还必须分开验证三个性质：选出的集合是否正确、相同分数如何打破平局、输出是否排序。对于只需要无序候选集合的后续算子，后一项可能不重要；对于依赖固定排列或确定平局规则的采样与测试流程，它就可能改变结果。性能回归与行为回归不能共用一张“通过”标签。

同一版 `DeviceScan` 提供浮点求和的 run-to-run 可复现模式，但其范围是相同 GPU、输入和构建配置。它不等价于跨 GPU 型号一致，更不能被外推为整个模型输出确定。[CCCL 确定性说明](https://github.com/NVIDIA/cccl/releases/tag/v3.5.0)

## 六、Python 封装的契约，不能从底层 C API 推出来

本次 CUDA 发布文章同时介绍原生 batched 1D copy 的图捕获支持，以及 Python `copy_batch()`。这两项放在一起，容易造成一个错误联想：既然底层支持，那么 Python 封装也自动支持相同用法。

实际查阅 **cuda.core 1.2.0** 的版本说明，其 `copy_batch()` 明确拒绝 graph capture，批内复制也不能相互 alias。它的 PDL 接口要求 compute capability 9.0 及以上。这些都是 Python 包本身的条件，不能由 Toolkit 版本号替代。[cuda.core 1.2.0 说明](https://nvidia.github.io/cuda-python/cuda-core/1.2.0/release/1.2.0-notes.html)

**本文分析：** 软件栈上下层同名能力之间，经常隔着版本与语义适配。对图执行相关功能，最小验证应覆盖应用实际调用的封装，而不是用一个 C++ 示例通过，就宣布 Python 服务已支持。包版本、bindings、driver、默认 stream、缓冲区生命周期和 capture 状态，都属于可复现环境的一部分。

## 七、怎样决定是否升级，而不是被版本号推动升级

这一版更适合按瓶颈选择评估项目：

- **宿主调度空隙明显：** 优先验证控制量留在 GPU、图复用和批量操作，观察实际请求延迟是否改善。
- **跨卡阶段切换昂贵：** 选择一个通信与计算可以连续组织的算子，先核对拓扑，再比较融合与未融合路径。
- **共享 GPU 利用率低：** 对弹性容量建立回收与尾延迟测试，不把平均吞吐当作服务保障。
- **自定义 Top-K 或扫描算子：** 对齐形状、排序、平局和数值重复性要求后，再谈替换。

验收应保留一个可回退的旧环境，先做输出与错误路径回归，再做性能对照。尤其是自定义 Tile 内核，发布说明仍列有循环携带 load 结果、某些大尺寸索引等可能导致错误结果或误编译的已知问题。使用了相关构造时，需要针对性测试，不能仅因编译成功就放行。[CUDA 13.5 已知问题](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html#known-issues)

CUDA 13.5 展示的是一条清楚的工程方向：让资源分配更可控，让通信与计算结合得更紧，让动态执行少依赖主机往返。它没有把性能工程变成一键升级。**越多控制权下沉到运行时、编译器和设备端，应用越需要把拓扑、形状、数值与生命周期约束写进自己的验收标准。**

## 资料范围与未验证部分

查阅截至北京时间 2026 年 11 月 5 日。本文以新公开的 CUDA 13.5 官方文章为入口，辅以相关版本与接口资料；旧版独立组件的日期已单独说明。CCCL 代码链接固定到 v3.5.0；带 `latest` 的 NVIDIA 文档会继续更新，复现时应保存相应版本。

本文未实测 Rubin、MPS 混部、Tile 跨卡融合或各 Python/C++ 组合，也未验证上述改动对具体模型的吞吐、尾延迟和成本收益。本文给出的是带边界的评估路径，不是生产容量或兼容性承诺。
