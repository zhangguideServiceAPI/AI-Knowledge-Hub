# Sprint 5：Knowledge / RAG

> Sprint 5 目标：把 Sprint 3 的 File Resource 与 Sprint 4 的 AI Gateway 连接起来，形成一个完整、可追溯、可扩展的 Knowledge / RAG 能力闭环。
>
> 长期路线只定义能力边界；具体 API、数据表、ADR、验收标准等，在推进到对应 Story 时再详细设计。

---

## 状态

Sprint 5 正在进行，当前进入 Story 5.7 Retrieval 的设计阶段。Story 5.1 至 5.6 已完成
领域模型、解析、Chunk、Embedding、Qdrant 和同步索引的实现；按当前学习约定，新增测试
暂缓，完整回归与 Story 验收仍待后续统一执行。

```text
Current Sprint: Sprint 5 Knowledge / RAG
Current Story: Story 5.7 Retrieval
Current Goal: 从已索引的 KnowledgeBase 中检索相关 Chunk，为 Context 与 Citation 准备输入
Current Step: 定义 KnowledgeService.search_knowledge(...) 的输入、输出与边界
```

| Story | 状态 | 已形成的实现证据 |
| --- | --- | --- |
| 5.1 Knowledge Domain Design | 实现完成，测试待补 | KnowledgeBase、KnowledgeDocument、DocumentVersion、DocumentChunk，复合 active Version 外键与处理指纹 |
| 5.2 Document Parsing | 实现完成，测试待补 | PDF、TXT、Markdown Parser 注册表与统一 ParsedDocument / Block 来源信息 |
| 5.3 Chunking Strategy | 实现完成，测试待补 | Token 计数、结构化切分、最大 Token 与 overlap 配置 |
| 5.4 Embedding Pipeline | 实现完成，测试待补 | EmbeddingProvider、EmbeddingGateway、模型 Profile、批量向量生成与维度校验 |
| 5.5 Vector Store / Qdrant | 实现完成，测试待补 | VectorStore 协议、Qdrant Adapter、Collection 初始化、payload 过滤索引、批量 upsert 与清理 |
| 5.6 Indexing Pipeline | 实现完成，测试待补 | 上传同步索引、Version 原子认领、状态机、补偿、active Version 提升、失败重试 API |
| 5.7 Retrieval | 进行中 | 先定义 Service 检索用例，再接 Query Embedding、Qdrant Search 与 MySQL 回填 |
| 5.8 Citation & Context | 未开始 | - |
| 5.9 RAG End-to-End & Review | 未开始 | - |

当前实现决策见 [ADR-0030](../architecture/adr/ADR-0030-knowledge-indexing-lifecycle-and-vector-store-consistency.md)。

---

## 一、Sprint 5 定位

### North Star

> **把用户上传的 File Resource，经过解析、切分、向量化、索引，最终变成可以被业务检索并返回 Citation 的 Knowledge Resource。**

```text
File Resource
      ↓
Document
      ↓
Parse
      ↓
Chunk
      ↓
Embedding
      ↓
Vector Store
      ↓
Retrieval
      ↓
Context
      ↓
Citation
      ↓
AI Gateway
      ↓
RAG Answer
```

---

# 二、Story 总览

| Story | 名称 | 核心问题 |
|---|---|---|
| **5.1** | Knowledge Domain Design | 文件和知识到底是什么关系？ |
| **5.2** | Document Parsing | PDF / Markdown / TXT 如何变成统一文本？ |
| **5.3** | Chunking Strategy | 一篇文档如何切成可检索的知识块？ |
| **5.4** | Embedding Pipeline | Chunk 如何转换成向量？ |
| **5.5** | Vector Store / Qdrant | 向量如何存储、索引和管理？ |
| **5.6** | Indexing Pipeline | File → Parse → Chunk → Embedding → Index 如何串起来？ |
| **5.7** | Retrieval | 如何找到最相关内容？ |
| **5.8** | Citation & Context | 检索结果如何形成可追溯 Context？ |
| **5.9** | RAG End-to-End & Review | 如何完成从文件到 AI 回答的完整闭环？ |

