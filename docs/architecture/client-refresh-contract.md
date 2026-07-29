# Client Refresh Contract

## 1. 目标与边界

本文定义客户端在 Access Token 失效后如何使用已经启用的 `POST /auth/refresh` 恢复普通业务请求。

当前仓库不包含 iOS 或浏览器客户端，因此 Story 2.5 不实现具体客户端网络层。本文只固定前后端必须共同遵守的状态机、失败语义和浏览器安全边界，客户端工程按此契约实现。

后端不会在普通业务 API 内部自动 Refresh。客户端统一网络层负责调用 Refresh API、替换 Token Pair 和重试原请求。

## 2. 触发条件

只有同时满足以下条件时，客户端才进入 Refresh 流程：

- 请求是携带 Access Token 的受保护普通 API。
- API 因 Access 认证失败返回 HTTP 401。
- 请求不是 `/auth/login`、`/auth/refresh` 或 `/auth/logout`。
- 当前原请求尚未因为 Refresh 重试过。

HTTP 403 表示账号状态或权限拒绝，不触发 Refresh。业务接口应保留 HTTP 401 表达认证失败，避免把普通业务校验错误混入 Refresh 触发条件。

## 3. 单航班状态机

同一客户端 Session 在同一时刻只能存在一个 Refresh 操作：

```text
普通请求 A、B、C 同时收到 Access 401
  -> 第一个请求创建共享 Refresh 操作
  -> 其他请求等待同一个 Refresh 结果
  -> 客户端只发送一次 POST /auth/refresh
  -> 成功后先原子替换本地 Access/Refresh Token
  -> A、B、C 分别使用新 Access Token 重试一次
  -> Refresh 操作结束后清理共享任务
```

每个原请求最多重试一次。`/auth/refresh` 自身以及已经重试过的请求不得再次触发 Refresh，防止递归刷新和无限重试。

单航班不仅是性能优化，也是正确性要求。多个并发 Refresh 如果重复提交同一个旧 Refresh Token，后端 Replay 防护会撤销当前设备 Session。

## 4. Refresh 结果处理

| Refresh 结果 | 客户端行为 |
| --- | --- |
| HTTP 200 | 原子保存新的 Access/Refresh Token Pair，再唤醒等待请求并各自重试一次 |
| HTTP 401 | 当前登录状态不能继续刷新；清除本地 Token 并进入登录页 |
| HTTP 403 | 账号已不可用；清除本地 Token 并进入登录页 |
| HTTP 503 | 认证依赖暂时不可用；不误判为登出，不清除 Token，当前请求向上返回暂时失败 |
| 网络超时或连接失败 | 结果未知；不并发重复提交旧 Refresh Token，不直接清除登录状态 |

客户端必须同时替换 Access Token 和 Refresh Token。只保存新的 Access Token 会让下一次 Refresh 继续提交已经失效的旧 Refresh Token。

## 5. iOS 契约

当前 API 面向 iOS 等原生客户端使用 JSON Body 传输 Refresh Token：

```json
{
  "refresh_token": "signed-refresh-jwt"
}
```

iOS 使用 Keychain 保存 Refresh Token。具体的共享异步任务、Token Store 和请求重试实现属于 iOS 客户端工程，不在当前后端仓库重复实现。

## 6. 浏览器安全边界

当前后端没有启用浏览器 Cookie Refresh，现有 JSON Body 契约不能被描述为已经具备浏览器 Cookie 安全能力。

未来引入浏览器客户端时采用以下基线：

- Refresh Token 保存到 `HttpOnly`、`Secure`、`SameSite=Lax` 且 `Path=/auth` 的 Cookie，JavaScript 不直接读取。
- Access Token 保存在页面内存中，并继续通过 `Authorization: Bearer` 发送。
- Cookie 模式的 Refresh 与 Logout 必须验证受信任 `Origin` 和 CSRF Token。
- CORS 只允许明确配置的前端 Origin，并启用凭据；禁止将允许 Origin 配置为 `*`。
- 如果未来必须跨站部署，Cookie 使用 `SameSite=None; Secure`，同时保留 CSRF 防护。

启用浏览器模式前，必须另行实现 Cookie 写入/删除、CSRF、CORS 配置和对应自动化测试。该浏览器基线不改变当前 JSON Body API。

## 7. 后端保证

- 普通业务 API 不在内部自动调用 Refresh。
- Refresh 成功返回完整的新 Token Pair。
- Refresh JWT、Redis Session 或 Token Hash 无效时返回 401。
- 账号已停用时返回 403，不执行 Rotation。
- Redis 无法完成必要校验或 Rotation 时返回 503。
- Rotation 保持 `sid` 不变，不延长固定的 Session 最终过期时间。

## 8. 验收标准

- 客户端实现者能够仅根据本文区分哪些响应触发 Refresh。
- 并发 Access 401 最终只产生一个 Refresh 请求。
- Refresh 成功后 Token Pair 一起替换，原请求最多重试一次。
- Refresh 401/403 与 503 具有不同的客户端终态。
- 当前 iOS JSON 契约与未来浏览器 Cookie 契约的边界明确。
