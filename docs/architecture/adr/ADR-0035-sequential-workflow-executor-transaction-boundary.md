# ADR-0035: 使用两段短事务的顺序 Workflow Executor

## 状态

已接受（2026-08-25）

## 背景

Story 6.1 已将 WorkflowRun、WorkflowStepRun 和 WorkflowAttempt 作为 MySQL 中的长期事实；
Story 6.2 已确保 Definition 与 Node 在启动期受控且可验证。现在需要在不持有长事务的前提下，
可靠执行一个已定义 Step，并留下成功或失败的审计记录。

Node 最终会通过业务 Service 调用索引、文件、审批或 Provider 等外部能力。这些调用的耗时和
失败不可预测，不能包在 MySQL 事务中，也不能让 Node 自己更新 Workflow 状态。

## 决策

- 使用 `SequentialWorkflowExecutor.execute_next(run_id, node_input)` 作为最小执行入口：仅从
  `running` Run 中选择 `step_index` 最小的 `pending` Step。
- 第一段短事务通过 `UPDATE ... WHERE status = 'pending'` 原子认领 Step 为 `running`，并创建
  同一事务中的 `Attempt A1 = running` 后提交。条件更新 `rowcount == 0` 是正常竞争或状态变化，
  此次调用返回无工作，不覆盖现有状态。
- 认领完成后才在事务外解析精确 Definition/Node 并调用 `Node.execute()`。Node 不直接访问
  Qdrant、Embedding 或 Provider SDK；真实业务动作仍经 Service 边界。
- 第二段短事务统一收口：成功时将 Attempt 和 Step 变为 `succeeded` 并保存有限 JSON 输出；没有
  后续 pending Step 时才将 Run 变为 `succeeded`。失败时将 Attempt、Step 和 Run 都写成 `failed`
  并保存稳定失败码。
- 任一收口条件更新未命中时回滚该段事务并报告状态竞争，避免只更新三层状态中的一部分。SQL/commit
  异常仍按数据库异常上抛，不能伪装成 `rowcount == 0`。

## 影响

- WorkflowRepository 只做数据访问，不自行提交；Executor 明确拥有每段短事务的 commit/rollback。
- Step 在认领后若发现 Definition/Node 配置异常、输入输出契约不匹配或 Node 抛异常，也必须走失败
  收口，避免永久停在 `running`。
- 首版只接受调用方明确传入的 `node_input`，只支持线性流程。字段映射与条件分支由 Story 6.4
  统一定义，不能在 Executor 内以任意字典或表达式临时拼接。

## 未采用方案

- 在一个数据库事务内调用 Node：网络慢、超时或进程中断会长期占锁并阻塞其他 Workflow 操作。
- 让 Node 直接写 StepRun / WorkflowRun：业务节点会耦合执行审计、并发规则和持久化细节。
- 把 `rowcount == 0` 一律当数据库故障：它通常是带旧状态条件的正常谓词未命中，应先保留状态并在
  更高层结合重读结果分类为幂等成功、冲突或不存在。
