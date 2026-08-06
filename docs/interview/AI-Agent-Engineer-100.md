# AI Agent 工程师（2026 企业版）100 道高频面试题计划

## 目标

这套题库不作为脱离项目的刷题任务，而是与 AI-Knowledge-Hub 的 Sprint 学习同步建设。

```text
学习知识
  -> 在项目中设计和实现
  -> 测试与 Review
  -> 整理成面试答案
  -> 用项目证据回答追问
```

完成一个 Sprint 后，应能够回答该阶段对应的高频问题；项目全部完成时，自然形成 100 道有真实工程证据的面试题，而不是最后集中背诵。

## 每道题的固定格式

```text
问题
30 秒简答
2 分钟完整回答
项目中的设计或代码证据
为什么没有采用其他方案
常见追问
容易说错的地方
掌握状态
```

掌握状态分为：

- `理解`：能看懂答案和项目实现。
- `能讲`：可以不看文档完整解释。
- `能画`：可以画出架构、时序或状态变化。
- `能写`：可以现场实现核心代码或测试。

只有达到题目要求的掌握状态，才算真正完成。并非所有系统设计题都要求现场写代码，也不能只会写代码却解释不清取舍。

## 100 道题分配

| Sprint | 面试主题 | 题数 |
| --- | --- | ---: |
| Sprint 1 | Authentication、密码 Hash、JWT、认证与授权边界 | 10 |
| Sprint 2 | Redis Session、Refresh Token、Rotation、Logout、安全与日志 | 10 |
| Sprint 3 | 对象存储、Streaming Upload、Metadata、一致性、文件安全 | 8 |
| Sprint 4 | LLM Gateway、流式输出、上下文、限流、成本与故障处理 | 10 |
| Sprint 5 | RAG、Chunk、Embedding、Vector Database、检索与评估 | 12 |
| Sprint 6 | Workflow、状态机、LangChain/n8n、重试与人工节点 | 8 |
| Sprint 7 | Agent、Tool Calling、Memory、Planning、Coding Agent | 14 |
| Sprint 8 | MCP、MCP vs Tool Calling、Resource、Prompt、Skill | 8 |
| Sprint 9 | Logging、Metrics、Tracing、Evaluation、告警 | 7 |
| Sprint 10 | Async IO、线程池、Celery、消息队列、幂等与补偿 | 6 |
| Sprint 11 | Kubernetes、GitOps、扩缩容、发布、Secret 和平台部署 | 7 |
| **总计** |  | **100** |

题数代表当前计划，不强行限制实际学习。某个主题出现重要追问时可以先增加，Sprint Review 时再合并重复问题，最终保持 100 道核心题。

## 当前进度

```text
题库结构与分配：已完成
正式完整答案：2 / 100

Sprint 1 项目实现：已完成
Sprint 1 面试答案：待根据现有代码和 ADR 回填 10 道

Sprint 2 项目实现：已完成
Sprint 2 面试答案：待根据现有代码、流程图和测试回填 10 道

Sprint 3 学习计划：已完成
Sprint 3 面试答案：2 / 8，Story 3.0 和 Story 3.1 各完成 1 道
```

不暂停 Sprint 3 去一次性补写前 20 道。Sprint 3 推进期间，每周可以额外回填 1 至 2 道 Sprint 1/2 问题；新 Story 的面试题则必须在 Story Review 时同步完成，避免继续产生历史欠账。

## Sprint 1: Authentication

重点问题范围：

- Authentication 与 Authorization 有什么区别？
- 为什么密码必须使用 bcrypt 等慢 Hash，而不是 SHA-256？
- JWT 的签名、编码和加密有什么区别？
- Access Token 为什么应该短期有效？
- 如何避免登录接口泄露邮箱是否注册？
- FastAPI 中 Router、Service、Repository 的认证职责如何划分？

