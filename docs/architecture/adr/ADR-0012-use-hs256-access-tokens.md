# ADR-0012 使用 HS256 签发 Access Token

## 状态

已接受（2026-07-22）

## 背景

邮箱和密码登录需要向已认证用户签发短期凭证，后续接口可以在不重复查询密码的情况下识别用户。Token 需要携带用户标识和有效期，并防止客户端篡改内容。

JWT 的 Header 和 Payload 只是 Base64URL 编码，不提供保密能力。认证系统必须验证签名和过期时间，不能信任未验证的 Payload。

## 决策

- 使用 `python-jose 3.5.0` 创建和验证 JWT。
- Access Token 使用 `HS256`，默认有效期为 30 分钟。
- Payload 包含 `sub`、`type=access`、`iat` 和 `exp`。
- JWT Header 包含公开的 `kid`，用于从服务端 Key Ring 选择验证密钥。
- `sub` 保存字符串形式的 User ID，不在 Token 中保存密码等敏感信息。
- 验证 Access Token 时要求 `sub`、`iat` 和 `exp` 必须存在，`type` 必须为 `access`，`sub` 必须能够转换为正数 User ID。
- `JWT_ACTIVE_KEY_ID` 和 `JWT_SIGNING_KEYS` 通过 Pydantic Settings 加载；每个 Secret 使用 `SecretStr` 并要求至少 32 个字符。
- 开发、测试和生产使用不同 Key Ring；同一环境的多实例共享一致的 Active Key ID 和 Key Ring。
- 仓库中的 `.env.example` 只保存占位值，真实 Secret 不提交 Git。

## 原因

- HS256 足以满足当前单体服务自行签发和验证 Token 的需求，结构简单且没有额外密钥基础设施。
- 短期 Access Token 可以限制凭证泄露后的有效时间。
- 明确 `type` 为后续区分 Access Token 和 Refresh Token 保留验证依据。
- 集中配置可以避免算法、有效期和 Secret 分散在业务代码中。

## 影响

- Login Service 成功验证邮箱和密码后调用 `create_access_token()`。
- 后续认证依赖必须使用 Token `kid` 对应的配置 Secret 和固定允许算法调用 `jwt.decode()`，并处理签名无效和 Token 过期。
- Current User 依赖通过验证后的 `sub` 查询用户；用户不存在时返回统一 401，用户非 active 时返回 403。
- 正常 Secret 轮换期间，旧密钥保留在 Key Ring 中，因此对应 `kid` 的未过期 Token 仍可验证；新 Token 只使用 Active Key 签发。
- 密钥泄露时可以从 Key Ring 立即删除旧密钥，使对应 Token 立即失效并要求客户端重新登录。
- Refresh Token、Redis Session、登出撤销和自动续期由 ADR-0016 至 ADR-0019 约束，JWT Secret Rotation 由 ADR-0020 约束。
- 测试使用专用假 Secret，不读取开发或生产 Secret。

## 未采用方案

- JWT 加密：当前 Token 不包含需要保密的数据，没有引入 JWE 的必要。
- RS256：当前只有一个后端负责签发和验证，非对称密钥管理会增加不必要的复杂度。
- 无过期时间的 Token：凭证泄露后无法自动失效，风险不可接受。
- 将 Secret 写入代码或 `.env.example`：会使所有获得仓库内容的人都能伪造 Token。
