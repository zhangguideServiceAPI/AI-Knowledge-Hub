# Backend

AI-Knowledge-Hub 的 FastAPI 后端。完整本地启动流程见[项目 README](../README.md)。

## 分层结构

```text
API -> Service -> Repository / StorageProvider
```

- `app/api/`：HTTP 路由和状态码
- `app/services/`：应用逻辑和依赖编排
- `app/schemas/`：请求与响应协议
- `app/models/`：SQLAlchemy 模型
- `app/db/`：SQLAlchemy Engine、Session、Redis 客户端和依赖探测
- `app/storage/`：Local/MinIO Provider、Factory、上传校验和 Storage Readiness
- `app/ai/`：稳定 ChatProvider 契约、Fake/真实 Adapter 与 Provider Factory
- `app/core/`：配置和日志

当前进程只启用 `STORAGE_PROVIDER` 指定的一个 Provider。已有文件时切换 Provider 需要先迁移对象并同步 Metadata；不匹配的下载、删除和 Cleanup 会被拒绝，当前版本不支持 Local 与 MinIO 资源混合在线访问。

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

普通测试默认跳过需要真实外部服务的 Integration Test。显式运行真实 Redis 测试：

```bash
RUN_REDIS_INTEGRATION_TESTS=1 uv run pytest -m integration -q
```

显式运行真实 MinIO Provider 与 HTTP 生命周期测试：

```bash
RUN_MINIO_INTEGRATION_TESTS=1 uv run pytest -m integration -q
```

显式运行真实 AI Provider 的非流式与 Streaming 测试：

```bash
RUN_AI_INTEGRATION_TESTS=1 \
AI_INTEGRATION_PROVIDER_KEY=primary \
AI_INTEGRATION_MODEL=<provider-model> \
uv run pytest -q tests/integration/test_openai_compatible_provider_integration.py
```

真实凭据只写入未提交的 `.env` 中的 `AI_PROVIDERS`；其中 `base_url` 是兼容 API
根路径，例如以 `/v1` 结尾的地址。普通测试不会读取这些凭据或访问外部模型。
