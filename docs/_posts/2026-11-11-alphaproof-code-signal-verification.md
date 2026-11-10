---
title: "AlphaProof Code：协议安全证明走到机器码，工程师还需要相信什么"
date: 2026-11-11T05:39:00+08:00
summary: "AlphaProof Code 将协议安全声明连接到编译后的 libsignal，并开放 Lean 证明材料。它展示了可检查的 AI 工程交付，也把规范、机器语义、密码假设与实际应用之间的边界摆到台前。"
section: explainer
label: "AI 与形式化验证"
tags: [AlphaProof Code, Lean, Signal, 形式化验证, 智能体, 软件安全]
demo: false
sources:
  - title: "Google DeepMind：Introducing AlphaProof Code，2026-11-10"
    url: "https://deepmind.google/blog/introducing-alphaproof-code/"
  - title: "Google DeepMind 官方 RSS：公告时间"
    url: "https://deepmind.google/blog/rss.xml"
  - title: "AlphaProof Code: Verifying Signal’s Security at the Machine-Code Level，2026-11-10"
    url: "https://deepmind.google/documents/36/Formal_Verification_of_Signal_4.pdf"
  - title: "公开验证材料固定快照 808b4b7"
    url: "https://github.com/google-deepmind/code-verification/tree/808b4b7ffef198e6a91f71ed776d641a1c236882"
  - title: "计算安全主定理"
    url: "https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/Computational/Theorems/Main.lean"
  - title: "符号安全主定理"
    url: "https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/Symbolic/Theorems/Security.lean"
  - title: "Comparator 的检查方式与边界"
    url: "https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/comparator/README.md"
---

## 这项进展值得看在哪里

AI 写出一段代码之后，工程师往往还要靠测试和审查判断它是否可靠。AlphaProof Code 展示了另一种交付方式：让 AI 针对既有代码生成可由独立检查器核验的证明，并将安全声明一路连接到编译后的程序。

11月10日，Google DeepMind 公开了针对 Signal 协议实现的研究与 Lean 验证材料。官方 RSS 标注公告时间为 **12:02:28 UTC，即北京时间20:02:28**，处于本轮最近24小时窗口。本文资料核验截至北京时间 **2026年11月11日05:39**，源码固定于 `808b4b7ffef198e6a91f71ed776d641a1c236882`。本文做了论文与源码的静态核对，**未运行 Lean 构建、Comparator 或 Signal 二进制**。

最重要的变化是证明的落点：公开成果把抽象的协议安全属性与一个明确的机器码执行对象连接起来。工程价值既取决于证明是否成立，也取决于被证明的对象、环境和攻击模型是否覆盖实际需求。

## 先锁定对象：是一份可识别的二进制

[仓库说明](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/README.md)给出的对象是 libsignal v0.105.4 与 spqr v1.6.0：把既有 Rust 实现接入一个命令行封装程序，再编译成 AArch64 Linux 可执行文件。核心入口是初始化会话、发送和接收。密钥生成不在本次证明范围，完整手机应用也没有随之获得覆盖。

机器码对象通过 [`cliElfBytes`](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/LibsignalBinary/Specifications/SignalSession/CliElf.lean) 绑定到 SHA-256 固定的 ELF 文件。主定理还检查代码布局、地址和重定位如何落在该文件中。因而，审阅者可以追问“你证明的究竟是哪一份程序”，而不只接受一个版本名称。

这里的意义是缩小设计与实现之间的空隙。协议在纸上成立，仍可能在序列化、会话状态更新、内存处理或编译结果中偏离设计。直接证明目标机器码，会把这类偏离纳入需要处理的对象；但换了编译参数、链接方式或运行环境，也必须重新论证对应关系。

## 证明链条怎样接起来

公开的[计算安全入口](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/Computational/Theorems/Main.lean)与[符号安全入口](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/Symbolic/Theorems/Security.lean)可以概括为三步：

1. 写清安全目标，例如哪些状态泄露之后，哪些消息还应保密，以及攻击者能够安排哪些交互。
2. 证明机器码在给定环境中实现了 Lean 模型描述的状态变化。
3. 将模型层的安全结果转移到该二进制的执行轨迹。

第二步尤其关键。一个模型很安全，并不能自动说明应用实现了它。公开代码中的 refinement（精化）证明负责搭这座桥，主定理再组合模型安全与实现对应关系。

两条安全路线各有用途。符号路线把密码操作视作具有规定性质的抽象运算，便于分析状态和交互；计算路线把攻击成功率与底层密码假设、查询预算及统计项联系起来。两者提供互补证据，不能把一条路线的优势无条件搬到另一条上。

## AI 可以写证明，验收目标仍要由人守住

Lean 检查的是形式化命题及其证明。假如命题把困难情况从前提中排除了，再长的证明也无法把它补回来。例如，若一项服务可靠性声明只允许“永远不会失败的输入”，形式上成立仍可能对工程验收毫无帮助。

