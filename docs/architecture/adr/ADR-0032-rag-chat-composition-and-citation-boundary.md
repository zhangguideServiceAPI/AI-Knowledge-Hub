# ADR-0032: RAG 复用 ChatService 并独立返回 Citation

## 状态

已接受（2026-08-21）

## 背景

Story 5.7 已经能够从一个经过认证的 KnowledgeBase 检索有效 `RetrievalHit`，Story 5.8
能够在 Chat 模型 Context Window 内选择完整 Chunk 并生成 Citation。最后还需要把 Context
交给 Sprint 4 的模型调用链。如果 RAG 自己直接调用 Provider，就会复制 Prompt、重试、Usage、
成本和错误处理；如果要求模型在正文中输出并解析引用，引用就可能与真正发送的 Chunk 脱离。

## 决策

- RAG 的唯一生成编排入口是 `RAGChatService.answer_knowledge_question()`。
- 调用顺序固定为：

  ```text
  RAG Router
    -> RAGChatService
    -> KnowledgeService Retrieval
    -> ContextBuilder / PromptCenter
    -> ChatService.chat_with_rendered_prompt()
    -> AIGateway
    -> ChatProvider
  ```

- `ChatService` 继续负责 Gateway 调用、Provider 错误转换、Usage、成本快照、超时和重试；RAG
  不直接依赖 Chat Provider SDK。
- 第一版只使用服务器默认 Chat 模型。RAG 预算 tokenizer 必须与该 Chat 模型配置一致；Embedding
  tokenizer 和 Chat tokenizer 分开管理。
- `ContextBuilder` 只选择完整 Chunk，超出预算时跳过 Chunk，不按字符、字节或模型未知规则
  截断。预算先扣除固定 System Prompt、用户问题、输出预留和安全余量。
- Citation 在 Context 构造时根据已选 Chunk 生成，并作为结构化 API 字段返回。模型正文不要求
  使用可解析的引用标记，API 也不从正文反向推断来源。
- 首版入口为非流式 `POST /knowledge-bases/{knowledge_base_id}/chat`。Streaming RAG、
  Hybrid Search、Reranker、Query Rewrite、评估平台和多模型路由留给后续 Sprint。

## 原因

- 复用 ChatService 可以保持普通 Chat 与 RAG 的 Usage、成本和故障语义一致，避免一次请求被
  多套逻辑重复记录。
- 默认模型限制确保预算计算、Prompt Tokenizer 和真实 Provider Context Window 不发生错配。
- 完整 Chunk 和独立 Citation 保留了可追溯证据；即使模型回答措辞改变，客户端仍能稳定定位
  `file_id`、`document_id`、`chunk_id` 和 `source_locator`。
- 非流式闭环先验证检索、预算、生成和来源之间的契约，再处理断连、首事件、部分 Usage 和
  流式 Citation 等额外状态。

## 失败与边界

- 无效模型或 Context 超预算映射为 400；Embedding/Chat 限流为 429；Provider 超时为 504；
  Provider 或 Qdrant 暂时不可用为 503。
- 无检索命中是合法业务结果，不能伪装成 Qdrant 故障；`RAGChatService` 保留后续策略决定
  是否生成无依据回答，当前模板要求模型基于提供的 Context 作答。
- Citation 说明使用的来源，不证明回答一定正确；质量评估需要独立评估集和指标。
- Chat Usage 落库失败不会把已经成功返回的模型回答改成失败；失败和取消仍按 ChatService
  的既有终态记录。

## 影响

- RAG API 不暴露 Prompt、向量、Qdrant Point 或对象存储内部 Key，只返回回答、Usage 和结构化
  Citation。
- 当前同步请求会等待完整 Retrieval、Prompt 和 Chat 结果；可靠后台索引调度和 Streaming RAG
  属于后续能力，不由本 ADR 预先承诺。
- 未来增加模型选择时，必须为每个模型明确 tokenizer、Context Window、输出上限和评估基线，
  不能简单放开客户端提交别名。

## 未采用方案

- RAG 直接调用 OpenAI/其他 Provider SDK：会绕过统一 Gateway、Usage 和错误边界。
- 将所有 Citation 拼进模型正文并在响应后解析：容易出现编号漂移、遗漏和来源伪造。
- 把整个文件或全部 RetrievalHit 放入 Prompt：不可控地消耗 Context 和成本。
- 在 Story 5.9 同时实现 Streaming、Reranker、Hybrid Search 和离线评估：缺乏独立回归基线，
  会掩盖当前闭环的基本契约问题。
