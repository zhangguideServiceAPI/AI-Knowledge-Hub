# ADR-0003 Pydantic Settings

## 决策
所有配置统一通过 Settings 获取。

## 原因
避免多处读取环境变量，形成单一配置来源（Single Source of Truth）。
