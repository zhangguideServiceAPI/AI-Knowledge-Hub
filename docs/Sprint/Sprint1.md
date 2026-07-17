**从现在开始，项目真正进入业务开发阶段。**

其实我一直在等这一刻。

因为 **Sprint 0** 是"修路"，**Sprint 1** 才是真正开始写业务。

不过，我们还是保持之前的节奏：**Story 一步一步完成**，每个 Story 都有目标、验收标准、需要理解的知识点，而不是一股脑把登录系统写完。

---

# Sprint 1 —— 用户认证（Authentication）

## Sprint 目标

> 实现一个企业级用户认证模块，为后续所有业务提供基础。

**最终交付：**

```
POST /auth/register
POST /auth/login
POST /auth/refresh（后续可选）
GET  /users/me
```

支持：

* 用户注册
* 用户登录
* JWT Token
* 密码加密
* 获取当前用户

---

# Sprint 1 为什么排在这里？

不是因为登录最简单。

而是因为它几乎涵盖了企业后端最核心的知识：

* FastAPI 路由
* Service
* Repository
* SQLAlchemy
* Alembic
* Pydantic Schema
* JWT
* Password Hash
* Dependency Injection
* Config
* Exception
* Logging

所以它是一个非常好的综合练习。

---

# Sprint 1 Story 拆分

我们仍然按 Story 开发。

## Story 1.1 —— User Model（今天）

**目标：**

建立用户的数据模型。

### 需要完成：

```
User ORM Model

↓

Alembic Migration

↓

MySQL 创建 users 表
```

### 字段建议：

```
id

username

email

password_hash

nickname

avatar

status

created_at

updated_at
```

暂时不要加太多字段。

以后再扩展。

---

### 需要理解

这一节重点不是写代码。

而是理解：

为什么：

ORM Model

和

Schema

必须分开？

为什么：

数据库里面叫：

password_hash

而不是：

password？

为什么：

created_at

统一自动生成？

为什么：

status

不用 bool？

---

### Story 1.1 验收标准

完成以后：

```
uv run alembic upgrade head

↓

users 表创建成功

↓

启动项目

↓

ORM 正常加载

↓

没有 Warning
```

---

# Story 1.2 —— Repository

建立：

```
UserRepository
```

实现：

```
create()

get_by_id()

get_by_email()

get_by_username()
```

这里只负责数据库。

不写业务。

---

# Story 1.3 —— Password

学习：

```
bcrypt
```

实现：

```
hash_password()

verify_password()
```

理解：

为什么永远不能存密码。

---

# Story 1.4 —— Register

实现：

```
POST

/auth/register
```

流程：

```
Request

↓

Schema

↓

Service

↓

Repository

↓

DB
```

---

# Story 1.5 —— JWT

学习：

```
JWT

Access Token

Expire

Secret Key
```

实现：

```
create_access_token()
```

---

# Story 1.6 —— Login

实现：

```
POST

/auth/login
```

流程：

```
用户名

↓

查询数据库

↓

验证密码

↓

JWT

↓

返回 Token
```

---

# Story 1.7 —— Current User

实现：

```
GET /users/me
```

重点：

FastAPI Dependency Injection。

---

# Story 1.8 —— Exception

统一：

```
401

403

404

409
```

错误。

不要：

raise

一堆。

---

# Story 1.9 —— Review

最后：

统一：

Review。

不是：

改 Bug。

而是：

Review：

整个：

Auth。

设计。

---

# Sprint1 学习重点（按优先级）

这一阶段不是把接口写出来，而是把下面这些知识真正吃透：

| 知识                 | 必须掌握程度 |
| ------------------ | ------ |
| SQLAlchemy Model   | ⭐⭐⭐⭐⭐  |
| Pydantic Schema    | ⭐⭐⭐⭐⭐  |
| Alembic Migration  | ⭐⭐⭐⭐☆  |
| Repository Pattern | ⭐⭐⭐⭐⭐  |
| Password Hash      | ⭐⭐⭐⭐⭐  |
| JWT                | ⭐⭐⭐⭐⭐  |
| FastAPI Dependency | ⭐⭐⭐⭐☆  |
| Config 管理          | ⭐⭐⭐⭐☆  |
| Exception Handler  | ⭐⭐⭐⭐☆  |

---

# 我们的合作方式保持不变

还是按照之前约定的节奏：

1. **我（Tech Lead）**

   * 制定 Story
   * 解释为什么这样设计
   * 控制学习节奏
   * Sprint 验收

2. **Codex**

   * 实现 Story
   * 调试
   * 自己按照 `08_CodeReview_Standard.md` 做 Review
   * 修复问题

3. **你**

   * 编码
   * 提问
   * 理解
   * 完成一个 Story 后回来同步

---

## 🎯 第一个任务（Story 1.1）

不要急着写注册接口。

**先只完成一件事：**

> **设计并实现 `User` 模型，并通过 Alembic 创建 `users` 表。**

完成后，我们一起验收：

* 为什么这些字段这样设计？
* 哪些字段以后可以扩展？
* 哪些字段现在故意不加？

等 Story 1.1 完成，我们再进入 Story 1.2（Repository）。

---

**另外，我准备在 Sprint 1 期间同步完成三份长期文档：**

* `08_CodeReview_Standard.md`（企业级 Review 规范）
* `00_PROJECT_CONSTITUTION.md`（项目宪法）
* `AI Systems Engineer Handbook`（成长手册，持续更新）

这样代码和文档会同步成长，而不是最后再补文档。
