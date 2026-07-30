# ADR-0017 Refresh Token Design

## 状态

已接受（2026-07-28）

## 背景

短期 Access Token 适合验证普通 API，但过期后需要一种不重复输入账号密码的续期机制。只签发一个长期 Refresh JWT 无法支持当前设备 Logout、服务端撤销、多设备 Session 或 Rotation 后旧 Token 失效。

项目已经使用 Redis 表示每台设备的独立 Session，因此需要确定 Refresh Token 的 Claims、传输方式、过期边界、客户端职责和 Redis 校验边界，再进入原子 Rotation 实现。

## 决策

- 普通 API 使用短期 Access Token，默认不查询 Redis；Refresh Token 只允许提交到 `/auth/refresh` 和当前设备 `/auth/logout`。
- 登录和 Refresh 成功后都返回新的 Access Token 与 Refresh Token，以及二者从响应时刻开始计算的剩余有效秒数。
- Refresh Token 使用 JWT，并包含 `sub`、`type=refresh`、`sid`、`jti`、`iat` 和 `exp`。
- 同一 Session 的 Rotation 保持 `sid` 不变，每次签发生成新的 `jti`、Refresh JWT 和 Token Hash。
- Redis 只保存完整 Refresh JWT 的 SHA-256 摘要，不保存原始 Token。
- Refresh 先验证 JWT，再验证 Redis Session 存在、Session 用户与 `sub` 一致、提交 Token 的 Hash 与当前 Hash 一致。
- Hash 比较与新 Hash 替换必须原子执行；具体 Redis 原子方案、并发行为和 Replay 处置由 ADR-0018 决定。
- 默认使用固定过期模式。Session、Redis TTL 和 Refresh Token `exp` 对齐到首次登录后第 7 天，Rotation 不延长最终期限。
- 目标实现中的 Access Token `exp` 不得晚于 Session 当前过期时间。
- Sliding 模式可以通过配置启用，但必须受 `absolute_expires_at` 限制；安全 Review 后仍决定默认使用固定过期模式。
- API 和 iOS 客户端当前通过 JSON Body 传输 Refresh Token，iOS 使用 Keychain 保存。
- 浏览器 HttpOnly Cookie、CSRF、CORS、`Secure` 和 `SameSite` 基线由 ADR-0019 定义；当前 JSON 契约仍未启用 Cookie 模式。
- 客户端统一网络层在 Access 认证返回 401 后发起 Refresh；同一客户端只运行一个 Refresh 请求，成功后同时替换两个 Token 并重试原请求一次。
- Refresh 或 Redis Session 验证失败返回 HTTP 401；Redis 无法完成必要校验或 Rotation 时失败关闭并返回 HTTP 503。
- Access 与 Refresh JWT Header 都包含 `kid`。新 Token 使用 Active Key 签发，验证时按 `kid` 从 Key Ring 选择密钥；具体轮换流程由 ADR-0020 约束。

## 原因

- 短期 Access Token 保持普通 API 简单且避免每次请求访问 Redis。
- Redis Session 为长期 Refresh 能力增加了服务端撤销、设备隔离和当前 Token 版本控制。
- `sid` 表示稳定的设备 Session，`jti` 表示某一次 Refresh Token，二者职责不同。
- 只保存 Token Hash 可以在 Redis 数据泄露时避免直接暴露可用的 Refresh Token。
- 固定的 Session 最终时间让用户明确知道最长登录周期，也避免每次 Refresh 无限续期。
- 由客户端协调 Refresh 可以保持业务 API 响应契约不变，并让客户端明确替换和持久化新 Token。
- 单航班 Refresh 可以避免同一客户端的并发请求互相把刚签发的 Token 判定为旧版本。

## 影响

- 登录接口已从只返回 Access Token 升级为返回 Token Pair，并创建初始 Redis Session。
- 客户端必须安全保存 Refresh Token，并在 Rotation 成功后原子替换本地 Token Pair。
- 固定过期模式下，`refresh_expires_in` 会随时间减少，不能在每次 Rotation 后固定返回 7 天。
- Logout 删除 Redis Session 后，Refresh 立即失败，但已经签发的 Access Token 仍等待自身过期。
- Logout 必须在一个 Redis Lua 脚本中原子校验 Session 用户和当前 Refresh Token Hash，再删除 Session Hash 与用户索引；旧 Token Hash 不匹配时不得删除当前 Session。
- Session 已不存在时 Logout 返回成功，保持重复请求幂等；Redis 故障时返回 503，不能假装撤销成功。
- Refresh Service/API 已完成，本文和 API 文档中的契约现已成为启用接口。
- 客户端恢复请求契约和未来浏览器安全基线由 ADR-0019 继续约束。
- Replay Attack 的 Session 撤销范围和并发误判策略已由 ADR-0018 明确；安全事件日志已在 Story 2.8 完成。

## 未采用方案

- 后端在普通业务 API 内部自动 Refresh：会改变各业务接口的响应和 Token 传递方式，职责不清晰。
- 客户端继续使用旧 Refresh Token：无法实现 Rotation，旧 Token 泄露后可以持续使用。
- 每次 Rotation 都生成新 Session ID：会把同一设备的一次连续登录拆成多个 Session，并留下旧索引状态。
- 每次 Rotation 都重新增加 7 天：形成无限 Sliding Session，不符合当前固定过期决策。
- 只验证 Refresh JWT，不验证 Redis：无法主动撤销、当前设备 Logout 或识别旧 Token。
- 在 Redis 中保存原始 Refresh Token：Redis 泄露后会直接暴露可使用的长期凭证。
- 当前直接采用浏览器 Cookie：没有同时完成 CSRF、CORS 和 Cookie 属性设计，安全边界不完整。
