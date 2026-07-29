# ADR-0019 Client Refresh Contract

## 状态

已接受（2026-07-29）

## 背景

后端已经提供登录 Token Pair、`POST /auth/refresh`、Refresh Token Rotation 和当前设备 Logout。Access Token 过期时，如果多个客户端请求分别使用同一个旧 Refresh Token，后端 Replay 防护可能把正常并发误判为旧 Token 重用并撤销当前设备 Session。

项目当前没有 iOS 或浏览器客户端源码，但必须先固定客户端恢复请求的协议边界，并明确当前 JSON Body 契约不等于已经支持浏览器 Cookie 安全。

## 决策

- 后端普通业务 API 不自动 Refresh；客户端统一网络层负责恢复请求。
- 只有携带 Access Token 的受保护普通 API 因认证返回 401 时才触发 Refresh；认证接口、403 和已经重试过的请求不触发。
- 同一客户端 Session 同时只运行一个共享 Refresh 操作，其他并发失败请求等待相同结果。
- Refresh 成功后客户端原子替换整个 Token Pair，再让每个原请求使用新 Access Token 重试一次。
- 原请求最多重试一次，`/auth/refresh` 自身不得递归 Refresh。
- Refresh 返回 401 或 403 时清除本地 Token 并重新登录；返回 503 或发生网络故障时不误判为登出。
- 当前 iOS 等原生客户端继续使用 JSON Body，iOS 使用 Keychain 保存 Refresh Token。
- 当前不启用浏览器 Cookie Refresh。未来浏览器基线使用 `HttpOnly`、`Secure`、`SameSite` Cookie，并同时实现受信任 Origin、CSRF、严格 CORS 和自动化测试。
- 具体客户端异步任务实现属于对应客户端工程，当前后端仓库不创建临时实现。

## 原因

- 客户端统一协调可以保持普通业务 API 的响应结构不变。
- 单航班 Refresh 可以避免同一个旧 Refresh Token 被正常并发请求重复提交。
- Token Pair 一起替换可以保证下一次 Refresh 使用后端当前允许的 Token 版本。
- 一次重试上限可以防止认证错误形成无限循环。
- 区分 401/403 与 503 可以避免依赖短暂故障导致用户被错误退出。
- Cookie 必须与 CSRF、CORS 和部署域名共同设计，不能只把 JSON 字段移动到 Cookie 就宣称安全。

## 影响

- 客户端工程必须提供共享 Refresh 操作和并发安全的 Token Store。
- 普通 API 的 401 保留为 Access 认证失败语义；业务拒绝优先使用对应 4xx 或 403。
- 当前后端无需为 Story 2.5 增加客户端代码或 Cookie 代码。
- 未来启用浏览器客户端会产生独立的后端实现、配置和测试工作。
- 网络中断可能导致客户端无法确定 Rotation 是否已经完成；客户端不得用并发自动重试放大该不确定性。

## 未采用方案

- 后端在普通业务 API 内静默 Refresh：职责不清晰，并会改变每个业务接口传递新 Token 的方式。
- 每个 401 都独立调用 Refresh：会触发 Rotation 竞态和 Replay 撤销。
- Refresh 失败后无限重试原请求：会形成请求循环并放大故障。
- Refresh 503 时直接清除 Token：会把 Redis 等依赖故障错误解释为用户退出。
- 当前直接启用浏览器 Cookie：缺少实际浏览器客户端、部署 Origin、CSRF 和 CORS 实现及测试。
