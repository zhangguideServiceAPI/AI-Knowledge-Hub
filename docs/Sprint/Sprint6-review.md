# Sprint 6 Review: Workflow

## 结论

Sprint 6 完成了一个固定、可恢复的知识修订审批 Workflow：提交后等待人工决定，批准后由 Workflow
Node 委托 KnowledgeService 索引并提升 active Version；失败和撤回均留下 MySQL 审计事实。

## 验收证据

| 目标 | 项目证据 |
| --- | --- |
| 持久化状态与并发认领 | `WorkflowRun`、`WorkflowStepRun`、`WorkflowAttempt` 与 Repository 条件 `UPDATE`；测试覆盖认领、失败、resume 和 Attempt 历史。 |
| 人工审批 | `KnowledgeRevision` 独立保存 `submitted/approved/rejected/expired/withdrawn`，批准和拒绝不混入 `DocumentVersion` 技术状态。 |
| 外部 I/O 边界 | `SequentialWorkflowExecutor.execute_next_async()` 在认领提交后再 await Node；`IndexAndActivateVersionNode` 只调用 `KnowledgeService`。 |
| RAG 可见性 | `KnowledgeService.complete_version_indexing()` 只在全部索引完成后把 Version 置为 `indexed` 并安全提升 active 指针；既有 RAG 路径只使用已验证的 active Version。 |
| 恢复 | `node_retryable`、稳定 Step 幂等键、`resume_failed_run()`、Version 的 `failed/cleanup_required` 技术恢复边界。 |
| 权限与撤回 | `/workflows` 从认证 Principal 取得身份；跨用户资源隐藏为 404；仅等待审批时可 withdraw。 |

## 本次验证

在 Sprint 收口时执行：Ruff、格式检查、全量 pytest、`alembic check`、`uv lock --check` 与
`git diff --check`。全量结果为 **727 passed, 18 skipped**（最终提交前重新执行并以输出为准）。

## 明确边界

- 没有后台 Worker、队列或自动过期扫描；Sprint 10 再复用已验证的 Executor。
- 没有运行中强杀取消；外部 I/O 已启动后需要未来的协作取消与补偿。
- 没有用户自定义 Definition / DSL、任意 DAG 或模型决定 Workflow 分支；Sprint 7 的 Agent 只能经受控 Tool 触发既有 Service / Workflow。

## 面试演练（3 题）

1. **条件 UPDATE 的 `rowcount=0` 与数据库异常如何区分？** SQL/commit 抛异常才是基础设施失败；正常执行但 `rowcount=0` 要重读并映射为 404、409 或幂等成功。证据：Workflow 与 Revision Repository。
2. **为什么 Workflow Node 不能直连 Qdrant？** Workflow 负责编排及 Attempt 审计；KnowledgeService 统一拥有 Version 状态、向量补偿和 active Version 提升，避免两套一致性逻辑。证据：ADR-0040 与 `IndexAndActivateVersionNode`。
3. **为什么不能把 running 的索引 Run 直接改成 cancelled？** 数据库状态不会停止已发出的 Embedding/Qdrant 请求；会产生“显示取消但仍有向量副作用”的谎言。首版只允许等待审批时 withdraw，后续由 Worker 在安全边界协作取消。证据：ADR-0041。

掌握状态：`理解并可结合代码说明`。下一次应不看文档画出“审批 -> 索引 -> 失败恢复 -> RAG 可见性”状态图。
