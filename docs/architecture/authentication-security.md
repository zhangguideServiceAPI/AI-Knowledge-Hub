# Authentication Security

## 1. 目的

本文汇总 Sprint 2 已实现的认证安全控制、明确保留的风险和上线前仍需结合部署环境完成的工作。它是安全 Review 的入口，不替代各 ADR 和具体架构文档。

当前系统保护的主要资产包括：

- 用户账号和密码。
- Access Token 与 Refresh Token。
- Redis Authentication Session。
- JWT Signing Keys 和 Redis/MySQL 凭据。
- 用户登录来源等隐私数据。

## 2. 账号与密码

- 邮箱在查询和限流前去除首尾空格并转为小写。
- 密码使用 bcrypt Hash，数据库不保存明文密码。
- 未知邮箱也执行一次 Dummy Password Hash 验证，降低明显的时间差异。
- 未知邮箱和错误密码统一返回相同 401，避免账号枚举。
- 停用账号拒绝登录并返回 403。
- 注册、登录日志不记录邮箱、昵称、密码或密码 Hash。

## 3. 登录限流

- Redis 使用固定窗口原子占用尝试额度，默认 60 秒最多 5 次。
- 第 5 次错误仍返回 401；窗口内第 6 次请求在密码验证前返回 429。
- 成功登录清除当前邮箱标识的失败计数。
- Redis 无法确认额度时失败关闭并返回 503。

当前只按规范化邮箱维度限流。账号与可信客户端 IP 双维度限流保留为后续部署安全增强；启用前必须明确反向代理信任链，不能直接使用可伪造的 `X-Forwarded-For`。

## 4. Access Token

- Access Token 使用 HS256 签名，包含 `sub`、`sid`、`type=access`、`iat` 和 `exp`。
- 默认最长有效 30 分钟，并且不能超过 Session 最终到期时间。
- 验证固定允许算法，根据 Header `kid` 从 Key Ring 选择 Secret。
- 缺少、未知或格式非法的 `kid` 会被拒绝。
- 普通业务 API 默认只验证 JWT，不查询 Redis，因此 Logout 后已签发 Access Token 最迟仍可使用到自身 `exp`。
- 敏感 Session 管理接口会根据 `sid` 二次验证 Redis Session，Session 被撤销后立即返回 401。

## 5. Refresh Token 与 Replay

- Refresh Token 包含 `sub`、`sid`、`jti`、`type=refresh`、`iat` 和 `exp`。
- Redis 只保存完整 Refresh JWT 的 SHA-256 Hash，不保存原始 Token。
- 每次 Refresh 都 Rotation 整个 Token Pair，同一 Session 的 `sid` 不变，`jti` 和 Token Hash 变化。
- Lua 原子比较旧 Hash 并写入新状态，保证并发请求只有一个能使用当前 Refresh Token 成功。
- Hash 不匹配视为旧 Token 重用或 Replay，原子撤销当前设备 Session。
- 客户端必须使用单航班 Refresh，避免正常并发请求重复提交同一个旧 Token。

## 6. Session、Logout 与多设备撤销

- 每次登录生成独立、高熵 Session ID，多设备之间不互相覆盖。
- Logout 使用 Lua 原子校验当前用户和 Refresh Hash，避免旧 Token 删除 Rotation 后的新状态。
- 撤销指定 Session 时原子验证目标 `user_id`，不能越权删除其他用户 Session。
- 目标不存在和属于其他用户统一返回 404，不暴露 Session 所有权。
- 全部设备登出原子验证当前 Session，并删除当前用户操作开始前已有的 Session。
- Refresh 能力在 Session 删除后立即失效；普通 Access Token 的撤销边界保持为自身 `exp`。

## 7. 固定与 Sliding 过期

默认固定过期模式：

```text
Session expires_at = 首次登录 + 7 天
Refresh exp        = Session expires_at
Access exp         = min(当前时间 + 30 分钟, Session expires_at)
```

