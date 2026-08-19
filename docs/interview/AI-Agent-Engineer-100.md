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
正式完整答案：26 / 100

Sprint 1 项目实现：已完成
Sprint 1 面试答案：待根据现有代码和 ADR 回填 10 道

Sprint 2 项目实现：已完成
Sprint 2 面试答案：待根据现有代码、流程图和测试回填 10 道

Sprint 3 项目与学习计划：已完成
Sprint 3 面试答案：8 / 8，项目证据已同步

Sprint 4 项目实现：已完成
Sprint 4 面试答案：10 / 10，项目证据已同步

Sprint 5 项目实现：5.1 至 5.6 已完成，5.7 至 5.9 未开始
Sprint 5 面试答案：8 / 12；检索、Citation、质量评估与 RAG 闭环题目待对应实现后补充
```

不暂停当前 Sprint 去一次性补写 Sprint 1/2 的 20 道历史答案。Sprint 4 推进期间可以额外回填少量历史问题；新的 Sprint 4 面试题必须在对应 Story Review 时同步完成，避免继续产生欠账。

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
4. MySQL 与对象存储无法共享事务时，如何处理孤儿对象和失败补偿？
5. 为什么需要 `StorageProvider` 抽象，怎样避免为未来 Provider 过度设计？
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
- 当前已实现 LocalStorage 与 MinIO 两种 Provider、配置 Factory、真实 HTTP 生命周期测试和 Bucket Readiness。

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
`能写`：已通过 LocalStorage Provider 和路径安全测试验证（2026-08-03）。
`能讲 / 能画`：已通过完整上传、下载与真实 MinIO 链路验证（2026-08-05）。

### Q2. FastAPI `UploadFile` 和直接接收 `bytes` 有什么区别，如何避免大文件占满内存？

**30 秒简答**

`bytes` 会让完整文件内容以一个 Python Bytes 对象进入业务代码；大文件和并发上传会显著增加应用内存压力。`UploadFile` 提供文件对象，可以按固定 Chunk 读取，并使用可溢出到临时磁盘的底层对象。应用仍必须在循环中累计真实大小，不能依赖 `Content-Length`，也不能调用无参数的 `read()` 一次读完文件。

**2 分钟完整回答**

上传请求使用 `multipart/form-data`，文件 Part 包含客户端文件名、Content-Type 声明和真实 Bytes。使用 `bytes` 简单但不适合大文件，因为完整内容会在业务进程中形成一个大对象。使用 `UploadFile` 时，框架能够将文件作为可读取对象提供，小内容可暂存内存，超过阈值可使用临时磁盘。

但临时磁盘不是正式文件存储。FileService 仍应以配置的 Chunk Size 循环读取，每次更新 `total_size` 和 SHA-256；一旦累计值超过配置上限，就抛出业务异常。业务异常最终由统一 Handler 映射为 HTTP 413。客户端 Header 可以帮助提前拒绝，但真实字节累计才是最终安全边界。

**项目中的设计或代码证据**

- Story 3.1 的 Multipart、`UploadFile`、Chunk、临时磁盘、类型安全和测试约束见 `docs/architecture/storage-architecture.md`。
- `POST /files` 已使用 `UploadFile` 接收 Multipart 文件，并由 FileService 分块校验实际大小、类型和 SHA-256。
- API 与 Service Test 已验证正常上传、413、415、空文件、异常文件名和 Provider 故障。

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

`理解 / 能写`：已通过真实 Upload API、流内校验和测试验证（2026-08-06）。
`能讲 / 能画`：待 Sprint 3 收尾口述与白板演练。

### Q3. 为什么数据库只保存 File Metadata，而不保存大文件内容？

**30 秒简答**

数据库适合保存可查询、可授权、可排序的 Metadata，例如文件所有者、状态、大小和内部对象位置；对象存储适合保存 PDF、图片等大二进制内容。分离后，文件不会绑定某台 FastAPI 机器，MySQL 也不需要承担大对象的容量、备份和 I/O 压力。

**2 分钟完整回答**

File Resource 是用户可见的业务资源，必须支持 Owner-only 权限、按时间分页、生命周期状态和未来 RAG 关联，因此由 MySQL 保存 UUID `file_id`、`owner_id`、文件名、类型、大小、SHA-256、状态和时间字段。Storage Object 是 Provider 中的真实 Bytes，通过 `storage_provider`、`bucket` 和 `object_key` 定位。

如果把大文件直接存 MySQL BLOB，数据库的事务、备份、容量和 I/O 会被文件内容放大；如果只存本机目录，又无法支持多实例、容器重建和可替换的对象存储。将 Metadata 和 Bytes 分离后，客户端只依赖稳定 `file_id`，后端可以从 LocalStorage 演进到 MinIO，不改变 API。

**项目中的设计或代码证据**

- File Resource 字段、响应边界和数据库约束见 `docs/architecture/file-resource-design.md`。
- Storage Evolution 和 ADR-0021 解释了 LocalStorage、MinIO 与 MySQL 的职责分离。
- `backend/app/models/file_resource.py` 和 `578d92bbd61c_create_files_table.py` 已实现 Metadata 表、外键、约束和索引。
- `FileRepository` 已实现 Owner-only、`READY`、软删除过滤、分页排序和状态更新，且不自行提交事务。
- File Response Schema 与测试证明 API Model 不返回 Owner、Object Key、SHA-256 和失败清理字段。

**为什么没有采用其他方案**

- 不使用 MySQL BLOB 作为默认文件存储。
- 不将本机 `uploads/` 当作唯一事实来源。
- 当前不做跨用户物理去重，避免引用计数、删除和权限复杂度。

**常见追问**

- 相同 SHA-256 文件为什么当前仍保存两份？
- `object_key` 为什么不返回客户端？
- File Resource 和未来 Document、Chunk 的关系是什么？

**容易说错的地方**

- UUID `file_id` 是资源身份，不是权限；仍必须校验 `owner_id`。
- `original_filename` 可以重名，也不能直接作为 Object Key。

**掌握状态**

`理解 / 能写`：已通过 Model、Migration、Repository、Schema 和测试验证（2026-08-04）。
`能讲 / 能画`：已通过 Local 与真实 MinIO 的完整上传、下载和删除链路验证（2026-08-06）。

### Q4. MySQL 与对象存储不能共享事务时，如何处理孤儿对象和失败补偿？

**30 秒简答**

不能把 MySQL 和对象存储当作一个可共同回滚的事务。项目用资源状态机表达中间状态：上传创建 `PENDING_UPLOAD`，对象和 Metadata 都成功后才变为 `READY`。如果对象成功但数据库更新失败，Service 尝试删除对象补偿；补偿仍失败时记录 `CLEANUP_REQUIRED`，由可重复调用的 Cleanup Service 收尾。

**2 分钟完整回答**

上传先完成大小、类型和 SHA-256 的流内校验，再创建 `PENDING_UPLOAD` Metadata 并写入对象。对象写入成功后，Service 更新 Metadata 为 `READY`，此时才返回 201，普通列表和下载也只允许 `READY`。

对象写入报错时不能假设对象一定不存在，因为可能是服务端已写入但响应丢失；Service 会先执行幂等删除。更困难的情况是对象写入成功、MySQL 更新失败：Service 不能回滚对象存储，只能显式调用删除作为补偿；删除失败或结果不确定时，保持资源不可见并记录 `CLEANUP_REQUIRED`。同步 Cleanup Service 只查询该状态，根据固定失败原因决定终态，Provider 或 Metadata 再次失败时继续保留可重试状态。删除流程同理：先 `DELETING`，删除对象成功后才逻辑删除 Metadata。

**项目中的设计或代码证据**

- 上传、下载、删除时序和测试矩阵见 `docs/architecture/storage-flow.md`。
- ADR-0023 固化了状态机、补偿、可见性与不实现自动 Worker 的边界。
- `FileService` 已实现上传、删除补偿与 `cleanup_file()`；Repository 只允许内部清理读取 `CLEANUP_REQUIRED`。
- Unit Test 验证未知原因先于物理删除被拒绝、Provider 失败保留状态、Metadata 失败后可重试。
- 真实 MinIO Integration Test 验证遗留对象删除、Metadata 终态和重复调用幂等性。

**为什么没有采用其他方案**

- 不假设调用顺序本身就能保证一致性。
- 不先物理删除 Metadata。
- 不在当前 Sprint 引入分布式事务、两阶段提交或后台 Worker。

**常见追问**

- 为什么 `CLEANUP_REQUIRED` 不直接对用户显示？
- 用户重新上传时为什么不用旧 Object Key？
- 如何让 DELETE 具备幂等性？

**容易说错的地方**

- 补偿不是跨系统回滚，只是一个可能再次失败的独立操作。
- `READY` 不是“已创建数据库记录”，而是对象与 Metadata 都已可用。

**掌握状态**

`理解 / 能写`：已完成（2026-08-06），并通过 Repository、Service 和真实 MinIO Cleanup 测试验证。
`能讲`：已完成一次带纠正的口述演练，能够说明不确定写入、`CLEANUP_REQUIRED` 和单资源幂等清理。
`能画`：已通过 `storage-flow.md` 上传补偿与 Cleanup 流程图验证。

### Q5. 为什么需要 `StorageProvider` 抽象，怎样避免为未来 Provider 过度设计？

**30 秒简答**

业务层只依赖保存、打开、删除和存在性检查这四项稳定能力，不应直接依赖本地路径或 MinIO SDK。项目使用最小 `Protocol` 定义结构化契约，并用 LocalStorage 实现和测试验证它；只有出现真实业务需求时才增加能力，避免提前抽象 Bucket 管理、分片上传或厂商特有参数。

**2 分钟完整回答**

如果 FileService 直接调用 `Path.open()`，以后切换 MinIO 时就必须修改上传、下载和删除业务流程；如果它直接接收 MinIO Client，又会把 Endpoint、Bucket 和 SDK 异常传播到业务层。StorageProvider 把这些实现细节隔离在适配层，对业务只暴露基于 `object_key` 的 `put/open/delete/exists`。

项目选择 Python `Protocol`，因为当前只需要描述调用方依赖的结构，不需要共享状态或强制继承。LocalStorageProvider 通过相同方法自然满足协议。它将 Storage Root、临时文件和真实路径隐藏起来，把路径越界转换成 `InvalidObjectKeyError`，把底层 I/O 错误转换成 `StorageOperationError`，并把缺失对象转换成 `StorageObjectNotFoundError`。

本地写入先在目标目录创建临时文件，按 Chunk 复制数据，全部完成后使用 `os.replace()` 原子替换正式对象。如果读取或写入中断，临时文件会被清理，原有正式对象保持不变。删除使用幂等语义，因此重复删除不会让上层补偿流程产生额外失败。

**项目中的设计或代码证据**

- `backend/app/storage/provider.py` 定义了四个最小 Provider 方法。
- `backend/app/storage/local.py` 实现了根目录约束、分块读写、原子替换和统一异常。
- `backend/app/storage/minio.py` 使用 S3-compatible API 实现同一最小契约，并统一 SDK 异常。
- `backend/app/storage/factory.py` 根据 Settings 切换 Provider，并复用 boto3 Client 与连接池。
- `backend/tests/test_local_storage_provider.py` 验证成功读写、路径越界、缺失对象、幂等删除、写入中断和构造失败。
- 真实 MinIO Integration Test 验证完整生命周期、错误凭据和不存在 Bucket。
- ADR-0022 记录了 Provider 边界及暂不增加厂商特有能力的原因。

**为什么没有采用其他方案**

- 不让 Router 或 FileService 直接拼接本地路径。
- 不让业务层直接依赖 MinIO SDK 的类型、异常或配置。
- 当前不增加 Bucket 创建、Signed URL、分片上传等能力；它们将在真实调用方出现后评估。
- 当前不用复杂继承树；没有共享实现和生命周期状态需要 ABC 基类承载。

**常见追问**

- Python `Protocol` 与 ABC 有什么区别？
- 为什么临时文件必须和目标文件位于同一文件系统？
- `os.replace()` 解决了什么问题，是否等同于数据库事务？
- 为什么 Provider 不负责检查用户权限和上传大小？

**容易说错的地方**

- 原子替换只能保证单个本地文件不会对外暴露半成品，不保证 MySQL 与对象存储的一致性。
- `object_key` 是 Provider 内部定位符，不是客户端资源 ID，也不是授权凭据。
- Provider 负责对象能力和错误归一化；Owner 权限、业务大小限制和补偿编排属于 FileService。

**掌握状态**

`理解 / 能写`：已完成（2026-08-03）。
`能讲`：待不看文档口述验证。
`能画`：已通过 FileService 与真实 MinIO 调用链验证（2026-08-05）。

### Q6. 如何防御路径穿越、伪造 MIME、超大文件和恶意文件名？

**30 秒简答**

客户端文件名、扩展名、MIME 和 Content-Length 都不可信。项目只把原始文件名作为受限展示 Metadata，Object Key 由服务端 UUID 生成；上传时分块累计真实大小、计算 SHA-256，并联合检查允许扩展名、标准化 MIME 和文件签名。

**2 分钟完整回答**

路径穿越的根本防线不是过滤几个 `../` 字符，而是客户端文件名永远不参与内部路径。项目生成 `users/{owner_id}/{file_id}` Object Key，LocalStorage 解析真实路径后再次验证它仍位于 Storage Root 内，并拒绝空 Key、根目录自身和逃逸路径。

上传 Metadata 校验拒绝空文件名、超长文件名、`.`、`..`、斜杠、反斜杠和 Unicode 控制字符。MIME 会去除参数并标准化，扩展名必须属于对应允许集合；随后检查 PDF、PNG 或 JPEG 的实际文件签名。业务按 Chunk 读取真实 Bytes，累计大小超过配置立即拒绝，同时增量计算 SHA-256。Content-Length 只能用于提前提示，不能替代实际流内限制。

这些检查不等于病毒扫描、内容审核或沙箱执行。项目明确只实现类型与大小边界，不声称能识别所有恶意文档。

**项目中的设计或代码证据**

- `upload_validation.py` 实现文件名、MIME、扩展名、签名、大小和 SHA-256 校验。
- `LocalStorageProvider._resolve_path()` 约束真实路径必须位于 Storage Root。
- 上传 API Test 验证 400、413、415，Provider Test 验证绝对路径与 `..` 越界。
- Object Key 不包含 `original_filename`，相同文件名不会覆盖。

**为什么没有采用其他方案**

- 不信任扩展名或客户端 MIME 单独判断类型。
- 不使用 Content-Length 作为最终大小证据。
- 不把整个文件读入一个 `bytes` 再校验。
- 当前不引入 ClamAV、内容审核和文档沙箱；它们需要独立资源预算和故障边界。

**常见追问**

- Magic Number 是否能百分之百证明文件安全？
- 为什么 SHA-256 不能替代病毒扫描？
- `Path.resolve()` 和 Object Key 服务端生成分别防御什么问题？
- Multipart 解析完成前能否完全阻止上游接收超大请求？

**容易说错的地方**

- 文件签名只能提高类型可信度，不能证明内容无恶意。
- SHA-256 用于完整性和重复内容识别，不是加密或安全扫描。
- `UploadFile` 可溢出到临时磁盘，但仍需业务层限制实际大小。

**掌握状态**

`理解 / 能写`：已完成（2026-08-04）。
`能讲 / 能画`：待不看文档演练。

### Q7. StreamingResponse、后端代理下载和 Signed URL 分别适合什么场景？

**30 秒简答**

StreamingResponse 让后端边读边返回，适合 LocalStorage、细粒度审计和必须由应用控制的下载；Signed URL 让客户端短时间直连对象存储，适合大文件和高下载带宽。两者都必须先完成业务权限检查，Signed URL 本身是临时凭据，不是权限系统。

**2 分钟完整回答**

项目当前 LocalStorage 与 MinIO 都使用后端代理下载。FileService 先按 `file_id + owner_id + READY` 查询 Metadata，再打开内部 Object Key，返回结构化 `FileDownload`。Router 使用 StreamingResponse 按配置 Chunk 读取，设置 MIME、Content-Length 和经过编码的 Content-Disposition，并在响应完成或异常时关闭文件流或 MinIO `StreamingBody`。这样不会一次读取完整 PDF，也不会暴露本地路径、Bucket 或 Object Key。

代理下载的代价是 FastAPI 实例承担连接和带宽。未来当大文件或高并发数据证明代理流成为瓶颈后，可以在权限验证后签发短 TTL Presigned URL，让流量直接进入对象存储。URL 在有效期内可被持有者使用，因此不能记录到日志、不能使用过长 TTL，也不能跳过 owner 和状态检查。

**项目中的设计或代码证据**

- `FileService.download_file()` 在 Provider.open 前执行 Owner-only 查询。
- `FileDownload` 传递流和安全 Metadata，不泄露 Object Key。
- `GET /files/{file_id}/download` 使用分块 StreamingResponse，并编码下载文件名。
- API Test 验证分块读取、Content-Disposition、Content-Length 和流关闭。
- 真实 MinIO HTTP 测试验证同一代理流可读取 `StreamingBody` 并完成资源删除。
- ADR-0024 记录 Local/MinIO 当前代理流与未来 Signed URL 的边界。

**为什么没有采用其他方案**

- 不一次读取完整文件到内存。
- 不直接返回 LocalStorage 路径或永久公开 URL。
- 当前不强迫 LocalStorage 模拟 Signed URL 能力。
- 不让 Router 直接调用 Provider，避免绕过权限和状态机。

**常见追问**

- Signed URL 泄露后能否立即撤销？
- Range Request 和断点下载应在哪一层实现？
- 后端代理下载如何处理客户端中断和文件流关闭？
- 为什么下载成功默认不记录每次 INFO？

**容易说错的地方**

- StreamingResponse 降低的是一次性内存占用，不会降低总带宽。
- Signed URL 减少应用带宽，但在 TTL 内属于可转发凭据。
- UUID 难猜不代表有权限，签发流或 URL 前仍必须校验 owner。

**掌握状态**

`理解 / 能写`：已完成（2026-08-04）。
`能讲 / 能画`：已结合真实 MinIO 代理流完成对比验证（2026-08-05）。

### Q8. MinIO 接入为什么要区分 Root 与应用账号，怎样设计 Client 和 Readiness？

**30 秒简答**

MinIO Root 账号只用于初始化 Bucket、应用账号和 Policy，FastAPI 运行时只持有限定 Bucket 权限的应用凭据。boto3 Client 和连接池应在进程内复用，不能每个请求重新创建。MinIO 模式的 Readiness 使用短超时 `head_bucket()` 验证业务账号、网络和 Bucket；失败时应用仍存活，但停止接收需要完整依赖的新流量。

**2 分钟完整回答**

MinIO 提供 S3-compatible API，因此项目使用 boto3，不把业务绑定到 MinIO 专用 SDK。Compose 中的 `minio-init` 是一次性管理容器：等待 MinIO Healthy 后，使用 Root 凭据创建 Bucket、应用账号和 Bucket-scoped Policy，完成后正常退出。FastAPI 只注入应用 Access Key 与 Secret Key，不能获得创建用户、修改全局 Policy 或访问其他 Bucket 的管理权限。

boto3 Client 内部维护 HTTP 连接池，Factory 使用进程级缓存复用业务 Client 和 Provider。每个请求重新创建 Client 会增加连接、TLS 和线程资源开销。Readiness 使用独立缓存 Client，因为探测需要更短的连接和读取超时，并关闭 SDK 自动重试，避免依赖故障时健康检查阻塞十几秒。

Readiness 还必须按配置有条件执行：Local 模式不访问 MinIO；MinIO 模式调用 `head_bucket()`，同时验证 Endpoint 可达、应用凭据有效且目标 Bucket 存在。失败时 `/health/live` 仍表示进程存活，`/health/ready` 返回 Storage Unavailable；依赖恢复后无需重启即可重新 Ready。

**项目中的设计或代码证据**

- `infra/compose.dev.yaml` 使用固定版本 MinIO，并通过一次性 `minio-init` 完成初始化。
- `infra/minio/app-policy.template.json` 将权限限制到配置 Bucket 的对象读写和必要 Multipart 操作。
- `storage/factory.py` 分离并缓存业务 Client 与短超时 Readiness Client。
- `storage/readiness.py` 仅在 MinIO 模式调用 `head_bucket()`。
- Integration Test 验证真实上传、下载、删除、Cleanup、错误凭据、不存在 Bucket 和停止后恢复。

**为什么没有采用其他方案**

- 不让 FastAPI 使用 Root 凭据，避免应用漏洞扩大为整个对象存储管理权限。
- 不在每个请求创建 boto3 Client，避免浪费连接池和初始化成本。
- 不让 Liveness 检查外部依赖，避免 MinIO 故障导致容器被无意义重启。
- 不在 Local 模式探测 MinIO，否则未使用的依赖会错误阻止应用 Ready。

**常见追问**

- `127.0.0.1:9000` 与 `minio:9000` 分别适用于什么网络位置？
- 为什么 Readiness Client 不复用业务 Client 的超时与重试配置？
- 应用账号为什么仍需要 Bucket 级和 Object 级两组 Action？
- `minio-init` 成功退出为什么不是服务故障？

**容易说错的地方**

- S3-compatible 表示协议兼容，不代表所有云厂商能力、鉴权和扩展完全相同。
- Readiness 失败表示当前不应接收流量，不表示进程已经死亡。
- Named Volume 保存对象数据，不保存应用权限设计本身；账号和 Policy 仍由初始化流程管理。

**掌握状态**

`理解 / 能写`：已通过 Compose、最小权限 Policy、boto3 Factory、Readiness 和真实 MinIO 测试验证（2026-08-06）。
`能讲 / 能画`：待 Sprint 3 收尾口述与白板演练。

## Sprint 4: AI Gateway

计划形成 10 道核心题：

1. 为什么业务系统需要 AI Gateway，而不是直接调用 Provider SDK？
2. Adapter Pattern、Gateway 和简单 SDK Wrapper 有什么区别？
3. 为什么 Provider 接口应该按 Chat、Embedding 等 Capability 拆分？
4. Message Role、Token、Context Window 和 Finish Reason 分别是什么？
5. SSE、StreamingResponse 和 WebSocket 应如何选择？
6. 为什么 Streaming 发出首个 Token 后不能自动重试？
7. Timeout、Rate Limit、Context Too Long 和 Provider 5xx 应如何分类和映射？
8. Prompt 为什么需要 Key、Version、严格变量校验和审计？
9. Fake Provider、Contract Test 和真实 Provider Integration Test 分别证明什么？
10. Token Usage、Latency、TTFT 和成本快照应该怎样记录？

限流、熔断、降级和多 Provider 自动故障转移可以作为系统设计追问，但 Sprint 4 只实现已经进入范围的 Timeout、有限 Retry、统一错误和 Usage，回答时必须区分当前证据与未来演进。

### Q1. 为什么业务系统需要 AI Gateway，而不是直接调用 Provider SDK？

**30 秒简答**

Provider 的 SDK、模型名、请求、响应和异常会变化，业务需要的是稳定的文本生成能力。
AI Gateway 用模型别名和项目自己的契约隔离这些变化，让 ChatService、未来 RAG 和
客户端不依赖某个厂商；Adapter 转换 SDK，Gateway 负责选择和调用策略，Service
负责用户业务与 Usage 终态。

**2 分钟完整回答**

如果 ChatService 直接导入某个 SDK，它会同时知道 API Key、真实模型名、SDK Request、
原始 Chunk 和异常类。更换 Provider 不再只是配置变化，而会修改业务流程、测试和
客户端错误语义。本项目将公共 API Schema、内部 ChatRequest、ProviderChatRequest
和 SDK Model 分开：Gateway 解析模型别名、选择 Provider 并执行调用策略；Factory
创建 Adapter；Adapter 将 SDK 请求响应转为 `ChatResult` 或 `ChatEvent`，并把原生异常
转成 `ProviderError`。Gateway 不保存 Memory，Provider 不知道 `user_id`，ChatService
协调 Prompt、Gateway 和 Usage。当前它仍是应用内边界，不是独立微服务。

**项目中的设计或代码证据**

- ADR-0025 固化 Gateway、Factory、Adapter 和 ChatService 的职责。
- `app/ai/provider.py` 中的 DTO 和 Protocol 不导入任何厂商 SDK 类型。
- `FakeChatProvider` 证明业务可以只依赖稳定契约完成确定性测试。

**为什么没有采用其他方案**

- 不让 Router 或 ChatService 直接判断 Provider，避免 HTTP/业务层持有 Secret 和 SDK 类型。
- 不立即拆独立 Gateway 服务，当前没有跨服务复用和独立扩容证据。

**常见追问**

- Gateway 和 Factory 为什么不是重复职责？
- 什么情况下应用内 Gateway 应演进成独立服务？

**容易说错的地方**

- Gateway 不是所有 AI 功能的集合，也不负责 Conversation Memory。
- 使用 OpenAI-compatible 协议不等于不同 Provider 的错误、能力和运营限制完全相同。

**掌握状态**

`理解 / 能写`：Gateway、Factory、Adapter 和 ChatService 已完成（2026-08-14）。
`能讲 / 能画`：待不看文档画出四层请求契约。

### Q2. Adapter Pattern、Gateway 和简单 SDK Wrapper 有什么区别？

**30 秒简答**

Adapter 解决“如何把某厂商 SDK 转成项目协议”，Gateway 解决“本次业务调用选择什么模型、
如何 Timeout/Retry 并返回稳定结果”，Wrapper 常常只是把 SDK 方法换一个名字。三者可以
都很小，但职责不同；项目用 Factory 创建 Adapter，用 AIGateway 执行策略。

**2 分钟完整回答**

Adapter 的输入输出两端协议不同。例如 OpenAI-compatible Adapter 接受项目的
`ProviderChatRequest`，内部构造 SDK 请求，再把原始响应、流事件和异常转换为
`ChatResult`、`ChatEvent` 与 `ProviderError`。它不能决定业务默认模型，也不知道用户。

Gateway 面向项目业务请求：解析 model alias，取得对应 Provider，应用总 Deadline、有限
Retry、Context Window 校验，并屏蔽 SDK 类型。Factory 则只负责由 Settings 的 Provider Key
构造或缓存具体 Adapter。简单 Wrapper 若只是 `sdk.chat()` 外再包一层，业务仍然要知道
真实模型名、SDK Exception 和响应字段，无法形成可替换边界。

**项目中的设计或代码证据**

- `app/ai/providers/openai_compatible.py` 是厂商协议 Adapter。
- `app/ai/factory.py` 根据 Provider Key 取得 Adapter；`app/ai/gateway.py` 处理模型策略。
- `ChatService` 只构造项目 `ChatRequest`，不导入 SDK 类型。

**为什么没有采用其他方案**

- 不把 Factory、Gateway 和 Adapter 合为一个类，否则初始化、策略和协议转换会一起膨胀。
- 不为当前单体拆独立 Gateway 微服务，暂无跨服务部署与独立扩容需求。

**常见追问**

- 模型 alias 为什么属于 Gateway，而不是 Router？
- 新增 Anthropic Provider 时哪些层不应变化？

**容易说错的地方**

- Adapter 不是“所有业务调用的总入口”。
- Factory 不等于动态路由策略，它只解决实例如何获得。

**掌握状态**

`理解 / 能写`：Adapter、Factory、Gateway 已完成（2026-08-10）。
`能讲 / 能画`：待结合真实调用链口述复查。

### Q3. 为什么 Provider 接口应该按 Chat、Embedding 等 Capability 拆分？

**30 秒简答**

不同 Provider 支持的能力不同。把 Chat、Embedding、Rerank、Image 和 Tool Calling
放进一个万能接口，会强迫实现类提供不支持的方法，也让调用方看不出能力边界。
当前只定义最小 `ChatProvider.generate/stream`，新能力出现真实需求后再建独立 Protocol。

**2 分钟完整回答**

Capability-specific Interface 是 Interface Segregation 在 Provider 设计中的应用。
Chat 需要 Message、Finish Reason 和流式 Delta；Embedding 返回向量；Rerank 输入
Query 与 Documents 并返回排序分数，它们的数据和生命周期不同。硬塞进一个父接口，
Adapter 只能抛 `NotImplementedError` 或伪造实现，类型契约失去价值。本项目使用结构化
`Protocol` 约束行为，不规定共同构造函数；当前 Chat 契约只有非流式 `generate()`
和返回 `AsyncIterator[ChatEvent]` 的 `stream()`。Factory 在外部负责具体初始化。

**项目中的设计或代码证据**

- ADR-0026 记录 Capability-specific 决策和未采用方案。
- `ChatProvider` 只有两个方法，`ChatEvent` 只有 Delta、Usage 和 Done。
- Provider Contract Test 检查异步返回类型、不可变 DTO 和事件专属数据。

**为什么没有采用其他方案**

- 不使用万能 Provider 基类，避免大量无意义的方法和构造参数。
- 不返回原始 SDK Model，否则接口虽然名字统一，调用方仍然绑定厂商。

**常见追问**

- 为什么这里选择 Protocol 而不是 ABC？
- Tool Calling 应扩展 ChatProvider 还是建立新能力？

**容易说错的地方**

- 接口越小不是目的；边界必须完整表达当前真实能力。
- Capability 拆分不代表每个方法都单独建一个文件或微服务。

**掌握状态**

`理解 / 能写`：Chat 与 Embedding 已分别使用独立 Provider/Gateway 边界（2026-08-19）。
`能讲 / 能画`：待说明新增 Rerank 时为何不扩张 ChatProvider。

### Q4. Message Role、Token、Context Window 和 Finish Reason 分别是什么？

**30 秒简答**

Role 表示消息在模型对话中的受控身份；Token 是模型处理文本的计量单位；Context Window
限制本次输入和输出 Token 总量；Finish Reason 表示模型为何结束。它们都不是客户端可以
任意伪造的业务字段，Service 和 Gateway 必须分别控制。

**2 分钟完整回答**

公共 Chat API 只接收用户正文，`ChatService` 固定把它转换为 `user` Message，并从 Prompt
Center 生成受控 `system` Message，客户端不能提交任意 Role 覆盖系统策略。Gateway 在调用
Provider 前估算输入 Token，并加上 `max_output_tokens` 与模型配置的 Context Window 比较；
超限直接抛出稳定请求错误，避免无意义地调用外部模型。

Finish Reason 是模型最终结果，例如正常停止或长度耗尽，不等于 HTTP 是否成功。Token Usage
若 Provider 未可信返回则保持未知；不能把字符数、字节数或 `0` 冒充模型 Token。RAG 接入后
Context 也必须进入同一个输入预算，而不是无限追加检索文本。

**项目中的设计或代码证据**

- `ChatService._build_gateway_request()` 创建受控 system/user Message。
- `AIGateway._prepare_provider_call()` 校验输入估算与 `context_window_tokens`。
- `ChatResult` / `ChatDone` 使用项目 `FinishReason` 与可选 `TokenUsage`。

**为什么没有采用其他方案**

- 不把 Role 直接暴露给客户端，避免用户伪造 system 指令。
- 不用字节数替代 Token，中文、英文和模型 tokenizer 的比例不稳定。

**常见追问**

- RAG Context 应给用户问题预留多少输出 Token？
- `length` Finish Reason 时业务应如何提示？

**容易说错的地方**

- Context Window 是输入和输出共同的总预算。
- Finish Reason 不是 Provider 原始错误正文。

**掌握状态**

`理解 / 能写`：受控 Role、上下文校验和结果 DTO 已实现（2026-08-11）。
`能讲 / 能画`：待用一次超长请求流程复述。

### Q5. SSE、StreamingResponse 和 WebSocket 应如何选择？

**30 秒简答**

`StreamingResponse` 是 FastAPI 的逐段 HTTP 响应能力，SSE 是建立在 HTTP 流上的事件格式，
适合服务端连续推送模型 Delta；WebSocket 适合双方都需要持续主动发送的双向会话。当前聊天
输出是单向模型流，所以项目用 SSE，外层用 `StreamingResponse` 承载。

**2 分钟完整回答**

模型生成的主要方向是服务端到客户端，且事件有明确类型：`delta`、`usage`、`done` 和
流中 `error`。SSE 使用普通 HTTP、浏览器支持较好、代理配置简单，并允许客户端按事件名
处理终态。`StreamingResponse` 本身只负责把迭代器写到 HTTP Body，不定义事件字段，因此
项目在 `ai_sse.py` 将领域 `ChatEvent` 序列化为 SSE 格式。

WebSocket 并非更高级的 SSE 替代品。当需要客户端中途频繁发控制命令、协作编辑、实时
房间状态或双向二进制流时才值得增加连接协议、心跳和会话管理。当前取消通过 HTTP 断连
传播即可，不为一个单向输出引入 WebSocket 生命周期复杂度。

**项目中的设计或代码证据**

- `POST /ai/chat/stream` 使用 `StreamingResponse`。
- `app/api/ai_sse.py` 负责 SSE Event 编码；`ChatService.stream()` 产生领域事件。
- ADR-0027 记录首事件、流中错误、断连和关闭规则。

**为什么没有采用其他方案**

- 不把原始 Provider Chunk 直接透传，避免客户端绑定厂商事件格式。
- 不为单向生成使用 WebSocket，避免额外状态和运维边界。

**常见追问**

- SSE 断线重连会不会自动恢复模型流？
- 哪些代理设置会影响流式 Flush？

**容易说错的地方**

- SSE 是 HTTP 响应格式，不是 WebSocket 的子协议。
- StreamingResponse 不自动解决客户端断连和上游资源关闭。

**掌握状态**

`理解 / 能写`：SSE Router、Service Stream 与断连处理已实现（2026-08-12）。
`能讲 / 能画`：待白板画出首事件与取消路径。

### Q6. 为什么 Streaming 发出首个 Token 后不能自动重试？

**30 秒简答**

首个 Token 发出后客户端已经看到部分回答；重试会生成另一条回答并与旧片段拼接，造成
重复内容和重复计费。项目只允许在首个事件前重试可恢复 Provider 错误，之后把错误转换
为 SSE `error` 并关闭流。

**2 分钟完整回答**

非流式调用在 HTTP 响应开始前仍可安全地重试，因为客户端没有看到任何业务结果。流式
调用不同：一旦 `yield` 了 Delta，HTTP Headers 和部分文本已经发送，Service 无法撤回。
新的 Provider 调用即使成功，也不能知道旧模型已生成到哪个语义位置，因此不能可靠续写；
用户会得到重复、矛盾或混合的答案，Usage 也会变得难以解释。

`AIGateway.stream()` 用 `has_emitted_event` 记录是否输出过事件。仅在尚未输出、异常可重试
且次数未超限时回退；输出后异常向上抛，由 SSE 层发送稳定 `error` 终态，并由资源关闭逻辑
取消上游流。这是输出可见性决定幂等边界的例子。

**项目中的设计或代码证据**

- `app/ai/gateway.py` 的 `has_emitted_event` 与有限 Retry 条件。
- `app/api/ai_sse.py` 将流中异常映射为公共 SSE error Event。
- ADR-0027 记录该约束和取消语义。

**为什么没有采用其他方案**

- 不在客户端拼接两次 Provider 输出，因为无法证明语义连续。
- 不宣称支持断点续传；当前 Provider 契约没有可恢复的生成游标。

**常见追问**

- 如果 Provider 支持 resume token，能否重试？
- 首事件前收到 Usage Event 算不算已经可见输出？

**容易说错的地方**

- “网络失败可重试”必须区分响应是否已经对用户可见。
- Retry 次数不是唯一条件，事件边界同样关键。

**掌握状态**

`理解 / 能写`：首事件前 Retry 与流中 Error 已实现（2026-08-12）。
`能讲 / 能画`：待结合一次断连情景复述。

### Q7. Timeout、Rate Limit、Context Too Long 和 Provider 故障如何分类？

**30 秒简答**

Context Too Long 和非法模型/参数是客户端请求问题，应稳定拒绝且不重试；Timeout、Rate
Limit、Provider 不可用是外部暂时故障，可在输出前有限重试并映射为安全业务错误。Router
只返回 HTTP/SSE，Gateway 负责归一化 Provider 细节。

**2 分钟完整回答**

错误分类的目的不是给每个 SDK 错误起新名字，而是决定调用方是否能修正、系统能否重试
以及日志是否安全。Gateway 将 Provider Timeout、Rate Limit、Unavailable 转为项目
`AIProvider...Error`；超过 Context Window、未配置模型或空请求为 `AIInvalid...Error`。
只有可恢复 Provider 类错误，且仅在结果尚未可见时，才进入有限 Retry 和 Backoff。

Service 和 Exception Handler 再把稳定领域错误映射为公共响应，不能泄露 Base URL、SDK
异常正文或 Secret。总 Deadline 限制“初次调用 + 等待 + Retry”的总时间，避免每次重试
都重新获得完整超时预算。

**项目中的设计或代码证据**

- `app/ai/exceptions.py` 定义稳定 AI 异常层次。
- `AIGateway.generate()` / `stream()` 处理总 Deadline、Retry 与翻译。
- API Exception Handler 提供不含 Provider 细节的 HTTP/SSE 响应。

**为什么没有采用其他方案**

- 不把 Provider HTTP 状态码直接暴露为业务契约。
- 不对非法参数和 Context 超限自动重试，重试不会改变输入。

**常见追问**

- 429 应立即重试还是排队？
- 总 Deadline 与单次 Provider Timeout 如何共同配置？

**容易说错的地方**

- 5xx 不一定意味着调用一定没有产生结果，流式场景更要谨慎。
- Rate Limit 是服务端限额，不等于用户自己的请求校验错误。

**掌握状态**

`理解 / 能写`：统一异常、Deadline 和有限 Retry 已实现（2026-08-11）。
`能讲`：待从客户端可修复性角度口述分类。

### Q8. Prompt 为什么需要 Key、Version、严格变量校验和审计？

**30 秒简答**

Prompt 是会改变模型行为的运行时资产。Key 标识用途，Version 固定可复现内容，严格变量
校验防止漏填或多填，文件与 Git 历史提供审计。ChatService 选择受控 Prompt，客户端不
提交任意 System Prompt。

**2 分钟完整回答**

把 Prompt 写死在 Service 会让改动和业务代码混在一起，无法回答某次请求使用了哪份指令。
项目用 `assistant/v1` 目录保存模板与 metadata；PromptCenter 负责加载、缓存、验证变量
并渲染，Service 只按明确 Key/Version 请求。变量必须与模板声明一致，未提供、空白或额外
变量都会在进入模型前失败，避免悄悄输出错误指令。

版本不是“随时覆盖同一个文件名”。已有 `v1` 的语义应稳定；需要调整时创建新版本，随后
由业务显式切换。当前只实现文件与 Git 审计，不提前建设在线编辑、审批、灰度和 A/B 平台。

**项目中的设计或代码证据**

- `app/ai/prompt_center/center.py` 负责加载、严格渲染与缓存。
- `app/ai/prompts/assistant/v1/` 是当前 Chat 使用的版本化资产。
- ADR-0028 固化文件型 Prompt Center 和范围边界。

**为什么没有采用其他方案**

- 不允许 API 直接传 System Prompt，避免绕过受控策略。
- 不在数据库建 Prompt CMS，当前缺少审批、权限和运营需求。

**常见追问**

- Prompt 改版如何回滚？
- RAG Context 应作为模板变量还是用户 Message？

**容易说错的地方**

- Prompt Version 不等于模型版本。
- 文件存储不自动等于完整审批与发布流程。

**掌握状态**

`理解 / 能写`：PromptCenter、版本目录和严格变量已实现（2026-08-13）。
`能讲 / 能画`：待解释一次 Key/Version 到 ChatService 的调用链。

### Q9. Fake Provider、Contract Test 和真实 Provider Integration Test 分别证明什么？

**30 秒简答**

Fake Provider 让上层确定性触发成功、错误、断流和取消；Contract Test 约束所有
Provider 都必须遵守相同输入输出、异常和清理行为；真实 Integration Test 才证明
SDK、网络、认证和厂商协议确实可用。三者互补，Fake 通过不能证明真实服务已接入。

**2 分钟完整回答**

Fake Provider 是测试替身，可以预先配置 `ChatResult`、事件序列、错误位置和延迟，
所以 Service/Gateway 测试不需要网络、Secret 或费用。Contract Test 针对稳定边界，
验证非流式结果、流事件顺序、异常基类、取消传播和资源关闭；未来 Fake 与真实 Adapter
都要运行相同契约。Integration Test 跨过 Adapter 边界，检查 SDK 初始化、Base URL、
真实模型字段、Native Error 转换、HTTP Streaming 和 Usage 映射。它需要显式 Marker、
真实 Secret、调用次数和 Token 上限，不能放进默认测试套件。

**项目中的设计或代码证据**

- Fake Provider 覆盖成功、流前/流中错误、`aclose()`、任务取消和 `finally` 清理，默认
  测试不访问网络。
- `OpenAICompatibleChatProvider` 与 opt-in Integration Test 覆盖真实 SDK、认证、
  非流式、Streaming 和 Usage 映射。
- Sprint 4 Review 已执行离线回归与受控真实 Provider 纵向验证。

**为什么没有采用其他方案**

- 不让普通测试调用真实模型，避免不稳定、Secret 泄露和费用失控。
- 不只做 Mock SDK 方法调用，因为它不能约束上层实际消费的稳定契约。

**常见追问**

- 哪些 Contract Test 应由 Fake 和真实 Adapter 共同运行？
- Integration Test 如何控制费用和偶发网络失败？

**容易说错的地方**

- Fake Test 证明的是项目逻辑，不证明真实 Provider 协议可用。
- Integration Test 不是越多越好，必须可控、可隔离且不进入默认离线测试。

**掌握状态**

`理解 / 能写`：Fake、Contract、API 与 opt-in Integration 分层均已实现（2026-08-14）。
`能讲 / 能画`：待解释为什么真实测试不进入默认离线套件。

### Q10. Token Usage、Latency、TTFT 和成本快照应该怎样记录？

**30 秒简答**

一条客户端请求只记录一条最终 Usage，由 ChatService 在成功、失败或取消后使用短事务
落库。Token 只相信 Provider 返回值，缺失时保存 `NULL`；流式首个 Delta 计算 TTFT；
价格与输入/输出 Token 都完整时用 Decimal 保存成本、币种和价格版本快照。Usage 和
日志不保存 Message、Prompt、回答、Secret 或原始异常。

**2 分钟完整回答**

Usage 是可查询的调用事实，不是应用日志、Metrics 或 Provider 账单。`latency_ms` 从
业务请求开始到终态，Streaming 的 `time_to_first_token_ms` 从开始到首个 `ChatDelta`；
非流式或首 Delta 前失败时 TTFT 是 `NULL`。一次 Gateway Retry 仍属于同一个客户端
请求，因此只生成一条 `ChatUsage`。成功记录 `finish_reason`，失败和取消记录固定内部
`error_code`。Provider 可能不返回 Usage，或流中断时只返回部分统计，未知值必须是
`NULL` 而不是零。

成本配置放在模型别名注册表中，输入与输出单价统一按每百万 Token 表达。只有输入与
输出 Token 都可信时，才使用 `Decimal` 计算并保存 `estimated_cost + currency +
pricing_version`。三者组成调用发生时的历史快照，以后修改价格不会改写旧记录。Service
协调这些业务终态，Repository 只执行 SQL；模型生成期间不持有数据库事务，结束后才
用独立 Session 写短事务。落库失败回滚并写安全日志，但不把成功回答改成失败。

**项目中的设计或代码证据**

- `app/models/usage.py` 用 Check Constraint 约束终态、Token、成本快照和非负耗时。
- `app/ai/usage_cost.py` 使用 Decimal 与价格版本生成不可变成本快照。
- `ChatService` 记录非流式和 Streaming 的 success/failed/cancelled，并在首 Delta 计算
  TTFT；`ChatUsageRepository` 只负责创建与查询。
- ADR-0029 固化短事务、未知 Token、价格快照和内容数据最小化。

**为什么没有采用其他方案**

- 不让 Gateway/Provider 写 Usage，因为它们不知道认证用户和最终业务终态。
- 不在 Streaming 期间持有数据库事务，避免慢模型长期占用数据库连接。
- 不用字符数猜 Token，也不把未知值写成零。
- 不保存完整 Prompt 和回答换取排查便利，当前没有对应权限、保留和脱敏需求。

**常见追问**

- Provider 成功但 Usage 落库失败，API 应该返回成功还是失败？
- 流中断只拿到 input_tokens 时，成本能否估算？
- 为什么成本快照不是账单？

**容易说错的地方**

- TTFT 是首个内容 Delta 的等待时间，不是收到最终 Usage 或 Done 的时间。
- `NULL` 表示不知道，零表示明确没有消耗，两者不能混用。
- 成本快照是配置价格下的估算，不保证等于 Provider 最终结算。

**掌握状态**

`理解 / 能写`：Usage、TTFT、三种终态、成本快照与短事务已实现（2026-08-13）。
`能讲 / 能画`：Sprint 4 Review 已完成；仍建议不看文档画出流式终态。

## Sprint 5: RAG

Sprint 5 当前只补充 5.1 至 5.6 已实现的知识入库问题。查询 Retrieval、Citation、质量
评估和 RAG Chat 闭环仍在后续 Story，不能把设计目标写成已完成事实。

### Q1. RAG 的完整数据和查询链路是什么？

**30 秒简答**

RAG 有两条链路：入库将 File 解析、分块、Embedding 并索引；查询将用户问题向量化、按
知识库过滤检索 Chunk、构造 Context，再交给 ChatService 和 AIGateway 生成带 Citation 的
回答。当前项目已完成入库到 Qdrant，查询从 Story 5.7 开始实现。

**2 分钟完整回答**

入库链路的事实来源是 Sprint 3 的 FileResource。KnowledgeService 将 READY 文件登记为
Document，按 Parser/Chunker/Embedding 配置产生 Version 和 Chunk；EmbeddingGateway 为
Chunk 批量产生向量，VectorStore 写入 Qdrant，成功后 Version 才能成为 active。MySQL 保存
所有权、原文、来源、状态和 Version，Qdrant 保存可再生向量与最小过滤 payload。

查询链路不能直接让模型“读整个文件”。它应从一个已授权 KnowledgeBase 开始，将 Query
用同一向量空间的 Embedding Model 转换为向量，在 Qdrant 得到 Top K，再由 MySQL 验证
Chunk/Version/来源并压缩成预算内 Context。最后 ChatService 通过 PromptCenter/AIGateway
生成回答，Citation 指回 File、页码或 Chunk。后半段尚未实现。

**项目中的设计或代码证据**

- `KnowledgeService.ingest_file_to_base()` 到 `index_document_version()` 已形成入库闭环。
- `VectorStore` / `QdrantVectorStore` 隔离向量 SDK；ADR-0030 固化状态和一致性。
- `ChatService -> AIGateway` 是将来 RAG Context 复用的既有生成边界。

**为什么没有采用其他方案**

- 不把原始 PDF 全量塞入 Prompt，Context Window 和成本都不可控。
- 不在 Story 5.6 提前实现 Query Rewrite、Rerank 或 Agentic RAG。

**常见追问**

- 为什么查询也必须使用兼容的 Embedding Profile？
- Citation 在检索层还是生成层产生？

**容易说错的地方**

- 当前项目尚未完成 Retrieval 和 RAG Answer，不能宣称端到端问答可用。
- Qdrant 命中只是候选，业务来源和权限仍要回到 MySQL。

**掌握状态**

`理解 / 能画`：已完成入库链路与后续查询边界梳理（2026-08-19）。
`能写`：入库完成；查询待 Story 5.7。

### Q2. FileResource、KnowledgeDocument、DocumentVersion 和 DocumentChunk 如何分工？

**30 秒简答**

FileResource 是原始文件及存储生命周期；KnowledgeDocument 是“这个文件被加入某知识库”
的管理关系；DocumentVersion 是一次固定 Parser、Chunker、Embedding 配置的索引快照；
DocumentChunk 是 Version 下可检索的原文片段。原文件不变也可能因处理配置变化产生新
Version。

**2 分钟完整回答**

把 File 当作知识本身会把对象存储、权限、解析和向量配置耦合。FileResource 属于 Sprint
3，负责 owner、Object Key、SHA-256、READY/删除等生命周期；同一 File 可以在不同
KnowledgeBase 建立不同 Document。Document 不承载一次解析的具体结果，因为 Parser
版本、Chunk 参数或 Embedding 模型变化后需要保留新旧索引并支持回滚。

因此 Version 保存 processing fingerprint、处理配置和状态；Chunk 保存内容、顺序、Token
数和来源定位。Document 的 `active_version_id` 仅在某个 Version 成功 indexed 后更新，
所以新版本失败时旧知识仍可检索。复合外键确保 active Version 一定属于同一个 Document。

**项目中的设计或代码证据**

- `models/knowledge_base.py`、`knowledge_document.py`、`document_version.py`、
  `document_chunk.py` 定义四层模型与约束。
- `build_processing_fingerprint()` 把文件摘要和处理配置变成幂等键。
- ADR-0030 与 Migration 记录 Version、active 指针和索引状态。

**为什么没有采用其他方案**

- 不让 Chunk 直接外键 File，因为它需要绑定一次处理版本。
- 不为每次重试创建新 Document，避免同一文件管理关系重复。

**常见追问**

- 为什么一个 File 能进入多个 KnowledgeBase？
- active Version 是否必须是最大 Version Number？

**容易说错的地方**

- Document 不是文件 Bytes 的复制。
- Version 不是“每个 Chunk 一条 Version”；一个 Version 对应多个 Chunk。

**掌握状态**

`理解 / 能写`：模型、约束和持久化流程已实现（2026-08-19）。
`能讲 / 能画`：待画出 File 到 Version 的多对一/一对多关系。

### Q3. Parser 为什么要把 PDF、TXT、Markdown 转成统一的 ParsedDocument/Block？

**30 秒简答**

不同格式的读取方式不同，但 Chunker 只需要“有序文本和来源定位”。Parser 负责把格式
差异转换为统一 Block；Chunker 不需要知道 PDF 页、TXT 编码或 Markdown 标题的底层库。
这让后续新增格式不会污染分块和索引业务。

**2 分钟完整回答**

PDF 通过页读取，Markdown 有标题结构，TXT 需要编码处理；若 Service 直接写多层
`if content_type`，每个后续步骤都会被文件格式分支污染。ParserRegistry 依据受支持的
Content-Type 选择 Parser，输出统一 ParsedDocument 和 ParsedBlock。Block 保留 text、
block_index、source_locator 等信息，使 Chunker 能按原始顺序处理，未来 Citation 可以回答
“来自哪一页或哪一段”。

Parser 的版本也必须进入 Version 指纹。相同原文件若更换 pypdf 版本或修正解析逻辑，文本
可能变化，旧向量不能被错误复用。Parser 只负责内容规范化，不负责权限、对象存储、分块、
Embedding 或数据库写入。

**项目中的设计或代码证据**

- `knowledge/parsing.py` 定义 ParsedDocument / ParsedBlock 与 ParsingError。
- `knowledge/parsers/` 提供 PDF、TXT、Markdown Parser 和 ParserRegistry。
- `prepare_document_version()` 将 parser name/version 写入 fingerprint 与 Version。

**为什么没有采用其他方案**

- 不把 pypdf、编码和 Markdown 分支写入 Chunker。
- 不只输出纯字符串，否则会失去页码等 Citation 所需来源。

**常见追问**

- 扫描版 PDF 没有文本时应如何演进？
- Parser 升级为什么不覆盖旧 Version？

**容易说错的地方**

- Parser 不是把所有格式转成 PDF；它是转成项目的统一解析模型。
- `parser_version` 是 Parser 实现版本，不是用户文件的版本号。

**掌握状态**

`理解 / 能写`：PDF、TXT、Markdown Provider 与统一解析契约已实现（2026-08-19）。
`能讲`：待从一个 PDF 页到 Block 的路径复述。

### Q4. 为什么 Chunk 按 Token 和结构切分，并使用 overlap，而不是按字节数截断？

**30 秒简答**

模型的输入限制按 Token，不按 UTF-8 字节。按字节会截断中文、单词或句子，也不能反映
模型预算；结构化 Chunker 先保持标题/段落边界，再按 Token 上限切分，overlap 保留相邻
语义以避免关键句刚好跨边界丢失。

**2 分钟完整回答**

Chunk 太大时，一次向量会混合多个主题，检索与 Prompt 预算变差；太小时上下文不足，
答案需要的限定条件可能分散在相邻块。第一版使用可配置的 `max_tokens` 与
`overlap_tokens`，并先消费 Parser 输出的结构 Block。只有某个 Block 超过上限时才继续
按句子/Token 边界拆分，这比固定字符或字节切割更稳定。

Overlap 使下一块带有上一块尾部的一部分 Token，提高跨句、跨段检索的召回机会，但会增加
Embedding、存储和 Context 去重成本。参数本身进入 processing fingerprint，因此改变
Chunk 策略会创建新 Version，而不是悄悄复用旧向量。

**项目中的设计或代码证据**

- `StructureAwareChunker` 和 `ChunkingConfig` 实现结构优先、Token 上限和 overlap。
- `TiktokenTokenCounter` 负责模型相关 Token 计数。
- `chunker_config.fingerprint_payload()` 进入 `build_processing_fingerprint()`。

**为什么没有采用其他方案**

- 不按 bytes/字符数硬切，避免文本损坏和预算失真。
- 不在第一版使用昂贵、不可预测的 LLM Semantic Chunking。

**常见追问**

- overlap 是否总能提高检索效果？
- Markdown 标题应该复制到每个子块吗？

**容易说错的地方**

- Token 不是字符数，也不是字节数。
- overlap 是相邻 Chunk 的冗余，不是重复建多个 Version。

**掌握状态**

`理解 / 能写`：Token Chunk、结构边界与 overlap 配置已实现（2026-08-19）。
`能讲 / 能画`：待用一个跨段定义举例说明召回影响。

### Q5. Embedding、Vector、Embedding Profile 和处理指纹分别解决什么问题？

**30 秒简答**

Embedding Model 把文本映射为固定维度的浮点 Vector，使语义相近文本在同一向量空间距离
更近。Embedding Profile 固定模型别名、维度和 tokenizer；处理指纹把文件、Parser、Chunker
和 Profile 合在一起，决定旧 Version 能否幂等复用。

**2 分钟完整回答**

Vector 是数值数组，例如 1536 个 float，不是加密后的原文，也不是关键词列表。Embedding
Provider 对同一个模型空间中的 Query 和 Chunk 分别产生 Vector，Vector Store 才能以距离
或相似度检索候选。不同模型的维度、训练语义和 tokenizer 可能不同，因此 1536 维旧向量
不能与 3072 维新向量混用，即使数据库字段名字相同。

项目将模型 Profile 作为服务器配置，客户端不能选择任意 Provider/维度；EmbeddingGateway
检查每批返回数量、顺序、维度和数值有限性。processing fingerprint 包含 File SHA-256、
Parser、Chunker 配置和 Profile，配置任意一项变化就形成新 Version，避免重复付费或错误
复用旧索引。

**项目中的设计或代码证据**

- `EmbeddingGateway.embed()` 统一 Provider 调用、Deadline 和结果校验。
- `EmbeddingProfile` 与 `resolve_default_embedding_profile()` 解析模型配置。
- `knowledge/indexing.py` 计算稳定 SHA-256 processing fingerprint。

**为什么没有采用其他方案**

- 不让 KnowledgeService 直接调用厂商 SDK，保持 Capability-specific Gateway 边界。
- 不只按 File SHA-256 去重，因为处理配置变化会改变索引结果。

**常见追问**

- 为什么 Query 不能用另一个不兼容模型生成 Vector？
- Float Vector 是否需要保存在 MySQL？

**容易说错的地方**

- Embedding 不是生成摘要，也不会直接生成最终答案。
- 同维度不保证两个模型的向量空间兼容。

**掌握状态**

`理解 / 能写`：Embedding Gateway、批处理和 Profile 校验已实现（2026-08-19）。
`能讲`：待以 Query/Chunk 同空间为例解释相似度。

### Q6. 为什么 MySQL 和 Qdrant 要职责分离？

**30 秒简答**

MySQL 保存业务真相：owner、Base、Document、Version、Chunk 原文与状态；Qdrant 保存可再生
Vector 和最小过滤 payload，用于相似度搜索。Qdrant 不是权限数据库，检索命中后仍要按
MySQL 的事实回填内容和来源。

**2 分钟完整回答**

关系数据库擅长外键、唯一约束、事务、所有权和可审计状态；向量数据库擅长近邻搜索和
向量索引。将两者混为一个存储，会让 Qdrant 承担复杂业务关系、文件生命周期和权限校验，
同时把原文复制到多个系统造成漂移。项目使用 `DocumentChunk.id` 作为 Qdrant Point ID，
payload 只保留 `knowledge_base_id` 和 `document_version_id`，可用于未来 Base Filter 与
Version Cleanup。

MySQL 不是向量库的备份，而是业务权威；Qdrant 也不是可随意丢弃的缓存，因为其重建有
Embedding 时间与费用。两者无共享事务，所以 Service 必须用 Version 状态和补偿处理部分
成功，而不是假设写入顺序天然一致。

**项目中的设计或代码证据**

- `VectorStore` Protocol 不暴露 Qdrant SDK；`QdrantVectorStore` 是唯一 SDK Adapter。
- `VectorPoint` 明确 Point ID、Vector、Base ID、Version ID。
- ADR-0030 固化业务真相与派生索引的边界。

**为什么没有采用其他方案**

- 不把权限和完整 Chunk Content 全量复制到 Qdrant。
- 不把 Embedding Vector 作为 MySQL 主要检索索引。

**常见追问**

- Qdrant payload Filter 能否替代 MySQL owner 校验？
- 为什么要按 Version 而不是 Document 清理向量？

**容易说错的地方**

- Qdrant 类似数据库，但不是 MySQL 的直接替代品。
- payload 是检索辅助元数据，不是完整业务实体。

**掌握状态**

`理解 / 能写`：VectorStore、Qdrant Adapter、Compose 服务与边界已实现（2026-08-19）。
`能讲 / 能画`：待画出一次检索的 Qdrant 候选到 MySQL 回填路径。

### Q7. 跨 MySQL、Embedding Provider 与 Qdrant 的索引如何保证可恢复？

**30 秒简答**

不能做到分布式原子事务，只能用 Version 状态机、幂等键和补偿。先写 pending Version/Chunk，
原子认领为 processing，在事务外生成向量并写 Qdrant，成功后再短事务标记 indexed；失败
删除已写向量，清理失败则记录 cleanup_required，后续先清理才能重试。

**2 分钟完整回答**

Service 不在模型调用期间持有 MySQL Transaction。Repository 通过带状态条件的 UPDATE 实现
compare-and-set，多个请求只有一个能从 pending 变 processing。Qdrant 批量写入任一批失败
时，Service 按 `document_version_id` 删除本次可能写入的全部 Point；清理成功进入 failed，
清理失败进入 cleanup_required，明确表达外部状态尚不确定。

若 Qdrant 已写成功但 MySQL 无法完成 indexed，Service 同样删除向量，避免“数据库未索引
但向量可被查询”的孤儿数据。retry 对 failed 重新排队；cleanup_required 先执行幂等删除。
`active_version_id` 只在 indexed 后提升，并且只接受比当前更高的 Version Number，旧版本
晚完成不会回退新版本。

**项目中的设计或代码证据**

- `claim_pending_version()`、`complete_version_indexing()`、`mark_version_indexing_failed()`。
- `upsert_vector_points()` 和 `_cleanup_failed_vector_write()` 负责批量补偿。
- `retry_document_version()` 与 `POST .../versions/{version_id}/retry` 实现安全重试。

**为什么没有采用其他方案**

- 不把外部 I/O 放进 MySQL 长事务。
- 不把 cleanup_required 直接当 failed 后立即重试，可能留下残留向量。

**常见追问**

- MySQL 完成写入失败但 Qdrant 删除也失败时怎么办？
- 为什么 processing 需要原子认领？

**容易说错的地方**

- 补偿不是回滚，外部删除也可能失败。
- HTTP 上传成功不总等于知识已可检索，必须看 Version 状态。

**掌握状态**

`理解 / 能写`：索引状态、补偿和 retry API 已实现（2026-08-19）。
`能讲 / 能画`：待画出 Qdrant 成功但 MySQL 失败的补偿路径。

### Q8. 为什么 Sprint 5 先同步索引，而不立即使用 Celery 或消息队列？

**30 秒简答**

异步 Worker 只能改变调度方式，不能替代 Version 状态、幂等和补偿规则。Sprint 5 先在同步
请求中证明入库状态机正确；Sprint 10 再把同一 Service 用例交给队列、重试策略和监控平台
调度，避免基础设施掩盖领域问题。

**2 分钟完整回答**

Embedding 和 Qdrant 都是网络 I/O，生产规模最终通常需要异步任务。可是如果当前没有明确
pending/processing/failed/cleanup_required、无原子认领，也不知道向量部分成功后如何清理，
把调用移到 Celery 只会让失败在不同进程和消息重投之间更难观察。同步实现让调用链、状态
和失败返回清晰，也便于学习 Service、Repository、Provider 的职责。

当前 API 仍是 `async def`，因为 Embedding/Qdrant Client 是异步 I/O；这不等于已有后台
任务或流式上传索引。未来 Worker 应调用 `retry_document_version()` 或同一索引用例，不能
绕过 ownership、状态、处理指纹和 Vector 清理。请求级 Qdrant Client 也需要在 Worker 中
改为任务级资源管理。

**项目中的设计或代码证据**

- Sprint 5 文档明确将队列和后台重试留给 Sprint 10。
- `index_document_version()` 把 MySQL 短事务与异步网络 I/O 分开。
- ADR-0030 明确未来调度不能绕过现有状态机。

**为什么没有采用其他方案**

- 不把 FastAPI BackgroundTasks 当可靠队列；其重试、持久化和可观测性不足。
- 不提前引入 Celery/RabbitMQ，避免当前学习被部署与消息语义主导。

**常见追问**

- 同步上传接口的超时和用户体验如何演进？
- Worker 至少一次投递如何避免重复 Embedding？

**容易说错的地方**

- `async def` 不等于后台异步任务。
- 把任务丢给队列不自动获得幂等性或补偿。

**掌握状态**

`理解 / 能讲`：同步状态机与未来异步边界已明确（2026-08-19）。
`能写`：当前同步索引已实现；Worker/队列待 Sprint 10。

### 待后续 Story 补充的 Sprint 5 题目

- Q9：Dense Retrieval 的 Top K、Score、Threshold 与 KnowledgeBase Metadata Filter。
- Q10：Citation、Context Token Budget 与 Prompt 注入边界。
- Q11：如何评价 Retrieval Recall、Answer Faithfulness 和 Citation Accuracy。
- Q12：Dense、Sparse、Hybrid、Reranker 和 Query Rewrite 的演进取舍。

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
