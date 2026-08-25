# AI-Knowledge-Hub

AI-Knowledge-Hub 是一个长期工程实践项目，目标是在构建生产级 AI 知识平台的过程中，系统培养 AI Systems Engineering 能力。

项目坚持先设计后编码：理解问题、记录决策、亲自实现、测试验证、完成 Review。

## 当前进度

当前阶段：**Sprint 6 - Workflow，正在完成 Story 6.7 API & Security**

已经完成：

- 使用 `uv` 管理 Python 项目和依赖
- FastAPI 应用结构
- Pydantic Settings 配置中心
- Python logging
- SQLAlchemy 2.x Engine、Session 和 Base
- Alembic Migration
- Docker Compose 本地 MySQL 和 Redis
- 独立 Liveness 和包含 MySQL、Redis 状态的 Readiness 健康检查
- pytest 健康接口测试
- User Model 和第一份 Alembic Migration
- User Repository 与事务边界
- bcrypt 密码哈希和验证
- `POST /auth/register` 用户注册接口
- JWT Access Token 配置、签发和验证测试
- `POST /auth/login` 用户登录接口
- `GET /users/me` 当前用户接口与 Bearer 认证依赖
- 全局业务异常到 HTTP 响应的统一映射
- Story 2.0 认证体系演进学习与架构文档
- Redis 固定窗口原子登录准入、HTTP 429 和 Redis 故障关闭策略
- Redis Session Repository、TTL、多设备 Sorted Set 索引和失效索引清理
- Refresh JWT、固定/Sliding 过期计算和 Redis Lua 原子 Rotation
- 当前设备原子 Logout、Refresh Replay 撤销和客户端单航班契约
- JWT `kid`、Active Key 与 Key Ring 密钥轮换
- Register、Login、Refresh、Replay、Logout 和 Redis 故障的安全事件日志
- 多设备 Session 列表、当前设备识别、单设备撤销和全部设备登出
- File Resource Metadata、Owner-only 权限、上传、列表、代理下载和幂等删除
- LocalStorage 与 MinIO 两种可配置 Storage Provider
- MinIO 最小权限应用账号、Named Volume、一次性 Bucket 初始化和真实集成测试
- 可重试的文件 Cleanup 边界、Provider/Metadata 一致性保护和生命周期测试
- MySQL、Redis 与条件化 Storage Readiness
- AI Gateway Architecture、Flow、Security 与 ADR-0025 至 ADR-0027
- ChatProvider 稳定 DTO、Protocol、领域异常和确定性 Fake Provider
- Provider 契约、异常与 Fake Provider 的 22 个测试
- 多 Provider 配置注册表、按 Provider Key 缓存的 Factory
- OpenAI-compatible 真实 Adapter、错误清理和非流式/流式真实联调
- AIGateway 模型别名、Context Window、Timeout、有限 Retry 和稳定错误映射
- 认证非流式 `/ai/chat` 与 SSE `/ai/chat/stream`，支持断连取消和完整资源关闭
- 文件型 Prompt Center、严格变量、显式版本和受控 System Message
- Chat Usage 成功/失败/取消终态、Latency、TTFT 和可选 Decimal 成本快照
- ADR-0025 至 ADR-0029，以及 Fake、Contract、API、Streaming 和真实 Provider 测试

Sprint 1 Authentication、Sprint 2 Session & Identity Management、Sprint 3 Storage &
Resource Management、Sprint 4 AI Gateway 与 Sprint 5 Knowledge / RAG 第一版已完成。
当前 Sprint 6 正在为知识修订审批、索引与恢复闭环建立持久化 Workflow 能力；已完成
WorkflowRun、WorkflowStepRun、WorkflowAttempt 的领域模型、状态机、Migration 与测试，以及
代码型 Definition、Node Protocol、Registry、启动期校验、最小顺序 Executor，以及受控字段映射和
固定条件分支、失败 Run 恢复、Step 级幂等键、人工审批 Revision 与认证 Workflow API；尚未实现知识索引 Node 或后台 Worker。

## 技术栈

- Python 3.13+
- uv
- FastAPI
- Pydantic 2
- SQLAlchemy 2
- Alembic
- MySQL 8.4
- Redis 7.4
- MinIO
- boto3
- OpenAI Python SDK
- Docker / Docker Compose
- pytest

RAG、Agent、监控、CI/CD 和 k3s 将在后续 Sprint 中逐步引入。

## 项目结构

```text
AI-Knowledge-Hub/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── ai/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── storage/
│   │   └── services/
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── uv.lock
├── docs/
│   ├── architecture/adr/
│   └── Sprint/
├── infra/
│   └── compose.dev.yaml
└── README.md
```

