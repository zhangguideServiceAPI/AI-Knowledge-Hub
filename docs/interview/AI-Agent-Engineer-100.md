# AI Agent 工程师（2026 企业版）100 道高频面试题计划

## 目标

这套题库不作为脱离项目的刷题任务，而是与 AI-Knowledge-Hub 的 Sprint 学习同步建设。

```text
学习知识
  -> 在项目中设计和实现
  -> 测试与 Review
  -> 整理成面试答案
  -> 用项目证据回答追问
```

完成一个 Sprint 后，应能够回答该阶段对应的高频问题；项目全部完成时，自然形成 100 道有真实工程证据的面试题，而不是最后集中背诵。

## 每道题的固定格式

```text
问题
30 秒简答
2 分钟完整回答
项目中的设计或代码证据
为什么没有采用其他方案
常见追问
容易说错的地方
掌握状态
```

掌握状态分为：

- `理解`：能看懂答案和项目实现。
- `能讲`：可以不看文档完整解释。
- `能画`：可以画出架构、时序或状态变化。
- `能写`：可以现场实现核心代码或测试。

只有达到题目要求的掌握状态，才算真正完成。并非所有系统设计题都要求现场写代码，也不能只会写代码却解释不清取舍。

## 100 道题分配

| Sprint | 面试主题 | 题数 |
| --- | --- | ---: |
| Sprint 1 | Authentication、密码 Hash、JWT、认证与授权边界 | 10 |
| Sprint 2 | Redis Session、Refresh Token、Rotation、Logout、安全与日志 | 10 |
| Sprint 3 | 对象存储、Streaming Upload、Metadata、一致性、文件安全 | 8 |
| Sprint 4 | LLM Gateway、流式输出、上下文、限流、成本与故障处理 | 10 |
| Sprint 5 | RAG、Chunk、Embedding、Vector Database、检索与评估 | 12 |
| Sprint 6 | Workflow、状态机、LangChain/n8n、重试与人工节点 | 8 |
| Sprint 7 | Agent、Tool Calling、Memory、Planning、Coding Agent | 14 |
| Sprint 8 | MCP、MCP vs Tool Calling、Resource、Prompt、Skill | 8 |
| Sprint 9 | Logging、Metrics、Tracing、Evaluation、告警 | 7 |
| Sprint 10 | Async IO、线程池、Celery、消息队列、幂等与补偿 | 6 |
| Sprint 11 | Kubernetes、GitOps、扩缩容、发布、Secret 和平台部署 | 7 |
| **总计** |  | **100** |

题数代表当前计划，不强行限制实际学习。某个主题出现重要追问时可以先增加，Sprint Review 时再合并重复问题，最终保持 100 道核心题。

## 当前进度

```text
题库结构与分配：已完成
正式完整答案：0 / 100

Sprint 1 项目实现：已完成
Sprint 1 面试答案：待根据现有代码和 ADR 回填 10 道

Sprint 2 项目实现：已完成
Sprint 2 面试答案：待根据现有代码、流程图和测试回填 10 道

Sprint 3 学习计划：已完成
Sprint 3 面试答案：随 Story 3.0 至 3.8 同步形成 8 道
```

不暂停 Sprint 3 去一次性补写前 20 道。Sprint 3 推进期间，每周可以额外回填 1 至 2 道 Sprint 1/2 问题；新 Story 的面试题则必须在 Story Review 时同步完成，避免继续产生历史欠账。

## Sprint 1: Authentication

重点问题范围：

- Authentication 与 Authorization 有什么区别？
- 为什么密码必须使用 bcrypt 等慢 Hash，而不是 SHA-256？
- JWT 的签名、编码和加密有什么区别？
- Access Token 为什么应该短期有效？
- 如何避免登录接口泄露邮箱是否注册？
- FastAPI 中 Router、Service、Repository 的认证职责如何划分？

RBAC 可以作为授权理论追问，但 Sprint 1 没有实现完整 RBAC，回答时必须明确“理解概念”和“项目已经实现”的区别。

## Sprint 2: Session & Identity

重点问题范围：

- Cookie、Authentication Session、SQLAlchemy Session 和 Redis 有什么区别？
- Access Token、Refresh Token 和 Redis Session 分别解决什么问题？
- Refresh Token Rotation 为什么必须原子执行？
- Replay Attack 为什么会撤销当前设备 Session？
- Logout 后 Access Token 为什么可能继续有效？
- 固定 Session 与 Sliding Session 如何选择？
- JWT `kid` 和 Key Ring 如何支持 Secret Rotation？
- 多设备 Session 如何查看和撤销？

Sprint 2 的完整答案应引用认证流程、Session Architecture、Refresh Token ADR、Lua 测试和安全日志测试。

## Sprint 3: Storage & Resource Management

计划形成 8 道核心题：

