# Backend

AI-Knowledge-Hub 的 FastAPI 后端。完整本地启动流程见[项目 README](../README.md)。

## 分层结构

```text
API -> Service -> Database
```

- `app/api/`：HTTP 路由和状态码
- `app/services/`：应用逻辑和依赖编排
- `app/schemas/`：请求与响应协议
- `app/models/`：SQLAlchemy 模型
- `app/db/`：Engine、Session 和数据库探测
- `app/core/`：配置和日志

## 依赖管理

项目使用 `uv` 管理依赖，并通过 `uv.lock` 锁定版本。

```bash
uv sync --dev
```

## 开发服务器

```bash
uv run uvicorn app.main:app --reload
```

## 数据库迁移

执行已有 Migration：

```bash
uv run alembic upgrade head
```

修改 SQLAlchemy Model 后生成 Migration：

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

## 测试

```bash
uv run pytest -q
```
