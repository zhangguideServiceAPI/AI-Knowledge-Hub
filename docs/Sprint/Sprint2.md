# Sprint 2: Session & Identity Management（会话与身份管理）

## 状态

进行中（2026-07-23）。

```text
Current Story: Story 2.1 Redis Foundation
Current Goal: Understand why authentication uses Redis
Current Step: Distinguish process memory, Redis, and database storage
```

## Sprint 目标

Sprint 2 的目标不是单独学习 Redis，也不是只实现 Refresh Token，而是构建企业级 Session（会话）管理体系，为未来 AI Platform 打下认证基础。

1. 能解释 Cookie、Session、JWT、Refresh Token、Redis Session、OAuth2/OIDC 各自解决什么问题。
2. 能设计 Access/Refresh Token 的签发、轮换、撤销、过期和重放防护。
3. 能正确使用 Redis 的 TTL、原子操作和数据结构支撑认证，而不把 Redis 只当缓存。
4. 能设计多设备会话、浏览器安全、Secret 轮换及 Redis 故障策略。
5. 能用 Fake/Stub 和真实 Redis 分层测试，并建立安全事件日志。

## 学习推进方式

Sprint 2 内容较多，按学习依赖逐步推进，不要求一次理解全部内容。

每次只学习当前 Story 中的一个小步骤：

```text
理解概念
  -> 完成小练习
  -> 开发者实现关键代码
  -> AI Review
  -> 测试验证
  -> 记录总结
```

如果当前概念没有理解，暂停编码和后续 Story，先通过项目中的真实场景继续讲解和练习。

建议学习顺序：

```text
Story 2.0 Authentication Evolution
  -> Story 2.1 Redis Foundation
  -> Authentication Security 基础概念预习
  -> Story 2.2 Session Architecture Design
  -> Story 2.3 Refresh Token Rotation
  -> Story 2.4 Logout
  -> Story 2.5 Client Refresh Contract
  -> Story 2.6 Authentication Security Review
  -> Story 2.7 Testing
  -> Story 2.8 Observability
  -> Story 2.9 User Session Design
  -> Sprint Review
```

Security 基础概念在架构设计前预习，是为了让 Replay Attack、Token Hash 和过期策略进入设计；完整安全验收仍在 Story 2.6 完成。

### 当前学习检查点

- Story 2.0 Authentication Evolution：已完成（2026-07-24）。
- 已完成（2026-07-24）：区分 Cookie、认证 Session、SQLAlchemy Session 和 JWT。
- 已完成（2026-07-24）：理解多设备 Session 需要使用独立 Session ID，不能只用 User ID 作为唯一 Key。
- 已完成（2026-07-24）：理解 JWT 验证和 Redis Session 验证的职责不同，Session 不存在时认证失败。
- 已完成（2026-07-24）：理解有状态与无状态认证，以及无状态 Access Token 不能被单独立即撤销。
- 已完成（2026-07-24）：理解 Access Token、Refresh Token 和 Redis Session 的不同职责。
- 已完成（2026-07-24）：理解无服务端 Session 的 Refresh Token 在 Logout、撤销、Rotation 和多设备管理上的限制。
- 已完成（2026-07-24）：理解 OAuth2 解决授权问题，OIDC 在 OAuth2 之上解决身份认证问题，当前项目暂不需要立即引入。
- 已完成（2026-07-24）：理解 Authorization Code、Token Exchange、第三方身份到本地用户的映射，以及本地 Session 创建流程。
- 已完成（2026-07-24）：完成 `docs/architecture/authentication-evolution.md` 初稿。
- 已完成（2026-07-24）：文档 Review 通过，确认当前项目选择 JWT + Redis Session 的原因和边界。
- 当前 Story：2.1 Redis Foundation。
- 当前 Step：区分进程内存、Redis 和数据库存储。
- 完成标志：能够说明三种存储的生命周期、共享范围和适用场景。

## North Star

构建企业级 Session & Identity Management，而不是单纯增加 Redis。

完成后应具备：

- 企业级认证体系认知。
- Refresh Token 生命周期管理能力。
- 正确使用 Redis 支撑认证系统的能力。
- 多设备登录扩展能力。
- 安全设计意识。
- 自动化测试基础。
- 可观测性基础。

## 能力演进

```text
Authentication（认证）
        ↓
Authorization（授权）
        ↓
Session（会话）
        ↓
Token Lifecycle（Token 生命周期）
        ↓
Security（安全）
        ↓
Scalability（可扩展）
```

## Story 2.0: Authentication Evolution

**状态：已完成（2026-07-24）**

### 学习目标

理解认证体系的发展过程：

```text
Cookie Session
      ↓
JWT
      ↓
JWT + Refresh Token
      ↓
JWT + Redis Session
      ↓
OIDC / OAuth2
```

### 输出

- `docs/architecture/authentication-evolution.md`

### 完成结果

- 理解 Cookie、认证 Session、SQLAlchemy Session 和 JWT 的职责边界。
- 理解 Access Token、Refresh Token 和 Redis Session 的生命周期及撤销边界。
- 理解有状态与无状态认证、多设备 Session 和 Refresh Token Rotation 的演进原因。
- 区分 OAuth2 授权与 OIDC 身份认证，理解 Authorization Code 和本地用户映射流程。
- 完成并 Review `docs/architecture/authentication-evolution.md`。
- Documentation Review：通过，无阻断问题，综合评分 96/100。

