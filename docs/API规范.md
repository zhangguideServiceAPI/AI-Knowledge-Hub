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
  "database": "ok"
}
```

必要依赖不可用：HTTP 503

```json
{
  "status": "not_ready",
  "database": "unavailable"
}
```

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
  "access_token": "signed-jwt",
  "token_type": "bearer",
  "expires_in": 1800
}
```

`expires_in` 的单位为秒。Access Token 默认有效期为 30 分钟，Payload 包含字符串形式的用户 ID、Token 类型、签发时间和过期时间。

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

请求字段校验失败：HTTP 422。登录密码允许历史账号使用至少 1 个字符的密码，但仍限制为最多 72 UTF-8 bytes。登录不会重新执行注册时的密码强度策略。

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
