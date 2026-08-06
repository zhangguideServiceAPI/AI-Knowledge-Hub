# Storage Architecture

## 1. 文档范围

本文先记录 Story 3.1 已确认的 HTTP Upload 与 Streaming 基础约束。

它不定义最终的 File Metadata 表、完整响应 Schema、StorageProvider 方法签名或对象存储一致性策略；这些内容由 Story 3.2 继续设计。

## 2. 上传请求草案

上传候选接口：

```http
POST /files
Authorization: Bearer <access_token>
Content-Type: multipart/form-data; boundary=<boundary>
```

请求只包含一个必需的 `file` Part。客户端不能提交 `owner_id`、`file_id`、`object_key`、Bucket 或服务器路径。

```text
multipart/form-data
  -> boundary 分隔每个 Part
  -> file Part 包含 filename、客户端声明的 Content-Type 和文件 Bytes
  -> FastAPI 将文件部分表示为 UploadFile
```

最终成功响应、列表响应和错误码细节在 Story 3.2 与 File Resource 领域设计一起确定。当前仅确认：超过应用大小上限的文件属于 HTTP 413 候选，类型不被允许的文件属于 HTTP 415 候选。

## 3. Streaming 读取约束

```text
UploadFile
  -> 每次读取固定大小的 Chunk
  -> 累计实际 total_size
  -> 超过上限立即拒绝
  -> 对每个 Chunk 更新 SHA-256
  -> 后续 Story 才将已验证的内容交给 StorageProvider
```

不能只检查 `Content-Length`：

- 客户端可能不发送该 Header。
- 它是客户端或上游声明，不能替代应用对实际 Bytes 的限制。
- 即使 Header 可用，也只能用于提前拒绝明显过大的请求；最终限制必须由 `total_size` 执行。

`UploadFile` 底层使用可溢出到临时磁盘的文件对象。小文件可能暂存在内存，超过阈值后可能写入临时磁盘；这不是正式 LocalStorage，也没有稳定 Resource ID、Metadata 或下载语义。

业务代码禁止为了处理上传而一次读取全部文件：

```text
不使用：await file.read()
使用：循环 await file.read(chunk_size)
```

Chunk Size 是性能与内存的取舍：

| 选择 | 好处 | 代价 |
| --- | --- | --- |
| 较小 Chunk | 单请求内存占用更低 | I/O 调用和 Hash 更新次数更多 |
| 较大 Chunk | I/O 调用更少 | 并发上传时内存占用更高 |

初始候选为 1 MiB，必须在后续通过 Pydantic Settings 配置，而不是在 Service 中散落魔法数字。

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

## 5. 职责与错误草案

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
  -> 在后续 Story 保存、读取和删除已允许的 Bytes
  -> 不决定用户权限、文件大小或类型策略
```

候选异常语义：

| 业务异常 | 负责层 | HTTP 候选 |
| --- | --- | ---: |
| `FileTooLargeError` | FileService | 413 |
| `UnsupportedFileTypeError` | FileService | 415 |
| 未认证 | 认证依赖 | 401 |
| Multipart 缺少必需 `file` Part | FastAPI 请求校验 | 后续确认 |

最终 Exception 类、错误码和统一 Handler 映射由 Story 3.2 一次性确认，避免在本 Story 提前写生产 Upload Helper。

## 6. 配置与测试草案

后续 Settings 候选：

```text
MAX_UPLOAD_SIZE_BYTES
UPLOAD_CHUNK_SIZE_BYTES
ALLOWED_UPLOAD_CONTENT_TYPES
```

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

Story 3.1 只完成上传入口的协议和内存安全学习。下一步 Story 3.2 再统一确定 Metadata、完整 API、状态机、跨 MySQL 与对象存储的一致性和错误契约。
