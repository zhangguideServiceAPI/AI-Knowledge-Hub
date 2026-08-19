# ADR-0031: 使用 MySQL 校验 Qdrant 向量检索候选

## 状态

已接受（2026-08-19）

## 背景

Qdrant 中一个 Point 只保存 Chunk 向量、`knowledge_base_id` 和 `document_version_id`。
它可能暂时保留旧 Version、已经删除文件或等待清理的向量；而 `active_version_id`、文件
READY 状态、所有权和 Chunk 原文仍是 MySQL 的业务真相。若 API 直接返回 Qdrant 命中，
就可能检索到旧知识或已不可访问的文件内容。

Sprint 5 的第一版只实现 Dense Vector Retrieval，不实现 Hybrid Search、Reranker、Query
Rewrite、Context 组装或 Chat 回答。检索参数也不能由客户端任意扩大，否则会绕开模型成本
和 Context 预算策略。

## 决策

- 检索入口为受认证的 `POST /knowledge-bases/{knowledge_base_id}/search`，请求体只接收
  非空 `query`；Embedding 模型、Top K、候选倍率和 Cosine 分数阈值均由 Settings 决定。
- `KnowledgeService.search_knowledge()` 先验证当前用户拥有 KnowledgeBase，再以默认
  Embedding Profile 将 Query 转为 Vector。Query 与已索引 Chunk 必须使用兼容的向量空间。
- `VectorStore.search()` 只接收 Query Vector、KnowledgeBase ID、limit 和 threshold，返回
  有序的 `chunk_id + score` 候选，不返回 SDK 对象、原文或权限结论。
- Qdrant 使用 `knowledge_base_id` payload 进行第一层范围过滤。Service 以 `top_k * 候选
  倍率` 预取，补偿 MySQL 过滤掉旧 Point 后可能出现的结果空洞。
- Repository 在单条 MySQL 查询中确认：Chunk 所属 Document 在目标 KnowledgeBase；其
  Version 同时为 `indexed` 且等于 `Document.active_version_id`；File 仍为 `READY` 且未
  删除。只有通过这些条件的记录才能成为 `RetrievalHit`。
- Service 按 Qdrant 分数顺序恢复 MySQL 回填结果，最多返回服务端 Top K。`RetrievalHit`
  包含 `chunk_id`、`document_id`、`file_id`、原文、`source_locator` 和 `score`，为后续
  Citation / Context 提供稳定输入。
- Embedding 错误继续使用既有 AI Error 映射；Qdrant 不可用返回 503，不把外部故障伪装为
  空结果。非法向量库配置或响应契约错误返回安全的 500。

## 原因

- Qdrant 擅长近邻搜索和 payload 预过滤，MySQL 擅长关系、状态、文件可见性和审计；两者
  各自完成擅长的部分，避免复制业务真相。
- active Version 检查保证新 Version 成功后旧向量不会继续参与检索，即使它们尚未物理清理。
- 预取候选而非直接只查 Top K，可在旧 Point 被过滤后保留更多有效结果，同时仍由服务器
  限制最终返回量与外部模型成本。
- 独立 RetrievalHit 隔离 SQLAlchemy Model 和 Qdrant SDK，使 Story 5.8 可以专注
  Context 截断与 Citation，而不重新解释存储实现。

## 影响

- 一次检索包含 Query Embedding、一次 Qdrant 请求和一次 MySQL 回填查询；不会修改
  DocumentVersion、Qdrant Point 或索引状态。
- 旧/删除 Point 会被静默过滤，而不是作为错误返回；Qdrant 无法连接、超时或无法处理响应
  才是调用方需要重试的 503。
- 第一版可能因为候选倍率不足而少于 Top K；这比返回未经 MySQL 校验的数据更安全。可在
  真实评估数据出现后调整倍率或使用分页检索。
- Citation、Context Token Budget、Prompt 注入防护与 ChatService 集成仍属于 Story 5.8/5.9。

## 未采用方案

- 直接将 Qdrant 搜索结果返回客户端：会绕过 active Version、File 生命周期和 MySQL 原文
  事实来源。
- 把完整权限与原文复制到 Qdrant：会制造多份业务真相和同步漂移。
- 客户端提交任意 Top K、threshold 或 Embedding 模型：会导致成本、性能、越界模型空间和
  Context 预算不可控。
- 在 Story 5.7 同时实现 Hybrid、BM25、Rerank 或 Query Rewrite：缺少评估基线，复杂度
  会掩盖 Dense Retrieval 的正确性边界。
