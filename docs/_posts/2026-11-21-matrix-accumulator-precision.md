---
title: "矩阵乘法究竟用多少位累加？拆开 H100、B200 和其他 AI 芯片的精度链"
date: 2026-11-21T12:45:00+08:00
summary: "从 FP4、FP8、FP16、BF16 到 TF32 和真 FP32，逐层区分乘数、指令累加槽、内部归约、跨卡加法与写回精度，并给出验证方法。"
section: explainer
label: "芯片与数值计算"
tags: [Tensor Core, H100, B200, FP4, FP8, 精度, GEMM]
demo: false
sources:
  - title: "NVIDIA PTX ISA 9.5：矩阵指令与目标架构约束"
    url: "https://docs.nvidia.com/cuda/parallel-thread-execution/"
  - title: "NVIDIA cuBLAS：GEMM 数值行为和 fast accumulation"
    url: "https://docs.nvidia.com/cuda/cublas/"
  - title: "DeepSeek-V3 技术报告：FP8 高精度累加"
    url: "https://arxiv.org/html/2412.19437v2"
  - title: "Khattak、Mikaitis：Tensor Core 算术微基准"
    url: "https://arxiv.org/html/2512.07004v4"
  - title: "SF Tensor：B200 tcgen05 位级测量及模型"
    url: "https://sf-tensor.com/engineering/bitwise-tcgen05"
  - title: "AMD CDNA4 ISA"
    url: "https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-cdna4-instruction-set-architecture.pdf"
---

**最容易读错的一行是「FP8 输入、FP32 累加」：它可能只告诉你 MMA 接口用 FP32 接收和保存部分和，不代表硬件内部逐项执行 IEEE FP32 FMA，也没告诉你沿 K 连跑几百条指令、切给多个 CTA、最后跨卡求和时用的精度。** H100 就有官方明确的反例：原生 FP8 WGMMA 即便选择 FP32 结果，中间累加精度仍介于半精度和单精度之间。B200 的低精度路径也不只一种，普通 FP8、MXFP8、MXFP4 和 NVFP4，不能共用一个所谓的「内部累加位宽」。

## 1. 先把「多少位」问完整

矩阵指令 MMA（matrix multiply-accumulate）做的是一个小块的 **D = A × B + C**。C 是进入该指令的部分和，D 是本次结果；库最后写回的输出也经常被叫 D，但不是同一层的 D。要读一张规格表，至少补齐以下几栏：

| 边界 | 应该问什么 | 常见误读 |
|---|---|---|
| 内存与互联 | 权重、激活、scale、跨卡 buffer 分别存什么？ | W4A16 就等于 FP4 Tensor Core |
| 乘数、乘积 | 硬件收到的是低精乘数，还是先反量化？乘积如何对齐？ | 两个 8 bit 相乘就是 8 bit 乘积 |
| 单条 MMA | C/D 格式是什么？指令里多少项一起合？哪些舍入公开承诺？ | FP32 槽就等于每项单精度 FMA |
| 跨 MMA / Split-K | 每个输出 tile 局部和存哪里？何时提升？部分和怎么跨 CTA 汇总？ | tile 数越多，归约层数必然越多 |
| 跨卡与写回 | send/recv dtype、通信算法、归约、bias 和最终 cast 顺序？ | 单卡 FP32 局部和足以保证端到端 FP32 |

