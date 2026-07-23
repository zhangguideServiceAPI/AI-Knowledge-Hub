# ADR-0001 使用 uv

## 决策

使用 uv 管理 Python 项目依赖。`backend/pyproject.toml` 是依赖声明的单一来源，`backend/uv.lock` 负责锁定解析结果；不并行维护容易漂移的 `requirements.txt`。

## 原因
- 速度快
- 锁文件统一
- 更适合现代 Python 工程
- 生产依赖与开发工具通过 dependency groups 分离
