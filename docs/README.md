# AI-Knowledge-Hub 文档地图

本目录保存项目愿景、长期规则、当前契约、架构决策、Sprint 交付记录和学习证据。

## 当前状态

```text
Completed: Sprint 0 Foundation
Completed: Sprint 1 Authentication
Completed: Sprint 2 Session & Identity
Completed: Sprint 3 Storage & Resource Management
Completed: Sprint 4 AI Gateway, Prompt Center, Streaming & Usage
Completed: Sprint 5 Knowledge / RAG first-version closeout
Current:   Sprint 6 Workflow, Story 6.4 Mapping & Branching
Next:      Sprint 6.5 Retry, Resume & Idempotency
```

当前学习与实施总控文档：[Sprint 6 Workflow](Sprint/Sprint6.md)。

## 开始新任务时怎么读

### 所有任务必读

1. [项目宪法](PROJECT_CONSTITUTION.md)：最高学习与工程约束。
2. [项目愿景](项目愿景.md)：产品方向、目标用户和成功标准。
3. [AI 协作规范](AI协作规范.md)：开发者与 AI 的协作方式。
4. [当前 Sprint 6](Sprint/Sprint6.md)：Workflow 目标、边界、Story 和验收证据。

### 修改代码前追加阅读

1. 与功能相关的 Architecture 文档和 ADR。
2. [编码规范](编码规范.md)、[API 规范](API规范.md)和[数据库规范](数据库规范.md)。
3. [Code Review 规范](CodeReview规范.md)及相关源码、测试。

### 部署或基础设施任务追加阅读

- [部署规范](部署规范.md)
- 根目录 [README](../README.md)
- `infra/` 中的实际配置与环境变量示例

## 文档职责

| 文档类型 | 回答的问题 | 是否记录当前进度 |
| --- | --- | --- |
| 项目愿景 | 为什么做、为谁做、最终成功是什么 | 否 |
| 项目宪法 | 所有 AI 和开发工作必须遵守什么 | 只记录当前 Sprint 指针 |
| 工程规范 | 编码、API、数据库、部署和 Review 的共同规则 | 否 |
| Architecture | 当前系统结构、流程、安全和领域设计是什么 | 记录当前事实与明确后续边界 |
| ADR | 为什么接受某项长期技术决策 | 记录决策当时背景，不重写历史 |
| Sprint | 当前阶段学什么、做什么、如何验收 | 是 |
| Interview | 如何用项目证据回答高频问题 | 是 |
| Learning | 不属于当前主线的扩展学习 | 必须标明与当前项目的边界 |

同一个事实只保留一个主要所有者。其他文档使用链接引用，避免复制后产生状态漂移。

## 工程规范

- [编码规范](编码规范.md)
- [API 规范](API规范.md)
- [数据库规范](数据库规范.md)
- [部署规范](部署规范.md)
- [Code Review 规范](CodeReview规范.md)

## 系统架构

- [系统概览](architecture/system-overview.md)
- [项目结构与分层](architecture/project-structure.md)
- [架构决策记录](architecture/adr/)

### Authentication & Session

- [认证体系演进](architecture/authentication-evolution.md)
- [认证总流程](architecture/authentication-flow.md)
- [认证安全](architecture/authentication-security.md)
- [Redis Authentication](architecture/redis-authentication.md)
- [Session Architecture](architecture/session-architecture.md)
- [Refresh Token Design](architecture/refresh-token-design.md)
- [Client Refresh Contract](architecture/client-refresh-contract.md)

### Storage & Resource

- [Storage Evolution](architecture/storage-evolution.md)
- [Storage Architecture](architecture/storage-architecture.md)
- [File Resource Design](architecture/file-resource-design.md)
- [Storage Flow](architecture/storage-flow.md)
- [Storage Security](architecture/storage-security.md)

### AI Gateway

- [AI Gateway Architecture](architecture/ai-gateway-architecture.md)
- [AI Gateway Flow](architecture/ai-gateway-flow.md)
- [AI Gateway Security](architecture/ai-gateway-security.md)
- [ADR-0025：AI Gateway 边界](architecture/adr/ADR-0025-use-ai-gateway-boundary.md)
- [ADR-0026：Capability-specific ChatProvider](architecture/adr/ADR-0026-use-capability-specific-chat-provider.md)
- [ADR-0027：Streaming、Retry 与错误终态](architecture/adr/ADR-0027-streaming-retry-and-terminal-state.md)
- [ADR-0028：文件型 Prompt Center](architecture/adr/ADR-0028-file-based-prompt-center.md)
- [ADR-0029：Usage、成本快照与数据最小化](architecture/adr/ADR-0029-usage-cost-snapshot-and-data-minimization.md)

当前已实现 Provider 契约、真实 Adapter、AIGateway、ChatService、非流式与 SSE Router、
文件型 Prompt Center，以及成功/失败/取消 Usage、TTFT 和可选成本快照。

## Sprint 记录

- [Sprint 0：Backend Foundation（已完成）](Sprint/Sprint0.md)
- [Sprint 1：Authentication（已完成）](Sprint/Sprint1.md)
- [Sprint 2：Session & Identity（已完成）](Sprint/Sprint2.md)
- [Sprint 3：Storage & Resource Management（已完成）](Sprint/Sprint3.md)
- [Sprint 4：AI Gateway（已完成）](Sprint/Sprint4.md)
- [Sprint 5：Knowledge / RAG（已完成）](Sprint/Sprint5.md)
- [Sprint 6：Workflow（进行中）](Sprint/Sprint6.md)
- [Sprint 长期路线](Sprint/Sprint长期路线.md)

历史 Sprint 是阶段交付证据。即使其中保留了当时的“候选”或“下一步”表述，也不应改写为新 Sprint 的当前计划；当前状态以本页、项目宪法和当前 Sprint 为准。

## 学习与面试

- [AI Agent 工程师 100 道高频面试题计划](interview/AI-Agent-Engineer-100.md)

## 扩展学习

- [知识蒸馏与图片识别训练流程](learning/knowledge-distillation-and-image-training.md)
- [企业 AI 应用全景：RAG、Workflow、Agent Runtime 与 MCP](learning/enterprise-ai-application-rag-workflow-agent-mcp.md)

扩展学习文档不代表项目已经实现对应能力，也不能改变当前 Sprint 边界。

## 维护规则

- 新 Feature 同步 Sprint、API、Architecture 和必要 ADR。
- 文档中的“已实现”必须能指向真实代码、测试或基础设施证据。
- 候选设计使用“候选 / 计划 / 后续边界”标记，不与当前事实混写。
- 当前 Sprint 变化时同步本页、根 README 和项目宪法的 Current State。
- 复杂功能优先提供思维导图、端到端流程图及必要时序图或状态图。
- Markdown 修改后检查单一 H1、标题层级、代码围栏、内部链接和 `git diff --check`。
