# API 规范

## Health Check

健康检查分为 Liveness 和 Readiness。Liveness 只表示 FastAPI 进程可以响应，Readiness 表示应用所需依赖已经可用。

### Liveness

```http
GET /health/live
```

成功响应：HTTP 200

```json
{
  "status": "ok"
}
```

Liveness 不访问 MySQL、Redis 等外部依赖。请求超时、连接失败或非 2xx 状态均表示当前实例不存活。

### Readiness

```http
GET /health/ready
```

依赖正常：HTTP 200

```json
{
  "status": "ready",
  "database": "ok",
  "redis": "ok",
  "storage": "ok"
}
```

必要依赖不可用：HTTP 503

```json
{
  "status": "not_ready",
  "database": "ok",
  "redis": "ok",
  "storage": "unavailable"
}
```

`database`、`redis` 和 `storage` 分别报告依赖状态。任一必要依赖不可用时，整体 `status` 为 `not_ready` 并返回 HTTP 503。LocalStorage 模式不访问 MinIO；MinIO 模式使用短超时 `head_bucket()` 检查配置 Bucket。Liveness 不访问这些依赖。

Jenkins 蓝绿发布使用 Readiness 判断新实例是否可以接收流量。未来 Kubernetes 分别使用 Liveness 和 Readiness 探针。

## Authentication

### Register

```http
POST /auth/register
Content-Type: application/json
```

请求：

```json
{
  "email": "user@example.com",
  "password": "password123",
  "nickname": "User"
}
```

`nickname` 可省略。密码至少 8 个字符，最多 72 UTF-8 bytes。

注册成功：HTTP 201

```json
{
  "id": 1,
  "email": "user@example.com",
  "nickname": "User",
  "avatar_url": null,
  "status": "active",
  "created_at": "2026-07-21T17:00:00",
  "updated_at": "2026-07-21T17:00:00"
}
```

响应中禁止出现 `password` 或 `password_hash`。

邮箱已注册：HTTP 409

```json
{
  "detail": "Email is already registered."
}
```

请求字段校验失败：HTTP 422。邮箱格式、密码最小字符数和 bcrypt 最大字节数均由 `RegisterRequest` 校验，校验失败时不会调用注册 Service。

### Login

```http
POST /auth/login
Content-Type: application/json
```

请求：

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

登录成功：HTTP 200

```json
{
  "access_token": "signed-access-jwt",
  "refresh_token": "signed-refresh-jwt",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_expires_in": 604800
}
```

登录成功会为当前设备创建独立的 Redis Session。`expires_in` 和 `refresh_expires_in` 的单位均为秒；默认固定过期模式下，Access Token 最多有效 30 分钟，Refresh Token 和 Redis Session 最多有效 7 天。

Access Token Payload 包含字符串形式的用户 ID、Token 类型、签发时间和过期时间。Access 与 Refresh JWT Header 都包含 `kid`，服务端使用它从 Key Ring 选择验证密钥；客户端不需要解析或管理 `kid`。

邮箱不存在或密码错误统一返回 HTTP 401，不向客户端暴露邮箱是否已注册：

```http
WWW-Authenticate: Bearer
```

```json
{
  "detail": "Invalid email or password."
}
```

邮箱和密码正确但账号状态不是 `active`：HTTP 403

```json
{
  "detail": "User account is inactive."
}
```

每次登录在密码验证前通过 Redis 事务原子占用一次尝试额度。同一登录标识在固定窗口内最多允许 5 次进入密码验证；第 5 次错误本身仍返回 HTTP 401，第 6 次及后续请求返回 HTTP 429。登录成功会清除计数：

```json
{
  "detail": "Too many login attempts. Try again later."
}
```

Redis 无法完成登录限流检查或创建 Session 时，登录采用失败关闭策略，不签发可用的 Token Pair，并返回 HTTP 503。响应不暴露内部 Redis 组件名称：

```json
{
  "detail": "Authentication service is temporarily unavailable."
}
```