---

# 三、Story 详细规划

## Story 5.1：Knowledge Domain Design

核心问题：

> **File Resource 和 Knowledge Resource 是不是一个东西？**

建议形成：

```text
File Resource
    │
    │ ingest
    ▼
Knowledge Document
    │
    ├── Document Version
    └── Chunk
```

核心领域关系：

```text
User
 ↓
Knowledge Base
 ↓
Document
 ↓
Chunk
 ↓
Embedding
```

核心概念：

- Knowledge Base
- Document
- Document Version
- Chunk
- Embedding
- Index

必须理解：

- 为什么 `File ≠ Knowledge`
- 原始文件与知识文档为什么需要分离
- Knowledge Base 为什么需要独立 Domain
- Document Version 为什么重要
- Chunk 为什么不能直接等同于 File

第一阶段不深入 Qdrant API、Embedding SDK、RAG Chat API。

---

## Story 5.2：Document Parsing

解决：

```text
PDF
Markdown
TXT
```

如何统一转换为：

```text
ParsedDocument
```

基础流程：

```text
File
 ↓
Parser
 ↓
Document
 ↓
text
metadata
source
```

第一阶段关注：

- PDF
- Markdown
- TXT
- 编码
- 空文件
- 无法解析
- metadata
- page information

### Source Metadata

后续 Citation 必须能够回答：

```text
来自哪个文件？
哪一页？
哪个 Chunk？
```

因此解析阶段就必须保留足够的来源信息。

---

## Story 5.3：Chunking Strategy

核心问题：

> **一篇文档应该如何切成适合检索的知识块？**

需要理解：

### Fixed-size Chunk

```text
1000 tokens
```

### Overlap

```text
Chunk A
████████████

       ████████████
       Chunk B
```

### Semantic / Structure Chunk

按照标题、段落、语义边界切分。

第一版策略：

> **稳定的结构化 Chunk + 长度控制 + overlap**

暂不追求复杂 Semantic Chunking。

后续可扩展：

```text
ChunkStrategy

├── Fixed
├── MarkdownStructure
└── Semantic
```

必须理解：

- 为什么需要 Chunk
- Chunk 太大有什么问题
- Chunk 太小有什么问题
- Overlap 解决什么问题
- 为什么 Chunk Strategy 应该可扩展

---

## Story 5.4：Embedding Pipeline

核心流程：

```text
Chunk
 ↓
AI Gateway
 ↓
Embedding Provider
 ↓
Vector
```

### 核心原则

Embedding 不应该绕过 Sprint 4 AI Gateway，直接在 Knowledge 模块里调用 Provider SDK。

```text
                 AI Gateway
                /                    Generation      Embedding
             │                │
             ▼                ▼
          Workflow           RAG
                              │
                              ▼
                            Qdrant
```

需要理解：

- 为什么 Embedding 也应该经过 AI Gateway
- Embedding Model
- Embedding Dimension
- Model Version
- Provider
- Usage Tracking

### Embedding Versioning

例如：

```text
Model A
1536 dimensions

↓

Model B
3072 dimensions
```

旧 Vector 不能直接与新 Vector 混用，因此需要理解 Embedding Versioning。

---

## Story 5.5：Vector Store / Qdrant

正式引入：

> **Qdrant**

重点不是单纯掌握 Qdrant API，而是理解：

> **MySQL 和 Vector Store 为什么需要职责分离？**

推荐结构：

```text
Knowledge Document
        │
        ├───────────────┐
        ▼               ▼
      MySQL           Qdrant
    metadata          vector
```

### MySQL

负责：

- Knowledge Base
- Document
- Document Version
- Chunk Metadata
- Processing State
- 权限关系
- 业务元数据

