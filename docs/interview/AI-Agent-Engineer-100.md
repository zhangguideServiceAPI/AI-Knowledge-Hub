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
正式完整答案：7 / 100

Sprint 1 项目实现：已完成
Sprint 1 面试答案：待根据现有代码和 ADR 回填 10 道

Sprint 2 项目实现：已完成
Sprint 2 面试答案：待根据现有代码、流程图和测试回填 10 道

Sprint 3 学习计划：已完成
Sprint 3 面试答案：7 / 8，Story 3.0 至 3.6 已同步
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
