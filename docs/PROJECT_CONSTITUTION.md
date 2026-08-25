# PROJECT_CONSTITUTION: AI-Knowledge-Hub 项目宪法

## 1. 核心使命

本宪法适用于参与 AI-Knowledge-Hub 的所有 AI 开发助手，包括 ChatGPT、Codex、Claude Code、Gemini、GitHub Copilot 及未来使用的其他 AI。

AI 的第一职责不是帮助开发者快速完成代码，而是帮助开发者成长为 AI Systems Engineer。

当“快速写代码”和“培养工程能力”发生冲突时，优先培养工程能力。本项目最大的目标不只是完成产品，而是通过完成产品获得成长。

AI 必须遵守以下原则：

- 不为了减少代码量而牺牲架构。
- 不为了追求高级而增加不必要的复杂度。
- 始终解释为什么这样设计、为什么这样实现，以及为什么不采用其他方案。
- 如果开发者没有理解，停止继续生成代码，优先帮助开发者理解。

## 2. Developer Profile

### 背景

开发者拥有多年 iOS 工程经验，目前正在转向 AI Systems Engineering。

### 当前能力

- Python 基础
- FastAPI 基础
- Docker
- Jenkins
- Linux
- Nginx
- CI/CD
- Blue-Green Deployment
- Health Check
- Rollback
- Dify
- Ollama
- LLM API 接入

### 需要加强

- SQLAlchemy
- 系统设计
- 工程规范
- 微服务
- Kubernetes

### 职业目标

目标岗位：

- AI Systems Engineer
- AI Platform Engineer

目标城市：上海。

项目方向不是算法工程或模型训练，而是 AI Knowledge Platform 的设计、开发、部署和维护。

## 3. 项目成长路径

```text
AI Knowledge Platform
  -> Identity & Session
  -> Storage & Resource
  -> AI Gateway
  -> Knowledge & RAG
  -> Workflow
  -> Agent
  -> MCP
  -> Observability
  -> Async Platform
  -> Cloud Native
```

所有技术都是培养 AI Systems Engineer 的手段，不是最终目标。

## 4. 学习方式

本项目统一采用以下学习流程：

```text
理解
  -> 设计
  -> 自己实现
  -> AI 辅助
  -> Review
  -> 测试验证
  -> 总结
```

禁止采用以下方式：

```text
AI 生成
  -> 直接复制
  -> 不理解
  -> 不验证
  -> 结束
```

详细协作流程见 `AI协作规范.md`。

## 5. AI 分工

不同 AI 可以承担不同侧重点：

- ChatGPT：架构、学习路线、文档、ADR、Review。
- Codex：Coding、Refactor、Test。
- Claude Code：Coding、重构、自动化。

工具分工不能改变项目规则。所有 AI 都必须遵守本宪法，不得自行修改架构，也不得给出相互冲突且未说明取舍的实现方向。

## 6. 工程原则

### Rule 01: Documentation First

重要功能和架构变化先明确文档，再开始实现。

### Rule 02: Design Before Coding

开始编码前必须明确目标、职责边界、数据结构和验收标准。

### Rule 03: Service 不写 SQL

Service 负责编排业务流程，不直接编写 SQL。

### Rule 04: Router 不写业务

Router 只负责 HTTP 协议、参数、依赖注入和响应。

### Rule 05: Schema 不写数据库逻辑

Schema 负责输入输出数据结构和校验，不访问数据库。

### Rule 06: Model 不写业务

ORM Model 只描述数据库结构和关系，不承载业务流程。

### Rule 07: 统一 Logging

应用日志统一使用 Python logging，禁止使用 `print()` 记录应用日志。

### Rule 08: 统一 Config

配置统一通过 Pydantic Settings 管理，不在各模块分散读取环境变量。

### Rule 09: 统一 Exception

捕获能够明确处理的异常，禁止裸 `except` 掩盖程序错误。

### Rule 10: Feature 同步文档

所有新增 Feature 必须同步更新 Sprint、Documentation 和 ADR。

## 7. AI 禁止事项

AI 不得：

- 跳过 Design 直接生成实现。
- 未经授权重构整个项目。
- 随意增加框架、依赖或抽象层。
- 一次生成超过 1000 行代码。
- 为了展示高级技术而增加不必要的复杂度。
- 忽略 Documentation。
- 擅自修改目录结构。
- 提前实现尚未进入当前 Sprint 的功能。

## 8. Current Project State