RBAC 可以作为授权理论追问，但 Sprint 1 没有实现完整 RBAC，回答时必须明确“理解概念”和“项目已经实现”的区别。

## Sprint 2: Session & Identity

重点问题范围：

- Cookie、Authentication Session、SQLAlchemy Session 和 Redis 有什么区别？
- Access Token、Refresh Token 和 Redis Session 分别解决什么问题？
- Refresh Token Rotation 为什么必须原子执行？
- Replay Attack 为什么会撤销当前设备 Session？
- Logout 后 Access Token 为什么可能继续有效？
- 固定 Session 与 Sliding Session 如何选择？
- JWT `kid` 和 Key Ring 如何支持 Secret Rotation？
- 多设备 Session 如何查看和撤销？

Sprint 2 的完整答案应引用认证流程、Session Architecture、Refresh Token ADR、Lua 测试和安全日志测试。

## Sprint 3: Storage & Resource Management

计划形成 8 道核心题：

1. Block、File 和 Object Storage 有什么区别，AI 平台为什么通常使用对象存储？
2. FastAPI `UploadFile` 和直接接收 `bytes` 有什么区别，如何避免大文件占满内存？
3. 为什么数据库只保存 File Metadata，而不保存大文件内容？
4. 为什么需要 `StorageProvider` 抽象，怎样避免为未来 Provider 过度设计？
5. MySQL 与对象存储无法共享事务时，如何处理孤儿对象和失败补偿？
6. 如何防御路径穿越、伪造 MIME、超大文件和恶意文件名？
7. StreamingResponse、后端代理下载和 Signed URL 分别适合什么场景？
8. 如何设计 Owner-only 文件权限、删除状态和真实 MinIO 集成测试？

每道题必须随着对应 Story 完成逐步补充答案，不能在尚未实现前把候选设计描述成项目事实。

### Q1. Block、File 和 Object Storage 有什么区别，AI 平台为什么通常使用对象存储？

**30 秒简答**

Block Storage 是给机器使用的原始磁盘，File Storage 是按目录和路径访问的共享文件树，Object Storage 是通过 Bucket、Object Key 和 API 保存对象。AI 平台通常将文件 Bytes 放进对象存储，将用户、权限、状态和索引 Metadata 放进数据库，因为对象存储可以被多个应用实例共同访问，也不会把大文件绑定到某一台 FastAPI 机器。

**2 分钟完整回答**

Block Storage 解决的是机器磁盘问题，常用于 MySQL 等数据库的数据目录。File Storage 提供目录和路径，例如 NAS 共享目录，多个实例可以挂载同一位置。Object Storage 不要求应用共享本机目录，而是通过网络 API 把文件保存到 Bucket 中的 Object Key。

对于 AI Platform，上传的 PDF、图片和音频是容量大、结构多样的二进制对象；业务需要的却是可查询、可授权、可分页的资源信息。因此 MySQL 保存稳定 `file_id`、`owner_id`、大小、Checksum、状态和内部 Object Key；对象存储保存文件 Bytes。客户端只使用 `file_id`，后端检查权限后再从 Metadata 找到对象位置。这样可以从 LocalStorage 迁移到 MinIO 或云对象存储，而不修改客户端 API。CDN 是对象存储前的下载缓存层，不是业务事实来源。

**项目中的设计或代码证据**

- Story 3.0 的资源链路和存储类型对比见 `docs/architecture/storage-evolution.md`。
- ADR-0021 已确定 LocalStorage 用于快速开发和 Unit Test，MinIO 用于真实 S3-compatible 集成验证。
- 当前项目尚未实现 StorageProvider、上传 API 或 MinIO；以上是已接受的设计边界，不应描述为已经运行的业务能力。

**为什么没有采用其他方案**

