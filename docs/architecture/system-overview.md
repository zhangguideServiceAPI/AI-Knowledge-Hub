# System Overview

Client
  |
FastAPI
  |
Config (Pydantic Settings)
  |
Logging
  |
Router
  |
Service (Sprint1)
  |-------------------|
Repository (Sprint1)  Redis Client (Sprint2)
  |                   |
SQLAlchemy            Redis
  |
MySQL

所有组件共享同一份 Settings 配置。
