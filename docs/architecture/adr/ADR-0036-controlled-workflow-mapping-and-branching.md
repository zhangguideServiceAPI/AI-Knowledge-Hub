# ADR-0036: 使用受控字段映射与固定 Workflow 分支

## 状态

已接受（2026-08-25）

## 背景

Workflow Node 的输入不能由 HTTP 请求在每一步任意拼装，也不能依赖内存中的上次调用结果；恢复时
必须能从 MySQL 中的 Run 输入快照和成功 Step 输出重建同一输入。审批等业务还需要根据 Node 的
结构化输出选择后继，但若允许字符串表达式、`eval`、用户 DSL 或模型临时建议，流程将失去可审计的
确定性。

## 决策

- `WorkflowInputBinding` 只允许把 `run_input` 或 `previous_step_output` 的一个顶层字段复制到
  Node 输入的一个唯一顶层字段。它不读取对象属性、请求体、环境变量或任意 JSONPath。
- `WorkflowBranchDefinition` 以一个字符串 selector 字段和一组不可变 `WorkflowBranchCase` 表示
  固定分支；每个 expected value 只能指向一个已定义的后继 Step。未知、缺失或非字符串 selector
  都是明确的分支失败，绝不默认批准或回退。
- 一个 Step 只能有一个线性 `next_step_id` 或一组固定 branch cases，不能同时拥有两种后继规则。
  Registry 将全部候选边纳入现有的目标存在性、类型兼容、环路、可达性和单前驱校验。
- `WorkflowRouteResolver` 保持纯计算；Executor 对带 bindings 的 Step 只读取持久化 Run/Step 摘要，
  不接受调用方提供的替代输入，并在 `StepExecutionResult` 中报告明确选中的后继。

## 影响

- 同一 Run 事实与同一 Node 输出在重试/恢复中得到相同的映射和分支结果。
- 字段缺失与未知 decision 会在真正访问后续 Node 前失败，不会误索引、误发布或绕过审批。
- Story 6.4 只负责计算和报告目标；选择后的 Step 持久化激活及未选择分支的终态仍需后续
  WorkflowService 与条件更新统一协调，不能由纯路由类伪造数据库事实。

## 未采用方案

- 在 Definition 内保存可执行 Python、字符串条件或 `eval`：代码审计、权限边界和恢复语义都会失控。
- 由客户端在请求 `execute_next()` 时提交下一 Node 输入：会绕过 Run 快照、审批输出和历史审计。
- 未知 decision 默认进入 approved 或默认后继：业务错误会变成不可逆的索引/发布副作用。
