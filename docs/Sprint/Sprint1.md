# Sprint 1: 用户认证（Authentication）

## 状态

已完成（2026-07-23）。

```text
Final Story: Story 1.9 Authentication Review
Result: Passed
Overall: 97/100
```

## Sprint 目标

实现基于邮箱、密码和短期 Access Token 的认证闭环，为后续业务提供统一的用户身份基础。

| Method | Path | Success | Error responses |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | 201 | 409, 422 |
| `POST` | `/auth/login` | 200 | 401, 403, 422 |
| `GET` | `/users/me` | 200 | 401, 403 |

## 认证方案

- 使用邮箱和密码注册、登录。
- `email` 是唯一登录标识，不使用 `username`。
- `nickname` 是可选展示名称，不要求唯一。
- 数据库只保存 `password_hash`，不保存原始密码。
- Access Token 使用 JWT，有效期默认 30 分钟。
- 邮箱验证码发送、过期和限流不属于 Sprint 1，在后续 Story 中单独设计。

## Sprint 边界

Sprint 1 不提前引入 Redis。以下会话生命周期能力统一放入 Sprint 2：

- 7 天 Refresh Token。
- Redis Refresh Session 存储与撤销。
- Refresh Token 轮换和旧 Token 失效。
- 登出使当前 Refresh Session 失效。
- Access Token 自动续期协议。
- 登录、注册和 Refresh 接口的限流与防暴力破解。

## 学习范围

Sprint 1 综合覆盖 FastAPI Router、Service、Repository、SQLAlchemy、Alembic、Pydantic Schema、JWT、Password Hash、Dependency Injection、Config、Exception 和 Logging。

## Story 1.1: User Model

**状态：已完成（2026-07-17）**

### 目标

建立 User ORM Model，通过 Alembic Migration 在 MySQL 创建 `users` 表。

字段：

```text
id
email
password_hash
nickname
avatar_url
status
created_at
updated_at
```

### 需要理解

- ORM Model 与 API Schema 为什么必须分开。
- 数据库为什么保存 `password_hash`，而不是 `password`。
- `created_at` 和 `updated_at` 为什么统一生成。
- `status` 为什么使用可扩展字符串，而不是 bool。

### 验收标准

```text
alembic upgrade head
-> users 表创建成功
-> ORM 正常加载
-> 无 Schema 漂移和 Warning
```

### 完成结果

- User Model 使用 `email` 作为唯一登录标识，不保留 `username`。
- `nickname` 和 `avatar_url` 允许为空，默认头像由客户端处理。
- `status` 默认值为 `active`，为后续账号状态扩展保留空间。
- 第一份 Migration：`a0d1adf95f0b_create_users_table.py`。
- `upgrade -> inspect -> downgrade -> upgrade` 完整验证通过。
- MySQL 中的主键、email 唯一索引、可空性和默认值符合设计。
- `alembic check`：`No new upgrade operations detected.`
- ORM 查询正常，pytest：`3 passed`。

## Story 1.2: Repository

**状态：已完成（2026-07-20）**

### 目标

创建 `UserRepository`，实现：

```text
create()
get_by_id()
get_by_email()
```

Repository 只负责数据库访问，不包含业务、HTTP 或事务提交逻辑。

### 完成结果

- 创建 `app/db/repositories/user_repository.py`。
- Repository 通过构造函数接收 SQLAlchemy `Session`。
- `create()` 使用 `add -> flush -> refresh`，不调用 `commit()`。
- 事务由上层 Service 统一提交或回滚。
- 使用内存 SQLite 测试 Repository，不依赖本地 MySQL。
- 覆盖创建、主键查询、邮箱查询和 rollback。
- pytest：`5 passed`。

## Story 1.3: Password

**状态：已完成（2026-07-20）**

### 目标

使用 bcrypt 实现：

```text
hash_password()
verify_password()
```

### 完成结果

