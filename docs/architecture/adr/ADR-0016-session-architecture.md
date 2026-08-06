# ADR-0016 Redis Session Architecture

## 状态

已接受（2026-07-28）

## 背景

短期 Access Token 可以让普通 API 无状态验证身份，但不能表示某台设备当前是否仍被允许刷新，也不能独立支持当前设备登出、多设备列表和服务端撤销。

项目需要在 Redis 中表达一次独立登录，并让同一用户的多台设备互不覆盖。Session 必须自动过期，不能保存原始 Refresh Token；Session Hash 到期时还需要处理用户索引中的残留成员。

## 决策

- 每次登录使用独立且不可猜测的 Session ID，不使用 User ID 作为唯一 Session Key。
- 使用 Redis Hash `auth:session:{session_id}` 保存 `user_id`、`refresh_token_hash`、`created_at`、`last_used_at`、`expires_at` 和 `absolute_expires_at`。
- `expires_at` 表示当前过期时间，`absolute_expires_at` 表示不可突破的最终上限。固定过期模式下二者相同。
- Session Hash 的 TTL 与当前 `expires_at` 一致。默认固定过期模式不因读取或最后活动时间变化自动延长 TTL。
- Redis 只保存高熵 Refresh Token 的 SHA-256 摘要，不保存原始 Refresh Token。
- 使用 Sorted Set `auth:user:{user_id}:sessions` 保存用户的 Session ID，以 `last_used_at` 为 Score，支持按最近使用时间倒序读取。
- 创建 Session 使用事务 Pipeline 一次提交 `HSET`、`EXPIRE` 和 `ZADD`。
- 当前设备撤销使用事务 Pipeline 一次提交 `DEL` Session Hash 和 `ZREM` 用户索引成员。
- 用户 Session 列表先用 `ZREVRANGE` 读取有序 ID，再用非事务 Pipeline 批量 `HGETALL`。没有对应 Hash 的 ID 视为失效成员并用 `ZREM` 懒清理。
- Repository 将不存在的 Session 从 Redis 空字典 `{}` 转换为 `None`，不向上层暴露 Redis 的缺失值细节。
- Redis Session 校验或必要写入失败时采用失败关闭策略，不绕过服务端 Session 状态。
- 默认数据模型支持多设备。未来单设备或设备数量限制通过登录策略撤销旧 Session，不改变 Key 结构。

## 原因

- 独立 Session ID 可以精确表示和撤销某台设备的一次登录。
- Hash 适合保存一个 Session 的多个字段，TTL 可以自动终止 Refresh 能力。
- Sorted Set 同时提供成员集合和最近使用顺序，普通 Set 无法满足有序 Session 列表。
- 事务 Pipeline 避免创建或删除时出现只更新一部分 Redis 结构的状态。
- Sorted Set 不支持成员级 TTL；读取时懒清理可以在不引入后台扫描任务的情况下修复自然过期留下的索引。
- 批量读取 Pipeline 避免为每个 Session 单独进行一次网络往返。

## 影响

- Session Hash 是 Refresh 登录状态的权威来源；只有索引成员而没有 Hash 时，Session 仍视为不存在。
- Logout 可以立即阻止 Refresh，但已经签发的 Access Token 继续自然过期。
- 用户索引允许短暂包含已经过期的 Session ID；读取列表会清理它们，显式 Logout 则立即清理。
- Session Repository 依赖 redis-py 使用 `decode_responses=True`，Hash 字段读取为字符串并在边界转换为整数。
- Sliding 模式若在后续启用，只能把 `expires_at` 延长到 `absolute_expires_at`，同时更新 Refresh Token `exp` 和 Redis TTL。
- `last_used_at` 的更新、Refresh Token 原子轮换、Replay Attack 和 Secret Rotation 由后续 Story 决定并测试。
- IP、User Agent 和当前设备展示字段在 Story 2.9 设计，不提前加入当前最小 Session Record。

## 未采用方案

- 只按 User ID 保存一个 Session：后登录设备会覆盖先登录设备，无法支持当前设备登出和多设备管理。
- 使用普通 Set 保存用户 Session：可以保存成员，但不能按最后活动时间排序。
- 只保存 Refresh JWT 且不保存 Redis Session：无法主动撤销、管理设备或让旧 Token 在 Rotation 后立即失效。
- 在 Redis 保存原始 Refresh Token：Redis 数据泄露后攻击者可以直接使用 Token，因此只保存摘要。
- 给用户索引统一设置与某个 Session 相同的 TTL：不同 Session 的创建和过期时间不同，一个 Key TTL 不能表达成员级生命周期。
- 当前引入后台定时扫描任务：可以主动清理索引，但会增加调度和全量扫描复杂度，当前规模采用读取时懒清理。
