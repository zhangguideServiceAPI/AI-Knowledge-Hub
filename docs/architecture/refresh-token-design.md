# Refresh Token Design

## 1. 目的

本文定义 AI-Knowledge-Hub 的 Access Token、Refresh Token 与 Redis Session 如何协作，以及客户端怎样在 Access Token 过期后恢复请求。

当前代码已经完成登录 Token Pair、Refresh JWT、Session 过期计算、Redis Lua 原子 Rotation、Replay 撤销和 Refresh Service/API。本文描述的是当前已启用的 `/auth/refresh` 契约；客户端自动刷新和并发请求协调仍由 Story 2.5 实现。

## 2. 整体位置

```text
登录
  -> 验证账号和密码
  -> 创建 Redis Session
  -> 返回 Access Token + Refresh Token

普通 API
  -> 只验证短期 Access Token
  -> 默认不查询 Redis

Refresh
  -> 验证 Refresh JWT
  -> 验证 Redis Session 和 Token Hash
  -> 原子 Rotation
  -> 返回新的 Access Token + Refresh Token

Logout
  -> 验证当前 Refresh Token 与 Redis Session
  -> 删除 Session Hash 和用户 Session 索引
  -> Refresh 立即失效
  -> 已签发的 Access Token 等待自身过期
```

## 3. 职责边界

| 凭证或状态 | 主要职责 | 服务端能否主动撤销 | 普通 API 是否使用 |
| --- | --- | --- | --- |
| Access Token | 在较短时间内证明当前用户身份 | 当前设计不能单独撤销 | 是 |
| Refresh Token | 在 Session 仍有效时换取新 Token | 通过 Redis Session 和 Rotation 控制 | 否 |
| Redis Session | 表示某台设备当前是否仍允许刷新 | 可以删除或使其过期 | 默认不使用 |

JWT 签名验证只能证明 Token 由本服务签发且 Claims 合法，不能证明它仍是当前 Session 允许使用的版本。Refresh 必须同时通过 JWT 验证和 Redis Session 验证。

## 4. Token Claims

### 4.1 Access Token

| Claim | 含义 |
| --- | --- |
| `sub` | 本地用户 ID |
| `type=access` | 防止 Refresh Token 被当作 Access Token 使用 |
| `iat` | 签发时间 |
| `exp` | 过期时间 |

Access Token 默认有效期为 30 分钟。目标实现需要把它的 `exp` 限制在 Session 最终过期时间以内。

### 4.2 Refresh Token

| Claim | 含义 |
| --- | --- |
| `sub` | 本地用户 ID |
| `type=refresh` | 防止 Access Token 被提交到 Refresh 接口 |
| `sid` | Redis Session ID；同一 Session 的 Rotation 期间保持不变 |
| `jti` | 当前 Refresh Token 的唯一 ID；每次 Rotation 都变化 |
| `iat` | 本次 Refresh Token 的签发时间 |
| `exp` | 当前 Session 的过期时间 |

Redis 不保存原始 Refresh Token，只保存完整 Refresh JWT 的 SHA-256 摘要。`jti` 让每次签发的 JWT 都具有独立身份，Hash 则用于判断客户端提交的 Token 是否仍是 Redis 中允许的当前版本。

## 5. 过期规则

### 5.1 固定过期模式

默认配置为固定过期模式：

```text
Session expires_at = 首次登录时间 + 7 天
Redis Session TTL  = expires_at - 当前时间
Refresh Token exp  = Session expires_at
Access Token exp   = min(当前时间 + 30 分钟, Session expires_at)
```

成功 Rotation 会创建新的 Access Token 和 Refresh Token，但不会把 Session 延长为“从本次 Refresh 再加 7 天”。响应中的 `refresh_expires_in` 是距离 Session 最终过期还剩的秒数，因此只有首次登录时通常接近 `604800`。

### 5.2 Sliding 模式

项目保留可配置的 Sliding 模式。成功 Rotation 后：

```text
expires_at = min(本次签发时间 + SESSION_TTL_DAYS, absolute_expires_at)
```

新 Refresh Token 的 `exp` 和 Redis TTL 必须使用同一个新 `expires_at`。`absolute_expires_at` 是不可突破的最终上限，避免活跃 Session 永不结束。默认仍使用固定过期模式，Sliding 模式在 Authentication Security Review 后再决定是否启用。

## 6. API 与客户端传输

### 6.1 请求

API 和 iOS 客户端通过 JSON Body 提交 Refresh Token：

```http
POST /auth/refresh
Content-Type: application/json
```

```json
{
  "refresh_token": "signed-refresh-jwt"
}
```