- 创建 `app/core/security.py`，集中管理密码安全能力。
- 使用 bcrypt 5.0 生成和验证密码哈希。
- 原始密码只在当前请求内使用，数据库只保存 `password_hash`。
- bcrypt hash 已包含算法版本、cost 和随机 salt，不单独保存 salt。
- 密码最大长度为 72 UTF-8 bytes，禁止截断超长密码。
- 注册哈希超限时抛出明确错误，登录验证超限时返回 `False`。
- 覆盖明文隔离、正确密码、错误密码、随机 salt 和长度边界。
- pytest：`10 passed`。

## Story 1.4: Register

**状态：已完成（2026-07-21）**

### 目标

实现：

```http
POST /auth/register
```

调用链：

```text
Request -> Schema -> Service -> Repository -> Database
```

### 完成结果

- 新增 `RegisterRequest`，校验邮箱格式、密码最小字符数和 bcrypt 72-byte 上限。
- 新增 `UserResponse`，支持 ORM 属性读取并排除所有密码字段。
- 新增 `AuthService.register()`，负责 email 规范化、密码哈希和注册事务。
- 重复邮箱预检查和数据库 UNIQUE 并发冲突统一转换为 `EmailAlreadyRegisteredError`。
- 注册成功返回 201，邮箱冲突返回 409，请求校验失败返回 422。
- API 测试使用 FastAPI dependency override 注入内存 SQLite Session。
- 移除 Sprint 0 遗留的 `/hello` 日志演示接口。
- OpenAPI 正确声明 201、409 和 422。
- pytest：`21 passed`。

## Story 1.5: JWT

**状态：已完成（2026-07-22）**

### 目标

理解 JWT、Access Token、Expire 和 Secret Key，实现 `create_access_token()`。

### 设计约定

- Access Token 使用 `HS256` 签名，有效期默认 30 分钟。
- Payload 包含 `sub`、`type`、`iat` 和 `exp`。
- Payload 不存放密码等敏感信息。
- 开发、测试和生产分别使用不同 Secret。
- 同一环境的多台服务实例共享该环境的 Secret。

### 学习记录

- `bytes.decode("utf-8")` 和 `str.encode("utf-8")` 只转换 Python 数据类型，不是密码的解密和加密。
- bcrypt 是单向哈希，无法还原原密码；算法版本、cost 和 salt 已包含在完整哈希字符串中。
- bcrypt 验证会使用完整哈希中的 salt 重新计算并比较，换机器后仍可验证。
- JWT 当前采用签名而非加密，Header 和 Payload 可以被读取，Secret 用于验证内容是否被篡改。
- JWT 可以在任意机器上读取；只有持有同一 Secret 的服务才能验证签名。
- Secret 更换后，旧 Secret 签发的 Token 将失效。
- 错误 Secret 调用 `jwt.decode()` 会抛出 `JWTError`，不会返回 Payload。
- 跳过签名验证虽可读取 Payload，但内容不可信，不能用于认证或授权。
- `python-jose 3.3.0` 在 Python 3.13 触发 `datetime.utcnow()` 弃用警告，项目升级到已使用时区感知 UTC 时间的 3.5.0。

### 完成结果

- 使用 Pydantic Settings 管理 JWT Secret、`HS256` 算法和 30 分钟有效期。
- Secret 使用 `SecretStr` 隐藏显示，并要求至少 32 个字符。
- 真实 Secret 只保存在不提交 Git 的 `.env` 中。
- 新增 `create_access_token()`，测试正确 Secret、错误 Secret、Claims 和有效期。
- 配置测试验证短于 32 个字符的 Secret 会被拒绝。
- pytest 使用固定测试 Secret，不依赖开发者本机 `.env`。
- Refresh Token、Redis 撤销、登出和自动续期推迟到 Sprint 2。

## Story 1.6: Login

**状态：已完成（2026-07-22）**

### 目标

实现：

```http
POST /auth/login
```

调用链：

```text
email -> UserRepository -> verify_password() -> create_access_token()
```

### 学习记录

