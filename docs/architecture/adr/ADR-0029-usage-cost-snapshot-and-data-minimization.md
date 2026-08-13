# ADR-0029: 使用 Usage 终态与成本快照并最小化内容数据

## 状态

已接受（2026-08-13）

## 背景

AI 调用需要留下可查询的 Token、耗时、模型和最终状态，才能分析稳定性与资源消耗。
非流式请求、流式请求、Provider 失败和客户端取消的生命周期不同，Provider 也可能
不返回完整 Usage。模型价格还会随 Provider、时间和配置变化，若查询时按最新价格
重新计算，历史结果会失去可解释性。

Message、System Prompt、模型回答、API Key 和 Provider 原始异常可能包含敏感内容，
它们不应为了可观测性被复制到新的数据库或日志中。Sprint 4 也不需要账单、预算、
配额、跨系统 Metrics 或 Tracing 平台。

## 决策

- 一次客户端 Chat 请求只生成一条 `ChatUsage`，Provider 内部 Retry 不单独生成记录。
- 终态固定为 `success / failed / cancelled`；成功记录 `finish_reason`，失败和取消记录
  项目内部固定 `error_code`，两组字段互斥。
- `ChatService` 负责判断业务终态、计算 Latency/TTFT 和协调写入；
  `ChatUsageRepository` 只负责 SQL，不判断业务状态或价格规则。
- Streaming 生成期间不持有数据库事务。请求进入终态后，通过独立 `SessionLocal`
  创建短事务写入 Usage。
- Provider 未返回可信 Token 时保存 `NULL`，不使用 `0` 伪造未知数据。已经收到的部分
  Token 可以保留，但只有输入和输出 Token 都已知时才能估算成本。
- 模型价格是 `AI_MODELS` 中的可选配置，输入和输出单价统一按每百万 Token 表达，
  使用 `Decimal` 计算并按 `Numeric(20, 10)` 精度四舍五入。
- 成本、三位大写币种和 `pricing_version` 在调用终态同时写入，形成不可变历史快照；
  修改以后价格不会重算旧记录。
- Usage 允许保存 `request_id`、`user_id`、模型别名、内部 Provider/模型标识、Prompt
  Key/Version、Token、Latency、TTFT、终态和成本快照。
- Usage 与普通日志禁止保存 Message、Prompt 正文、模型回答、API Key、完整 Base URL、
  原始 Provider 请求响应、SSE Chunk 或原始异常正文。普通 AI 日志不记录 `user_id`。
- Usage 持久化失败只记录安全的 `request_id + status`，并回滚短事务；它不会替换已经
  完成的模型结果，也不会掩盖原本的 Provider 错误或取消。

## 原因

- 终态记录属于用户业务请求，而不是某一次 SDK 尝试，因此由 ChatService 统一协调。
- 短事务不会在模型慢响应期间占用数据库连接或持有事务状态。
- `NULL` 明确表达未知，`0` 则会错误地进入成本和容量统计。
- 保存价格版本快照可以解释历史估算，同时避免建设当前不需要的完整计费系统。
- 内容数据最小化减少数据库泄漏、日志聚合和错误排查过程中扩散敏感信息的风险。

## 影响

- `chat_usages.request_id` 唯一，因此重复提交同一终态会触发持久化失败并安全降级。
- Usage 写入不是模型调用的分布式事务；模型成功但 Usage 写入失败时优先返回模型结果，
  日志提供后续告警线索。
- Streaming 在最终 Usage Event 前失败时，Token 与成本可能为空或部分已知；这是事实，
  不是数据缺陷。
- 当前成本是估算值，不代表 Provider 账单，也不支持扣费、退款、预算或配额。

## 未采用方案

- 在 Gateway 或 Provider 中写 Usage：这些层不知道认证用户和最终业务状态，会让稳定
  调用边界承担用户业务职责。
- Streaming 全程持有数据库 Session/Transaction：会让外部模型延迟直接占用数据库资源。
- 缺失 Token 时填写零或本地猜测：会把未知数据伪装成精确数据。
- 查询时按当前价格动态计算历史成本：价格更新后同一请求会得到不同结果。
- 保存完整 Prompt、回答或原始异常用于排查：当前没有足够的权限、保留和脱敏需求，
  风险大于收益。
- 在 Sprint 4 建设账单、预算、Dashboard 或 Metrics 平台：超出本 Sprint 的调用边界与
  生命周期目标。