iOS 将 Refresh Token 保存到 Keychain。浏览器的 HttpOnly Cookie、`Secure`、`SameSite`、CSRF 和 CORS 策略在 Story 2.5 单独设计，当前接口不能直接宣称已经具备 Cookie 安全边界。

### 6.2 成功响应

登录和 Refresh 成功后都返回完整 Token Pair：

```json
{
  "access_token": "new-signed-access-jwt",
  "refresh_token": "new-signed-refresh-jwt",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_expires_in": 604800
}
```

`expires_in` 和 `refresh_expires_in` 的单位都是秒，并表示从响应时刻开始的剩余有效时间。接近 Session 最终过期时，两者都可能小于示例值。

## 7. Refresh 验证与 Rotation 边界

后端按以下顺序处理 Refresh：

```text
1. 验证 JWT 签名、type、sid、jti、iat 和 exp
2. 根据 sid 定位 Redis Session
3. 验证 Session 存在，并且 user_id 与 sub 一致
4. 计算客户端原始 Refresh Token 的 Hash
5. 原子比较 Redis 中的旧 Hash，并替换为新 Token Hash
6. 更新 last_used_at、过期字段和 TTL
7. 返回新的 Access Token 和 Refresh Token
```

第 5 步不能使用普通的“先 GET、再 SET”。并发 Refresh 时，比较与替换必须是一个原子操作，保证只有第一个请求成功。ADR-0018 决定使用 Redis Lua，并在发现旧 Token 重用时原子删除当前设备的 Session Hash 和用户 Session 索引成员。

Rotation 保持 `sid` 不变，生成新的 `jti`、Refresh JWT 和 Token Hash。这样同一设备仍属于同一个 Session，但旧 Refresh Token 已不再是当前版本。

## 8. 客户端恢复请求

客户端统一网络层负责 Refresh，业务接口本身不在后端内部静默刷新：

```text
普通 API 返回 Access 认证 401
  -> 客户端发起一次 POST /auth/refresh
  -> 其他同时失败的请求等待同一个 Refresh 结果
  -> 成功：同时替换 Access/Refresh Token，并重试原请求一次
  -> 失败：清除本地 Token，进入登录页
```

客户端必须避免多个请求同时各自 Rotation，也不能对 `/auth/refresh` 的 401 再次 Refresh，防止并发误判和无限重试。

## 9. 失败语义

| 场景 | 目标结果 |
| --- | --- |
| Refresh JWT 无效、过期或类型错误 | HTTP 401 |
| Redis Session 不存在或已撤销 | HTTP 401 |
| Token Hash 不匹配 | 原子撤销当前设备 Session，并返回 HTTP 401 |
| 本地账号已停用 | HTTP 403，不执行 Rotation |
| Redis 无法完成必要校验或 Rotation | HTTP 503，失败关闭 |
| Refresh 成功 | 返回新 Token Pair |

401 表示当前登录状态不能继续刷新，客户端必须重新登录；503 表示认证依赖暂时不可用，客户端不能把它误判为账号已退出。

## 10. Logout 契约

当前设备 Logout 通过 JSON Body 提交 Refresh Token。后端验证 JWT 后取得 `sub` 和 `sid`，读取 Redis Session，并确认 Session 用户和当前 `refresh_token_hash` 都与提交 Token 一致，然后使用 Repository 事务同时删除 Session Hash 和用户 Session 索引。

- 删除成功返回 HTTP 204，客户端删除本地 Token Pair。
- Session 已不存在时同样返回 HTTP 204，保证重复 Logout 幂等。
- JWT 无效、用户不一致或 Hash 不匹配时返回 HTTP 401；Hash 不匹配不能删除 Session，避免旧 Refresh Token 撤销 Rotation 后的当前状态。
- Redis 无法确认或删除 Session 时返回 HTTP 503，不能假装服务端撤销已经成功。
- Logout 不依赖 MySQL 账号状态；停用账号仍然可以撤销 Session。
- Logout 后 Access Token 等待自身过期，当前设计不为普通 API 增加 Redis 查询。

## 11. 后续边界

- ADR-0018：已确定使用 Lua 原子 Rotation，并在 Replay 时撤销当前设备 Session。
- Story 2.4：上述 Logout Service/API 与客户端删除 Token 契约已实现。
- Story 2.5：客户端单航班实现和浏览器 Cookie 安全策略。
- Story 2.6：Secret Rotation、Sliding Session 和完整安全 Review。
- Sprint 收尾：汇总注册、登录、Refresh 和 Logout 的端到端时序图。