- 不将文件固定写入某个 FastAPI 实例的 `uploads/`，因为多实例访问、容器重建、迁移和备份都会受限。
- 不将所有大文件写入 MySQL BLOB，因为数据库不适合承担大二进制对象的容量、备份和 I/O 压力。
- 不在 Story 3.0 直接接入 COS 或 S3，避免云账号、网络和费用配置掩盖存储边界本身的学习目标。

**常见追问**

- 为什么客户端使用 `file_id`，而不是 Object Key？
- NAS 和 Object Storage 在多实例场景中各有什么取舍？
- ETag 能否当作 SHA-256 使用？

**容易说错的地方**

- Object Storage 不是 Redis 一类的通用内存 Key-Value 数据库。
- Object Key 不是必须暴露给客户端的服务器路径。
- ETag 的含义由存储服务和上传方式决定，不能默认等同于 SHA-256。

**掌握状态**

`理解`：已完成（2026-08-02）。
`能讲 / 能画 / 能写`：待后续 Story 结合实际 Provider 和测试验证。

### Q2. FastAPI `UploadFile` 和直接接收 `bytes` 有什么区别，如何避免大文件占满内存？

**30 秒简答**

`bytes` 会让完整文件内容以一个 Python Bytes 对象进入业务代码；大文件和并发上传会显著增加应用内存压力。`UploadFile` 提供文件对象，可以按固定 Chunk 读取，并使用可溢出到临时磁盘的底层对象。应用仍必须在循环中累计真实大小，不能依赖 `Content-Length`，也不能调用无参数的 `read()` 一次读完文件。

**2 分钟完整回答**

上传请求使用 `multipart/form-data`，文件 Part 包含客户端文件名、Content-Type 声明和真实 Bytes。使用 `bytes` 简单但不适合大文件，因为完整内容会在业务进程中形成一个大对象。使用 `UploadFile` 时，框架能够将文件作为可读取对象提供，小内容可暂存内存，超过阈值可使用临时磁盘。

但临时磁盘不是正式文件存储。FileService 仍应以配置的 Chunk Size 循环读取，每次更新 `total_size` 和 SHA-256；一旦累计值超过配置上限，就抛出业务异常。业务异常最终由统一 Handler 映射为 HTTP 413。客户端 Header 可以帮助提前拒绝，但真实字节累计才是最终安全边界。

**项目中的设计或代码证据**

- Story 3.1 的 Multipart、`UploadFile`、Chunk、临时磁盘、类型安全和测试约束见 `docs/architecture/storage-architecture.md`。
- 当前尚未创建正式 Upload API 或生产 Upload Helper；配置字段、业务异常和接口响应将在 Story 3.2 设计后实现。

**为什么没有采用其他方案**

- 不直接接收完整 `bytes`，因为文件越大、并发越高，进程内存风险越大。
- 不只检查 `Content-Length`，因为 Header 可能缺失或不应成为唯一可信限制。
- 不在 Router 中读取、校验和保存全部文件，因为业务规则和错误语义属于 Service。

**常见追问**

- UploadFile 使用临时磁盘是否代表文件已经上传成功？
- Chunk Size 怎样选择？
- 文件名、MIME 和文件签名分别能信任到什么程度？

**容易说错的地方**

- UploadFile 不等于所有场景下真正的端到端网络直通流。
- 临时文件不是 LocalStorage，更不是可下载的正式业务资源。
- 客户端声明的 MIME 和扩展名都可能被伪造。

**掌握状态**

`理解`：已完成（2026-08-02）。
`能讲 / 能画 / 能写`：待后续 Story 在真实 API 和测试中验证。

## Sprint 4: AI Gateway

重点问题范围：

- 为什么需要统一 LLM Gateway？
- SSE、Streaming Response 和 WebSocket 如何选择？
- 如何管理上下文窗口、Token、成本、超时和重试？
- 如何处理不同模型供应商的协议差异？
- LLM 调用怎样做限流、熔断、降级和审计？

## Sprint 5: RAG

重点问题范围：

