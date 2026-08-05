# Storage Security

## 1. 范围

本文记录 Story 3.6 至 Story 3.7 已实现的文件列表、详情、下载、删除和 Owner-only 权限边界。
当前支持通过配置切换 LocalStorage 与 MinIO；两者都使用权限检查后的后端代理下载。

## 2. 资源权限

客户端只提交稳定的 `file_id`，`owner_id` 必须来自已验证的 Access Token。单资源操作统一使用：

```text
file_id = 请求路径参数
AND owner_id = current_user.id
AND status = READY
AND deleted_at IS NULL
```

不存在、属于其他用户、未上传完成、删除中、失败或已删除的资源都返回 404。统一 404 避免向非所有者泄露资源是否存在。UUID 只能降低枚举便利性，不能替代 Owner 校验。

## 3. 受控下载

```text
GET /files/{file_id}/download
  -> 验证 Access Token
  -> FileService 查询 Owner + READY Metadata
  -> StorageProvider.open(object_key)
  -> FileDownload 返回流和安全 Metadata
  -> StreamingResponse 按配置 Chunk 输出并关闭流
```

Router 不读取磁盘路径，也不接收客户端提供的 Object Key。响应使用 Metadata 中已经校验过的 `content_type` 和 `original_filename`，文件名通过 RFC 5987 `filename*` 编码进入 `Content-Disposition`。

当前 LocalStorage 与 MinIO 都采用后端代理流：权限检查和对象读取都发生在 FastAPI 内部。`StreamingResponse` 每次读取固定 Chunk，不将整个对象一次载入业务内存，并在完成或异常时关闭本地文件流或 MinIO `StreamingBody`。

MinIO 已具备签发 Presigned URL 的能力，但当前文件大小与下载并发没有证明需要新增厂商特有契约。未来如果代理带宽成为瓶颈，仍必须在签发短 TTL URL 前完成相同的 Owner 与状态检查，并禁止记录 URL。

如果 Metadata 为 `READY` 但对象不存在，资源进入 `CLEANUP_REQUIRED`，第一次请求返回稳定 500；Provider 临时 I/O 故障返回 503。日志不记录 Object Key、磁盘路径或文件内容。

## 4. 删除状态机

```text
READY
  -> DELETING（先提交，立即停止列表、详情和下载可见性）
  -> StorageProvider.delete()
     -> 成功：DELETED + deleted_at
     -> 失败或结果不确定：CLEANUP_REQUIRED
```

先提交 `DELETING` 可以阻止并发下载在物理删除期间继续获得资源。Metadata 不做物理删除，因为对象删除失败时仍需要 `file_id`、Provider 位置和失败状态进行审计与未来清理。

Provider 删除失败时保存固定 `failure_reason=provider_delete_failed` 并返回 503。对象已经删除但最终 Metadata 提交失败时，Service 尝试保存 `CLEANUP_REQUIRED`；内部数据库或补偿状态提交失败返回安全 500。

重复删除不会再次调用 Provider：资源不再是 `READY` 后，Owner 查询返回空并统一映射为 404。无论重复请求的 HTTP 状态如何，资源状态不会恢复，因此删除操作保持状态幂等。

## 5. 当前 API

| API | 成功 | 主要失败 |
| --- | --- | --- |
| `GET /files?limit&offset` | 200 安全分页列表 | 401、422 |
| `GET /files/{file_id}` | 200 Metadata | 401、404 |
| `GET /files/{file_id}/download` | 200 文件流 | 401、404、500、503 |
| `DELETE /files/{file_id}` | 204 | 401、404、500、503 |

## 6. 验证证据

- Service Test 验证 Owner 隔离、分页、下载 Metadata、Provider 故障、缺失对象和删除补偿。
- API Test 验证分页约束、404 隐藏、流式响应 Header、分块读取和流关闭。
- LocalStorage 纵向测试完成上传、详情、列表、下载、删除和删除后再次访问 404。
- 真实 MinIO 纵向测试验证 Provider Factory、MySQL 存储位置、SHA-256、代理下载、删除和对象清理。
- MinIO 故障测试验证错误凭据、不存在 Bucket、Endpoint 不可用和条件化 Readiness。
- Router 不使用本地路径或 Provider SDK；Repository 不访问文件 Bytes。

## 7. 当前未实现

- MinIO Presigned URL、CDN 和公开下载链接；待规模与带宽数据证明需要后再设计。
- 文件共享、组织空间、RBAC 和跨用户授权。
- 后台 Cleanup Worker、自动对账和人工运维接口。
- Range Request、断点下载和视频流媒体优化。