### Qdrant

负责：

- Vector
- Vector Index
- Retrieval Metadata

必须理解：

- 为什么不能把所有东西都放 Qdrant
- 为什么 Vector Store 不是业务数据库
- MySQL 与 Qdrant 的一致性问题

---

## Story 5.6：Indexing Pipeline

这是 Sprint 5 的核心工程 Story。

最终形成：

```text
File Resource
      ↓
Parse
      ↓
Chunk
      ↓
Embedding
      ↓
Vector Store
```

需要考虑：

- document status
- processing status
- failed
- retry
- version
- idempotency
- duplicate processing

状态可以先设计为：

```text
PENDING
   ↓
PROCESSING
   ↓
INDEXED
```

失败：

```text
PROCESSING
      ↓
FAILED
      ↓
RETRY
```

### 边界

Sprint 5：

> 先设计 Pipeline 的 Domain / Service / State。

Sprint 10：

> 再通过 Async Platform 将长任务真正异步化。

因此 Sprint 5 不以 Celery / RabbitMQ 等异步基础设施为核心实现。

### 当前实现状态

当前同步上传入口已经形成以下闭环：

```text
POST /knowledge-bases/{knowledge_base_id}/files
  -> FileService.upload
  -> KnowledgeDocument
  -> pending DocumentVersion + DocumentChunk
  -> 原子认领为 processing
  -> EmbeddingGateway 批量生成向量
  -> QdrantVectorStore 批量写入
  -> indexed + 安全提升 active_version_id
```

失败状态与恢复规则：

```text
Embedding 失败                 -> failed (embedding_failed)
Qdrant 写入失败且清理成功       -> failed (vector_store_failed)
Qdrant 清理失败或结果不确定     -> cleanup_required
MySQL 完成状态写入失败          -> 删除该 Version 向量，再进入 failed 或 cleanup_required

failed
  -> POST .../versions/{version_id}/retry
  -> pending -> processing

cleanup_required
  -> 先删除该 Version 的 Qdrant 向量
  -> 删除成功才允许 pending -> processing
```

`Document.active_version_id` 只会指向成功 `indexed` 的 Version；新 Version 失败或处理
较旧 Version 晚完成时，旧的有效 Version 不会被覆盖或回退。跨 MySQL 与 Qdrant 的完整
决策和补偿边界记录在 ADR-0030。

---

## Story 5.7：Retrieval

核心流程：

```text
Query
 ↓
Embedding
 ↓
Qdrant Search
 ↓
Top K
```

需要理解：

- Top K
- Similarity
- Score
- Threshold
- Metadata Filter

第一版：

> **先实现 Dense Vector Retrieval。**

暂不加入：

- BM25
- Hybrid Search
- Reranker

---

## Story 5.8：Citation & Context

这一 Story 必须保留。

目标不仅是“找到文本”，而是让知识：

> **可检索、可追溯、可评估。**

检索结果应该保留：

```text
Chunk

├── document_id
├── chunk_id
├── file_id
├── page
├── content
├── score
└── metadata
```

最终：

```text
Answer
  ↓
Citation
  ↓
Document
  ↓
Page / Chunk
```

用户需要能够知道：

> **AI 的答案到底来自哪里。**

---

## Story 5.9：RAG End-to-End & Review

完成完整闭环：

```text
Upload File
      ↓
Create Knowledge Document
      ↓
Parse
      ↓
Chunk
      ↓
Embedding
      ↓
Qdrant
      ↓
User Query
      ↓
Retrieval
      ↓
Context
      ↓
AI Gateway
      ↓
LLM
      ↓
Answer + Citation
```

最终能力：

1. 上传文件
2. 创建 Knowledge Document
3. 解析文档
4. Chunk
5. Embedding
6. 建立 Vector Index
7. Retrieval
8. Context
9. AI Gateway
10. Answer + Citation

完成后进行：

