# ADR-0030: 使用 Version 状态机与补偿保持知识索引一致性

## 状态

已接受（2026-08-19）

## 背景

Knowledge / RAG 索引跨越 MySQL、对象存储、Embedding Provider 和 Qdrant。它们没有共享
事务：文件解析、模型调用、向量写入或 MySQL 状态提交的任一步骤都可能失败或超时。
如果直接把 Qdrant 当作业务数据库，无法可靠地校验所属用户、文件来源、处理配置、版本
和清理状态；如果没有 Version 状态机，重复上传、并发重试或新旧 Version 乱序完成又会
产生重复索引、孤儿向量或 active Version 回退。

Sprint 5 第一版需要一条可理解、可恢复的同步索引路径，不在当前阶段引入 Celery、消息
队列、分布式事务或后台调度平台。

## 决策

- MySQL 是 Knowledge 的业务真相，保存 `KnowledgeBase -> KnowledgeDocument ->
  DocumentVersion -> DocumentChunk`、所有权、原文 Chunk、处理配置、状态和
  `active_version_id`。Qdrant 只保存可再生的向量索引。
- 一个 Qdrant Point 的稳定 ID 使用 `DocumentChunk.id`；payload 只保存
  `knowledge_base_id` 与 `document_version_id`，分别用于检索范围过滤和按 Version 清理。
  权限、原文和 File 元数据不复制为 Qdrant 业务真相。
- `DocumentVersion` 的索引生命周期固定为：

  ```text
  pending -> processing -> indexed
                 |
                 +-> failed
                 +-> cleanup_required
  ```

  `failed` 代表本次没有残留向量或已补偿成功；`cleanup_required` 代表向量残留可能存在，
  不能直接重新索引。
- Service 先在短 MySQL 事务内原子认领 `pending -> processing`，随后在事务外执行
  Embedding 和 Qdrant 批量 upsert。向量成功后，另一个短 MySQL 事务将 Version 标记为
  `indexed`，并仅在它比当前 active Version 新时更新 `active_version_id`。
- Qdrant 写入失败时，Service 按 `document_version_id` 删除本次可能写入的全部向量。
  补偿成功后标记 `failed`；补偿失败或结果不确定时标记 `cleanup_required`。
- `failed` 重试时重置为 `pending` 后复用正常索引流程。`cleanup_required` 重试必须先
  成功执行同一 Version 的 Qdrant 删除，再重置为 `pending`；删除仍不可用时保持原状态并
  返回可重试的服务不可用错误。
- 上传文件、创建 Document、创建 pending Version/Chunk 与索引阶段分别提交。解析或索引
  失败不会回滚已经成功保存的 File 和 Document，旧的 active Version 继续可用于检索。
- 当前上传 API 同步执行索引并返回 Version 的实际终态。未来后台任务只负责调度同一条
  Service 状态机，不能绕过状态、幂等和补偿规则。

## 原因

- MySQL 的关系、外键和所有权查询更适合作为业务审计与权限判断来源；Qdrant 擅长向量
  相似度搜索，不适合替代关系业务数据库。
- `DocumentVersion` 把原始文件不变但 Parser、Chunker 或 Embedding Profile 改变的索引
  结果隔离开来，保证不同向量空间不会混用。
- 原子认领防止并发请求为同一 Version 重复付费、重复写入；只允许更高版本激活避免
  较旧索引晚完成时覆盖较新的 active Version。
- 显式的 `cleanup_required` 比把不确定的外部状态伪装成失败更可靠，后续可以安全重试。

## 影响

- 检索只查询 active、已索引 Version 的 Qdrant 点，并仍从 MySQL 回填 Chunk 原文与来源；
  Retrieval 在 Story 5.7 实现。
- 业务操作需要处理 `pending / processing / indexed / failed / cleanup_required`，前端或
  调用方不能只依赖 HTTP 上传成功来判断知识是否可检索。
- 一次 Embedding 或 Qdrant 调用可能较慢，但不会长时间占用 MySQL 事务；Sprint 5 先以
  同步请求实现，后续 Sprint 10 再把索引调度迁移到异步平台。
- 清理按 Version 而不是按 Document 执行，因此新旧 Version 可以共存，直到明确的文档
  删除策略处理它们。

## 未采用方案

- 将 Chunk 原文、File 元数据、权限和状态全部写入 Qdrant：会复制业务真相，无法利用
  MySQL 的关系约束，也增加权限和数据漂移风险。
- 每次失败都直接创建一个新 Version：会让同一处理配置重复嵌入、重复付费且难以定位
  残留向量。
- 仅用调用顺序假设 MySQL 与 Qdrant 一定同时成功：跨系统没有共同事务，超时与部分成功
  时会留下不可解释的数据。
- 在 Sprint 5 直接引入 Celery、RabbitMQ 或分布式事务：当前目标是先验证领域状态机和
  补偿边界，基础设施调度属于 Sprint 10。
