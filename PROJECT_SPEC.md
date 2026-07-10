# AI Knowledge Hub - Project Spec

## 1. 项目目标

构建一个可扩展的 AI 知识管理系统，支持：

- 用户系统（注册 / 登录 / JWT）
- 文档管理（后续扩展）
- AI 问答（后续扩展）
- RAG（后续扩展）
- Agent（后续扩展）
- iOS 客户端接入

当前阶段：MVP 后端系统

---

## 2. 技术栈

### Backend
- Python 3.10+
- FastAPI
- SQLAlchemy 2.x
- Pydantic

### Database
- MySQL（Docker 部署）
- Alembic（数据库迁移）

### Auth
- JWT（python-jose 或 PyJWT）
- bcrypt（密码加密）

### Infra
- Docker + Docker Compose

---

## 3. 项目结构规范

```text
app/
  api/            # 路由层（只处理 HTTP）
  services/       # 业务逻辑层（核心逻辑）
  models/         # ORM 数据库模型
  schemas/        # 请求 / 响应结构
  core/           # 核心能力（config / auth / security）
  db/             # 数据库连接 / session
  utils/          # 工具函数
  middlewares/    # 中间件（后续使用）