# Sprint 0：Project Foundation

## 状态

已完成（2026-07-17）

## 目标

搭建可运行、可配置、可迁移、可测试的后端基础设施，为 Sprint 1 用户与认证功能提供稳定基础。

Sprint 0 不以业务功能为目标，重点建立 Python、FastAPI、SQLAlchemy、Alembic、Docker Compose 和工程文档之间的完整协作方式。

## 完成内容

- Story0.1 项目初始化（uv、FastAPI、Git）
- Story0.2 Pydantic Settings 配置中心
- Story0.3 Logging（Python logging）
- Story0.4 SQLAlchemy（Engine、Session、Base）
- Story0.5 Alembic 初始化与 Model metadata 加载
- Story0.6 Docker Compose（本地 MySQL、命名卷、健康检查、独立应用账号）
- Story0.7 Health Check（Liveness、Readiness、MySQL 探测、自动化测试）
- Story0.8 README（本地启动、验证、测试和环境变量模板）
- Story0.9 Sprint 总结

## 最终运行结构

```text
FastAPI（宿主机，通过 uv 运行）
    |
    | 127.0.0.1:3306
    v
MySQL 8.4（Docker Compose）
    |
    v
命名卷 ai-knowledge-hub-mysql-data
```

应用内部调用关系：

```text
Router -> Service -> Database
```

## 关键架构决策

- 使用 uv 管理 Python 依赖，不使用手工 pip 安装。
- 使用 SQLAlchemy 2.x，不使用 SQLModel。
- 所有应用配置统一通过 Pydantic Settings 获取。
- 数据库结构变化统一通过 Alembic Migration 管理。
- 使用 Python logging，不使用 print 记录应用日志。
- 本地 MySQL 使用 `infra/compose.dev.yaml` 管理。
- MySQL root 账号与应用账号 `ai_knowledge_hub` 分离。
- Liveness 与 Readiness 使用不同接口和语义。
- 本地 Compose 与未来生产部署配置分离设计。

详细背景和取舍记录在 `docs/architecture/adr/`。

## 遇到的问题与解决方案

### Python 包导入失败

从错误目录启动 Uvicorn，以及使用不完整包路径，会导致 `ModuleNotFoundError`。

解决方案：从 `backend/` 执行 `uv run uvicorn app.main:app --reload`，项目内部统一使用 `app.*` 绝对导入。

### 目标数据库不存在

SQLAlchemy 最初可以连接 MySQL，但 `ai_knowledge_hub` 数据库尚未创建。

解决方案：由 MySQL Docker 镜像在空数据卷首次初始化时创建数据库和项目账号。

### 手工 docker run 无法复现

原 MySQL 容器由 `docker run` 创建，使用匿名数据卷，启动参数没有进入版本控制。

解决方案：改用 Docker Compose、固定 MySQL 8.4、命名卷、localhost 端口绑定和数据库健康检查。

### 应用使用 MySQL root

应用使用 root 会获得整个 MySQL 实例权限，不适合多业务环境。

解决方案：root 仅用于初始化，FastAPI 和 Alembic 使用只管理项目数据库的独立账号。

### 数据库不可用导致 FastAPI 无法启动

数据库检查原先在模块导入阶段执行，连接失败会阻止 `app.main` 加载。

解决方案：移除导入阶段连接，将数据库状态放入 Readiness；Liveness 不访问外部依赖。

### pytest 无法导入 app

直接运行 pytest 时，项目根目录没有稳定进入模块搜索路径。

解决方案：在 `pyproject.toml` 中配置 pytest `pythonpath` 和 `testpaths`。

### Mock 没有替换 Router 实际调用的函数

直接导入函数后，Router 模块保存了自己的函数引用。Patch Service 原始定义不会替换 Router 已保存的引用。

解决方案：测试在函数实际使用位置 `app.api.health.is_application_ready` 执行 monkeypatch。

### Alembic 看不到 User Model

Python 不会自动加载项目中的所有文件。只导入 `Base` 时，`Base.metadata` 为空。

解决方案：Alembic 环境显式导入 `app.models`，触发 ORM Model 注册。User Migration 按 Sprint 边界留到 Sprint 1。

## 验证结果

- MySQL Compose 状态：`healthy`
- 数据库应用账号可以连接 `ai_knowledge_hub`
- `/health/live`：应用存活时返回 HTTP 200
- `/health/ready`：MySQL 正常时返回 HTTP 200
- `/health/ready`：MySQL 停止时返回 HTTP 503
- MySQL 恢复后 Readiness 自动恢复 HTTP 200
- pytest：3 tests passed
- Python compileall：通过
- OpenAPI：声明 Readiness 的 HTTP 200 和 503
- Logging：DEBUG 和 INFO 配置门槛验证通过
- uv lock：状态有效

## 主要收获

- Model、Migration 和数据库中的真实表是三个不同层次。
- Python 文件只有被 import 后才会执行，ORM Model 也只有执行后才会注册到 metadata。
- Liveness 表示进程可以响应，Readiness 表示依赖就绪并可以接收流量。
- 日志配置等级是输出门槛，`logger.debug()` 等方法表示单条日志的严重程度。
- `response.status_code` 控制实际 HTTP 状态，OpenAPI `responses` 负责声明额外响应契约。
- Mock 应替换被测试代码实际读取的名字，而不只是函数最初定义的位置。
- Docker Compose 描述可复现环境，数据生命周期由命名卷管理。
- 应用账号必须遵循最小权限原则，不能默认使用数据库 root。

## 已知技术债

- Sprint 1 需要先 Review User 字段、可空性和唯一约束，再生成第一份 User Migration。
- Settings 中的数据库默认账号和密码需要在生产化前改为必填配置。
- 数据库 URL 需要支持特殊字符密码的安全编码。
- Readiness 数据库连接需要在生产部署前配置明确超时。
- `backend/main.py` 和 `/hello` 日志演示代码需要在正式业务开发前清理。
- 后续应引入统一 Formatter/Linter，自动处理缩进、尾部空格和导入顺序。
- Logging 后续需要与 Uvicorn、结构化日志和请求关联 ID 统一设计。

## Sprint 1 入口

Sprint 1 从用户与认证设计开始：

1. 明确注册、登录和用户字段需求。
2. Review User Model，不直接沿用未确认字段。
3. 生成并 Review 第一份 Alembic Migration。
4. 实现密码哈希、JWT、注册和登录。
5. 为业务逻辑补充自动化测试。
