# ADR-0023: 使用资源生命周期和补偿处理 Metadata 与对象存储一致性

## 状态

已接受（2026-08-03）

## 背景

MySQL Transaction 无法回滚 LocalStorage 或 MinIO 的对象操作。一次上传或删除跨越两个独立系统，任一步骤失败都可能留下只存在于其中一侧的数据。

## 决策

- 上传在完成流内校验后创建 `PENDING_UPLOAD` Metadata。
- 对象写入成功且 Metadata 更新成功后，资源才进入 `READY`，并返回 HTTP 201。
- 对象写入失败且 Provider 能确认对象不存在，或补偿删除成功时，将资源标记为 `UPLOAD_FAILED`，并向客户端返回失败。
- 对象写入超时或报错但结果不确定时，Service 同样尝试删除对象；补偿失败或结果不确定时使用 `CLEANUP_REQUIRED`。
- 对象已写入但 Metadata 更新失败时，Service 尝试删除对象作为补偿；补偿失败或结果不确定时使用 `CLEANUP_REQUIRED`、安全日志和未来清理边界记录问题。
- 删除先将 `READY` 资源标记为 `DELETING`，随后删除对象；成功后设置 `DELETED` 与 `deleted_at`，失败时进入 `CLEANUP_REQUIRED`。
- 只有 `READY` 且未逻辑删除的资源可被普通用户列表、详情或下载。
- 当前不实现异步 Cleanup Worker 或自动上传重试；失败上传由客户端重新提交，生成新的 Resource ID 和 Object Key。

## 原因

- 状态机让客户端可见性和内部失败状态明确，避免对象存在却被错误展示为可下载。
- 补偿动作承认跨系统没有原子事务，比假装调用顺序天然安全更可靠。
- 逻辑删除保留失败清理和审计依据，避免 Object 删除失败后丢失定位信息。
- 先在 Service 确定业务状态，Provider 和 Repository 各自维持单一职责。

## 影响

- 需要为状态转换、Provider 异常、Repository 异常和补偿路径编写 Unit/API/Integration Test。
- 资源状态会增加查询过滤和运维排查成本，但使失败可观察、可恢复。
- `CLEANUP_REQUIRED` 需要未来后台 Worker 或人工运维流程处理；当前日志必须能定位该类事件。
- 用户看到的是明确上传或删除失败，不会自动复用不确定状态下的旧对象。

## 未采用方案

- 先写对象再写 Metadata：数据库写入失败会产生孤儿对象，仍需补偿且缺少已有资源状态。
- 不保存中间状态、只按调用顺序假设成功：无法安全处理超时、部分成功和重试。
- 删除时先物理删除 Metadata：对象删除失败后失去清理定位信息。
- 当前直接实现分布式事务或两阶段提交：LocalStorage、MinIO 和 MySQL 不提供适合本项目的共同事务协议，复杂度不成比例。
