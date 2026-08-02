# ADR-0021: 建立对象存储边界，并采用 LocalStorage + MinIO 学习策略

## 状态

已接受（2026-08-02）

## 背景

Sprint 3 需要让用户上传的文件成为后续 Knowledge、Document、RAG、Workflow、Agent 和 MCP 都能使用的稳定资源。

将文件固定写到 FastAPI 某个本机目录，虽然能够快速完成单机上传，但会把文件可用性绑定到单个应用实例和容器生命周期。将大文件直接写入 MySQL BLOB 则会使事务数据、备份、查询和数据库容量承担不适合的二进制负担。

项目需要在本地学习阶段保持简单，同时验证与生产对象存储相同的基本契约。

## 决策

- 文件 Bytes 通过后续的 `StorageProvider` 边界保存，不由 Repository 直接写入 MySQL。
- MySQL 保存可查询的 File Metadata，包括稳定 `file_id`、`owner_id`、内部 Object Key、大小、SHA-256 和生命周期状态。
- Sprint 3 先实现 LocalStorage，便于在不依赖对象存储服务时进行快速开发和 Unit Test。
- Sprint 3 再使用 MinIO 进行真实 S3-compatible 对象存储集成验证。
- 面向客户端的 API 使用稳定 `file_id`，不暴露本地路径、Bucket 或内部 Object Key。
- Tencent COS 与 Amazon S3 是未来 Provider 扩展，不作为本 Sprint 的直接集成目标。

## 原因

- 文件内容与业务 Metadata 的读写模式、容量和生命周期不同。
- LocalStorage 降低早期学习与调试门槛；MinIO 验证 API、Bucket、凭据和真实对象存储故障边界。
- Provider 边界允许替换底层存储，而不会把对象存储 SDK、用户权限或 SQL 分散到 Router、Service 和 Repository。
- 稳定 Resource ID 允许存储位置迁移，同时保留下载、删除、权限、日志和未来 RAG 的业务语义。

## 影响

- MySQL 与对象存储不能共享数据库事务；后续必须设计上传、删除失败时的状态和补偿。
- LocalStorage 仅适合单机开发或明确挂载共享目录的简单部署，不可视为多实例生产方案。
- 后续需要新增 MinIO 配置、健康检查、Volume、访问凭据和真实集成测试。
- Bucket、Object Key、Signed URL 和下载方式必须在各自 Story 中明确，不能以本 ADR 代替详细 API 设计。

## 未采用方案

- 将所有上传文件直接保存到 MySQL BLOB：数据库会承担大二进制容量、备份与 I/O 压力，且不利于对象存储演进。
- 直接在 Router 中将文件写入 `uploads/`：缺少业务权限、Metadata、一致性边界和 Provider 可替换性。
- 一开始接入 COS 或 S3：会过早引入云账号、费用、网络和权限配置，降低当前学习反馈速度。
- 只使用 LocalStorage：无法验证对象存储 API、Bucket、凭据和故障语义。
