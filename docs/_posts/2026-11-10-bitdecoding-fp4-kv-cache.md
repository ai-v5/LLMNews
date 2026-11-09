---
title: "BitDecoding-FP4：KV缓存压到4位之后，怎样同时守住精度与吞吐"
date: 2026-11-10T05:46:00+08:00
summary: "BitDecoding-FP4把查询量化、概率下溢、键异常值与GPU内核一起设计，在特定长上下文负载下报告接近BF16 KV的平均准确率和更高吞吐。本文拆解它真正改变的计算路径，以及均分、硬件、MLA适配和公开实现的边界。"
section: explainer
label: "低比特推理解读"
tags: [KV缓存, FP4, 推理优化, vLLM, 开源]
demo: false
sources:
  - title: "BitDecoding-FP4 论文 v1"
    url: "https://arxiv.org/abs/2611.09825v1"
  - title: "BitDecoding-FP4 完整正文与附录"
    url: "https://arxiv.org/html/2611.09825v1"
  - title: "arXiv cs.AI 公告列表"
    url: "https://arxiv.org/list/cs.AI/recent"
  - title: "arXiv 公告日程说明"
    url: "https://info.arxiv.org/help/availability.html"
  - title: "arXiv cs.AI 官方 RSS"
    url: "https://rss.arxiv.org/rss/cs.AI"
  - title: "官方实现，核验版本4e2907d"
    url: "https://github.com/OpenBitSys/BitDecoding-FP4/tree/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f"
  - title: "官方基准运行说明"
    url: "https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/benchmark/README.md"
  - title: "官方准确率评测说明"
    url: "https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/evaluation/README.md"
---

## 本次新公开了什么

爱丁堡大学与腾讯混元研究者提出的 **BitDecoding-FP4**，研究如何把低比特KV缓存直接交给FP4张量核计算，同时控制准确率损失。值得关注的并不只是“4位更省显存”，而是它把数值误差、算子布局和在线服务放到同一条计算路径里处理。