请求字段校验失败：HTTP 422。登录密码允许历史账号使用至少 1 个字符的密码，但仍限制为最多 72 UTF-8 bytes。登录不会重新执行注册时的密码强度策略。

### Refresh

登录接口返回 Token Pair 并创建初始 Redis Session。`/auth/refresh` 已接入 Router 和 Service，客户端可以使用当前 Refresh Token 换取新的 Token Pair。

Refresh 请求：

```http
POST /auth/refresh
Content-Type: application/json
```

```json
{
  "refresh_token": "signed-refresh-jwt"
}
```

Refresh 成功返回新的 Token Pair：

```json
{
  "access_token": "new-signed-access-jwt",
  "refresh_token": "new-signed-refresh-jwt",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_expires_in": 603000
}
```

`expires_in` 和 `refresh_expires_in` 的单位为秒，表示从响应时刻起的剩余有效时间。固定过期模式下，Rotation 不会重新增加 7 天；接近 Session 最终过期时，Access Token 的有效期也不能超过 Session 剩余时间。

Refresh JWT 无效、已过期、类型错误、Session 不存在或 Token Hash 不匹配时返回 HTTP 401。Token Hash 不匹配视为旧 Token 重用，服务端会撤销当前设备 Session；其他设备 Session 不受影响。Redis 无法完成必要校验或 Rotation 时采用失败关闭策略，返回 HTTP 503。

Refresh Token 和 Session 有效但本地账号已停用时返回 HTTP 403，不执行 Rotation。

API 和 iOS 客户端当前使用 JSON Body 传输 Refresh Token，iOS 应保存到 Keychain。当前接口没有启用浏览器 Cookie Refresh；未来浏览器安全基线见 `architecture/client-refresh-contract.md` 和 ADR-0019。

客户端统一网络层在携带 Access Token 的受保护普通 API 因认证返回 401 后发起 Refresh。一个客户端同时只允许一个共享 Refresh 请求；成功后原子替换两个 Token，并只重试原请求一次。认证接口、403 和已经重试过的请求不触发 Refresh。

Refresh 返回 401 或 403 时客户端应清除本地 Token 并重新登录；返回 503 或发生网络故障时不得误判为登出。Refresh 自身不得再次触发 Refresh。

### Logout

```http
POST /auth/logout
Content-Type: application/json
```

请求：

```json
{
  "refresh_token": "signed-refresh-jwt"
}
```

当前 Refresh Token 与 Redis Session 匹配时，服务端使用 Redis Lua 原子比较用户与 Token Hash，并同时删除 Session Hash 和用户 Session 索引成员，返回 HTTP 204 且没有响应 Body。客户端随后删除本地 Access Token 与 Refresh Token。

Session 已经不存在时仍返回 HTTP 204，使重复 Logout 保持幂等。Refresh JWT 无效、已过期、用户与 Session 不一致或 Token Hash 不匹配时返回 HTTP 401；Hash 不匹配时不会删除当前 Session，避免旧 Token 使新 Session 状态被强制登出。Redis 无法完成必要校验或删除时返回 HTTP 503。

Logout 不查询 MySQL 账号状态，停用账号仍允许撤销自己的 Session。已经签发的 Access Token 默认不查询 Redis，因此会继续有效到自身 `exp`，Logout 只会让该 Session 的 Refresh 能力立即失效。

### Current User

```http
GET /users/me
Authorization: Bearer <access_token>
```

认证成功：HTTP 200

```json
{
  "id": 1,
  "email": "user@example.com",
  "nickname": "User",
  "avatar_url": null,
  "status": "active",
  "created_at": "2026-07-21T17:00:00",
  "updated_at": "2026-07-21T17:00:00"
}
```

响应使用 `UserResponse`，禁止出现 `password` 或 `password_hash`。

Bearer Header 缺失、格式错误、Token 签名无效、Token 过期、Claims 不完整、Token 类型错误或 Token 对应用户不存在：HTTP 401

