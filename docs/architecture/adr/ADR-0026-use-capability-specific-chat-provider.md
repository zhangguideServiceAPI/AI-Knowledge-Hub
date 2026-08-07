# ADR-0026: 使用 Capability-specific ChatProvider Protocol

## 状态

已接受（2026-08-07）

## 背景

不同模型 Provider 支持的能力并不相同。有的只支持 Chat，有的支持 Embedding 或
Rerank，有的才支持图片、音频或 Tool Calling。提前定义一个包含所有方法的万能
Provider，会迫使 Adapter 实现不支持的方法，也会让调用方无法从类型判断真实能力。

Story 4.3 当前只需要文本生成的非流式和流式调用，并需要一个 Fake Provider 验证
结果、事件、异常、取消和关闭行为。

## 决策

- 定义最小 `ChatProvider` Protocol，只包含 `generate()` 和 `stream()`。
- `generate()` 异步返回 `ChatResult`；`stream()` 返回 `AsyncIterator[ChatEvent]`。
- Provider `ChatEvent` 只包含 `ChatDelta`、`ChatUsageEvent` 和 `ChatDone`。
- Provider 失败通过 `ProviderError` 子类抛出，不把 `error` 混入成功事件联合类型。
- 使用项目自己的不可变 dataclass 表达 Message、Provider Request、Result、Usage 和 Event。
- Token Usage 允许缺失，不在 Provider 未报告时伪造数值。
- Embedding、Rerank、Image、Audio 和 Tool Calling 不进入 ChatProvider；未来按真实需求建立独立 Protocol。
- 使用结构化 Protocol，不要求 Adapter 继承项目基类；Fake 和真实 Adapter 通过契约与测试满足接口。

## 原因

- Interface Segregation 让每个 Provider 只实现真实支持的能力。
- Protocol 适合以行为和类型约束 Adapter，不需要共享构造函数或强制继承关系。
- 不可变 DTO 可以降低异步调用期间被跨层修改的风险。
- 将错误作为异常使事件流只表达正常数据与正常终态，Gateway 可以统一处理失败策略。
- 最小接口更容易为 Fake 和真实 Provider 编写同一 Contract Test。

## 影响

- 业务需要新能力时必须明确新增 Protocol，而不是随意向 ChatProvider 追加方法。
- Provider 原始 SDK Model 和 Chunk 必须在 Adapter 内转换后再返回。
- 公共 SSE `error` 不能由 Provider 直接产生，需要由 Gateway、Service 和 Router 翻译。
- Protocol 不提供运行时初始化规则；Factory 和 Settings 在 Story 4.4 单独负责具体 Adapter 的构造。

## 未采用方案

- 包含 Chat、Embedding、Rerank、Image 和 Tool Calling 的统一 Provider 基类：接口过大且大量方法无法实现。
- 直接返回 SDK Response 和原始 Chunk：会让调用方重新依赖厂商协议。
- 用 `ChatEventError` 表达 Provider 失败：会把异常控制流混入正常事件，并模糊 Retry 与资源清理位置。
- 使用抽象基类规定所有构造参数：不同 SDK 初始化差异很大，当前没有可共享实现需要继承。
