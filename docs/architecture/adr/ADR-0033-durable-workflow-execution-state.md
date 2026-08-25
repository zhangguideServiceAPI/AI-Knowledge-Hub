# ADR-0033: 使用 MySQL 保存 Workflow 执行事实与状态边界

## 状态

已接受（2026-08-25）

## 背景

知识修订审批跨越多个请求：提交后需要等待人工决定，审批通过后才会进入索引。内存中的
Python 对象、单个 HTTP 请求或 Redis 不能在重启、多进程或并发审批后提供可审计的流程真相。

Sprint 6 的首个可持久化领域模型必须区分整条流程、流程中的一步与某一步的实际执行尝试；
否则无法可靠表达等待、失败、恢复和并发竞争。该模型也不能混入 `DocumentVersion` 的技术
索引状态，或把业务审批结论误写成 Workflow 技术失败。

## 决策

- MySQL 保存三类长期执行事实：`WorkflowRun`、`WorkflowStepRun` 与
  `WorkflowAttempt`。Redis 只可用于缓存、限流或短期协调，不替代这些表。
- `WorkflowRun` 保存 `owner_id`、`definition_key`、`definition_version`、经校验的
  `run_input` 快照和整体状态。已创建 Run 的 Definition 身份在后续 Service 中不可变，
  恢复时必须按保存的 key + version 解析，不能静默改用新版本。
- `WorkflowStepRun` 用稳定 `step_id` 与 `step_index` 描述该 Run 中的一个 Definition
  Step；`WorkflowAttempt` 用同一 Step 内唯一且从 1 开始的 `attempt_number` 记录 A1、A2。
- 受控状态使用 Python `StrEnum` 与数据库 `CheckConstraint` 双层约束。`failed` 状态
  必须有稳定 `failure_code`；其他状态不得携带过期失败码。
- Run 的合法“状态 + 领域事件 -> 下一状态”由只读纯函数表集中定义；它只验证领域规则，
  不替代后续 Service 在 MySQL 中的条件 UPDATE。
- 三张表以外键、唯一约束和查询索引固定所有权、顺序与审计关系。节点输出只允许有限 JSON
  摘要；不保存向量、Prompt、Provider 原始异常或 Secret。
- 本 Story 只建立持久化模型与状态取值，尚不实现状态迁移 Service、Definition Registry、
  Node、Executor、重试、审批 API 或外部调用。后续 Service 必须以
  `UPDATE ... WHERE status = :expected_status` 推进状态，并在 `rowcount == 0` 后重读分类。

## 原因

- Run / StepRun / Attempt 分层使“流程正在等待审批”和“第几次索引尝试失败”都可独立审计，
  不需要依赖临时内存或日志推断。
- 数据库约束把无效状态、空 Definition 标识、重复 Step 顺序和重复 Attempt 编号拒绝在最终
  持久化边界；Schema 校验或 Python if 不能替代它。
- 以 JSON 保存小型、受验证的输入/输出快照，保留 Definition 演进后的恢复上下文，同时不在
  当前 Story 预先引入 Artifact、DSL 或任意用户工作流图。

## 影响

- 新增 Alembic Migration `e6f4c13e2a7b`，创建 `workflow_runs`、
  `workflow_step_runs` 和 `workflow_attempts`。
- 当前没有 API 或 Executor 创建这些记录；它们是 Story 6.2～6.7 的持久化基础。
- 业务审批状态仍属于未来 `KnowledgeRevision`，索引技术状态继续属于已有
  `DocumentVersion`；两者不迁移进 Workflow 表。

## 未采用方案

- 只在 Redis 保存 Run 状态：重启、过期或多进程协调后不可审计，且不符合 MySQL 作为业务
  真相的边界。
- 只使用一张 `workflow_runs` 表：无法表达多个 Step 与每次 Attempt 的独立状态和错误摘要。
- 在 ORM Model 中实现状态迁移方法：会把并发、事务和业务规则塞进 Model，违反 Model 只
  描述持久化结构的分层原则。
- 本 Story 提前创建可配置 Definition 表或用户 DSL：Definition 是后续 Story 的代码型不可变
  契约，当前只保存 Run 对它的版本引用。
