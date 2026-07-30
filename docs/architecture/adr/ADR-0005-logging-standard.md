# ADR-0005 Logging

## 状态

已接受（2026-07-15），认证事件边界更新于 2026-07-30。

## 背景

应用需要同时记录正常业务事件、安全拒绝和基础设施故障，但日志本身不能成为密码、Token、Session 或用户隐私的泄露渠道。认证接口还可能受到大量无效请求，若把每个普通 401 都记录为 WARNING 或 ERROR，攻击者可以制造日志洪泛并掩盖真正异常。

## 决策

- 统一使用 Python `logging` 和项目 logger `ai_knowledge_hub`，不使用 `print()` 记录应用日志。
- INFO 记录已经完成的业务事件，包括注册成功、登录成功、Refresh Rotation 成功和 Logout 成功。
- WARNING 记录需要安全关注但应用仍按预期工作的事件，包括登录限流、Refresh Replay 和已验证 Refresh Token 对应的 Session 拒绝。
- ERROR 记录 Redis 等必要基础设施故障。RedisError 在全局 HTTP 异常处理边界统一记录 method、path 和异常类型，避免各 Service 重复记录同一次故障。
- Service 负责记录它能够确认最终业务结果的事件；Router 不记录业务日志，Repository 不决定认证事件级别。
- 只在身份已经由签名 Token 或数据库结果确认后记录 `user_id`。固定 `reason` 和 `result` 只能来自服务端枚举或分支，不能直接使用客户端输入。
- 禁止记录密码、邮箱、昵称、原始 Access Token、原始 Refresh Token、Refresh Token Hash、完整 Session ID、JWT Secret、Redis 密码、请求 Body 或未经筛选的异常消息。
- 普通无效或缺失 Access Token 返回 401，但不默认记录 WARNING 或 ERROR。重复注册和普通请求校验失败也不记录账号标识；未来通过限流、指标和 Request ID 观察滥用行为。
- 当前日志输出到进程标准流，不由 FastAPI 自行管理日志文件。日志采集、持久化、检索、保留策略、结构化格式和请求关联 ID 留到 Sprint 9 Observability 统一设计。

## 原因

- 统一事件名称和字段便于后续接入 ELK、Loki、Grafana 等日志平台。
- 把业务结果放在 Service，可以避免 Router 和 Repository 对同一事件重复记录或产生语义漂移。
- 数据最小化可以降低日志平台、备份和运维查询对认证凭证与个人信息的暴露风险。
- 不记录普通无效 Access Token 可以控制噪声和存储成本，让 WARNING 与 ERROR 保持可操作性。
- 标准流适合 Docker 和 Kubernetes，由外部平台负责采集与轮转，避免多实例各自维护易丢失的本地文件。

## 影响

- 日志消费者使用固定事件名识别认证事件，不解析自然语言错误消息。
- 认证失败调查当前主要依赖事件计数和固定原因，不提供邮箱或完整 Session ID 关联。
- Redis 故障日志可以定位 HTTP 路径和异常类型，但不会直接包含底层连接错误文本。
- Sprint 9 需要继续设计 JSON 结构化日志、Request ID、指标、集中式存储、脱敏查询权限和保留周期。

## 未采用方案

- 在应用内写入滚动日志文件：容器文件生命周期短，多实例日志分散，并增加磁盘容量和轮转责任。
- 记录邮箱或普通 SHA-256 邮箱摘要：邮箱属于个人信息，普通摘要仍可被常见邮箱字典枚举；未来确有跨请求关联需求时再评估独立 Secret 的 HMAC。
- 对所有认证 401 记录 WARNING：容易被攻击流量制造日志洪泛，且大多数 401 属于协议内的预期拒绝。
- 直接记录 `str(error)` 或完整异常堆栈：异常文本可能暴露内部地址、配置或客户端数据；当前 Redis 边界只记录异常类型。