- Code Review
- Test Review
- Architecture Review
- Knowledge Review
- Sprint Review

---

# 四、Sprint 5 整体架构

```text
                 ┌──────────────┐
                 │ File Resource│
                 │   Sprint 3   │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │    Parser    │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │   Chunker    │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │ AI Gateway   │
                 │  Sprint 4    │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │  Embedding   │
                 └──────┬───────┘
                        │
                ┌───────┴────────┐
                ▼                ▼
             MySQL            Qdrant
          Metadata           Vector
                │                │
                └───────┬────────┘
                        │
                        ▼
                   Retrieval
                        │
                        ▼
                    Context
                        │
                        ▼
                  AI Gateway
                        │
                        ▼
                  Answer + Citation
```

---

# 五、Sprint 5 明确暂不做

第一版明确排除：

- Hybrid Search
- BM25
- Reranker
- Multi-modal RAG
- Graph RAG
- Agentic RAG
- Query Rewrite
- HyDE
- 复杂多租户权限
- Celery
- Kafka
- Kubernetes

特别是：

```text
Hybrid Search
Rerank
Query Rewrite
Agentic RAG
```

不是“不学习”，而是：

> **不放进 Sprint 5 第一版 RAG 闭环。**

---

# 六、Sprint 5 能力验收

Sprint 5 完成后，不以“代码能运行”作为唯一标准。

应该能够回答：

### 架构

> 为什么 MySQL + Qdrant？

### Domain

> File、Document、Chunk、Embedding 分别是什么？

### Chunk

> 为什么需要 Chunk？

### Embedding

> 为什么 Embedding Model 变化会影响整个索引？

### Retrieval

> Top K 和 Similarity Threshold 分别解决什么问题？

### 工程

> 一个文档重复上传 / 重复索引怎么办？

### 可靠性

> Parsing 失败怎么办？

### 可追溯

> AI 的答案怎么知道来自哪一页？

### Async

> 为什么 Sprint 5 不直接使用 Celery？

### AI Gateway

> 为什么 Embedding 也应该经过 AI Gateway？

如果这些问题能够解释清楚，才算真正完成 Sprint 5。

---

# 七、Story 执行顺序

```text
5.1 Knowledge Domain Design
        ↓
5.2 Document Parsing
        ↓
5.3 Chunking Strategy
        ↓
5.4 Embedding Pipeline
        ↓
5.5 Vector Store / Qdrant
        ↓
5.6 Indexing Pipeline
        ↓
5.7 Retrieval
        ↓
5.8 Citation & Context
        ↓
5.9 RAG End-to-End
        ↓
Code Review
        ↓
Architecture Review
        ↓
Sprint Review
```

---

# 八、与其他 Sprint 的边界

```text
Sprint 3
Storage & Resource
        │
        ▼
File Resource
        │
        ▼
Sprint 5
Knowledge / RAG
        │
        ├── Parse
        ├── Chunk
        ├── Embedding
        ├── Vector Store
        └── Retrieval
        │
        ▼
Sprint 4
AI Gateway
        │
        ▼
LLM / Embedding Provider
```

后续：

```text
Sprint 5
Knowledge / RAG
        │
        ▼
Sprint 6
Workflow
        │
        ▼
Sprint 7
Agent Runtime
```

异步能力：

```text
Sprint 5
Pipeline Domain / State
        │
        ▼
Sprint 10
Async Platform
```

因此 Sprint 5 不提前吞掉 Workflow、Agent Runtime、Async Platform 的职责。

---

# 九、Tech Lead 原则

Sprint 5 的学习重点不是：

> “记住 Qdrant API。”

而是建立：

```text
少学 API
多理解系统

少背代码
多理解边界

少做 Demo
多理解真实 AI 系统为什么这样运行
```

最终目标：

> **能够独立解释一个企业 Knowledge / RAG 系统为什么这样设计，并能够使用 AI Coding 工具把设计可靠地落地。**
