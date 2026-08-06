# AI-Knowledge-Hub

AI-Knowledge-Hub 是一个长期工程实践项目，目标是在构建生产级 AI 知识平台的过程中，系统培养 AI Systems Engineering 能力。

项目坚持先设计后编码：理解问题、记录决策、亲自实现、测试验证、完成 Review。

## 当前进度

当前阶段：**Sprint 2 - Session & Identity Management 进行中**

已经完成：

- 使用 `uv` 管理 Python 项目和依赖
- FastAPI 应用结构
- Pydantic Settings 配置中心
- Python logging
- SQLAlchemy 2.x Engine、Session 和 Base
- Alembic Migration
- Docker Compose 本地 MySQL
- Liveness 和 Readiness 健康检查
- pytest 健康接口测试
- User Model 和第一份 Alembic Migration
- User Repository 与事务边界
- bcrypt 密码哈希和验证
- `POST /auth/register` 用户注册接口
- JWT Access Token 配置、签发和验证测试
- `POST /auth/login` 用户登录接口
- `GET /users/me` 当前用户接口与 Bearer 认证依赖
- 全局业务异常到 HTTP 响应的统一映射

当前从 Story 2.0 认证体系演进开始，先理解并完成设计文档，再进入 Redis Foundation。

## 技术栈

- Python 3.13+
- uv
- FastAPI
- Pydantic 2
- SQLAlchemy 2
- Alembic
- MySQL 8.4
- Docker / Docker Compose
- pytest

Redis、RAG、Agent、监控、CI/CD 和 k3s 将在后续 Sprint 中逐步引入。

## 项目结构

```text
AI-Knowledge-Hub/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
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

示例密码只用于本地开发。使用 `openssl rand -hex 32` 生成
`JWT_SECRET_KEY`，并只写入 `backend/.env`。禁止提交真实 `.env` 文件。

### 2. 安装后端依赖

```bash
cd backend
uv sync --dev
cd ..
```

### 3. 启动 MySQL

```bash
docker compose \
  --env-file backend/.env \
  --env-file infra/.env \
  -f infra/compose.dev.yaml \
  up -d --wait mysql
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
{"status":"ready","database":"ok"}
```

## 测试

在 `backend/` 目录执行：

```bash
uv run pytest -q
```

## 停止本地服务

在项目根目录执行：

```bash
docker compose \
  --env-file backend/.env \
  --env-file infra/.env \
  -f infra/compose.dev.yaml \
  down
```

普通 `down` 会保留 MySQL 数据。只有明确需要删除本地数据库时，才使用 `down -v`。

## 项目文档

- [文档索引](docs/README.md)
- [项目宪法](docs/PROJECT_CONSTITUTION.md)
- [项目愿景](docs/项目愿景.md)
- [AI 协作规范](docs/AI协作规范.md)
- [Code Review 规范](docs/CodeReview规范.md)
- [当前 Sprint](docs/Sprint/Sprint1.md)
- [API 规范](docs/API规范.md)
- [架构决策记录](docs/architecture/adr/)

## Roadmap

项目将逐步实现用户认证、认证会话、用户中心、文档处理、AI Chat、RAG、Workflow、Agent、MCP、监控、异步任务和 k3s。