```http
WWW-Authenticate: Bearer
```

```json
{
  "detail": "Invalid or missing access token."
}
```

Token 有效但用户状态不是 `active`：HTTP 403

```json
{
  "detail": "User account is inactive."
}
```

## Session Management

Session 管理接口属于敏感接口。除验证 Access Token 和加载 active User 外，还会使用 Token 中的 `sid` 确认当前 Redis Session 仍然存在且属于当前用户。

因此，当前 Session 已 Logout、过期或被撤销后，即使 Access Token 尚未到自身 `exp`，Session 管理接口也会返回 HTTP 401。普通 `/users/me` 仍保持 Access Token 自然过期边界。

### List Sessions

```http
GET /users/sessions
Authorization: Bearer <access_token>
```

成功：HTTP 200

```json
{
  "sessions": [
    {
      "id": "opaque-session-id",
      "current": true,
      "ip_address": "127.0.0.1",
      "user_agent": "Example Client",
      "created_at": "2026-07-31T10:00:00Z",
      "last_used_at": "2026-07-31T10:30:00Z",
      "expires_at": "2026-08-07T10:00:00Z"
    }
  ]
}
```

- `current` 由 Access Token 的 `sid` 与列表项 ID 比较得到。
- IP 和 User Agent 是可选展示信息，不作为设备身份证明或授权条件。
- 响应不返回 `user_id`、Refresh Token Hash 或绝对过期上限。
- 失效的 Sorted Set 索引成员在列表读取时懒清理，不返回客户端。

认证无效或当前 Redis Session 已失效：HTTP 401。账号停用：HTTP 403。Redis 不可用：HTTP 503。

### Revoke One Session

```http
DELETE /users/sessions/{session_id}
Authorization: Bearer <access_token>
```

撤销成功：HTTP 204，无响应 Body。

- 只能撤销当前用户拥有的 Session。
- 目标是当前 Session 时，客户端收到 204 后应清除本地 Access/Refresh Token。
- 目标是其他设备 Session 时，当前设备继续登录；目标设备的 Refresh 能力立即失效。
- 已签发的普通 Access Token 默认继续有效到自身 `exp`，但敏感 Session 管理接口会因二次校验立即返回 401。
- 目标不存在、已过期或属于其他用户时统一返回 HTTP 404，避免泄露其他用户 Session。

认证无效或当前 Redis Session 已失效：HTTP 401。账号停用：HTTP 403。Redis 不可用：HTTP 503。

### Revoke All Sessions

```http
DELETE /users/sessions
Authorization: Bearer <access_token>
```

撤销成功：HTTP 204，无响应 Body。

后端通过 Redis Lua 原子验证当前 Session，并撤销操作开始前已经存在的当前用户全部 Session。当前客户端收到 204 后必须清除本地 Token。Lua 执行完成后新创建的 Session 视为新的登录，不属于本次撤销集合。

认证无效或当前 Redis Session 已失效：HTTP 401。账号停用：HTTP 403。Redis 不可用：HTTP 503。

## File Resources

File Resource 是可查询、可授权和可删除的业务资源；真实 Bytes 保存在当前配置的 LocalStorage 或 MinIO，MySQL 保存 Metadata。客户端只使用稳定 `file_id`，不能提交或获取内部 Bucket、Object Key 或服务器路径。

所有 Files API 都要求：

```http
Authorization: Bearer <access_token>
```

当前权限模型为 Owner-only。详情、下载和删除统一查询：

```text
file_id 匹配
AND owner_id = current_user.id
AND status = ready
AND deleted_at IS NULL
```

资源不存在、属于其他用户或处于不可见状态时统一返回 HTTP 404。

### Upload File

```http
POST /files
Content-Type: multipart/form-data; boundary=<boundary>
Authorization: Bearer <access_token>
```

Multipart 只包含一个必需的 `upload` 文件 Part。`owner_id` 来自认证用户，客户端不能提交 File ID、Provider、Bucket、Object Key 或服务器路径。