因此，AlphaProof Code 的流程把规范审阅与证明生成分开。公开的 [Comparator 配置与说明](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/comparator/README.md)要求同时检查命题、递归依赖的定义、允许使用的公理，并在新的 Lean 内核环境中重放导出的证明。只比较最外层定理的一行文字不够，下面被引用的定义也可能改变其含义。

**我们的分析：**这是一种值得借鉴的 AI 工程验收方法。任务目标要有可追踪版本；负责完成任务的一方，不应靠自行修改目标来宣布成功。允许修订规范是必要的，但修订本身应成为单独审阅的变更。

不过，公开检查脚本不等于现成的隔离安全系统。Comparator 文档明确写出：规范依赖在检查中仍被信任；先构建不可信解答再准备挑战目标的流程，不能直接承担防恶意代码篡改的威胁模型。把它推广到外部投稿、供应链或自动合并平台时，还需设计构建隔离与目标保护。

## 剩下的信任集中在哪里

形式化验证减少了需要逐行相信的证明推导，却仍有一组必须审查的前提。

- **Lean 检查内核。** 检查器本身需要可靠，这是接受其核验结果的基础。
- **规范。** 它是否真的表达了用户需要的安全，而非更容易成立的弱化版本。
- **机器与进程语义。** Lean 中的指令、内存、加载器及系统调用模型，需要对应真实运行环境。项目把这些放在明确的[可信定义目录](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/arm64-semantics/Arm64/Trusted/README.md)，与可由内核检查的推导分层。
- **外部例程合约。** 目标中的部分底层密码原语、库函数及输出操作使用 hook，以规定行为代替逐条执行其真实实现。这些合约与密码安全假设仍需成立。
- **对象与环境对应关系。** 固定的二进制、符号提取、构建过程和部署环境，都属于结果落地时必须核对的链条。

这让审计资源有了更明确的去向：重点看“证明了什么、假设了什么、对应哪份产物”，而不是要求人阅读每一行 AI 生成的证明。

## 安全结论要按具体场景读取

[公开定理定义](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/Symbolic/Specifications/Security/Binary.lean)直接包含合约、初始化、随机性和碰撞分支等条件；[执行轨迹定义](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/Symbolic/Specifications/Refinement/Statement.lean)也明确约束调用和会话状态。阅读结果时，不能跳过这些条件只看“secure”这个名字。

论文第5节进一步划定了几条实用边界：计算安全结果面向经典攻击者；符号路线允许碰撞例外而不计算其概率，针对棘轮的结论也不证明 SPQR 带来的抗量子入侵后恢复。侧信道、群聊、多设备和完整应用环境没有因此获得验证。概率界还受会话规模影响，过宽的上界可能失去实际信息。[原始论文，第5节](https://deepmind.google/documents/36/Formal_Verification_of_Signal_4.pdf)

这些限制不抵消“连接至机器码”的价值，而是决定这份成果可以怎样被复用。安全关键系统应逐项对照自己的攻击模型、状态生命周期与部署差异，确定哪些条件已有证据，哪些还需要新的证明或测试。

## 开放材料带来了什么，尚未带来什么

作者报告约650万行 Lean 证明，项目由5位研究者在四周内推进。四周包含规范制定、审阅以及持续运行代理的工作，不能据此推导无人值守能力或固定的人力节省倍数。[原始论文，第7节](https://deepmind.google/documents/36/Formal_Verification_of_Signal_4.pdf)

公开材料的价值在于给读者留下可检查的入口。[README](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/README.md)固定了 Lean、Rust 等工具版本，并给出构建、二进制校验与 Comparator 重放路线。代码原则上按 Apache 2.0 发布，第三方 libsignal 等材料保留各自许可，不能把整个仓库统一当成单一许可的软件包。

静态核对还提示了一个现实问题：说明文档也会落后于代码。例如论文映射表中，历史漏洞反证的迁移状态仍有旧表述，而[具体反证声明](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/Symbolic/BugInjection/Disproofs/Cheval26WeakStateCli.lean)已经使用当前的 placed 安全谓词。另有辅助合成反证保留未完成项，位于[非默认构建目标](https://github.com/google-deepmind/code-verification/blob/808b4b7ffef198e6a91f71ed776d641a1c236882/lakefile.lean#L664-L675)，不能据此推断主定理依赖它们。本文没有把文档里提到的 CI 流程当作已实际核验的公开构建结果。

**我们的判断：**AlphaProof Code 最值得关注的方向，是让 AI 的大规模工作产出具备清晰对象、明确规范与独立验收路线。下一步的实用性，要看外部团队能否重放、规范能否持续审计，以及软件升级之后证明维护的代价。证明生成更快之后，工程重心会更明显地转向定义目标、控制可信边界与维护版本一致性。
