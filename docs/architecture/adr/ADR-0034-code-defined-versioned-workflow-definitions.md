# ADR-0034: 使用代码定义且带不可变版本的 Workflow Definition

## 状态

已接受（2026-08-25）

## 背景

WorkflowRun 必须在数天后的审批、失败或恢复中保留原流程语义。若系统读取一份可随时修改的
数据库 JSON、用户上传 DSL 或最新配置，历史 Run 会在恢复时悄悄改走新节点或新分支，审计
记录也无法解释。

在执行流程前还必须发现 Definition 的配置错误：缺失 Node、重复版本、未知后继、环路、
不可达步骤或相邻输入输出类型不一致，不应等到已创建 WorkflowRun 或调用外部服务后才失败。

## 决策

- Definition 是服务端代码中的冻结 `dataclass`，由 `key + version` 唯一标识；当前不创建
  Definition 数据库表，不允许客户端提交任意 Workflow JSON、DSL 或 Python。
- `WorkflowDefinition` 保存流程输入类型、起始 Step 和有序 Step 集合；
  `WorkflowStepDefinition` 保存稳定 `step_id`、`node_key`、输入类型和一个线性
  `next_step_id`。受控字段映射与条件分支留给 Story 6.4。
- `WorkflowNode` 是结构化 `Protocol`：每个 Node 必须声明 `node_key`、`input_type`、
  `output_type` 与 `execute()`。Node 负责业务动作，后续必须调用 Service，不直接调用
  Embedding、Qdrant 或 Provider SDK。
- 应用组装期使用只读 `WorkflowNodeRegistry` 和 `WorkflowDefinitionRegistry`。Registry 在
  任何 Run 创建前验证重复 key/version、缺 Node、未知边、多前驱、环、不可达 Step，以及
  Definition/Node/相邻 Step 的类型身份一致性。
- Registry 以精确 key/version 查询；未来 `resume_run()` 只能读取 Run 保存的版本。没有
  历史 Definition 时必须抛出 `WorkflowDefinitionNotFoundError`，不能回退到最新版。

## 原因

- 代码版本、测试和发布历史共同保存 Definition 语义，便于审核、回滚与保留 v1/v2。
- 启动期失败比运行中失败安全：不会产生半条 Run、外部副作用或难以恢复的状态。
- `Protocol` 把 Executor 与具体审批/索引实现解耦，同时使每一条边可在执行前进行类型校验。
- 当前仅支持顺序单后继，避免在基础契约未稳定时预先实现任意 DAG、循环或用户可编程平台。

## 影响

- Story 6.2 新增 `app.workflow.definition`、`node`、`registry` 和稳定配置异常。
- Story 6.3 可以依赖已验证的 Definition 和 Node 选择逻辑实现顺序 Executor，但仍需负责短
  事务、Attempt 与状态持久化。
- 发布新 Definition 时需新增版本并保留仍被数据库 Run 引用的旧版本；删除旧版本必须先完成
  数据保留与迁移策略。

## 未采用方案

- 直接在数据库保存可编辑流程图：历史 Run 的语义会随编辑漂移，且需要额外的权限、校验与
  发布版本系统。
- 在执行时才检查 Node、边或类型：会在 Run 已持久化甚至发生外部副作用后失败。
- 允许一个 Step 有任意多个后继或循环：当前 Story 没有字段映射、条件表达式、幂等执行器和
  并行收敛语义，提前开放会制造未定义行为。