## Story 2.1: Redis Foundation

**状态：进行中（2026-07-24）**

### 技术实现

- Docker Compose 增加固定版本的 Redis。
- 使用 Pydantic Settings 管理 Redis 配置。
- Readiness 检查 Redis。
- 配置 Redis 操作超时。
- 管理 TTL。
- 设计登录限流。

### 学习重点

理解 Redis 不只是缓存，还可以承担以下职责：

- Memory Store。
- TTL。
- Atomic Operation。
- Distributed Cache。
- Distributed Lock。
- Queue。

学习以下数据结构：

- String。
- Hash。
- Set。
- Sorted Set。

### 输出

- ADR-0015：为什么认证系统选择 Redis。

## Story 2.2: Session Architecture Design

**状态：未开始**

先设计，再编码。

### 时序设计

- 登录时序图。
- Refresh 时序图。
- Logout 时序图。

### 设计内容

- Redis Key。
- Session 生命周期。
- Token Rotation。
- 多设备登录。
- Secret Rotation。

### 输出

- Architecture Diagram。
- Sequence Diagram。
- ADR-0016：Session Architecture。
- ADR-0017：Refresh Token Design。

## Story 2.3: Refresh Token Rotation

**状态：未开始**

### 接口

```http
POST /auth/refresh
```

### 要求

- Access Token 有效期为 30 分钟。
- Refresh Token 有效期为 7 天。
- JWT 包含 `jti`。
- JWT 包含 `type=refresh`。
- Redis 保存 Session 或 Token 标识。
- Rotation 后旧 Token 立即失效。

### 测试范围

- Token 过期。
- Token 类型错误。
- Session 不存在。
- Replay Attack。

### 输出

- ADR-0018：Token Rotation。

## Story 2.4: Logout

**状态：未开始**

### 接口

```http
POST /auth/logout
```

### 实现范围

- 当前设备登出。
- 删除当前 Refresh Session。
- Access Token 自然过期。

### 预留范围

- Logout All Devices。

## Story 2.5: Client Refresh Contract

**状态：未开始**

### 客户端约定

客户端负责刷新 Token：

```text
API
 ↓
401
 ↓
Refresh
 ↓
Retry
```

### 要求

- 同一客户端只允许一个 Refresh 请求。
- 不实现静默刷新。
- 定义浏览器安全策略。

## Story 2.6: Authentication Security

**状态：未开始**

### 学习内容

- Replay Attack。
- Sliding Session。
- Absolute Expiration。
- Token Rotation。
- Refresh Token Hash。
- Secret Rotation。

### 需要理解

- 为什么 Redis 不保存原始 Refresh Token。

## Story 2.7: Testing

**状态：未开始**

### 测试体系

- pytest。
- JWT Test。
- 使用 Fake 或 Stub 完成 Redis 边界的单元测试。
- 使用真实 Redis 完成 TTL、原子轮换和重放场景的集成测试。
- API Test。

### 最低覆盖范围

- Login。
- Refresh。
- Logout。
- Replay。

## Story 2.8: Observability

**状态：未开始**

### INFO 日志

- Login Success。
- Refresh Success。
- Logout。

### WARNING 日志

- Replay Attack。
- Invalid Refresh Token。

### ERROR 日志

- Redis 不可用。
- Session 持久化或轮换失败。

普通无效 Access Token 属于预期认证失败，不默认记录为 ERROR，避免攻击者制造日志洪泛。

本 Story 为 Sprint 9 的 Prometheus 和 Grafana 可观测性建设铺路。

## Story 2.9: User Session Design

**状态：仅设计，暂不实现接口**

### 设计接口

```http
GET /users/sessions
```

### 设计内容

- 当前设备。
- 登录时间。
- IP。
- User Agent。
- 最后活动时间。

### 预留范围

- 单设备踢下线。
- 全部设备登出。

## 文档输出

- `docs/architecture/authentication-evolution.md`
- `docs/architecture/session-architecture.md`
- `docs/architecture/refresh-token-design.md`
- `docs/architecture/redis-authentication.md`
- `docs/architecture/authentication-security.md`
- Sprint 过程和验收结果继续记录在当前 `docs/Sprint/Sprint2.md`。

## ADR 规划

- ADR-0015：为什么认证使用 Redis。
- ADR-0016：Session Architecture。
- ADR-0017：Refresh Token Design。
- ADR-0018：Token Rotation。

## 验收标准

### 功能

- Redis 接入完成。
- Refresh Token Rotation 完成。
- Logout 完成。
- Session 生命周期正确。
- 多设备设计完成。

### 工程

- Architecture Review 完成。
- Code Review 完成。
- 文档同步完成。
- ADR 完成。
- 测试通过。
- 日志规范完成。

综合评分达到 **90 分及以上**，才进入 Sprint 3。

## 长期路线

- Sprint 1：Authentication。
- Sprint 2：Session & Identity。
- Sprint 3：Storage。
- Sprint 4：AI Gateway。
- Sprint 5：RAG。
- Sprint 6：Workflow。
- Sprint 7：Agent Runtime。
- Sprint 8：MCP。
- Sprint 9：Observability。
- Sprint 10：Async Platform。
- Sprint 11：Cloud Native。