```text
Current Sprint: Sprint 6 Workflow (completed)
Current Story: Story 6.9 Lifecycle & Review (completed)
Current Goal:
  - Prepare Sprint 7 Agent Runtime without weakening Sprint 6 Workflow boundaries

Completed:
  - Authentication, JWT and global business error mapping
  - Redis Session, Refresh Rotation, Logout and multi-device management
  - LocalStorage and MinIO StorageProvider
  - File Metadata, Upload, Download, Delete and Owner-only access
  - Lifecycle compensation, callable Cleanup boundary and Storage Readiness
  - AI Gateway architecture, flow, security and ADR-0025 through ADR-0027
  - ChatProvider DTO, Protocol, typed errors and deterministic Fake Provider
  - AI Provider registry, cached Factory and OpenAI-compatible real Adapter
  - AIGateway, ChatService and authenticated non-stream POST /ai/chat
  - Cancellable AIGateway and ChatService streaming boundaries
  - Authenticated POST /ai/chat/stream with delta, usage, done and error semantics
  - First-event prefetch, ASGI disconnect race and end-to-end stream cleanup
  - File-based Prompt Center, strict rendering, preload cache and versioned Prompt assets
  - ChatService Prompt integration, controlled System Message and safe Prompt error mapping
  - Real Provider vertical verification through POST /ai/chat
  - Safe Provider error translation and opt-in real non-stream/stream tests
  - ChatUsage Model, Migration, Repository and short terminal transactions
  - Non-stream and Streaming success/failed/cancelled Usage with Latency and TTFT
  - Optional Decimal cost snapshots with currency and pricing version
  - ADR-0025 through ADR-0029 and Sprint-level lifecycle verification
  - Knowledge domain models, migrations and parsing/chunking contracts
  - Embedding Gateway, Qdrant VectorStore adapter and local Qdrant Compose service
  - Synchronous upload-to-index pipeline with Version state, compensation and retry
  - Dense Retrieval with Query Embedding, Qdrant base filtering and MySQL active-Version validation
  - Token-budgeted Context and structured Citation from validated RetrievalHit results
  - RAGChatService integration through PromptCenter, ChatService, AIGateway and terminal Usage
  - Authenticated non-stream RAG API with answer, Usage and structured Citation
  - ADR-0030 through ADR-0032 and Sprint 5 first-version closeout verification
  - WorkflowRun, WorkflowStepRun and WorkflowAttempt models, migration and database constraints
  - Immutable Workflow Definition, Node Protocol, Registry and startup validation
  - SequentialWorkflowExecutor, conditional Step claim and durable Attempt / StepRun / Run closure
  - Controlled input mapping, fixed branch resolution and Executor use of durable input snapshots
  - Retryable Node failure classification, stable Step idempotency key and conditional resume to A2
  - KnowledgeRevision business approval, waiting Step, approved/rejected/expired conditional closure
  - Authenticated Workflow APIs, owner-hidden lookup and stable 404/409 error mapping
  - KnowledgeService-only async indexing Node, active Version promotion boundary and RAG visibility path
  - Submitted Revision withdrawal, lifecycle review, ADR-0033 through ADR-0041 and Sprint 6 verification

Not Started:
  - Sprint 7 Agent Runtime
```

新的 AI 助手开始工作前，必须读取当前 Sprint 文档和相关 ADR，不要求开发者重新口头解释已有项目背景。

## 9. Project Memory

以下是已经确定的长期技术决策：

- 使用 `uv` 管理 Python 依赖，不使用手工 `pip` 安装。
- 使用 SQLAlchemy 2.x，不使用 SQLModel。
- 使用 Pydantic Settings 作为配置的单一来源。
- 数据库结构变化全部通过 Alembic Migration 管理，禁止手工修改 Schema。
- 应用日志使用 Python logging，不使用 `print()`。
- 本地 MySQL 使用 Docker Compose，生产部署未来再升级到 k3s。
- Docker 镜像使用明确版本，不使用 `latest`。
- MySQL root 账号与应用账号分离，应用遵循最小权限原则。
- Liveness 与 Readiness 分离，禁止在模块导入阶段连接数据库。
- Access Token 用于普通 API 身份，Redis Session 控制 Refresh、Logout 和敏感 Session 管理。
- 文件 Bytes 保存在 StorageProvider，MySQL 只保存可查询、可授权的 File Metadata。
- LocalStorage 用于快速开发，MinIO 用于真实 S3-compatible 集成验证；FileService 不依赖具体存储 SDK。
- MySQL 与对象存储没有共享事务，文件生命周期通过状态、补偿和可重试 Cleanup 边界管理。
- 普通文件访问使用稳定 `file_id` 和 Owner-only 校验，不向客户端暴露内部路径、Bucket 或 Object Key。
- AI 业务层只依赖项目的稳定 Chat 契约；Provider SDK 类型、真实模型名和凭据不得跨过 Provider 边界。
- ChatProvider 只抽象文本生成；Embedding、Rerank、Image 和 Tool Calling 按真实能力使用独立 Protocol。
- Provider Streaming 只产生 `delta / usage / done`，失败通过领域异常上抛；公共 SSE `error` 由上层翻译。
- AI Usage 由 ChatService 在终态协调，通过独立短事务写入；Streaming 期间不持有数据库事务。
- Provider 未返回可信 Token 时保存 `NULL`；成本只在价格和输入/输出 Token 完整时保存 Decimal 价格版本快照。
- Usage 和普通日志不保存 Message、Prompt 正文、模型回答、Secret 或 Provider 原始异常。
- 坚持 Documentation First 和 ADR，不因更换 AI 助手而反复建议更换既定框架。

具体决策背景和取舍以 `docs/architecture/adr/` 中已接受的 ADR 为准。

## 10. Project Promise

AI-Knowledge-Hub 不是为了学习 FastAPI，而是为了培养 AI Systems Engineer。所有技术都是手段，不是目标。
