# Storage Flow

## 1. 上传主线

```mermaid
sequenceDiagram
    participant C as Client
    participant R as File Router
    participant S as FileService
    participant DB as MySQL Metadata
    participant P as StorageProvider

    C->>R: POST /files multipart/form-data
    R->>R: 验证 Access Token，得到 current_user.id
    R->>S: UploadFile + current_user.id
    S->>S: 分块读取，校验大小、类型，计算 SHA-256
    S->>DB: 创建 PENDING_UPLOAD Resource
    S->>S: 将 UploadFile 回到起点
    S->>P: 写入对象
    P-->>S: 写入成功
    S->>DB: 更新为 READY
    S-->>R: FileResourceResponse
    R-->>C: 201 Created
```

先完成流内校验，再创建 Resource，避免因为超大文件、类型拒绝或恶意文件名在 MySQL 留下无意义记录。文件通过校验后，Service 生成 UUID、Provider、Bucket 和 Object Key，创建 `PENDING_UPLOAD` Metadata。由于校验已经分块读取过 `UploadFile`，写入 Provider 前必须将它回到起点，再次以 Chunk 读取；整个过程不把完整文件读入业务内存。

当前上传是同步 API。客户端只有在对象写入成功并且 Metadata 已更新为 `READY` 时才得到 `201 Created`；否则得到明确错误响应，不能把 `PENDING_UPLOAD` 当作上传成功返回。

## 2. 上传失败与补偿

```mermaid
flowchart TD
    A["PENDING_UPLOAD Metadata 已创建"] --> B["写入 Storage Object"]
    B -->|失败且确认对象不存在| C["标记 UPLOAD_FAILED 并返回错误"]
    B -->|失败或超时且结果不确定| F
    B -->|成功| D["更新 Metadata 为 READY"]
    D -->|成功| E["201 Created"]
    D -->|失败| F["尝试删除刚写入的 Object"]
    F -->|成功| G["资源保持不可见，标记 UPLOAD_FAILED"]
    F -->|失败或结果不确定| H["CLEANUP_REQUIRED + ERROR 日志"]
```

MySQL 与对象存储没有共享 Transaction。对象写入成功、数据库更新失败时，删除对象是补偿动作，不是假装回滚了一个分布式事务。对象写入报错或网络超时也不必然代表对象不存在；如果 Provider 无法确认结果，Service 同样必须尝试删除对象。只有确认对象不存在或补偿删除成功后，资源才进入 `UPLOAD_FAILED`；补偿失败或结果不确定时进入 `CLEANUP_REQUIRED`。

当前提供可重复调用的 `FileService.cleanup_file(file_id)` 清理边界，但不实现后台 Worker、任务队列或 Scheduler。发生失败时 API 返回失败；用户重新上传会创建新的 UUID 与 Object Key。未来 Cleanup Worker 只负责任务调度和重试，仍复用当前 Service，不重新实现状态机。

## 3. 下载主线

```text
GET /files/{file_id}/download
  -> 验证 Access Token，得到 current_user.id
  -> 查询 file_id + owner_id + status=READY + deleted_at IS NULL
  -> 从 Metadata 获取内部 Provider、Bucket、Object Key
  -> 验证 Metadata 与当前 Provider / Bucket 匹配
  -> StorageProvider.open(object_key)
  -> FastAPI StreamingResponse 按 Chunk 代理输出并关闭流
```

不存在、非所有者、上传中、删除中、失败或已删除资源都返回 404。当前 LocalStorage 与 MinIO 都使用权限检查后的后端代理流；未来只有在带宽和并发数据证明需要时，才评估短 TTL Signed URL。

## 4. 删除主线

```mermaid
sequenceDiagram
    participant C as Client
    participant S as FileService
    participant DB as MySQL Metadata
    participant P as StorageProvider

    C->>S: DELETE /files/{file_id}
    S->>DB: 查询 owner_id + READY
    S->>DB: 更新为 DELETING
    S->>P: 删除 Object
    alt 删除成功
        P-->>S: 成功
        S->>DB: 更新为 DELETED，设置 deleted_at
        S-->>C: 204 No Content
    else 删除失败或结果不确定
        P-->>S: 失败
        S->>DB: 标记 CLEANUP_REQUIRED
        S-->>C: 明确失败响应
    end
```

先提交 `DELETING` 能避免并发下载继续把资源视为可用。Metadata 不立即物理删除，因为 Object 删除失败时它仍是补偿、审计和后续清理的唯一依据。

## 5. Cleanup 重试边界

```mermaid
flowchart TD
    A["内部任务传入 file_id"] --> B{"Metadata 是否为 CLEANUP_REQUIRED"}
    B -->|否| C["返回 False，不访问 Storage"]
    B -->|是| D{"failure_reason 是否受支持"}
    D -->|否| E["保留状态并记录固定错误"]
    D -->|是| F["幂等删除 Storage Object"]
    F -->|Provider 失败| G["保持 CLEANUP_REQUIRED，等待重试"]
    F -->|成功，来源是上传| H["更新为 UPLOAD_FAILED"]
    F -->|成功，来源是删除或对象缺失| I["更新为 DELETED + deleted_at"]
    H --> J["返回 True"]
    I --> J
```

Cleanup 是内部 Service 能力，不暴露用户 Router，也不接收 `owner_id`。Repository 只允许它读取 `CLEANUP_REQUIRED`，未知 `failure_reason` 必须在删除对象前拒绝。对象删除成功但 Metadata 提交失败时，Transaction 回滚后仍保持 `CLEANUP_REQUIRED`；下一次调用可依靠 Provider 的幂等删除重新收尾。

## 6. 错误、日志与测试

日志事件：

| 事件 | 级别 | 允许字段 |
| --- | --- | --- |
| `storage.upload.success` | INFO | `user_id`、`file_id`、`size_bytes` |
| `storage.upload.rejected` | WARNING | `user_id`、固定 `reason` |
| `storage.provider.unavailable` | ERROR | HTTP method、path |
| `storage.download.failed` | ERROR | `user_id`、`file_id`、固定 `reason` |
| `storage.compensation.failed` | ERROR | operation、`file_id`、固定 `reason` |
| `storage.delete.success` | INFO | `user_id`、`file_id` |
| `storage.cleanup.success` | INFO | `file_id`、目标状态 |
| `storage.cleanup.failed` | ERROR | `file_id`、固定 `reason` |

日志不记录原始文件内容、完整 Object Key、Bucket、Signed URL、访问密钥或未经处理的文件名。

测试矩阵：

| 范围 | 必须验证 |
| --- | --- |
| Schema | Response 不暴露内部位置，分页参数有界 |
| Repository | owner/status/deleted 过滤、唯一约束与状态更新 |
| Service | 上传主线、超限、类型拒绝、Provider 失败、数据库更新失败补偿 |
| API | 201、401、404、413、415、503、204 契约 |
| Permission | 非所有者不能列出、读取、下载或删除他人资源 |
| Integration | Local 与真实 MinIO 的上传、读取、删除、Cleanup 与故障路径 |

Provider 故障测试必须覆盖“明确写入失败”和“请求超时、对象结果不确定”两类情况。
