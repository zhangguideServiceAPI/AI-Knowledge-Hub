# Storage Architecture

## 1. 文档范围

本文记录当前已经实现的 HTTP Upload、Streaming 读取、安全校验、配置和职责边界。File Metadata、生命周期和跨系统补偿分别由 `file-resource-design.md` 与 `storage-flow.md` 详细说明。

## 2. 上传请求

当前接口：

```http
POST /files
Authorization: Bearer <access_token>
Content-Type: multipart/form-data; boundary=<boundary>
```

请求只包含一个必需的 `upload` Part。客户端不能提交 `owner_id`、`file_id`、`object_key`、Bucket 或服务器路径。

```text
multipart/form-data
  -> boundary 分隔每个 Part
  -> upload Part 包含 filename、客户端声明的 Content-Type 和文件 Bytes
  -> FastAPI 将文件部分表示为 UploadFile
```

上传只有在 Storage Object 写入成功且 Metadata 进入 `READY` 后才返回 HTTP 201。完整响应和资源字段见 `file-resource-design.md`；正式错误契约见 `../API规范.md`。

## 3. Streaming 读取约束

```text
UploadFile
  -> 每次读取固定大小的 Chunk
  -> 累计实际 total_size
  -> 超过上限立即拒绝
  -> 对每个 Chunk 更新 SHA-256
  -> 将文件指针回到起点
  -> 交给 StorageProvider 写入对象
```

不能只检查 `Content-Length`：

- 客户端可能不发送该 Header。
- 它是客户端或上游声明，不能替代应用对实际 Bytes 的限制。
- 即使 Header 可用，也只能用于提前拒绝明显过大的请求；最终限制必须由 `total_size` 执行。

`UploadFile` 底层使用可溢出到临时磁盘的文件对象。小文件可能暂存在内存，超过阈值后可能写入临时磁盘；这不是正式 LocalStorage，也没有稳定 Resource ID、Metadata 或下载语义。

业务代码禁止为了处理上传而一次读取全部文件：

```text
不使用：source.read()
使用：循环 source.read(chunk_size)
```

Chunk Size 是性能与内存的取舍：

| 选择 | 好处 | 代价 |
| --- | --- | --- |
| 较小 Chunk | 单请求内存占用更低 | I/O 调用和 Hash 更新次数更多 |
| 较大 Chunk | I/O 调用更少 | 并发上传时内存占用更高 |

当前默认 Chunk Size 为 1 MiB，通过 Pydantic Settings 的 `UPLOAD_CHUNK_SIZE_BYTES` 配置，不在 Service 中散落魔法数字。

## 4. 不可信输入与安全边界

| 输入 | 是否直接信任 | 后端策略 |
| --- | --- | --- |
| `filename` | 否 | 仅作为展示 Metadata；限制长度与控制字符；不用它直接生成路径或 Object Key |
| 扩展名 | 否 | 仅作提示，不能证明真实文件格式 |
| 客户端 `Content-Type` | 否 | 用于初步允许列表判断，不能单独证明文件类型 |
| `Content-Length` | 否 | 仅可提前拒绝，实际大小由分块累计 |
| 文件 Bytes | 需要处理 | 读取实际大小，后续按类型策略检查签名并计算 SHA-256 |
| `owner_id` | 客户端不可提供 | 从已认证 Access Token 获得 |
| `file_id` 与 `object_key` | 客户端不可提供 | 由后端生成 |

客户端文件名可能包含 `../../` 等路径穿越字符。即使最终使用对象存储，也不能将原始文件名直接用作内部 Object Key；内部位置必须由服务端生成。

扩展名、MIME 和文件签名不是同一回事。Sprint 3 建立明确的允许类型策略，但不实现病毒扫描、内容审核或沙箱执行。

## 5. 职责与错误边界

```text
Router
  -> 接收 UploadFile 和认证依赖
  -> 调用 FileService

FileService
  -> 读取 Chunk、累计大小、执行类型策略、计算 SHA-256
  -> 违反业务约束时抛出明确业务异常

Global Exception Handler
  -> 将业务异常映射为稳定 HTTP 错误响应

StorageProvider
  -> 保存、读取和删除已经通过业务校验的 Bytes
  -> 不决定用户权限、文件大小或类型策略
```

当前异常语义：

| 业务异常 | 负责层 | HTTP |
| --- | --- | ---: |
| `FileTooLargeError` | FileService | 413 |
| `UnsupportedFileTypeError` | FileService | 415 |
| `InvalidFileNameError` / `EmptyFileError` | FileService | 400 |
| `StorageUnavailableError` | FileService / Handler | 503 |
| 未认证 | 认证依赖 | 401 |
| Multipart 缺少必需 `upload` Part | FastAPI 请求校验 | 422 |

Provider 将文件系统或 S3 SDK 错误转换为稳定 Storage 异常；FileService 再根据业务阶段转换为上传、下载或删除领域异常；全局 Handler 负责 HTTP 映射。

## 6. 配置与测试

当前 Settings：

```text
MAX_UPLOAD_SIZE_BYTES
UPLOAD_CHUNK_SIZE_BYTES
STORAGE_PROVIDER
STORAGE_LOCAL_ROOT
STORAGE_MINIO_ENDPOINT
STORAGE_MINIO_ACCESS_KEY
STORAGE_MINIO_SECRET_KEY
STORAGE_MINIO_BUCKET
```

当前允许 PDF、PNG 和 JPEG，扩展名、MIME 与文件签名映射由 `upload_validation.py` 的固定策略维护。若以后需要运行时配置允许列表，必须同时设计启动校验、签名策略和测试，不能只开放 MIME 字符串配置。

最小测试矩阵：

| 场景 | 预期 |
| --- | --- |
| 正常 Multipart 文件 | Router 能接收为 UploadFile |
| `Content-Length` 明显超限 | 可以提前拒绝，但不替代流内计数 |
| 实际流内大小超过上限 | FileService 抛出大小异常 |
| 大文件多 Chunk | 不调用无参数 `read()`，按配置 Chunk Size 读取 |
| 文件名包含路径穿越片段 | 不成为本地路径或内部 Object Key |
| 扩展名与 MIME 伪造 | 进入明确的类型拒绝策略 |

## 7. 当前边界

- 当前上传是同步请求，不实现浏览器直传、分片上传或断点续传。
- `UploadFile` 可能使用临时磁盘，但临时文件不是正式 Storage Object。
- 文件签名校验只能提高类型可信度，不等于病毒扫描、内容审核或沙箱执行。
- LocalStorage 与 MinIO 共用 FileService 主流程；配置切换已有资源前必须先迁移对象并同步 Metadata。
- Metadata、权限、状态机和 Cleanup 见 `file-resource-design.md`、`storage-security.md` 与 `storage-flow.md`。