Sliding 模式可以通过配置启用，但必须受 `absolute_expires_at` 限制，当前默认不启用。这样可以避免活跃 Session 无限续期。

## 8. Secret Rotation

- `JWT_ACTIVE_KEY_ID` 指定新 Token 使用的 Active Key。
- `JWT_SIGNING_KEYS` 保存验证期间允许使用的 Key Ring。
- 正常轮换先投放新旧 Key，再切换 Active Key，最后等待旧 Token 最长生命周期和运维缓冲后移除旧 Key。
- 密钥泄露时立即从 Key Ring 删除泄露 Key，并滚动更新实例，使对应 Token 立即验证失败。
- 生产 Secret 通过 Secret Manager、Kubernetes Secret 或等价机制注入，不写入代码、镜像或提交的 `.env`。

## 9. 浏览器与客户端边界

- 当前 iOS 等原生客户端通过 JSON Body 提交 Refresh Token，并应使用 Keychain 保存。
- 当前后端没有启用浏览器 Cookie Refresh，不能宣称已经完成浏览器 Cookie 安全。
- 未来浏览器模式必须同时实现 HttpOnly、Secure、SameSite、可信 Origin、CSRF、严格 CORS 和自动化测试。
- Refresh 返回 401/403 时客户端清 Token 并重新登录；503 或网络失败不能直接解释为登出。

## 10. 日志与隐私

- 应用统一使用 Python logging，不使用 `print()`。
- INFO 记录成功状态变化，WARNING 记录预期安全拒绝，ERROR 记录基础设施故障。
- 日志禁止包含密码、邮箱、原始 Token、Token Hash、完整 Session ID、IP 和 User Agent。
- 普通无效 Access Token 不默认记录 WARNING/ERROR，避免攻击者制造日志洪泛。
- RedisError 由全局 Handler 统一记录 method、path 和异常类型，不记录异常消息。

## 11. HTTP 安全语义

| 状态 | 含义 |
| --- | --- |
| 401 | Token 或当前登录状态不能通过认证 |
| 403 | 用户账号状态不允许继续操作 |
| 404 | 目标 Session 不存在或不属于当前用户 |
| 429 | 登录尝试超过固定窗口限制 |
| 503 | Redis 等认证依赖暂时不可用，操作未被安全确认 |

## 12. 已验证内容

- 密码 Hash、通用登录错误和限流分支。
- Access/Refresh Claims、过期上限、`kid` 和 Key Ring。
- Refresh Rotation、Replay 撤销和并发竞争。
- 原子 Logout、单设备撤销和全部设备登出。
- 固定与 Sliding Session 过期计算。
- 401/403/404/429/503 HTTP 映射。
- 日志事件、级别和敏感字段排除。
- 普通测试 185 项、真实 Redis Integration Test 10 项。

## 13. 保留风险

- 普通 Access Token 当前没有独立黑名单，服务端主动撤销后最迟仍可使用到 `exp`。
- 登录限流还没有可信 IP 维度和分布式密码喷洒检测。
- 尚未实现 MFA、recent re-auth、受信任设备和主设备策略。
- 尚未实现浏览器 Cookie、CSRF 和生产 CORS 配置。
- Redis Cluster 的跨 Slot Lua Key 设计需要在迁移集群前重新评估。
- 结构化日志、Request ID、指标和集中式日志平台留到后续 Observability Sprint。

这些风险已经明确边界，不阻断当前 Sprint 2 的 Session & Identity 学习目标。

## 14. 相关文档

- ADR-0013：通用登录失败。
- ADR-0015：认证使用 Redis。
- ADR-0018：Rotation 与 Replay。
- ADR-0019：客户端 Refresh 契约。
- ADR-0020：JWT Signing Key Rotation。
- `authentication-flow.md`：完整认证流程。
- `client-refresh-contract.md`：客户端单航班状态机。
- `session-architecture.md`：Session 与多设备撤销。