上传成功：HTTP 201

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "original_filename": "report.pdf",
  "content_type": "application/pdf",
  "size_bytes": 1048576,
  "status": "ready",
  "created_at": "2026-08-04T10:00:00",
  "updated_at": "2026-08-04T10:00:00"
}
```

当前允许 PDF、PNG 和 JPEG，并同时检查文件名、扩展名、客户端 MIME、文件签名和实际流内大小。默认大小上限为 20 MiB，Chunk Size 为 1 MiB；最终值由 Settings 控制。

| 场景 | HTTP | 对外 detail |
| --- | ---: | --- |
| Multipart 缺少 `upload` | 422 | FastAPI validation error |
| 文件名非法或文件为空 | 400 | `Invalid upload metadata.` |
| Access Token 无效 | 401 | `Invalid or missing access token.` |
| 实际字节超过上限 | 413 | `Uploaded file is too large.` |
| 类型、扩展名或文件签名不支持 | 415 | `Unsupported file type.` |
| StorageProvider 不可用 | 503 | `File storage is temporarily unavailable.` |
| Metadata 提交或补偿内部失败 | 500 | `File upload failed.` |

只有对象写入和 Metadata 最终进入 `ready` 后才返回 HTTP 201。失败上传不会作为普通文件资源返回。

### List Files

```http
GET /files?limit=20&offset=0
Authorization: Bearer <access_token>
```

成功：HTTP 200

```json
{
  "items": [],
  "limit": 20,
  "offset": 0
}
```

- `limit` 默认 20，范围为 1 至 100。
- `offset` 默认 0，必须大于等于 0。
- 只返回当前用户 `ready` 且未删除的资源。
- 按 `created_at DESC, id DESC` 稳定排序。
- 分页参数非法返回 HTTP 422；认证无效返回 HTTP 401。

### Get File Metadata

```http
GET /files/{file_id}
Authorization: Bearer <access_token>
```

成功：HTTP 200，响应结构与 Upload 成功的 File Resource 相同。

响应不包含 `owner_id`、`storage_provider`、Bucket、Object Key、SHA-256、失败原因或删除时间。资源不存在、非所有者或不可见时返回 HTTP 404：

```json
{
  "detail": "File not found."
}
```

### Download File

```http
GET /files/{file_id}/download
Authorization: Bearer <access_token>
```

权限和状态验证通过后，FastAPI 从当前 StorageProvider 代理流式返回文件：

```http
Content-Type: <validated-content-type>
Content-Length: <size-bytes>
Content-Disposition: attachment; filename*=UTF-8''<encoded-filename>
```

响应按配置 Chunk 读取，不把完整文件一次载入内存，并在完成或异常后关闭本地文件流或 MinIO `StreamingBody`。

| 场景 | HTTP | 对外 detail |
| --- | ---: | --- |
| Access Token 无效 | 401 | `Invalid or missing access token.` |
| 资源不存在、非所有者或不可见 | 404 | `File not found.` |
| Metadata 存在但对象缺失 | 500 | `File content is unavailable.` |
| Provider 临时读取失败 | 503 | `File storage is temporarily unavailable.` |

当前 LocalStorage 和 MinIO 都使用后端代理流，尚未向客户端返回 Presigned URL。

### Delete File

```http
DELETE /files/{file_id}
Authorization: Bearer <access_token>
```

删除成功：HTTP 204，无响应 Body。

删除先将资源从 `ready` 变为 `deleting`，再删除对象，最后进入 `deleted` 并记录 `deleted_at`。Provider 删除失败或最终 Metadata 状态不确定时进入内部 `cleanup_required`，不重新对普通用户可见。

重复删除不会再次调用 Provider；资源已不可见时统一返回 HTTP 404。Provider 暂时不可用返回 HTTP 503，数据库状态提交或补偿失败返回安全 HTTP 500。

## AI Chat

### Non-stream Chat

```http
POST /ai/chat
Authorization: Bearer <access_token>
Content-Type: application/json
```

请求：

```json
{
  "messages": [
    {
      "content": "请用三个要点解释 AI Gateway 的作用。"
    }
  ],
  "model": "general",
  "temperature": 0.3,
  "max_output_tokens": 256
}
```

`messages` 至少一条，客户端只提交 `content`，不能提交 `role`、`user_id`、Provider、
真实 Provider Model、Base URL、API Key 或厂商特有字段。`model`、`temperature` 和
`max_output_tokens` 可以省略，使用服务端配置的默认值。显式输出上限超过模型策略时
直接拒绝，不静默截断。

成功：HTTP 200

```json
{
  "request_id": "服务端生成的 UUID",
  "model": "general",
  "content": "模型回答",
  "finish_reason": "stop",
  "usage": {
    "input_tokens": 24,
    "output_tokens": 80,
    "total_tokens": 104
  }
}
```

Provider 没有返回可信统计时，`usage` 为 `null`，不伪造为零。合法生成达到输出预算
上限时，`finish_reason` 为 `length`；自然结束时为 `stop`。响应不返回真实 Provider、
内部模型名称、原始厂商响应或 Secret。

AI 领域错误统一使用 `{code, detail}`：

| 场景 | HTTP | `code` |
| --- | ---: | --- |
| 模型别名不存在 | 400 | `ai_invalid_model` |
| 生成参数或 Context Window 非法 | 400 | `ai_invalid_request` |
| Provider Rate Limit | 429 | `ai_provider_rate_limit` |
| Provider Timeout | 504 | `ai_provider_timeout` |
| Provider 不可用 | 503 | `ai_provider_unavailable` |
| 未预期 AI 内部错误 | 500 | `ai_internal_error` |

请求 Schema 的结构校验失败仍由 FastAPI 返回 HTTP 422。Provider 原始错误、API Key、
请求正文和模型回答不会进入错误响应或普通日志。

### Streaming Chat

流式接口已在 Story 4.6 实现，复用非流式请求 Schema 和认证边界：

```http
POST /ai/chat/stream
```

它使用独立的 `text/event-stream` 响应，并遵循 `delta -> usage -> done` 或安全
`error` 终态。首 Event 预取阶段和流开始后的客户端断开都会取消上游 Provider 请求
并释放连接。

首 Event 之前发生的模型、限流、超时或不可用错误仍使用上表 JSON HTTP 状态；首
Event 预取成功后 HTTP 200 已确定，后续领域错误使用单个公共 SSE `error` Event，
且不会再发送 `done`。响应包含 `Cache-Control: no-cache` 与
`X-Accel-Buffering: no`，避免代理缓冲完整回答。

```text
event: delta
data: {"request_id":"...","content":"第一段"}

event: usage
data: {"request_id":"...","input_tokens":24,"output_tokens":80,"total_tokens":104}

event: done
data: {"request_id":"...","finish_reason":"stop"}
```

Provider 未返回可信 Usage 时对应 Token 字段为 `null`。客户端断开不会生成一个无法
送达的 `cancelled` Event；服务端让原生取消沿调用链传播，并关闭 Service、Gateway、
Provider 与 SDK Stream。

### 服务端 Usage 审计

非流式与流式请求结束后，服务端为认证用户记录一条 `success / failed / cancelled`
终态。记录包含项目 Request ID、模型路由、Prompt Key/Version、可信 Token、Latency、
流式 TTFT 和可选成本快照，但不属于公共 API 响应。

Provider 未返回完整 Token 时数据库保存 `NULL`，不伪造为零。模型配置同时提供价格、
币种和价格版本且输入/输出 Token 都已知时，服务端保存本次请求发生时的估算成本快照；
它不是 Provider 账单，也不会因为以后修改价格配置而重算。

Usage 与日志都不保存 Message、System Prompt、模型回答、API Key、Base URL、原始
Provider 请求响应、SSE Chunk 或原始异常正文。Usage 写入失败不会改变已经确定的公共
JSON/SSE 结果。
