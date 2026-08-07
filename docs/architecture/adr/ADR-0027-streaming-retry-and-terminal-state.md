# ADR-0027: 固化 Streaming、Retry 与错误终态策略

## 状态

已接受（2026-08-07）

## 背景

非流式 HTTP 在完成前没有向客户端提交成功响应，失败时仍可选择 HTTP 状态码。
SSE 一旦发送 Header 和第一个 Event，后续就不能修改状态码。此时自动重试可能把
已经发出的文本再次生成，造成重复内容、重复计费和无法判断的终态。

客户端断开还会同时影响两条连接：客户端到 FastAPI 的下游连接，以及 Provider
Adapter/SDK 到外部 LLM 的上游连接。取消不正确会让模型在无人接收时继续生成。

## 决策

- 非流式与 Streaming 使用不同端点和明确 Content-Type，不用一个 `stream` 布尔值返回两种协议。
- Provider 流按 `delta -> usage -> done` 的正常语义输出；`done` 与 `error` 互斥。
- 第一个公共 Event 前，Rate Limit、建连失败和 Provider 5xx 可以在严格次数与总体 Deadline 内有限重试。
- Context Too Long、请求校验、鉴权、余额和配置错误不重试。
- 第一个 Delta 发出后禁止自动重试；后续失败转换为一个安全公共 SSE `error` Event。
- Provider Adapter 抛 `ProviderError`，不直接生成公共 SSE Error。
- 客户端断开使用原生 `asyncio.CancelledError` 沿 Router、Service、Gateway 传播到 Provider。
- 每层在 `finally` 中释放自己拥有的资源；Adapter 关闭上游 SDK/HTTP Stream。
- 客户端断开通常不再发送取消 Event，由 ChatService 记录 `cancelled` Usage 终态。
- Streaming 期间不持有数据库 Transaction；终态使用短事务写入 Usage。
- Provider 未返回最终 Usage 时 Token 字段保存为空，不伪造为零。

## 原因

- 在协议允许的时间点保留有限恢复能力，同时避免已输出后的重复响应。
- 区分正常 `done` 与异常 `error`，客户端可以可靠判断结果是否完整。
- 原生取消语义能被 asyncio Task 和 SDK 正确识别，不会误触发业务 Retry。
- 明确资源所有权可防止上游连接、生成任务和数据库事务泄漏。
- Usage 记录真实证据，即使 Provider 没有给出完整 Token 统计也不制造假数据。

## 影响

- Gateway 必须跟踪是否已经产生可见输出，并让 Retry 策略受此状态约束。
- Router 在 SSE 开始前必须完成认证、Schema 校验和可以提前执行的业务校验。
- Service 必须为 success、failed 和 cancelled 三种终态协调 Usage。
- Streaming Test 必须覆盖流前错误、首个 Delta 后错误、客户端取消和 `aclose()`。
- Retry 可能发生在 Provider 已经开始计费但尚未输出的调用上，因此必须限制次数并记录 Attempt。

## 未采用方案

- 流开始后自动重新调用模型：会重复输出并可能重复计费。
- 所有错误都依赖 HTTP 状态码：SSE Header 发出后无法改变状态。
- 捕获 `CancelledError` 并转换成 ProviderUnavailable：会把用户取消误判为系统故障并触发 Retry。
- Streaming 全程持有数据库事务：慢客户端或长生成会长时间占用连接和锁。
- Provider 未返回 Usage 时写零：零表示已知没有消耗，与未知统计语义不同。