这里的「有效位」要和「存储位」分开。FP32 是 1 符号位、8 指数位、23 个显式小数位，正规数含隐含首位共 **24 个有效二进制位**；FP16 是 1/5/10（11 个有效位），BF16 是 1/8/7（8 个），TF32 是 1/8/10（11 个）；常见 FP8 E4M3、E5M2 分别是 4、3 个有效位，FP4 E2M1 是 2 个。这里描述的是正规数的格式，不意味着不同 FP8 编码对特殊值、指数偏置或次正规数处理相同。算浮点数时，两个正规乘数的完整有效数乘积，最多需要两者有效位数之和；接下来把不同指数的乘积对齐相加，又是另外一个精度和动态范围问题。**「FP32 有效位 24」「实验看到 14 个有效位」「固定点归约器总宽 33 位」是三种口径，不能相减或横比。** [CUDA 浮点说明](https://docs.nvidia.com/cuda/floating-point/index.html) · [PTX 数据类型与矩阵指令](https://docs.nvidia.com/cuda/parallel-thread-execution/)

## 2. H100、B200：逐格式对照

下表的「累加槽」只指所列矩阵指令的架构接口，不是显存输出 dtype，不是对物理加法树的描述。主要列原生密集路径，实际内核还要核对变体、形状、稀疏性和目标架构。

| 输入/工作模式 | H100（Hopper，SM90） | B200（数据中心 Blackwell，SM100） | 实际读法 |
|---|---|---|---|
| **FP4 E2M1** | 没有 Hopper 原生 FP4 浮点 WGMMA；存成 4 bit 可由内核反量化成硬件支持的格式再做 MMA | 非块缩放的 tcgen05 f8f6f4 支持 FP4/FP6，按变体有 FP16/FP32 D；原生 MXFP4/NVFP4 块缩放的相应变体为 FP32 D | 同为 4 bit，非块缩放与块缩放是不同指令路径 |
| **INT4 / W4A16** | 兼容的 warp-level S4/U4 整数 MMA 变体是 S32；W4A16 是低位权重存储加高精激活，不能认作双 INT4 | 同理；不能把兼容 warp 指令当成 tcgen05 FP4，也不能按原生 FP4 FLOPS 估 weight-only | 写清输入是整数还是浮点、是否反量化，哪条指令实际执行 |
| **FP8 E4M3/E5M2** | 原生 WGMMA 支持 FP16/FP32 累加槽；FP32 D 变体有官方的低于单精度中间累加说明 | 非块缩放 f8f6f4 支持 FP16/FP32 D；MXFP8 对应块缩放变体为 FP32 D | 对历史 Hopper FP8，是否启用周期性提升非常关键；不外推 B200 |
| **INT8 S8/U8** | WGMMA 整数路径为 S32 | tcgen05 i8 为 S32 | 整数溢出/饱和要按具体指令，量化的 zero point 或重缩放另算 |
| **FP16** | WGMMA 提供 FP16 或 FP32 累加槽 | tcgen05 f16 类提供 FP16 或 FP32 D | FP32 槽通常是关心的混合精度模式，非默认唯一选择 |
| **BF16** | WGMMA 为 FP32 | tcgen05 为 FP32 | 与 FP16 同为 16 bit，但输入精度、指数范围不同 |
| **TF32** | TF32 乘数，WGMMA FP32 累加槽 | TF32 乘数，tcgen05 FP32 D | 不是 FP32 × FP32。Hopper PTX 还列明 WGMMA 发起乘法前对 TF32 操作数位的截取；把 FP32 准备成 TF32 时的舍入是独立步骤 |
| **真 FP32 × FP32** | 标量/向量 FP32 FMA 是基本路径；不可直接拿 TF32 矩阵峰值 | 同理。例如库可采用 BF16 多分量仿真，要按具体算法和误差看 | FP32 张量类型不保证乘法实际用了真 FP32；检查[库的 compute 策略](https://docs.nvidia.com/cuda/cublas/#cublascomputetype-t) |

核对源：[Hopper WGMMA 的类型、K 形状与精度说明](https://docs.nvidia.com/cuda/parallel-thread-execution/#asynchronous-warpgroup-level-matrix-multiply-accumulate-instructions-wgmma-mma-async)；[PTX warp-level MMA](https://docs.nvidia.com/cuda/parallel-thread-execution/#warp-level-matrix-instructions-mma)；[Blackwell 指令描述符](https://docs.nvidia.com/cuda/parallel-thread-execution/#tcgen05-instruction-descriptor)；[CUTLASS SM100 支持矩阵](https://github.com/NVIDIA/cutlass/blob/main/python/CuTeDSL/cutlass/cute/nvgpu/tcgen05/mma.py)及[原生 NVFP4 示例](https://github.com/NVIDIA/cutlass/blob/main/examples/72_blackwell_narrow_precision_gemm/72b_blackwell_nvfp4_nvfp4_gemm.cu)。当接口给出精度下限但未规定加法顺序、舍入或次正规数行为时，不能据此写出逐位一致的仿真公式。对后一代同品牌产品，也不能从营销规格反推同一微架构。

### H100/H800 的 FP8：为什么已经写回 FP32 还要再加一次？

[NVIDIA PTX 9.5](https://docs.nvidia.com/cuda/parallel-thread-execution/#asynchronous-warpgroup-level-matrix-multiply-accumulate-instructions-wgmma-mma-async) 的特例明确限定 FP8 E4M3/E5M2、FP32 D 型 WGMMA：当前实现的中间累加宽于半精度、窄于单精度。[NVIDIA Tile IR 数值文档](https://docs.nvidia.com/cuda/tile-ir/latest/sections/stability.html#execution-numerical-guarantees) 也把 Hopper 的快速累加与周期性提升分开。这里不能仅看 PTX 泛化段落而忽略特例。Hopper 的 WGMMA 由四个 warp（128 线程）协同发起；以密集 FP8 m64nNk32 为例，一个指令逻辑上为每个输出元素合入 32 个 K 项，不等于公开了这 32 项的门级加法树。

- **H100 实测**：[PyTorch 托管的原始微基准](https://pytorch.org/blog/some-matrix-multiplication-engines-are-not-as-accurate-as-we-thought/)在其 native QGMMA 的 K=32/128 探针上，观察到 FP32 结果低 10 个小数位已无有效信息，留下约 13 个显式小数位，含隐含首位约 14 个有效位。不是一个对外可读写的 FP22 类型。
- **H800 实测与训练做法**：[DeepSeek-V3 §3.3.2/§3.5.2](https://arxiv.org/html/2412.19437v2)观察到相近问题，其随机 K=4096 示例报告最大相对误差接近 2%，不是所有层的误差上限。做法是先在 Tensor Core 做 128 个 K 元素的局部点积（4 条 K32 WGMMA），再把 chunk 的 FP32 表示送 CUDA Core，用 FP32 把块级部分和相加，并在相应位置合入 K 分块缩放。**提升保护的是不同块之间的和，不会复原块内已丢的位。** 128 是该实现的选择，不是 H100 的硬件精度定律。
- **库的开关**：[cuBLASLt](https://docs.nvidia.com/cuda/cublas/#cublasltmatmuldescattributes-t) 的 FAST_ACCUM 属性文档把跳过周期性较高精度提升与速度/精度权衡相连，注明当前影响 Ada/Hopper；不要拿它推断其他架构的内部行为，也不要把关闭它写成「每项严格 IEEE FP32」。[CUTLASS 实现](https://github.com/NVIDIA/cutlass/blob/main/include/cutlass/gemm/collective/fp8_accumulation.hpp)能看到独立的临时累加器、提升间隔以及何时将余下部分和并入。

### B200 的块缩放：scale 并不是片尾乘一次就完了

Blackwell tcgen05 可由单线程发起，架构可见的部分和放 Tensor Memory（TMEM），而不是 Hopper WGMMA 那样呈现为线程寄存器片段。TMEM 的槽是接口；单线程发起也不意味着单线程顺序做所有乘加。[NVIDIA tcgen05 编程指南](https://docs.nvidia.com/cutlass/4.8.0/media/docs/pythonDSL/guides/mma/tcgen05_programming.html)

以同一输出元素为例，每个 K 分段 b 有各自的 A/B scale（可以随输出行或列变化）。数学等价式如下，硬件不必按这段伪代码实现：

```text
P[b] = sum over k in block b of qA[i,k] * qB[k,j]
Y[i,j] = C[i,j] + sum over b of sA[i,b] * sB[b,j] * P[b]
```

只有 scale 对这条点积的所有 K 项恒定时，才可在整条点积之后乘同一个 scale。取两个块 P₀=8、P₁=8，两块 scale 乘积分别为 1 和 1/8，则结果是 9，不是 16 再乘某个块的 scale。MXFP4 通常是 32 个元素配 E8M0 scale；NVFP4 典型是 16 个元素配 E4M3 scale，软件格式还可配独立的张量级缩放；MXFP8 典型是 32 个元素配 E8M0。**量化分组大小不是整条 MMA 的 K 大小，也不是软件跨 MMA 提升间隔。** [PTX 块缩放语义](https://docs.nvidia.com/cuda/parallel-thread-execution/#tcgen05-block-scaling) · [NVIDIA NVFP4 格式说明](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/)

内部细节目前最好的公开证据来自**指定指令的数值探针**：

| 独立原始研究 | 实验拟合到了什么 | 为什么不能升格为芯片通用规格 |
|---|---|---|
| [Khattak 与 Mikaitis，v4 表 3/4、图 5](https://arxiv.org/html/2512.07004v4#S5) | 密集 native FP8、K32：H100 WGMMA 对齐参数 (2,13)，固定点求和模型宽 21；B200 非块缩放 tcgen05 对齐参数 (2,25)，固定点宽 33。同文的 FP16/BF16→FP32 两代均拟合为 25 个小数对齐位 / 32 位求和宽 / K16，TF32→FP32 为 25 / 31 / K8 | 模型宽含符号/整数空间与对齐，不是 21/33 位浮点，也不是芯片公开物理布局；同名 PTX 在所测工具链还可能降成不同的 SASS，要核对 native 指令 |
| [SF Tensor 的 B200 探针、公开数据及模型](https://sf-tensor.com/engineering/bitwise-tcgen05) | 非块缩放 F8/F6/F4 及其所测 MXF8F6F4 符合以最大原始指数为参考、向低位延伸 25 位的对齐模型；单独的 MXF4/NVFP4 家族符合更宽、由原始乘积和 scale 指数共同影响的窗口，NVFP4 路径可拟合先合 4 项再截断的局部分组；在 C 指数主导的特定探针中，还可观察到 K16 块级的截断边界 | 25 是对齐窗口模型参数，不与上一行 33 位总和宽冲突，也不能把更宽窗口叫通用的「39 位 FP4 累加器」。分组模型能解释观测，不等于公开了 RTL、流水阶段数或 Rubin 的行为 |

## 3. 真正经历了哪几次累加？

以 M×K 乘 K×N 为例。**切 M/N 是做不同输出；切 K 才是在给同一个输出做不同部分和。** 这句话能排除多数关于「并行必有全局累加」的误会。

```text
乘数 + scale
    ↓
MMA 指令内部：若干乘积 / 块部分和 → 对齐 → 局部归约 → C/D 槽
    ↓
同一输出 tile 沿 K 循环：保留局部和，可定期提升到另一累加槽
    ↓
[仅当 Split-K] 多个 CTA 的部分和 → workspace / 原子或第二步归约
    ↓
[仅当跨设备切 K] rank partial → AllReduce / ReduceScatter
    ↓
完整和 → α/β、bias / 激活等 epilogue → 最终输出格式
```

1. **指令内部**：可以把典型做法想成并行生成乘积，依据指数对齐到共同或分组的固定点空间，再归约、进入下一阶段。对齐时小项可能丢低位，树或阵列如何分组决定哪里舍入。由多操作数归约构成的 MMA 不能等同于标量 FMA 链。一个标量 IEEE FMA 只保证单个 ab+c 融合后舍入一次，不能让长点积只舍入一次。
2. **CTA 内沿 K**：给同一个 tile 的一条线程束/线程块持续发 MMA。示意：K=4096，K32 指令，需 128 条逻辑 MMA 贡献；每 4 条提升一次则外层合入 32 个部分和。如果局部 C 在每条指令都会重新对齐，不能因槽叫 FP32 就把整个序列按 FP32 标量加法估误差。流水重叠/双缓冲是执行调度，亦不代表数值上存在独立部分和。 [CUTLASS GEMM 分块](https://docs.nvidia.com/cutlass/4.8.1/media/docs/cpp/efficient_gemm.html)
3. **单设备跨 CTA**：M/N 小、K 大时 Split-K 可让更多 CTA 同时跑，代价是额外的部分和归约、workspace 或原子更新。问清 partial 从哪种格式写出、归约是否又窄化、最后何时 cast。[cuBLAS 数值行为](https://docs.nvidia.com/cuda/cublas/#gemm-algorithms-numerical-behavior)举出计算类型高于输出类型时的中间溢出；CUBLAS_MATH_DISALLOW_REDUCED_PRECISION_REDUCTION 约束对应 cuBLAS 路径的低精归约，不等于关闭 Split-K，也不是 Tensor Core 内部精度开关。cuBLASLt 应另核算法及 reduction scheme。
4. **跨设备**：行并行线性层前向分 K，得把 rank partial 合起来；列并行前向通常是切 N，合并的是不同输出分片（不等于同一元素的 K 求和，反向还需另看）。各 rank 可以先在 FP32 形成局部和但以 BF16 发送；通信 API 的 datatype 是可见接口，不能据此推断所有协议/算法的内部临时精度。拓扑、树/环、分块可改变加法顺序。 [Megatron Core 并行层](https://docs.nvidia.com/megatron-core/developer-guide/latest/apidocs/core/core.tensor_parallel.layers.html) · [NCCL 集合接口](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/api/colls.html)
5. **片尾**：完整归约后再算应当只应用一次的 bias、βC；非线性通常也要等全和。库可能融合这一阶段，请单独记录 epilogue 计算和最终存储类型。最后写 BF16 不等于前面 BF16 累加；反过来，最后转成 FP32 也不能救回前面的丢位。

再深一层：固定点对齐后，若同号项幅度相近，要无溢出地合并 p 项，整数侧最坏约多留 ⌈log₂ p⌉ 个增长位；但增加整数侧空间并不能救回指数对齐时截掉的小数位。可以用树并行合并，也可以让部分和停在处理单元里，随 A/B 沿阵列流动而更新（输出驻留的脉动阵列）。两者都可实现同一个矩阵乘法，却不必有相同的中间舍入点。Hopper/Blackwell 的门级具体拓扑没有从这些公开接口中得到证明。以阵列数据流作直觉模型，某个输出留在一个 PE 时，PE 可逐拍收到新的 aₖ、bₖ 更新局部和；如果做空间并行的 K 分段，则多个局部和还需合并。前者少搬部分和，后者可提高小 M/N 下的并行度。不能光看 PE 个数倒推出归约位宽。

三个可手算的边界案例：

- **即使全是标准 FP32 加法也依赖顺序。** RNE 下，(2²⁴+1)−2²⁴ 得 0，(2²⁴−2²⁴)+1 得 1。
- **跨卡 cast 可独立造成误差。** 精确的 rank partial 为 257 和 −256，应得 1；第一个数转 BF16 时恰在 256 与 258 中间，RNE 得 256。之后即使用 FP32 归约也只剩 0。
- **Split-K 的半精度 workspace 可让有限值变 NaN。** 取四个可由 FP16 乘数构成的贡献 40000、40000、−40000、−40000。两个 FP32 局部和为 ±80000，先合再转 FP16 得 0；若各自先写 FP16，RNE 下变成 ±Inf，再相加得 NaN。

整数更容易算边界，而非自动安全。S8×S8 的最坏同号积可达 16384，从 C=0 开始，连续 131072 项取该值就超过有符号 32 位正上限。实际还要计已有 C、zero point 修正和中间归约；S32 出口既不代表无限 K，也不说明具体指令选择了饱和还是回绕。Hopper WGMMA INT8 的普通形式溢出回绕，加 satfinite 才饱和；B200 查看 i8 描述符对应模式。对于 INT4，兼容 warp-level PTX 不是芯片有原生双 INT4 高吞吐路径的证明，依目标查看编译后的机器指令。

## 4. 其他芯片：可以对比的规格，与不能对比的位宽

| 芯片/单元 | 可从公开资料核到的路径 | 不能顺手推断什么 |
|---|---|---|
| **AMD MI300X / CDNA3** | MFMA 可用 FP16/BF16、FP8/BF8 乘数和 F32 C/D；INT8 路径用 I32；另有 F32 乘数的 F32 MFMA | CDNA3 FP8 编码须看该代 FNUZ 等约定，不按 H100 同名格式直接交换比特 |
| **AMD MI355X / CDNA4** | 缩放 MFMA 支持 FP8/FP6/FP4，分 K 每 32 元素 E8M0 scale，F32 C/D。ISA 描述为块点积缩放后累加；另有 BF16/FP16、F32 与整数路径 | 不把 F32 槽、指令级舍入/次正规数说明推广成逐项 IEEE FMA 或内部保护位已公开 |
| **Google Cloud TPU MXU** | Google 明确 BF16 乘数/FP32 累加；新代按代际另列 FP8、INT8 支持，不把它们和 BF16 文档互换 | FP32 累加与 systolic 阵列数据流公开也不等同于每种低精度变体的逐位等价保证 |
| **Intel Gaudi 3 MME** | Intel 公布 FP32 累加器，列出 FP8 E4M3/E5M2、BF16、FP16、TF32、FP32 矩阵路径；公开材料描述输出驻留的 systolic MME | 文档没给所有模式的内部归约位数、分组和舍入行为 |
| **昇腾 950DT/PR** | MmadMx 公开 FP4 族内 E1M2/E2M1、FP8 族内 E4M3FN/E5M2 的混合组合，按 K32 用 E8M0 缩放、FP32 bias 与 FP32 L0C。C 接口允许将 L0C 原值作为累加初值；另有 BF16/FP16 的 float MMAD 路径 | 文档没说 FP4×FP8 混乘，也没披露阵列内部归约、保护位、逐项舍入。普通 Mmad 的原生 FP8 模式与 MmadMx 要分开查 |

来源：[AMD CDNA3 ISA](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-mi300-cdna3-instruction-set-architecture.pdf) · [AMD CDNA4 ISA](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-cdna4-instruction-set-architecture.pdf) · [Google TPU 架构](https://docs.cloud.google.com/tpu/docs/system-architecture-tpu-vm)与[BF16 精度说明](https://docs.cloud.google.com/tpu/docs/bfloat16) · [Gaudi 3 白皮书](https://cdrdv2-public.intel.com/817486/gaudi-3-ai-accelerator-white-paper.pdf)及[MME 架构资料](https://cdrdv2-public.intel.com/845118/gaudi-3-ai-accelerator-30-3-30.pdf) · [昇腾 MmadMx 类型表](https://asc.gitcode.com/api/SIMD-API/basic_api/cube_compute_ISASI/mmad_compute/MmadMx.html)、[FP32 累加初值 C 接口](https://asc.gitcode.com/api/SIMD-API/c_api/cube_compute/mmad_compute/asc_mmad_mx.html) · [CANN Mmad 类型](https://www.hiascend.com/document/detail/zh/canncommercial/83RC1/API/ascendcopapi/atlasascendc_api_07_0249.html)及 [L0C 留存说明](https://www.hiascend.com/doc_center/source/en/CANNCommunityEdition/900/programug/Ascendcopdevg/atlas_ascendc_best_practices_10_0023.html)。

## 5. 怎么测，才能知道应该修哪一层？

**先建立两份参考，而不是拿最终 BF16 结果和 FP32 GEMM 简单相减。** 第一份用 FP64 或更高精度计算原始 A、B 的乘积和；第二份用同样参考算法计算实际量化码值加实际 scale 所代表的 Â、B̂。两份参考之间主要是输入量化误差；设备结果与第二份之间才包含 MMA、跨块/跨卡归约和片尾误差。逐元素误差可分解，但误差范数不能简单相减。对消减严重的输出，结果本身可能接近零，用最大相对误差判定很不稳。建议同时报告非有限值、绝对误差分位数、相对 Frobenius 误差，以及逐输出的绝对误差除以 Σ|aₖbₖ|（零分母单独标记）。

| 顺序 | 保持什么不变 | 只切什么 / 看什么 |
|---|---|---|
| 1. 确认真实算子 | 卡型、编译器/驱动、同一输入码值、同一 scale | 单卡单 tile、FP32 写回、无 Split-K，记录实际指令；对单条 MMA 探测一个大项加一串小项、正负相消、指数差、tie、次正规数 |
| 2. 确认长 K 漂移 | 同一算子家族与输出类型 | 扫 K、K-block 边界和提升间隔；fast 与较高精路径对照，同时看时间、吞吐、额外寄存器/带宽 |
| 3. 确认 kernel 级归约 | 固定输入及量化参考 | Split-K 开关、分片数量、workspace 精度、输出格式分别改；抓中间 partial，不把调度变化和精度变化混到一组 |
| 4. 确认跨卡归约 | 固定每个 rank 的部分和语义和业务输入 | 比较写回前后、发送前后及归约输出；对相同部分和另做高精度主机参考，扫通信 dtype、算法、TP 规模与拓扑 |
| 5. 回到训练/推理业务 | 相同模型与质量条件 | 训练分别测 fwd、dgrad、wgrad，覆盖真实 K/长尾梯度和收敛；推理分别测 prefill/decode、长上下文、MoE 小/大 batch，评估质量和性能的 Pareto |

给性能建模的落点：为每条 GEMM 记清 **存储格式 → 真实乘数 → MMA C/D → 周期提升 → Split-K partial → collective dtype → epilogue/output**。按真实指令选峰值代表计算上限，按真实物理 dtype 和 scale、workspace、通信 buffer 算带宽；需要软件 FP32 提升或额外归约时，单算其开销，不能藏进同一张低精 TFLOPS 规格表。平台对比可以先拿单卡 FP32 输出、固定真实输入的探针锁定数值路径，再到相同精度目标下比较吞吐。**能查清的是指令契约与部分实测；不能查清的晶体管级加法宽度，不用一个看起来精确的数字填空。**

本文使用公开文档和他人发布的原始实验，未做独立上卡复测。同品牌不等于同数值实现。比如 [NVIDIA Rubin 架构说明](https://developer.nvidia.com/blog/inside-the-NVIDIA-rubin-platform-six-new-chips-one-ai-supercomputer/)公开格式与编程兼容性，不等于给出了与 B200 逐位一致的实现；本文不移植前述内部位宽。
