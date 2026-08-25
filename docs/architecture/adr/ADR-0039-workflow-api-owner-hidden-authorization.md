# ADR-0039: 使用认证主体范围限制 Workflow API

## 状态

已接受（2026-08-25）

## 决策

- Workflow Router 只从认证 `current_user` 取得 owner/approver，客户端不能提交这些身份字段、状态或
  Definition 选择。Definition 固定为服务端注册的 `knowledge_revision_approval@1`。
- 查询、恢复和审批均由 WorkflowService 的 owner 条件读取授权；不存在与越权统一返回 404，避免
  Resource ID 枚举。状态冲突、永久失败与重试耗尽使用 409。
- Router 不调用 Repository/SQL、不执行 Node，也不组装 Provider 或 Qdrant 客户端；Workflow Node 的
  外部动作仍由后续 Service 边界负责。

## 影响

API 能安全暴露 Workflow 的启动、查询、批准、拒绝和恢复意图，同时保留 Service 的事务与并发裁决。
未来引入审批角色时只替换 Service 授权策略和 Principal 范围，不改写 Router 的信任边界。
