# ADR-0020 JWT Signing Key Rotation

## 状态

已接受（2026-07-30）

## 背景

HS256 使用同一个 Secret 签发和验证 JWT。只配置单个 Secret 时，更换 Secret 会让所有尚未过期的 Access Token 和 Refresh Token 同时失效，也无法区分正常轮换与密钥泄露后的紧急撤销。

项目需要让新 Token 切换到新密钥，同时允许旧 Token 在有限时间内自然过期；密钥泄露时又必须能够立即拒绝旧密钥签发的 Token。

## 决策

- 继续使用 HS256，不在当前单体服务中提前引入非对称密钥基础设施。
- 使用 `JWT_ACTIVE_KEY_ID` 指定新 Token 的签名密钥，使用 `JWT_SIGNING_KEYS` 保存可用于验证的 Key Ring。
- Access Token 和 Refresh Token 的 JWT Header 都写入公开的 `kid`；`kid` 不是 Secret，也不提供任何权限。
- 新 Token 只使用 Active Key 签发。验证 Token 时先读取 Header `kid`，再从 Key Ring 选择 Secret；缺少或未知 `kid` 时统一拒绝。
- JWT 算法仍固定为配置允许的 `HS256`，不能根据 Token Header 提供的算法动态放宽验证算法。
- Key ID 只允许字母、数字、点、下划线和连字符，长度为 1 至 64；每个 Secret 至少 32 个字符，并通过 `SecretStr` 避免意外显示。
- 正常轮换按以下顺序执行：先让所有实例获得包含旧、新密钥的 Key Ring，再切换 Active Key，最后从最后一个仍可能签发旧 Token 的实例退出时开始等待最长 Token 生命周期和运维缓冲，之后删除旧密钥。
- 当前最长 Token 生命周期为 Refresh Token 的 7 天。Sliding Session 的最终登录周期可以达到 30 天，但 Active Key 切换后不会再签发旧密钥 Token，因此旧密钥保留时间仍按最后一次旧密钥签发 Token 的最长剩余生命周期计算。
- 密钥泄露时执行紧急轮换：立即从 Key Ring 删除泄露密钥并滚动更新实例。对应 Token 即使尚未到 `exp` 也会验证失败，客户端必须重新登录。
- 生产环境通过 Secret Manager、Kubernetes Secret 或等价机制注入两个环境变量，不把真实 Secret 写入镜像、代码仓库或提交的 `.env` 文件。
- 应用不自动按时间删除旧密钥。密钥投放、Active Key 切换、等待窗口和旧密钥移除属于可审计的运维发布流程。

## 原因

- `kid` 让验证端可以在多个候选 Secret 中确定性选择一个密钥，避免逐个尝试所有 Secret。
- Active Key 与验证 Key Ring 分离后，签发切换和旧 Token 兼容可以分阶段完成。
- 正常轮换避免无故强制所有设备退出，紧急轮换则优先终止泄露密钥带来的伪造能力。
- 固定验证算法可以避免攻击者利用 Header 影响服务端算法选择。
- 运维显式移除旧密钥比应用根据本机时间自动删除更容易协调多实例发布、回滚和审计。

## 影响

- 所有新签发的 Access Token 和 Refresh Token 都带有 `kid`；Story 2.6 之前没有 `kid` 的 Token 在部署后会被拒绝，需要重新登录。
- 正常轮换期间 Key Ring 同时保存至少两个 Secret，所有 FastAPI 实例必须获得一致配置。
- 使用旧密钥签发的 Refresh Token 可以在旧密钥仍保留时完成 Rotation；成功后返回的 Access Token 和 Refresh Token 都由当前 Active Key 签发。
- 紧急删除密钥会立即使对应 Access Token 和 Refresh Token 失效。Redis 中尚未自然过期的 Session 不会恢复这些 Token 的验证能力。
- HS256 的验证方同时拥有签发能力；未来拆分独立签发服务或向第三方公开验证能力时，需要重新评估 RS256 或 EdDSA。

## 未采用方案

- 直接覆盖单个 `JWT_SECRET_KEY`：实现简单，但正常轮换会让全部现有 Token 同时失效。
- 使用 `JWT_SECRET_KEY_V1`、`JWT_SECRET_KEY_V2` 等编号字段：每次增加密钥都需要修改配置模型和代码，不能表达通用 Key Ring。
- 验证时依次尝试所有 Secret：无法确定 Token 声明使用哪个密钥，验证成本随 Key 数量增长，也不利于审计未知 Key ID。
- 立即升级为非对称签名：当前仍是单体服务自行签发和验证，新增公私钥生命周期与发布复杂度没有带来足够收益。
