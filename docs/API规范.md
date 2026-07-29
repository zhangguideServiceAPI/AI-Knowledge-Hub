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
  "redis": "ok"
}
```

必要依赖不可用：HTTP 503

```json
{
  "status": "not_ready",
  "database": "ok",
  "redis": "unavailable"
}
```

`database` 和 `redis` 分别报告依赖状态。任一必要依赖不可用时，整体 `status` 为 `not_ready` 并返回 HTTP 503；Liveness 不访问这些依赖。

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

Access Token Payload 包含字符串形式的用户 ID、Token 类型、签发时间和过期时间。

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

同一登录标识在固定窗口内失败 5 次后，后续请求在密码验证前返回 HTTP 429。第 5 次错误本身仍返回 HTTP 401：

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

API 和 iOS 客户端当前使用 JSON Body 传输 Refresh Token，iOS 应保存到 Keychain。浏览器 HttpOnly Cookie、CSRF 和 CORS 契约延后到 Story 2.5。

客户端统一网络层在普通 API 因 Access 认证返回 401 后发起 Refresh。一个客户端同时只允许一个 Refresh 请求；成功后同时替换两个 Token，并只重试原请求一次。Refresh 自身返回 401 时不得再次 Refresh，客户端应清除 Token 并重新登录。

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

当前 Refresh Token 与 Redis Session 匹配时，服务端同时删除 Session Hash 和用户 Session 索引成员，返回 HTTP 204 且没有响应 Body。客户端随后删除本地 Access Token 与 Refresh Token。

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
