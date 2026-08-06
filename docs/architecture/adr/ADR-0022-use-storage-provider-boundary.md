# ADR-0022: 使用 StorageProvider 隔离文件资源与具体存储 SDK

## 状态

已接受（2026-08-03）

## 背景

FileService 需要保存、读取和删除文件 Bytes，但 Local 文件系统和 MinIO 使用不同 API、异常类型和配置方式。将这些调用直接散落在 Router、Service 或 Repository 会使权限、业务流程、SQL 和 Provider SDK 强耦合。

## 决策

- 定义最小 `StorageProvider` 边界，负责对象的保存、打开读取和删除。
- FileService 负责权限、生命周期、跨系统编排、补偿和日志时机。
- FileRepository 只保存和读取 MySQL Metadata，不调用 Provider SDK。
- Router 只接收 HTTP UploadFile、认证依赖和响应，不处理对象存储细节。
- Story 3.3 先提供 LocalStorage 实现；Story 3.7 再提供 MinIO 实现，FileService 主流程不因 Provider 切换而改变。
- 当前进程只启用一个 Provider；对象操作前必须验证 Metadata 中的 Provider 与 Bucket，配置切换已有数据时需要独立迁移流程。

## 原因

- 可以用 LocalStorage 快速验证业务流程，并用 MinIO 验证 S3-compatible 行为。
- Provider 不了解用户、HTTP、SQL 或业务状态，测试替身更简单。
- 当前只抽象已经需要的 Put、Get 和 Delete，不为 COS、S3、CDN、分片续传或异步任务预先设计复杂通用接口。

## 影响

- 后续需要为 Provider 定义明确的领域异常和流式输入输出边界。
- StorageProvider 不是事务管理器；MySQL 与对象存储一致性仍由 FileService 处理。
- 增加新的 Provider 时必须通过现有 Provider 契约和生命周期测试，而不是让 Router 判断不同 Provider。
- 当前不支持按单条资源动态路由多个 Provider；该能力只有在真实迁移或混合存储需求出现后再设计 Provider Registry。

## 未采用方案

- 直接在 FileService 调用 MinIO SDK：早期代码更短，但会锁死业务流程并难以进行 Local Test。
- Repository 同时操作 MySQL 和对象存储：违反 Repository 只负责数据库访问的项目约束。
- 一次实现 COS、S3、MinIO、CDN 和多个高级接口：当前没有真实需求，会造成过度抽象。
