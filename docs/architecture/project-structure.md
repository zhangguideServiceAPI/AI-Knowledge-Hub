# Project Structure & Layering

## 目的

本文定义稳定目录职责和依赖方向，不维护每个文件的完整快照。实际文件以仓库为准；新目录只有在当前 Story 出现真实职责时才创建。

## 当前结构

```text
AI-Knowledge-Hub/
  backend/
    app/
      api/              # Router、依赖注入、HTTP 异常映射
      ai/               # ChatProvider 契约、领域异常与 Provider Adapter
      core/             # Settings、Security、Logging、业务异常
      db/
        repositories/  # MySQL / Redis 数据访问
      models/           # SQLAlchemy Models
      schemas/          # Pydantic 请求与响应
      services/         # 业务规则、事务和流程编排
      storage/          # StorageProvider、Local、MinIO、Factory
      main.py           # FastAPI 组装和 Router 注册
    alembic/            # Migration 环境与版本
    tests/              # Unit、API 和 Integration Test
    pyproject.toml
    uv.lock
  docs/
    Sprint/             # 阶段计划、进度、验收和总结
    architecture/       # 当前架构、流程、安全和领域设计
      adr/              # 长期技术决策及取舍
    interview/          # 面试题与项目证据
    learning/           # 主线以外的扩展学习
  infra/                # 本地 Compose 和基础设施配置
  README.md             # 项目状态与本地运行入口
```

## 依赖方向

```mermaid
flowchart LR
    API["api"] --> SVC["services"]
    SVC --> REP["db/repositories"]
    SVC --> PRO["storage / AI provider boundary"]
    REP --> MOD["models"]
    API --> SCH["schemas"]
    SVC --> SCH
    API --> CORE["core"]
    SVC --> CORE
    REP --> CORE
    PRO --> CORE
```

允许：

```text
Router -> Service -> Repository
Router -> Service -> Provider
Service -> Schema / DTO
Repository -> Model
```

禁止：

```text
Router -> Repository
Router -> Provider SDK
Repository -> Service
Model -> Business Workflow
Schema -> Database
Provider -> User Permission
```

## 各层约束

### API

- 处理 HTTP Method、Path、Header、Body、Query、依赖注入和响应类型。
- 不写 SQL、不控制业务事务、不转换厂商 SDK Response。

### Service

- 负责业务规则、权限、跨依赖编排、事务、补偿和业务日志时机。
- 不直接写 SQL；通过 Repository 访问数据。
- 不向 Router 返回 ORM 对象。

### Repository

- 负责单一数据系统的读取与写入。
- MySQL Repository 默认不自行 `commit()`；事务由 Service 协调。
- 不包含 HTTP、对象存储或用户交互逻辑。

### Provider

- 隔离外部系统或 SDK，例如 Local/MinIO Storage 和未来 LLM Provider。
- 使用项目稳定类型和领域异常，不向业务扩散 SDK 类型。
- 只抽象当前已经需要的最小能力。

### Model 与 Schema

- Model 描述数据库结构、约束和关系，不承载业务流程。
- Schema 描述输入输出和校验，不访问数据库或文件系统。

## 新模块准入

新增目录或抽象前必须回答：

1. 它解决哪个当前 Story 的真实职责？
2. 现有层为什么无法清晰承担？
3. 它的输入、输出和依赖方向是什么？
4. 怎样通过测试证明该边界有效？

不能只因为未来可能需要，或为了让目录看起来更“企业级”，提前创建空的 Gateway、Client、Manager、Factory 或 Utils 层。

## Sprint 4 当前扩展

Story 4.6 已形成以下真实结构：

```text
app/ai/
  provider.py          # Provider DTO、ChatEvent 与 ChatProvider Protocol
  exceptions.py        # Provider 层可预期领域异常
  gateway.py           # 模型别名、Context 预检、Retry、Deadline 与稳定结果/Event
  factory.py           # 根据 Provider Key 创建并缓存 Adapter
  providers/
    fake.py            # 不访问网络的确定性测试替身
    openai_compatible.py # OpenAI-compatible SDK Adapter
  prompt_center/
    models.py          # 未渲染模板与渲染结果的不可变契约
    exceptions.py      # 独立 Prompt 领域异常
    center.py          # 文件加载、全量校验、严格渲染与模板缓存
    factory.py         # 预加载并缓存 PromptCenter 单例
  prompts/
    assistant/v1/      # 无变量的默认 System Prompt
    summary/v1/        # language + style 变量示例
    translation/v1/    # 语言与 tone 变量示例
app/api/
  ai.py                # 认证的非流式与 SSE Chat Router
  ai_sse.py            # 公共 SSE Event 编码与流中安全错误终态
app/schemas/
  ai.py                # 公共 Chat JSON/SSE Schema 与 AI 错误响应
app/services/
  chat_service.py      # 公共请求到 Gateway 的非流式/流式业务编排
```

`models/chat_usage.py` 和 `db/repositories/chat_usage_repository.py` 仍未创建，留给 Usage
Story。Prompt Center 已由依赖注入接入 ChatService；非流式和流式请求都使用受控
SYSTEM Message，并把公共 API Message 转换为 USER Message。
