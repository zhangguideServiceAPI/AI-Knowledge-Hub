# Code Review 规范

## 1. Review 目标

每个 Story 完成后，按照本规范 Review 当前 Story 的全部修改。

发现违反规范的问题时，必须先修复并重新验证。没有阻断问题且综合评分达到 90 分以上，才能结束 Review 并进入下一个 Story。

## 2. Review 流程

1. 确认本次 Review 的 Story、变更范围和验收标准。
2. 阅读全部变更，检查架构、行为、安全性、测试和文档。
3. 按严重程度列出问题，并提供文件位置、原因和修改建议。
4. 修复问题后重新运行相关测试和检查。
5. 输出分类评分、综合评分和仍然存在的非阻断风险。

综合评分达到 90 分不能掩盖阻断问题。只要仍存在架构越层、安全漏洞、核心行为错误或缺少必要测试，就不能通过 Review。

## 3. Review 规则

### Rule 1: Architecture

遵守项目目录和分层边界。

```text
Router -> Service
```

允许。

```text
Router -> Repository
```

禁止。Router 不得绕过 Service 直接访问 Repository。

### Rule 2: Dependency

模块之间不得出现循环依赖。依赖方向必须与项目分层一致。

### Rule 3: Naming

命名必须清晰、统一并表达职责。

```text
user_service.py  -> 正确
UserService.py   -> 错误
service.py       -> 错误，含义不明确
```

Python 文件使用 `snake_case`，类使用 `PascalCase`，函数和变量使用 `snake_case`。

### Rule 4: SQLAlchemy

事务边界必须统一，禁止在大量位置分散调用 `session.commit()`。

Model 只描述数据库结构，Repository 负责数据库访问，Service 负责业务流程和事务协调。

### Rule 5: Logging

禁止使用 `print()` 记录应用日志。必须使用项目统一的 Logger，并根据事件语义选择 `debug`、`info`、`warning`、`error` 或 `critical`。

### Rule 6: Exception

禁止使用裸捕获：

```python
except:
```

应捕获能够明确处理的异常类型，例如 `SQLAlchemyError`。除系统边界外，应避免使用范围过大的 `except Exception` 掩盖代码错误。

### Rule 7: Magic Number

禁止直接使用含义不明确的数字或字符串。

```python
86400
```

应定义为具有业务含义的配置或常量，例如：

```python
JWT_EXPIRE_SECONDS
```

### Rule 8: Config

禁止在各模块中分散调用 `os.getenv()`。所有应用配置必须统一通过 Pydantic Settings 获取，形成单一配置来源。

### Rule 9: FastAPI Router

Router 只负责 HTTP 协议相关工作，包括参数接收、依赖注入、调用 Service、设置状态码和返回 Schema。

禁止在路由函数中堆积业务逻辑、SQL 或大段数据处理代码。

### Rule 10: Service

Service 不直接向 Router 返回 ORM 对象，应返回 DTO、Schema 或明确的业务结果。

Service 不写 SQL，负责业务规则、流程编排和事务边界。

### Rule 11: Repository

Repository 只负责数据库访问，不包含业务规则、HTTP 逻辑或响应 Schema 组装。

### Rule 12: Documentation

新增或修改 API 时，必须同步更新对应的 `docs` 文档。涉及架构决策、Sprint 状态或运行方式的变化，也必须更新对应 ADR、Sprint 或 README。

### Rule 13: Test

新增或修改业务行为时，必须补充相应测试。测试必须验证行为和响应契约，不能因为依赖真实外部服务而产生假通过。

### Rule 14: Docker

Docker 镜像必须使用明确版本，禁止使用 `latest`。

### Rule 15: Compose

Compose 文件中不得硬编码真实密码。敏感配置通过环境变量提供，仓库只提交不含真实凭据的 `.env.example`。

### Rule 16: Commit

一个 Commit 对应一个清晰功能或修复，避免把无关改动混入同一个 Commit。

### Rule 17: TODO

TODO 必须有明确处理计划，不得无说明地跨越当前 Sprint。无法在当前 Sprint 完成的事项应记录为技术债或后续 Story。

### Rule 18: AI Review Output

AI 完成 Review 后必须输出分类评分和综合评分，例如：

```text
Architecture       ★★★★★
Dependency         ★★★★★
Naming             ★★★★★
Maintainability    ★★★★☆
Performance        ★★★★★
Security           ★★★★★
Testing            ★★★★☆
Documentation      ★★★★★

Overall            93/100
```

评分后必须说明：

- 是否通过 Review。
- 是否存在阻断问题。
- 尚未解决的非阻断风险或测试缺口。
