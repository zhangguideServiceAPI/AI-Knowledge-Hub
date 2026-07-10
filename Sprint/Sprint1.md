---

# 🚀 Sprint 1 开始（正式进入开发）

现在开始进入真实编码阶段。

---

# 🧭 Sprint 1 任务（你第一步要做的）

## 🎯 目标

搭建：

> FastAPI + MySQL + SQLAlchemy + User 模型 + JWT 登录系统

---

# 📌 Step 1：初始化项目

你需要创建：

```text
backend/
  app/
    main.py
    api/
    services/
    models/
    schemas/
    core/
    db/
    utils/

```

# 📌 Step 2：Docker MySQL

你需要启动 MySQL（Docker）

要求：

数据可持久化
端口 3306
有 用户名 root 密码 123456



# 📌 Step 3：SQLAlchemy 初始化

你需要完成：

- DB Session
- Base
- engine

------

# 📌 Step 4：User Model

创建 User 表：

- username
- password_hash
- nickname
- timestamps
- is_deleted

------

# 📌 Step 5：JWT + bcrypt

实现：

- 密码加密
- token 生成
- token 解析

------

# 📌 Step 6：API（最小闭环）

必须完成：

### 1. 注册

```
POST /api/auth/register
```

### 2. 登录

```
POST /api/auth/login
```

返回：

```
{
  "access_token": ""
}
```

------

# 📌 Step 7：验证接口

- Swagger 可用
- 能注册用户
- 能登录拿 token
