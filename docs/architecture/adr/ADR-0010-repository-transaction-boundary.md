# ADR-0010 Repository 只负责数据访问，Service 负责事务

## 状态

已接受（2026-07-20）

## 背景

User 的数据库操作需要集中管理，避免 Router 或 Service 中分散编写 SQLAlchemy 查询。同时，用户注册未来可能需要在同一个事务中写入用户、邮箱验证记录和审计记录。

如果 Repository 内部直接调用 `commit()`，上层 Service 无法把多个数据库操作组合成一个原子事务。后续操作失败时，已经提交的 User 记录也无法回滚。

## 决策

- Repository 放在 `app/db/repositories/`。
- Repository 通过构造函数接收 SQLAlchemy `Session`。
- Repository 只负责查询和持久化，不处理业务规则、HTTP 异常或 Schema。
- `create()` 使用 `add()`、`flush()` 和必要的 `refresh()`，不调用 `commit()`。
- Service 负责事务边界，在完整业务流程成功后调用 `commit()`，失败时调用 `rollback()`。
- Repository 不强制为每个 ORM Model 创建一个类，只有存在明确数据访问职责时才创建。

## 原因

- `flush()` 可以执行 SQL 并获取自增主键、数据库默认值，同时保留回滚能力。
- Service 可以组合多个 Repository 操作，保证注册等业务流程的原子性。
- 通过注入 Session，Repository 可以使用生产数据库、测试数据库或事务测试 Session。

## 影响

- Repository 方法返回 ORM 对象或 `None`，不直接返回 HTTP 响应。
- “记录不存在”由 Repository 返回 `None`，由 Service 决定是 404、401 还是注册可继续。
- Repository 测试可以使用内存 SQLite，不依赖本地 MySQL 服务。

## 未采用方案

- Repository 内部 `commit()`：会破坏上层事务的原子性。
- Service 直接编写 SQL：会造成查询逻辑分散并违反分层规则。
- 所有 Model 机械创建 Repository：没有独立数据访问职责时只会增加空壳代码。