1. Block、File 和 Object Storage 有什么区别，AI 平台为什么通常使用对象存储？
2. FastAPI `UploadFile` 和直接接收 `bytes` 有什么区别，如何避免大文件占满内存？
3. 为什么数据库只保存 File Metadata，而不保存大文件内容？
4. 为什么需要 `StorageProvider` 抽象，怎样避免为未来 Provider 过度设计？
5. MySQL 与对象存储无法共享事务时，如何处理孤儿对象和失败补偿？
6. 如何防御路径穿越、伪造 MIME、超大文件和恶意文件名？
7. StreamingResponse、后端代理下载和 Signed URL 分别适合什么场景？
8. 如何设计 Owner-only 文件权限、删除状态和真实 MinIO 集成测试？

每道题必须随着对应 Story 完成逐步补充答案，不能在尚未实现前把候选设计描述成项目事实。

## Sprint 4: AI Gateway

重点问题范围：

- 为什么需要统一 LLM Gateway？
- SSE、Streaming Response 和 WebSocket 如何选择？
- 如何管理上下文窗口、Token、成本、超时和重试？
- 如何处理不同模型供应商的协议差异？
- LLM 调用怎样做限流、熔断、降级和审计？

## Sprint 5: RAG

重点问题范围：

- RAG 的完整数据和查询链路是什么？
- Chunk Size、Overlap 和文档结构如何影响检索？
- Embedding 是什么，向量相似度怎样理解？
- Dense、Sparse 和 Hybrid Retrieval 如何选择？
- Reranker、Metadata Filter 和 Query Rewrite 解决什么问题？
- 如何评估 Retrieval 和最终回答质量？

## Sprint 6: Workflow

重点问题范围：

- Workflow 与 Agent 有什么区别？
- 怎样表达状态、分支、重试、超时和人工审批？
- LangChain、LangGraph、n8n 和自研状态机如何取舍？
- Workflow 如何保证幂等和可恢复？

## Sprint 7: Agent Runtime

重点问题范围：

- Agent、Tool Calling 和普通 Workflow 有什么区别？
- Agent 如何进行 Planning、Reflection 和 Tool Selection？
- Short-term、Long-term 和 Episodic Memory 如何划分？
- Tool Schema、权限和 Prompt Injection 如何防护？
- Coding Agent 的 Workspace、Patch、Test 和 Sandbox 如何设计？
- 如何限制 Agent 循环、成本和不可控副作用？

## Sprint 8: MCP Integration

重点问题范围：

- MCP 解决什么问题？
- MCP 与普通 Function/Tool Calling 有什么区别？
- Tool、Resource、Prompt 和 Skill 的职责是什么？
- MCP Server 的权限、Transport、Discovery 和错误边界如何设计？

## Sprint 9: Observability

重点问题范围：

- Logging、Metrics 和 Tracing 分别回答什么问题？
- LLM 和 Agent 系统需要观察哪些延迟、Token、成本和质量指标？
- Trace ID 如何跨 API、Workflow、Agent 和异步任务传播？
- 什么是高基数标签，为什么会增加监控成本？

## Sprint 10: Async Platform

重点问题范围：

- Async IO、线程池和进程池如何选择？
- Celery、消息队列和普通 BackgroundTasks 有什么区别？
- 消息至少一次投递时如何保证幂等？
- Retry、Dead Letter Queue 和补偿任务如何设计？

## Sprint 11: Cloud Native

重点问题范围：

- Deployment、Service、Ingress、ConfigMap 和 Secret 的职责是什么？
- Readiness、Liveness 和 Startup Probe 如何选择？
- GitOps 如何实现可审计发布和回滚？
- AI 平台如何进行资源限制、自动扩缩容和 Secret Rotation？
- 有状态依赖为什么不能简单放入普通无状态 Deployment？

## 同步规则

### Story 完成时

- 选择 1 至 3 道与当前 Story 直接相关的问题。
- 用刚完成的代码、测试、架构图或 ADR 补充项目证据。
- 标记当前掌握状态和仍答不清的追问。
- 不为了凑题数编造没有实现或没有理解的内容。

### Sprint 完成时

- Review 本 Sprint 的全部核心题。
- 删除重复问题，补足遗漏的企业场景追问。
- 至少进行一次不看文档的口述或白板演练。
- 将回答中的项目事实与当前代码重新核对。
- Sprint Review 中记录面试题完成数量和掌握状态。

### 项目完成时

- 合并为最终 100 道核心题。
- 每道题都具有真实项目证据或明确标注为理论扩展。
- 按岗位 JD 重新排序为 Authentication、Platform、RAG、Agent、MCP、Observability 和 Cloud Native 专题。
- 使用真实面试方式进行限时回答、追问和系统设计演练。

## 回答原则

- 先直接回答结论，再解释原理和取舍。
- 优先用 AI-Knowledge-Hub 的真实实现举例。
- 明确区分“当前项目已经实现”“已经设计”“只理解理论”。
- 不堆术语；面试官追问时能画流程、指出代码位置并解释失败场景。
- 不把某个框架 API 当成系统设计答案。
- 遇到没有做过的生产规模问题，说明当前边界和合理演进方案，不伪造经验。