- `TokenResponse` 和 API 文档共同定义返回 JSON 契约。
- API 测试固定客户端依赖的状态码、Header、字段类型和业务语义。
- 新增可选响应字段通常不影响局部断言；删除、改名、改变类型或语义属于契约变化。
- Python 中 `==` 比较值，`=` 才执行赋值。
- 邮箱不存在和密码错误统一抛出 `InvalidCredentialsError` 并返回 401，避免通过响应内容枚举账号。
- 邮箱不存在时仍对固定 dummy hash 执行一次 bcrypt，降低登录失败路径的响应时间差异。
- 时间侧信道测试验证调用行为，不断言不稳定的具体耗时。

### 完成结果

- 新增 `LoginRequest` 和 `TokenResponse`。
- 新增 `AuthService.login()`，完成邮箱规范化、密码验证、账号状态检查和 Access Token 签发。
- 成功返回 200，无效凭据返回统一 401，非 active 账号返回 403，请求校验失败返回 422。
- 401 响应包含 `WWW-Authenticate: Bearer`。
- OpenAPI 正确声明 200、401、403 和 422。
- Service 和 API 测试覆盖成功登录、未知邮箱、错误密码、非 active 账号、请求校验和 Token Claims。
- 登录只读取数据库，不创建写事务。
- pytest：`38 passed`。

## Story 1.7: Current User

**状态：已完成（2026-07-23）**

### 目标

实现：

```http
GET /users/me
Authorization: Bearer <access_token>
```

调用链：

```text
HTTPBearer + get_db
-> get_current_user dependency
-> AuthService
-> UserRepository
-> UserResponse
```

### 学习记录

- `jwt.encode()` 的 `algorithm` 选择一个签名算法。
- `jwt.decode()` 的 `algorithms` 声明验证端允许的算法集合，不能盲目信任 Token Header。
- `HTTPBearer` 实例是可调用对象；FastAPI 每次请求执行其 `__call__(request)`。
- `HTTPBearer.__call__()` 返回 `HTTPAuthorizationCredentials` 或 `None`。
- `Annotated[T, Depends(provider)]` 中 `T` 描述注入值类型，`Depends(provider)` 描述值的来源。
- `HTTPAuthorizationCredentials` 保存 `scheme` 和 Token 字符串，不验证 JWT。
- 嵌套依赖中的任一步抛出异常后 Router 不再执行；业务异常由全局 Handler 转换为 HTTP 响应。
- Apifox 用于手工验证真实调用流程，pytest 用于持续固定接口契约。

### 完成结果

- 新增 `decode_access_token()`，验证签名、过期时间、允许算法、必填 Claims、`type=access` 和正数用户 ID。
- `AuthService.get_current_user()` 查询 Token 对应用户，并拒绝不存在或非 active 用户。
- 新增 `HTTPBearer` 认证依赖，统一处理 Bearer Header、Session 注入、401 和 403 映射。
- 新增 `GET /users/me`，Router 只接收依赖注入后的 `UserResponse`。
- OpenAPI 自动声明 `HTTPBearer` Security Scheme 和 200、401、403 响应。
- 测试覆盖有效 Token、错误签名、过期、错误类型、缺失 Claims、无效用户 ID、缺失 Header、用户不存在和 disabled 用户。
- pytest：`54 passed`。

## Story 1.8: Exception

**状态：已完成（2026-07-23）**

### 学习安排

- 在各 Story 中结合实际场景学习 `try/except`、`raise`、`pytest.raises()`、异常链和 `__cause__`。
- Pydantic `ValidationError.errors()` 是字段校验错误集合，普通业务异常和 JWT 异常通常没有该列表。
- Story 1.8 系统整理底层异常、业务异常和 HTTP 异常的职责。

### 异常分层

```text
IntegrityError / JWTError / ValidationError
-> Business Error
-> Global Exception Handler
-> HTTP Response
```

### 学习记录