- RAG 的完整数据和查询链路是什么？
- Chunk Size、Overlap 和文档结构如何影响检索？
- Embedding 是什么，向量相似度怎样理解？
- Dense、Sparse 和 Hybrid Retrieval 如何选择？
- Reranker、Metadata Filter 和 Query Rewrite 解决什么问题？
- 如何评估 Retrieval 和最终回答质量？

## Sprint 6: Workflow

重点问题范围：

- Workflow 与 Agent 有什么区别？
- 怎样表达状态、分支、重试、超时和人工审批？
- LangChain、LangGraph、n8n 和自研状态机如何取舍？
- Workflow 如何保证幂等和可恢复？

## Sprint 7: Agent Runtime

重点问题范围：

- Agent、Tool Calling 和普通 Workflow 有什么区别？
- Agent 如何进行 Planning、Reflection 和 Tool Selection？
- Short-term、Long-term 和 Episodic Memory 如何划分？
- Tool Schema、权限和 Prompt Injection 如何防护？
- Coding Agent 的 Workspace、Patch、Test 和 Sandbox 如何设计？
- 如何限制 Agent 循环、成本和不可控副作用？

## Sprint 8: MCP Integration

重点问题范围：

- MCP 解决什么问题？
- MCP 与普通 Function/Tool Calling 有什么区别？
- Tool、Resource、Prompt 和 Skill 的职责是什么？
- MCP Server 的权限、Transport、Discovery 和错误边界如何设计？

## Sprint 9: Observability

重点问题范围：

- Logging、Metrics 和 Tracing 分别回答什么问题？
- LLM 和 Agent 系统需要观察哪些延迟、Token、成本和质量指标？
- Trace ID 如何跨 API、Workflow、Agent 和异步任务传播？
- 什么是高基数标签，为什么会增加监控成本？

## Sprint 10: Async Platform

重点问题范围：

- Async IO、线程池和进程池如何选择？
- Celery、消息队列和普通 BackgroundTasks 有什么区别？
- 消息至少一次投递时如何保证幂等？
- Retry、Dead Letter Queue 和补偿任务如何设计？

## Sprint 11: Cloud Native

重点问题范围：

- Deployment、Service、Ingress、ConfigMap 和 Secret 的职责是什么？
- Readiness、Liveness 和 Startup Probe 如何选择？
- GitOps 如何实现可审计发布和回滚？
- AI 平台如何进行资源限制、自动扩缩容和 Secret Rotation？
- 有状态依赖为什么不能简单放入普通无状态 Deployment？

## 同步规则

### Story 完成时

- 选择 1 至 3 道与当前 Story 直接相关的问题。
- 用刚完成的代码、测试、架构图或 ADR 补充项目证据。
- 标记当前掌握状态和仍答不清的追问。
- 不为了凑题数编造没有实现或没有理解的内容。

### Sprint 完成时

- Review 本 Sprint 的全部核心题。
- 删除重复问题，补足遗漏的企业场景追问。
- 至少进行一次不看文档的口述或白板演练。
- 将回答中的项目事实与当前代码重新核对。
- Sprint Review 中记录面试题完成数量和掌握状态。

### 项目完成时

- 合并为最终 100 道核心题。
- 每道题都具有真实项目证据或明确标注为理论扩展。
- 按岗位 JD 重新排序为 Authentication、Platform、RAG、Agent、MCP、Observability 和 Cloud Native 专题。
- 使用真实面试方式进行限时回答、追问和系统设计演练。

## 回答原则

- 先直接回答结论，再解释原理和取舍。
- 优先用 AI-Knowledge-Hub 的真实实现举例。
- 明确区分“当前项目已经实现”“已经设计”“只理解理论”。
- 不堆术语；面试官追问时能画流程、指出代码位置并解释失败场景。
- 不把某个框架 API 当成系统设计答案。
- 遇到没有做过的生产规模问题，说明当前边界和合理演进方案，不伪造经验。
