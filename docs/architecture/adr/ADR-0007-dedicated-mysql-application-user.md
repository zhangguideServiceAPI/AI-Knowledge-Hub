# ADR-0007 MySQL 使用独立应用账号

## 状态

已接受（2026-07-16）

## 背景

FastAPI 最初使用 MySQL `root` 账号连接数据库。`root` 拥有整个 MySQL 实例的管理权限，一旦应用配置泄露或代码出现缺陷，可能影响同一实例中的其他业务数据库。

## 决策

- MySQL `root` 账号只用于数据库管理和环境初始化。
- FastAPI 使用独立账号 `ai_knowledge_hub`。
- 应用账号只获得 `ai_knowledge_hub` 数据库的权限。
- `MYSQL_ROOT_PASSWORD` 保存在 `infra/.env`。
- `DB_USER`、`DB_PASSWORD` 和 `DB_NAME` 保存在 `backend/.env`。
- 真实 `.env` 文件不提交 Git，只提交不含真实密码的示例文件。
- 本地首次初始化通过 MySQL 官方镜像的 `MYSQL_DATABASE`、`MYSQL_USER` 和 `MYSQL_PASSWORD` 创建数据库与应用账号。

## 原因

- 遵循最小权限原则。
- 避免一个项目获得其他业务数据库的访问权限。
- 将数据库管理员凭证与应用凭证分离。

## 影响

- MySQL 初始化变量只在空数据卷第一次启动时生效。
- 已初始化数据库不能通过修改环境变量完成密码轮换，需要执行 MySQL 用户管理语句。
- Alembic 和 FastAPI 都使用项目应用账号连接数据库。
- 生产环境中的数据库账号应在环境初始化阶段创建，不在每次应用发布时重复创建。

## 未采用方案

- FastAPI 继续使用 `root`：权限过大，不适合多业务或生产环境。
- 每次应用启动时创建数据库用户：应用不应持有数据库用户管理权限。
