# ADR-0041: 只允许在等待审批阶段撤回知识修订

## 状态

已接受（2026-08-25）

## 决策

- 作者可通过 `withdraw_revision()` 撤回仍为 `submitted` 的 Revision；同一短事务把等待中的
  WorkflowRun / WorkflowStepRun 变为 `cancelled`，Revision 变为业务终态 `withdrawn`。
- 撤回只适用于 `waiting_approval`，不创建 Attempt，也不修改 `DocumentVersion` 的技术索引状态。
- 一旦批准后索引 Step 已经可能进行 Embedding 或 Qdrant I/O，普通撤回请求返回冲突。后台 Worker
  引入前不承诺“杀线程式取消”；未来只能在 Node 的安全边界实现协作取消和补偿。

## 影响

用户可在无外部副作用的阶段安全撤回，审计记录能区分“人撤回”和“审批拒绝”。同时避免一个 SQL
状态更新假装已经取消可能仍在运行的索引请求，保护 Version/向量库一致性。