## 环境要求

- Python 3.13 或更高版本
- [uv](https://docs.astral.sh/uv/)
- Docker 和 Docker Compose
- Git

## 本地开发

以下初始化命令均从项目根目录开始执行。

### 1. 配置环境变量

```bash
cp backend/.env.example backend/.env
cp infra/.env.example infra/.env
```

示例密码只用于本地开发。使用 `openssl rand -hex 32` 分别生成 JWT
签名密钥、`REDIS_PASSWORD` 和 MinIO 应用 Secret。MinIO Root 凭据只写入
`infra/.env`，应用 Access Key 与 Secret Key 只写入 `backend/.env`。在 `backend/.env` 中设置
`JWT_ACTIVE_KEY_ID=v1`，并将签名密钥写入
`JWT_SIGNING_KEYS={"v1":"<generated-secret>"}`。禁止提交真实 `.env` 文件。

`STORAGE_PROVIDER` 为当前进程选择唯一活动 Provider。空环境可以在 `local` 与 `minio` 间切换；已有文件时不能只修改该配置，必须先迁移对象并同步 Metadata。FileService 会拒绝 Provider 或 Bucket 与 Metadata 不匹配的对象操作，避免误读或误删。

### 2. 安装后端依赖

```bash
cd backend
uv sync --dev
cd ..
```

### 3. 启动 MySQL、Redis、Qdrant 和 MinIO

```bash
docker compose \
  --env-file backend/.env \
  --env-file infra/.env \
  -f infra/compose.dev.yaml \
  up -d --wait mysql redis qdrant minio
```

使用一次性 MinIO Client 容器创建 Bucket、应用账号和最小权限 Policy：

```bash
docker compose \
  --env-file backend/.env \
  --env-file infra/.env \
  -f infra/compose.dev.yaml \
  up minio-init
```

### 4. 执行数据库迁移

```bash
cd backend
uv run alembic upgrade head
```

### 5. 启动 FastAPI

```bash
uv run uvicorn app.main:app --reload
```

FastAPI 地址：<http://127.0.0.1:8000>

Swagger UI：<http://127.0.0.1:8000/docs>

## 运行验证

在另一个终端检查 FastAPI 进程是否存活：

```bash
curl http://127.0.0.1:8000/health/live
```

检查 FastAPI 和必要依赖是否就绪：

```bash
curl http://127.0.0.1:8000/health/ready
```

预期响应：

```json
{"status":"ok"}
```

```json
{"status":"ready","database":"ok","redis":"ok","storage":"ok"}
```

## 测试

在 `backend/` 目录执行：

```bash
uv run pytest -q
```

普通测试默认跳过需要真实外部服务的 Integration Test。Redis 已启动时显式运行：

```bash
RUN_REDIS_INTEGRATION_TESTS=1 uv run pytest -m integration -q
```

MinIO 已启动时显式运行真实对象存储测试：

```bash
RUN_MINIO_INTEGRATION_TESTS=1 uv run pytest -m integration -q
```

真实 AI Provider 测试必须额外提供内部 Provider Key 和真实模型名。测试固定为两个
短请求，并把单次输出限制为 16 Token：

```bash
RUN_AI_INTEGRATION_TESTS=1 \
AI_INTEGRATION_PROVIDER_KEY=primary \
AI_INTEGRATION_MODEL=<provider-model> \
uv run pytest -q tests/integration/test_openai_compatible_provider_integration.py \
  -k 'provider_generate or provider_stream'
```

API Key 与 Base URL 只从 `backend/.env` 的 `AI_PROVIDERS` 读取，禁止写入命令、测试
文件、日志或 Git。普通测试不会访问真实 Provider。

## 停止本地服务

在项目根目录执行：

```bash
docker compose \
  --env-file backend/.env \
  --env-file infra/.env \
  -f infra/compose.dev.yaml \
  down
```

普通 `down` 会保留 MySQL、Redis、Qdrant 和 MinIO 的 Named Volume。只有明确需要删除本地数据时，才使用 `down -v`。

## 项目文档

- [文档索引](docs/README.md)
- [项目宪法](docs/PROJECT_CONSTITUTION.md)
- [项目愿景](docs/项目愿景.md)
- [AI 协作规范](docs/AI协作规范.md)
- [Code Review 规范](docs/CodeReview规范.md)
- [当前 Sprint](docs/Sprint/Sprint6.md)
- [API 规范](docs/API规范.md)
- [架构决策记录](docs/architecture/adr/)

## Roadmap

完整阶段依赖、状态和企业能力见 [Sprint 长期路线](docs/Sprint/Sprint长期路线.md)。
