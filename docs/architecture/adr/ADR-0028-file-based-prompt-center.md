# ADR-0028: 使用文件型 Prompt Center 管理版本化 System Prompt

## 状态

已接受（2026-08-12）

## 背景

ChatService 需要为模型调用提供受控 System Prompt，但长 Prompt 如果直接写在业务
Python 中，会把业务编排、Prompt 内容和版本发布耦合在一起。Prompt 还需要明确变量、
Review、审计和回滚能力，而客户端不能提交 System Role、模板路径或任意模板变量名。

Sprint 4 当前没有运行时动态编辑 Prompt、数据库检索 Prompt 或非开发人员独立发布
Prompt 的需求。Git 已经能够提供变更 Review、历史审计和版本回滚。

## 决策

- Prompt Center 代码位于 `app/ai/prompt_center/`，Prompt 资产位于
  `app/ai/prompts/`，执行代码与内容资产分离。
- Prompt 使用 `prompt_key + version` 显式定位，不自动选择最新版或回退旧版本。
- 每个版本目录包含 `metadata.toml` 和 `template.md`。元数据只声明 Key、Version 和
  `required_variables`，正文独立存放以便 Review。
- 使用 Python 标准库 `tomllib` 解析元数据，使用 `string.Formatter` 识别和渲染简单
  `{name}` 占位符，不新增 YAML 或模板引擎依赖。
- 目录 Key/Version、元数据身份、声明变量和模板实际变量必须完全一致；未知字段、
  重复变量、复杂占位符、缺失文件和空模板均视为配置错误。
- 渲染调用只接收 `Mapping[str, str]`，实际变量集合必须与声明集合完全相等。
- 模板只渲染一次；变量值中的占位符语法视为普通文本，不继续解释。
- 创建 Prompt Center 时全量预加载并校验资产，只缓存未渲染 `PromptTemplate`；不缓存
  带有请求变量值的 `RenderedPrompt`。
- Prompt 异常使用独立 `PromptError` 体系，不继承 Gateway `AIError` 或 Provider
  `ProviderError`。
- 日志和后续 Usage 只记录 Prompt Key、Version 和安全错误类型，不记录模板正文、
  渲染变量值或用户输入。

## 原因

- 显式版本让相同代码稳定使用同一 Prompt，变更需要 Review 和明确发布。
- 文件型资产符合当前单体应用和团队规模，不提前引入数据库、管理后台或远程服务。
- 严格变量集合同时发现 Prompt 配置漂移和 ChatService 调用契约错误。
- 单次渲染避免变量值被再次解释为模板结构。
- 预加载把文件 I/O 和配置失败移出正常渲染路径，并防止只在冷门 Prompt 首次使用时
  才发现损坏。
- 只缓存模板可以复用校验结果，又不会跨请求保留或复用渲染后的敏感值。

## 文件格式说明

`TOML` 和 `Markdown` 是通用格式，但 `metadata.toml + template.md` 的组合不是
Prompt Center 的行业强制标准，而是本项目在 ADR 中确定的文件契约：

- TOML 是有正式规范的配置格式。Python 3.11 起标准库提供 `tomllib` 读取 TOML，
  本项目可以直接解析字符串和数组等结构，不需要新增 YAML 等第三方依赖。
- Markdown 是广泛使用的纯文本标记格式，CommonMark 等规范定义了常见语法。不过
  本项目当前不渲染 Markdown，它只是把 `template.md` 按 UTF-8 读取为普通字符串。
- `metadata.toml` 适合机器读取和严格校验 Key、Version、变量数组；`template.md` 适合
  编写、Review 和比较多行 Prompt 正文。拆成两个文件，可以避免为编辑长正文处理
  TOML 多行字符串和转义细节。
- 其他系统也可以采用 JSON、YAML、数据库或远程 Prompt 平台。选择哪一种取决于是否
  需要动态编辑、权限管理、灰度发布和非开发人员操作，而不是由模型 SDK 规定。

因此，“TOML 管元数据、Markdown 管正文”是基于标准格式建立的项目约定。真正需要
保持稳定的是 Prompt Center 公开契约和目录规则，而不是说所有 AI 项目都必须使用这
两个扩展名。

## 影响

- 新 Prompt 或新版本必须同时提交元数据、模板、测试和调用方的显式版本修改。
- Prompt 文件损坏会在 Prompt Center 预加载时明确失败，而不是自动忽略或回退。
- ChatService 负责选择业务 Prompt、准备受控变量并创建 System Message；Prompt Center
  不决定业务场景，也不调用 Gateway 或 Provider。
- 当前文件读取为同步操作，但只发生在缓存单例首次预加载；后续请求渲染只访问内存。
- 当出现非开发人员在线编辑、灰度发布或动态实验等真实需求时，再评估数据库或远程
  Prompt 管理服务。

## 未采用方案

- 在 ChatService 中硬编码长字符串：无法独立版本化、Review 和回滚，并混合业务编排。
- 只按 Prompt Key 自动选择最新版本：部署内容变化会静默改变业务行为和历史可审计性。
- 使用一个简单字典保存已渲染字符串：缺少文件校验、严格变量和版本发布边界，并可能
  复用其他请求的变量值。
- 当前引入 Jinja2、YAML 或远程 Prompt 平台：现阶段不需要条件模板、循环或动态管理，
  会增加依赖和运行时故障面。
- 将用户完整正文作为模板再次渲染：会混淆可信模板结构与不可信用户内容。
