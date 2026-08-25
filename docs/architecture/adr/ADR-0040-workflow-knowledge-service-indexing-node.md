# ADR-0040: Workflow 索引 Node 只委托 KnowledgeService

## 状态

已接受（2026-08-25）

## 决策

- `IndexAndActivateVersionNode` 只接收已冻结的 Version 身份与 `KnowledgeService`，调用
  `KnowledgeService.index_document_version()`；Workflow 层不得直接使用 Embedding Gateway、Qdrant
  Client、VectorStore 或 Provider SDK。
- Executor 先用短事务以条件更新认领 Step 并创建 Attempt，随后结束事务，再 `await` Node 的外部
  I/O；Node 返回后才在第二段短事务收口 Attempt、StepRun 与 Run。
- 只有 `DocumentVersion = indexed` 才能收口 Workflow 成功。未认领、`failed` 和
  `cleanup_required` 都是显式可恢复故障，持久化为 `node_retryable`，由既有 Resume 和 Version
  reconciliation 流程处理。

## 影响

知识索引的技术状态、向量补偿和 active Version 提升继续集中在 KnowledgeService；Workflow 只持久化
编排事实。因此旧 active Version 会在新 Version 审批、索引或恢复期间继续服务 RAG，且 Sprint 10
可把同一 Executor 迁至后台 Worker 而不泄露 Provider 或 Qdrant 能力给 Workflow。
