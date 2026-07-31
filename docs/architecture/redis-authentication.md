# Redis Authentication

## 1. 目的

本文汇总 Redis 在当前认证系统中的位置。具体 Session 字段、Refresh Rotation 和客户端行为分别由 `session-architecture.md`、`refresh-token-design.md` 和 `client-refresh-contract.md` 约束；ADR-0015 记录选择 Redis 的原因。

Redis 在这里不只是缓存。它保存的是具有 TTL、共享性和原子并发要求的短期认证状态。

## 2. MySQL 与 Redis 的边界

| 数据 | 存储 | 原因 |
| --- | --- | --- |
| 用户 ID、邮箱、密码 Hash、昵称、账号状态 | MySQL | 长期事实，需要事务和持久化关系模型 |
| 登录失败次数 | Redis String | 高频原子计数，固定窗口后自动过期 |
| 每台设备的登录 Session | Redis Hash | 需要 TTL、主动撤销和多实例共享 |
| 用户的多设备 Session 索引 | Redis Sorted Set | 需要按最后活动时间排序 |
| 原始 Access/Refresh Token | 不存储 | Token 由客户端持有，禁止写入日志或 Redis |
| Refresh Token Hash | Redis Session Hash | 用于 Rotation 和 Replay 比较，不暴露原始 Token |

MySQL 回答“这个用户是谁、账号是否有效”，Redis 回答“这次登录现在是否仍被允许”。

## 3. Key 与数据结构

```text
auth:login:failures:{identifier_hash}
  -> String
  -> 固定窗口登录失败次数

auth:session:{session_id}
  -> Hash
  -> user_id、refresh_token_hash、时间和可选设备展示信息

auth:user:{user_id}:sessions
  -> Sorted Set
  -> member 是 session_id
  -> score 是 last_used_at
```

登录失败 Key 使用规范化邮箱的 SHA-256 摘要，避免邮箱明文直接进入 Redis Key。Session ID 使用高熵随机值，每次登录独立生成，不能用 User ID 代替。

## 4. TTL 与持久化

- 登录失败次数使用秒级固定窗口 TTL，窗口结束后 Redis 自动删除。
- Session Hash TTL 与当前 `expires_at` 对齐。
- 默认固定过期模式下，首次登录 7 天后 Session 最终失效，Refresh 不延长最终时间。
- Sorted Set 本身没有为每个成员设置独立 TTL；Session Hash 到期后，列表读取会懒清理失效成员。
- 本地 Redis 启用 AOF 和 Named Volume，减少开发环境重启造成的状态丢失；认证正确性仍不能假设 Redis 永不故障。

## 5. 必须原子的操作

| 场景 | 原子边界 |
| --- | --- |
| 登录失败计数 | `INCR + EXPIRE NX` 在事务 Pipeline 中一次提交 |
| 创建 Session | `HSET + EXPIRE + ZADD` 在事务 Pipeline 中一次提交 |
| Refresh Rotation | Lua 比较旧 Hash，并写入新 Hash、时间、TTL 和索引 Score |
| Refresh Replay | Lua 原子删除当前 Session Hash 和索引成员 |
| 当前设备 Logout | Lua 原子比较用户和 Refresh Hash，再删除 Hash 与索引成员 |
| 撤销指定 Session | Lua 原子校验目标所有者，再删除 Hash 与索引成员 |
| 全部设备登出 | Lua 原子验证当前 Session，并删除当前用户已有的全部 Session |

需要“先判断、再修改”的安全操作不能拆成多个普通 Redis 命令，否则并发请求可能同时通过旧状态检查。

## 6. Redis 故障语义

认证安全相关 Redis 操作采用失败关闭策略：

- 登录限流无法确认时，不绕过限流继续签发 Token。
- Refresh、Logout 或 Session 撤销无法确认时，不假装操作成功。
- API 统一返回 HTTP 503：`Authentication service is temporarily unavailable.`
- 客户端不能把 503 当成 Session 已失效，也不能因此直接清除 Token。

Liveness 不访问 Redis；Readiness 会检查 Redis，帮助部署系统停止向尚未准备好的实例发送流量。

## 7. 安全与隐私边界

- Redis 不保存原始 Refresh Token，只保存 SHA-256 Hash。
- Session ID、Token、Token Hash、IP 和 User Agent 不进入认证事件日志。
- IP 和 User Agent 只用于展示，不作为设备身份证明或授权条件。
- 服务端只读取可信连接边界观察到的 IP，不直接信任任意客户端提供的 `X-Forwarded-For`。
- Redis 只绑定本机地址，使用密码认证；生产凭据应由 Secret Manager 或 Kubernetes Secret 注入。

## 8. 验证方式

测试分为两层：

- Mock 单元测试验证 Python 调用、参数、返回码映射和异常处理。
- 真实 Redis 集成测试验证 TTL、Pipeline、Lua、Replay、并发竞争、所有者校验和索引维护。

Sprint 2 完成时，普通测试 185 项、真实 Redis Integration Test 10 项通过。

## 9. 相关决策

- ADR-0015：为什么认证系统使用 Redis。
- ADR-0016：Redis Session Hash、Sorted Set 和 TTL。
- ADR-0017：Refresh Token 与 Session 的关系。
- ADR-0018：Rotation 和 Replay 的 Lua 原子语义。
- `session-architecture.md`：Session 数据结构和多设备管理。
- `authentication-flow.md`：端到端认证流程。
