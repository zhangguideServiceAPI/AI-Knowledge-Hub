# ADR-0006 本地 MySQL 使用 Docker Compose

## 状态

已接受（2026-07-16）

## 背景

本地 MySQL 原先通过 `docker run` 手工启动。容器参数、数据卷和健康检查没有进入版本控制，其他开发环境无法稳定复现。

本地开发环境与云服务器的运行拓扑不同，不应直接复用同一份 Compose 配置。

## 决策

- 使用 `infra/compose.dev.yaml` 管理本地 MySQL。
- FastAPI 在 Sprint 0 继续通过 `uv run uvicorn` 在宿主机运行。
- 固定使用 `mysql:8.4`，不使用 `latest`。
- MySQL 端口只绑定到宿主机 `127.0.0.1`。
- 使用命名卷持久化 MySQL 数据。
- 使用 Compose `healthcheck` 判断 MySQL 是否可以接受连接。
- Redis 在对应 Sprint 引入，不提前加入当前 Compose。
- 生产环境 Compose 在部署架构确定后单独设计，不直接复制开发配置。

## 原因

- Compose 文件可以进入 Git，使本地基础设施可复现。
- 应用代码和有状态基础设施具有不同生命周期。
- 当前只容器化 MySQL，可以减少 Sprint 0 的学习范围。
- 命名卷比匿名卷更容易识别和维护。

## 影响

- 本地启动 MySQL 必须使用 Compose，而不再使用手工 `docker run`。
- `docker compose down` 保留数据，`docker compose down -v` 会删除本地数据。
- 当 FastAPI 仍在宿主机运行时，数据库地址使用 `127.0.0.1`。
- FastAPI 将来进入 Compose 后，数据库地址需要改为服务名 `mysql`。

## 未采用方案

- 继续使用 `docker run`：无法形成可复现的项目配置。
- 当前就容器化 FastAPI、Redis 和 Nginx：超出 Story 0.6 范围，增加不必要复杂度。
