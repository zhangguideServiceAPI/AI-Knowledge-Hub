# ADR-0014 使用全局业务异常处理器

## 状态

已接受（2026-07-23）

## 背景

注册、登录和当前用户接口最初在各自 Router 或 Dependency 中捕获业务异常，再手工转换为 `HTTPException`。随着相同的账号状态和认证失败规则被多个接口复用，局部转换会重复状态码、错误文案和 Header，并增加不同接口返回不一致的风险。

Service 和安全模块还需要能够脱离 FastAPI 被测试或复用，不应直接依赖 HTTP 状态码和响应对象。

## 决策

- 底层库异常在能够明确处理的边界转换为业务异常，例如 `IntegrityError -> EmailAlreadyRegisteredError`、`JWTError -> InvalidAccessTokenError`。
- Service、Repository 和安全模块只抛业务异常或明确的技术异常，不抛 `HTTPException`，不返回 `JSONResponse`。
- 在 `app/api/exception_handlers.py` 中集中注册业务异常到 HTTP 响应的映射。
- 全局 Handler 使用 `ErrorResponse` 构造统一的 `{"detail": "..."}` JSON，并按认证语义添加 `WWW-Authenticate: Bearer`。
- Router 和 Dependency 不重复捕获已注册的业务异常，让异常向上传播到全局 Handler。
- Router 装饰器继续保留 `responses={}`，因为全局 Handler 不会自动生成每个接口的 OpenAPI 错误声明。
- Pydantic 请求校验继续使用 FastAPI 默认 422 响应。
- 不捕获未知的 `Exception` 并伪装成业务错误，未预期错误保留 500 语义和服务端排查信息。

## 原因

- 业务异常与 HTTP 表达解耦后，Service 可以被 HTTP 之外的入口复用。
- 集中映射可以保证相同业务错误在不同接口中使用一致的状态码、文案和 Header。
- 保留框架标准 422 可以避免维护一套不必要的请求校验转换。
- 不吞掉未知异常可以防止程序错误被误报为用户输入问题。

## 影响

- 新增业务异常时，需要同时决定是否注册全局 Handler，并在相关 Router 的 OpenAPI `responses` 中声明。
- API 集成测试负责验证业务异常经过全局 Handler 后的最终状态码、JSON 和 Header。
- Exception Handler 返回的是最终 `JSONResponse`；Dependency 认证失败必须抛异常，不能返回响应对象作为依赖值。
- 当前没有真实 404 业务场景，未来资源详情接口出现后再增加对应业务异常和 Handler。

## 未采用方案

- 每个 Router 保留相同的 `try/except`：会重复 HTTP 映射并增加契约漂移。
- Service 直接抛 `HTTPException`：会让业务层依赖 FastAPI。
- 为所有业务异常创建一个携带 HTTP 状态码的基类：会把 HTTP 语义重新放回业务异常层，当前规模没有必要。
- 全局捕获 `Exception` 并统一返回 500 JSON：容易掩盖程序错误，日志和可观测性策略尚未进入当前 Story。
