# ADR-0037: 使用 Step 级幂等键和条件恢复 Workflow

## 状态

已接受（2026-08-25）

## 背景

Workflow 外部动作遵循 at-least-once 恢复语义：一次调用可能已到达下游而调用方尚未写回 MySQL。
仅凭“再执行一次”会重复索引、重复发布或重复调用其他外部系统。与此同时，短暂依赖故障需要能从
失败 Step 恢复，而不能从 Workflow 开头重放已成功的步骤。

## 决策

- `WorkflowStepRun.id` 是同一逻辑 Step 在 A1、A2… 中不变的 `idempotency_key`。Executor 通过
  `WorkflowNodeExecutionContext` 把它传给 Node，Node 再传给其 Service / 外部系统的去重契约。
- 只有 Node 显式抛出 `WorkflowRetryableNodeError` 才持久化 `node_retryable`；其他异常是默认不可重试
  的 `node_execution_failed`，避免将未知副作用当作安全重放。
- Definition 为每个 Step 固定 `max_attempts`，默认 3。`WorkflowService.resume_failed_run()` 必须检查
  Run 所有权、失败类别、失败 Step、历史 Attempt 数，并使用带旧状态条件的 Update 同时重开
  `failed Run -> running` 与 `failed Step -> pending`。
- 条件更新未命中时不覆盖状态：重读后 `running` 或 `succeeded` 视为重复 resume 的幂等结果，其余
  情况返回明确冲突/不可重试错误。Repository 不自行 commit，Service 控制短事务。

## 影响

- A2 保留 A1 的失败和时间审计，Executor 在新认领后才创建新的 Attempt。
- 成功、取消、审批等待和永久失败不会因普通 resume 被重新执行。
- Qdrant 成功而 MySQL 收口失败仍不靠 VectorStore 反查猜测；未来 Index Node 必须调用
  KnowledgeService 的受控 reconciliation，再用同一 Step key 幂等收口。

## 未采用方案

- 每次 Attempt 生成新的外部幂等键：下游无法识别 A2 是 A1 的恢复。
- 对所有异常自动重试：会重复永久业务失败和未知写入。
- 从 Run 的第一个 Step 重跑：会重复已经成功的审批、索引或发布副作用。