本文依据[论文v1及全部附录](https://arxiv.org/html/2611.09825v1)，以及官方仓库提交 `4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f`。资料核验截至**北京时间2026年11月10日05:46**。本文未运行模型、内核或基准，以下性能数字均为作者报告，不是本站实测。

时间上，论文[提交记录](https://arxiv.org/abs/2611.09825v1)为11月6日18:13 UTC，但它列于[arXiv官方11月9日公告批次](https://arxiv.org/list/cs.AI/recent)。[官方RSS](https://rss.arxiv.org/rss/cs.AI)将该v1标为新稿，条目`pubDate`是11月9日00:00（UTC−5），即北京时间13:00，这是feed日批次标时，不是逐篇上线日志。[公告日程](https://info.arxiv.org/help/availability.html)规定该提交批次通常于周日20:00美东时间公开，换算为11月9日北京时间09:00，同样在本轮窗口内。代码已有更早提交，本次入选依据是新公告论文，不是“今天首次开源”。

## 为什么存成4位，还需要重新设计计算

生成每个新词元时，注意力要用当前查询Q匹配历史键K，再用得到的概率P对值V加权。历史越长、同时服务的请求越多，KV缓存的容量和读取开销越突出。

低比特存储通常先解决“搬多少数据”。如果计算前仍要把每块缓存还原成高精度，解码过程还得支付转换成本。本篇尝试让GQA主路径的QK与PV两次矩阵乘法都直接使用FP4张量核，因此不仅K、V，Q和P也要适应低精度。

本项目采用微缩放格式：NVFP4每16个4位数共享一个8位E4M3缩放值；MXFP4每32个数共享一个E8M0缩放值。[格式定义](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_decode_kernel/_decode.py#L44-L49)与[NVIDIA格式说明](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/)可交叉查看。按该代码的页面数据与块缩放布局计算，NVFP4平均占4.5位，尚未计入其他开销。因此，把BF16的16位除以4，不能直接得到整套服务的显存收益。

这里的“分组”是共享缩放值，双残差则作用于Q，不是把较高位宽的KV拆成多个位平面重组。下文结合公开实现解释数值处理；这是代码阅读，不是运行结果。

## 三处误差，分别处理

### 查询：让第二个FP4表示补回第一轮舍入的残差

一个查询会同时和大量历史键相乘，查询上的舍入误差会影响整排注意力分数。作者先量化Q，再把原始Q与第一次近似的差额量化一次，得到两项各带独立缩放的FP4表示；两项与K相乘的结果相加，近似原来的分数。

这类似先记下粗略值，再单独记录修正量。[查询量化源码](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_decode_kernel/quantize_q_kernel.py)中，第二项确实来自第一次近似后的残差。它减少的是这一步的数值误差，并不能单独保证最终答案正确。

### 概率：防止很小的关注权重整块变成零

长上下文里，许多概率块都很小。即使FP4数本身能表示某个相对值，其共享缩放值仍可能因E4M3表示范围有限而舍入为零，整块历史信息随之失去作用。

实现把概率统一放大8倍，将这一步折入softmax指数计算，最后由归一化抵消；对于较小概率块，再根据校准阈值选择不同的缩放规则，把缩放值抬离下溢区域。[概率配置](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_decode_kernel/p_scale.py)给出了相关模式。这里保护的是小概率信息，不是简单增大注意力。

### 键：让异常通道不再支配整组数值

如果一组通道中有一个特别大的值，共享缩放便会主要照顾它，其余小值更容易被粗糙舍入。硬件又要求沿每个词元的通道分组，不能任意改成最有利于统计分布的布局。

方法结合离线校准均值与匹配的Hadamard旋转，消除静态偏移、分散突出的通道，再从少量缩放候选中选择重建误差较小者。实际代码先旋转K再减去旋转后的均值，可检查[键写入实现](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_decode_kernel/quantize_kv_kernel.py#L123-L162)、[旋转](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_vllm/rotation.py)及[量化参考实现](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_decode_kernel/reference.py)。从数学上看，共同平移不改变softmax分布，匹配的正交变换保持内积；但量化误差仍然存在，需要实验验证。

离线校准需要覆盖什么数据，仍是部署问题。即便一种流程在作者的模型和输入上有效，也不能由此证明任意领域、模型版本和上下文长度都不需要重新检查。

## 精度补救怎样避免拖慢内核

FP4矩阵乘法变快以后，softmax可能成为新的瓶颈。常见布局按查询头分配工作，但解码时查询头组较小，部分线程闲置，少数线程却要连续扫描许多键。

作者改用转置布局，让线程沿历史键展开，再通过并行归约完成softmax。概率量化需要的块最大值直接复用中间结果，避免多扫描一次。[内核对应实现](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_decode_kernel/fp4_decode_kernel.py#L5382-L5508)

双残差Q看似又增加一次矩阵乘。实现利用张量核原本需要填零的空位，把两项Q堆叠进去，一次较宽的乘法同时产生两份分数，再用FP32相加。该提交只在每KV头对应4、8或16个查询头且满足单Q阶段等条件时开启此优化，不能理解成任意矩阵都能免费增加一份计算。[启用条件](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_decode_kernel/fp4_decode_kernel.py#L859-L866)

在线缓存也并非全部4位：主实现保留最前16个词元和尚未填满128词元页面的近期内容为BF16；页面填满后才量化。设备端控制内核管理这些缓冲与分页缓存，降低元数据处理成本。核验入口是[解码内核](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_decode_kernel/fp4_decode_kernel.py)及[缓存升级实现](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_vllm/promote.py)。

## 数字要按三种测量分别读

**准确率是多项基准的平均值。** 官方README所列结果中，Qwen3-4B-Thinking-2507与Qwen3-30B-A3B-Thinking-2507的七项均分，相对BF16 KV均下降不到0.5个百分点。七项覆盖LongBench Pro、MRCR、RULER-NIAH、AIME 2024／2025、LiveCodeBench v6及GPQA-Diamond。[官方结果与评测入口](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/README.md)

这不等于每项都差不到0.5点。例如4B模型的MRCR从38.82降至36.68，差2.14点，部分其他任务的提升抵消了均值下降。作者用“接近无损”描述总体结果，不能据此保证检索任务或每条输出不受影响。

**内核加速不等于服务加速。** 官方基准把合成输入的解码内核测试和完整vLLM吞吐测试分开运行。我们认为，评估时也应保留这层区分：算子更快是一个局部结果，排队、预填充和调度仍会影响用户等待。

**服务吞吐同时受显存容量影响。** README展示的B300实验涵盖64K输入、单卡TP=1，以及128K输入、双卡TP=2，并发为1、8、16、32、64；论文报告这些长上下文场景的峰值每GPU吞吐为BF16 KV的2.4至3.0倍。缩小缓存能容纳更多请求，因而峰值收益不能全部解释为单请求算子加速。[基准配置](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/benchmark/README.md)

因此，不能把内核峰值、某个请求的延迟和服务吞吐拼成一个通用倍率。部署时需要固定模型、上下文、并发和质量要求，再画出完整的吞吐与延迟曲线。

## MLA适配有一条不同的边界

论文[附录G](https://arxiv.org/html/2611.09825v1#A7)对Hy4-preview的MLA适配保留BF16位置分支，分数乘法用FP4，加权汇总则反量化后以FP16计算，省去P量化；作者没有报告其延迟收益。因此，不能把GQA主路径“两次乘法都原生FP4”的描述直接套给MLA，也不能从容量下降推定服务提速。

## 公开实现离生产迁移还有多远

[官方README](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/README.md)确认这是vLLM外置CUSTOM后端，要求B200或B300、CUDA 13及以上、Python 3.12；原创实现采用MIT许可，第三方组件各保留自己的许可，部分softmax辅助代码为BSD派生代码，详见[NOTICE](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/NOTICE)。不能说它已合入vLLM，也不能由论文其他硬件上的内核结果推断安装入口都支持。

源码揭示了比README更具体的迁移约束：[后端](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_vllm/backend.py)限定FP4路径的头维度为128、页面为128词元；[配置检查](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/src/nvfp4_vllm/guards.py)拒绝前缀缓存、分块预填充、推测解码、KV卸载及多级流水线并行等组合。这些是该提交的实现限制，不是理论上永远无法支持。

比较基线时也应核对精度、混合缓存和服务框架的具体配置，不能把某次实验扩展成整个项目的优劣排名。

实际评估至少应分开问三个问题。第一，同一模型、同一批请求下，量化是否伤害业务最在意的子任务，而不只看总均分。第二，固定并发时每个用户是否更快，还是主要因为系统能塞入更多请求才提高总吞吐。第三，为使用新后端关闭前缀缓存等功能后，原有服务节省的工作是否又被做了一遍。第三点是根据公开实现约束提出的迁移风险，并非论文已测出的负收益。

对关键业务，受控数值测试不能代替自由生成时的任务成功率和长尾失败分析。均分接近仍需要逐项、逐负载核对。

我们的判断是：这项工作最有价值的地方，是让低比特存储、数值稳定性和GPU执行相互配合。对已有Blackwell硬件、长上下文高并发且显存受限的服务，值得按[官方基准](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/benchmark/README.md)和[评测流程](https://github.com/OpenBitSys/BitDecoding-FP4/blob/4e2907d74d8b1cdb3bce2b4795fc86bf76385e7f/evaluation/README.md)验证。短请求、不同模型结构或依赖上述服务特性的系统，应先测任务质量与真实负载下的延迟分布，再讨论迁移。
