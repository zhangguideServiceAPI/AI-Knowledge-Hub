# ADR-0018 Token Rotation and Replay Handling

## 状态

已接受（2026-07-29）

## 背景

Refresh Token Rotation 要求旧 Token 在成功换取新 Token 后立即失效。如果后端先读取旧 Hash、再通过另一个 Redis 命令写入新 Hash，两个并发请求可能同时通过检查并分别获得新 Token。

Hash 不匹配还可能表示已经使用过的 Refresh Token 被再次提交。服务端无法判断当前请求来自仍持有旧 Token 的正常客户端，还是来自已经取得新 Token 的攻击者，因此必须确定 Replay 时的 Session 撤销范围。

## 决策

- 使用 Redis Lua 脚本在一次原子操作中比较旧 Refresh Token Hash 并写入新状态。
- 脚本使用 Session Hash 和用户 Session Sorted Set 两个 Key。
- Session 不存在或缺少当前 Refresh Token Hash 时返回 `SESSION_NOT_FOUND`，不创建新 Session。
- 当前 Hash 与客户端提交 Token 的 Hash 一致时，脚本更新 `refresh_token_hash`、`last_used_at`、`expires_at`、Redis TTL 和用户 Session Sorted Set Score，并返回 `SUCCESS`。
- 当前 Hash 与客户端提交 Token 的 Hash 不一致时，视为旧 Token 重用或 Replay。脚本原子删除当前 Session Hash，并从用户 Session Sorted Set 删除该 Session ID，然后返回 `TOKEN_MISMATCH`。
- Replay 只撤销当前 `sid` 对应的设备 Session，不撤销同一用户的其他设备 Session。
- Refresh Service 将 `SESSION_NOT_FOUND` 和 `TOKEN_MISMATCH` 都映射为 HTTP 401，不向客户端暴露内部判断细节。
- Replay 安全事件已在 Story 2.8 使用 WARNING 日志记录，但日志不得包含原始 Token 或 Token Hash。
- Redis 无法完成脚本时失败关闭，由 API 返回 HTTP 503，不绕过 Rotation。
- 客户端必须使用单航班 Refresh，避免同一设备并发使用同一个旧 Token 导致 Session 被安全撤销。
- 使用真实 Redis 验证 Lua 更新、旧 Token 重用撤销和并发请求只有一次成功；Mock 只验证 Python 调用与返回码映射。

## 原因

- Lua 脚本在 Redis 内连续完成检查与写入，消除了普通 `GET` 后再 `SET` 的并发窗口。
- Hash 不匹配时只拒绝当前请求并不充分：攻击者可能已经先使用旧 Token 获得新 Token，继续保留 Session 会让攻击者保持 Refresh 能力。
- 撤销整个当前 Session 可以同时使攻击者取得的新 Refresh Token 失效，是无法识别请求双方身份时更保守的安全策略。
- 只撤销当前 `sid` 可以控制影响范围，不会让用户的其他正常设备退出登录。
- 更新 Sorted Set Score 可以保持用户 Session 列表的最近使用顺序；撤销时同步 `ZREM` 避免留下索引成员。

## 影响

- 同一设备的两个并发 Refresh 请求可能出现第一个成功、第二个触发 Replay 撤销，导致第一个请求拿到的新 Refresh Token 也无法再次使用。
- 客户端单航班 Refresh 从性能优化升级为正确性要求，必须让并发失败请求等待同一个 Refresh 结果。
- Session 撤销后，已经签发的 Access Token 仍等待自身过期，因为普通 API 默认不查询 Redis。
- Lua 脚本同时访问两个 Redis Key。当前单实例 Redis 支持该方案；未来迁移 Redis Cluster 时，需要让相关 Key 使用同一 Hash Slot 或重新设计原子边界。
- 单元测试无法证明 Lua 和 Redis 原子性，必须保留真实 Redis 集成验证。

## 未采用方案

- Python 先读取再写入：存在两个请求同时通过旧 Hash 检查的竞态条件。
- Hash 不匹配时只返回 401 并保留 Session：无法阻止已经抢先完成 Rotation 的攻击者继续使用新 Token。
- Replay 时撤销用户全部设备：安全范围过大，会使无关设备退出登录。
- 使用分布式锁包围多个 Redis 命令：相比单个 Lua 脚本增加锁超时、释放和故障恢复复杂度。
- 把原始 Refresh Token 保存到 Redis：Redis 数据泄露后会直接暴露可使用的长期凭证。
