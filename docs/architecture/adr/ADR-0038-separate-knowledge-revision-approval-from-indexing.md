# ADR-0038: 将知识修订审批与索引技术状态分离

## 状态

已接受（2026-08-25）

## 决策

- 使用 `KnowledgeRevision` 保存业务审批状态、`expires_at`、决定人和绑定的 WorkflowRun；使用
  `DocumentVersion` 继续保存 `pending/processing/indexed/failed/cleanup_required` 索引技术状态。
- 提交审批创建 `submitted Revision + waiting_approval Run + waiting Step`，等待人工并不创建 Attempt。
- 批准以条件更新裁决 Revision，完成等待 Step，恢复 Run 为 running 并根据固定 approved 分支创建下
  一个 pending Step；拒绝和过期取消 Run/Step，不启动索引。
- 过期采用查询/操作时的惰性 reconciliation，不引入本 Sprint 范围外的 Scheduler。

## 原因与影响

审批被拒绝是有效业务结论，不等于 Embedding 或 Qdrant 写入失败；将二者写到同一个字段会使重试、
审计和员工 RAG 可见性都无法解释。所有审批状态转换仍由 Service 用短事务协调，Repository 只提供
条件 Update。当前没有角色模型，审批权限暂为 Revision 所有者；未来扩展必须替换 Service 授权规则。
