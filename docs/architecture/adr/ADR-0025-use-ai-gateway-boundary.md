# ADR-0025: 建立 AI Gateway 边界隔离业务与模型 Provider

## 状态

已接受（2026-08-07）

## 背景

Chat、未来 RAG、Workflow 和 Agent 都需要调用外部模型，但 Provider 的 SDK、
认证、模型名称、请求字段、响应结构和异常会变化。如果 ChatService 或 Router 直接
调用某个 SDK，业务流程会依赖厂商类型，更换 Provider 时需要修改多个业务模块，
也难以统一 Timeout、Retry、Streaming、错误和 Usage 行为。

StorageProvider 已经证明稳定业务边界可以隔离 LocalStorage 与 MinIO 差异；模型调用
需要相同的依赖方向，但不能照搬对象存储接口或把所有 AI 能力放进一个抽象。

## 决策

- 建立项目内 AIGateway，业务层只依赖项目自己的 Chat 请求、结果和领域错误。
- 公共 API Schema、内部 ChatRequest、ProviderChatRequest 与 SDK Model 分离。
- Gateway 负责模型别名解析、Provider 选择、调用生命周期、Timeout、有限 Retry 和稳定返回。
- Provider Factory 只根据内部 Provider Key 与 Settings 创建或取得具体 Adapter。
- Adapter 负责 SDK 请求/响应转换、原生异常翻译和上游资源关闭。
- ChatService 负责 Prompt、Gateway、Usage 和业务终态编排；Gateway 不管理用户或持久化 Usage。
- 外部 LLM 默认不进入应用全局 Readiness，故障只影响 AI 能力。
- API Key、真实模型名、Base URL 和 SDK 类型不得穿过 Provider 边界进入公共或业务契约。

## 原因

- 后续业务可以复用同一模型调用边界，不重复处理不同 SDK。
- Model Alias 允许运维替换底层模型而不要求客户端和 ChatService 修改。
- Gateway 拥有跨 Provider 的调用策略，Factory 与 Adapter 保持单一职责。
- Provider 故障可以转换为稳定业务语义，避免客户端依赖厂商错误码和文案。
- Fake Provider 可以在不访问网络和不消耗费用的情况下验证业务调用链。

## 影响

- 增加了 Gateway、Factory 和 Adapter 三种不同职责，必须通过文档和测试防止互相吞并。
- 每个真实 Adapter 都必须通过相同 Provider Contract Test。
- Provider 特有能力不能直接泄露到公共 Chat API；确有需求时需要显式扩展或独立能力契约。
- 当前 Gateway 是应用内模块，不是独立微服务；只有出现独立扩缩容、跨服务复用或治理需求时才重新评估部署边界。

## 未采用方案

- ChatService 直接调用 OpenAI-compatible SDK：代码较短，但业务会绑定 SDK 请求、异常和流式 Chunk。
- Router 根据 `model` 判断并创建 SDK Client：混合 HTTP、业务策略、Secret 和 Provider 生命周期。
- 立即建设独立 AI Gateway 微服务：当前没有跨服务团队、独立扩容或网络治理证据，会过早增加部署复杂度。
- 让 Gateway 保存 Prompt 历史和 Conversation Memory：这些是业务能力，不属于模型中转边界。