- `raise HTTPException` 中断 Router 或 Dependency，由 FastAPI 内置 Handler 转换成 HTTP 响应。
- Exception Handler 捕获已注册的业务异常后 `return JSONResponse`，直接构造最终响应。
- Dependency 返回 `JSONResponse` 可能被当成普通注入值，认证失败应抛出异常。
- `app.add_exception_handler()` 显式建立业务异常类型与 Handler 的映射。
- Router 装饰器的 `responses={}` 只声明 OpenAPI 契约，不捕获异常、不执行 Handler。
- HTTP 401 使用 `WWW-Authenticate: Bearer`；HTTP 403 和 409 不需要认证挑战 Header。
- Service 成功时返回 Schema/DTO，明确业务失败时抛业务异常，未知程序错误不应被笼统捕获。
- Router 直接返回 `JSONResponse` 会绕过 `response_model` 的正常序列化和字段过滤，应谨慎使用。

### 完成结果

- 保留底层异常、业务异常和 HTTP 响应三层边界，Service 和 Core 不依赖 FastAPI。
- 新增全局 Exception Handler，集中映射四类认证业务异常。
- Router 和 Dependency 删除重复的局部业务异常转换。
- Router 保留 OpenAPI `responses` 声明。
- Pydantic 请求校验继续由 FastAPI 返回标准 422。
- 不增加笼统的 `except Exception` 或全局 500 Handler。
- 当前没有真实 404 场景，不提前创建未使用异常。
- API 集成测试验证全局 Handler 保持 401、403、409、JSON 和认证 Header 契约。
- pytest：`54 passed`。

## Story 1.9: Authentication Review

**状态：已完成（2026-07-23）**

### 完成结果

- 完成 User Model、Repository、密码哈希、注册、Access Token、登录、当前用户和异常处理的整体 Review。
- `pyproject.toml` 是 uv 依赖声明的单一来源，删除已漂移且未使用的 `requirements.txt`。
- Ruff 移入 dev dependency group。
- 使用 `UserStatus` 和 `ACCESS_TOKEN_TYPE` 消除认证核心中的业务魔法字符串。
- Ruff formatter 统一后端、测试和 Alembic 文件格式。
- pytest：`54 passed`，并将 `DeprecationWarning` 视为错误验证。
- Ruff lint、format check、`uv pip check` 和 `uv lock --check` 全部通过。
- MySQL 8.4 healthy，Alembic 位于 `a0d1adf95f0b (head)`，无 Schema 漂移。
- OpenAPI 包含三个认证接口的成功与错误响应，并为 `/users/me` 声明 `HTTPBearer`。
- 真实 JWT Secret 仅保存在 Git 忽略的 `.env`，仓库只保留占位模板。

### 最终 Review

```text
Architecture       ★★★★★
Dependency         ★★★★★
Naming             ★★★★★
Maintainability    ★★★★★
Performance        ★★★★☆
Security           ★★★★☆
Testing            ★★★★★
Documentation      ★★★★★

Overall            97/100
```

Review 通过，无阻断问题。

### 剩余非阻断风险

- `AuthService.register()` 当前将 User 写入阶段的 `IntegrityError` 解释为邮箱冲突；未来增加其他数据库约束时必须收窄判断。
- API 测试使用 SQLite，Migration 和 Schema 漂移使用真实 MySQL 验证；尚未增加 MySQL API 集成测试。
- 登录限流、防暴力破解、Refresh Token、登出撤销和 Token 轮换放入 Sprint 2。
- 邮箱验证码发送、TTL、限流和防刷仍需单独设计。

## 学习重点

| Knowledge | Target mastery |
| --- | --- |
| SQLAlchemy Model | 5/5 |
| Pydantic Schema | 5/5 |
| Alembic Migration | 4/5 |
| Repository Pattern | 5/5 |
| Password Hash | 5/5 |
| JWT | 5/5 |
| FastAPI Dependency | 4/5 |
| Config 管理 | 4/5 |
| Exception Handler | 4/5 |

## 协作方式

Sprint 1 遵守 `docs/AI协作规范.md`：理解、开发者实现关键学习代码、AI 辅助和机械整理、测试验证、Review、总结。每个 Story 均通过 `docs/CodeReview规范.md` 验收后进入下一项。
