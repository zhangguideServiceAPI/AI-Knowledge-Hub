# Authentication Evolution

## 1. 目的

本文记录 AI-Knowledge-Hub 从短期 Access Token 演进到 JWT + Redis Session 的原因，并明确 Cookie、Session、JWT、Refresh Token、OAuth2 和 OIDC 的职责边界。

Sprint 2 的目标不是单独增加 Redis，而是让服务端能够管理登录会话、Refresh Token 生命周期、多设备登录和主动撤销。

## 2. 核心概念

### Cookie

Cookie 是浏览器保存和发送数据的机制。服务端可以通过 `Set-Cookie` 要求浏览器保存 Cookie，浏览器根据 Domain、Path、Secure、HttpOnly 和 SameSite 等属性决定何时携带它。

Cookie 是客户端的传输和存储机制，不是服务端 Session，也不是 Redis。Cookie 中既可以保存随机 Session ID，也可以保存 JWT。

### Authentication Session

Authentication Session 表示某个用户在某台设备上的一次登录状态，例如：

```text
auth:session:abc -> user_id=42, device=iPhone
auth:session:def -> user_id=42, device=Mac
```

每台设备使用独立 Session ID，服务端才能实现当前设备登出和多设备管理。Session ID 应是随机且不可猜测的值，不能只使用 User ID 作为唯一 Session Key。

Authentication Session 与 SQLAlchemy `Session` 不同。后者负责 ORM 对象和数据库事务，不表示用户登录状态。

### JWT

JWT 是一种带签名的 Token 格式。签名用于验证 Token 是否由可信服务签发、内容是否被篡改；JWT Payload 默认可以被读取，不提供加密能力。

当前项目的 Access Token 包含 `sub`、`sid`、`type`、`iat` 和 `exp`。其中 `sub` 表示本地 User ID，`sid` 表示签发 Token 的当前 Redis Session；普通业务 API 默认只使用用户身份，敏感 Session 管理接口会使用 `sid` 二次验证登录状态。

## 3. 认证方案演进

### 3.1 Cookie Session

```text
用户登录
-> 服务端创建 Session
-> Cookie 保存随机 Session ID
-> 后续请求携带 Session ID
-> 服务端查询 Session 并得到 User ID
```

服务端保存每次登录的状态，因此这是有状态认证。删除 Session 后，凭证可以立即失效；但所有服务实例必须能够访问同一份 Session 数据，否则需要粘性会话或其他同步方案。

### 3.2 JWT Access Token

```text
用户登录
-> 服务端签发短期 JWT
-> 客户端通过 Authorization: Bearer 携带 JWT
-> 服务端验证签名、Claims 和过期时间
```

服务端不需要保存每个 Access Token 的记录，因此 Token 生命周期是无状态的，便于多个服务实例共同验证。

缺点是 Token 签发后难以单独撤销。当前项目的 Access Token 有效期为 30 分钟，Logout 后已经签发的 Access Token 仍然自然过期。

### 3.3 JWT + Refresh Token

短期 Access Token 过期后，如果没有其他凭证，用户必须重新输入邮箱和密码。Refresh Token 允许客户端在较长时间内换取新的 Access Token：

```text
Access Token 过期
-> 客户端调用 POST /auth/refresh
-> 服务端验证 Refresh Token
-> 签发新的 Access Token
```

Refresh Token 只用于刷新，不能直接调用普通业务接口。

如果服务端只验证 Refresh JWT 的签名和 `exp`，却不保存服务端 Session，Logout 无法主动撤销已经泄露的 Refresh Token，旧 Token 也无法在 Rotation 后立即失效。

### 3.4 JWT + Redis Session

Sprint 2 的目标方案为短期 Access Token 加受 Redis Session 控制的 Refresh Token：

```text
Access Token
-> 有效期 30 分钟
-> 用于普通 API
-> 默认不在每次请求中查询 Redis

Refresh Token
-> 有效期 7 天
-> 包含 type=refresh 和 jti
-> 只用于 POST /auth/refresh
-> 必须同时通过 JWT 和 Redis Session 验证
```

Refresh 的两层验证分别回答不同问题：

```text
JWT 验证
-> Token 是否由服务端签发、是否被篡改、是否到期？

Redis Session 验证
-> 服务端现在是否仍允许这次登录继续？
```

Logout 删除 Redis Session 后，Refresh JWT 即使尚未到达 `exp` 也会立即无法刷新。已经签发的 Access Token 仍然使用到自身过期时间。

Redis Session 还为以下能力提供基础：

- Refresh Token Rotation 和旧 Token 失效。
- 当前设备登出。
- 多设备 Session 管理。
- Session TTL。
- Replay Attack 检测。

Redis Key、Token Hash、用户 Session 索引和生命周期由 `session-architecture.md` 与 ADR-0016 固化；原子 Rotation、Replay 撤销和客户端恢复契约也已经在 Refresh Token 文档、ADR-0017 至 ADR-0019 及对应测试中实现。

### 3.5 OAuth2 / OIDC

OAuth2 主要解决授权问题，即第三方应用可以代表用户访问哪些资源。OIDC 建立在 OAuth2 之上，增加标准身份认证能力，用于确认当前用户是谁。

典型 Authorization Code 流程为：

```text
客户端打开身份提供方授权页面
-> 用户完成认证或授权
-> 身份提供方返回一次性 Code
-> 后端使用 Code 交换 Token
-> 后端验证外部身份
-> 查找、关联或创建本地 User
-> 创建本项目 Session 并签发本项目 Token
```

外部身份提供方的 Token 与本项目 Token 不能混用。当前项目使用自己的邮箱、密码和用户表，暂不引入 OIDC；未来增加企业 SSO 或第三方登录时再设计外部身份映射。

## 4. 方案对比

| 方案 | 服务端会话状态 | 主动撤销 | 多设备管理 | 主要用途 |
| --- | --- | --- | --- | --- |
| Cookie Session | 保存完整 Session | 容易 | 容易 | 传统 Web 登录 |
| JWT Access Token | 不保存单个 Token 状态 | 困难，通常等待过期 | 缺少会话视角 | 短期 API 访问 |
| JWT + Refresh Token | 取决于是否保存 Refresh 状态 | 无状态时困难 | 无状态时困难 | 减少重复登录 |
| JWT + Redis Session | 保存 Refresh Session | 可以撤销 Refresh | 支持独立设备 Session | 当前项目实现 |
| OAuth2 / OIDC | 由具体系统决定 | 由协议和本地会话共同决定 | 由本地系统设计 | 第三方授权、SSO 和身份联合 |

## 5. 当前项目结论

AI-Knowledge-Hub 当前使用 HS256 短期 Access Token、Refresh Token 和 Redis Session。

该方案的边界为：

- Access Token 负责普通 API 的短期访问认证。
- Refresh Token 负责在无需重新输入密码的情况下换取新 Access Token。
- Redis Session 负责控制 Refresh Token 是否仍然有效，并支持 Rotation、Logout 和多设备扩展。
- Logout 后客户端删除本地 Token，服务端删除当前 Refresh Session；已签发的 Access Token 自然过期。
- OIDC / OAuth2 不属于当前实现范围，未来出现第三方登录、企业 SSO 或外部资源授权需求时再引入。

这种设计在 Access Token 的扩展能力与 Refresh Token 的服务端可控性之间取得平衡，并为后续 Session Architecture Design 提供基础。
