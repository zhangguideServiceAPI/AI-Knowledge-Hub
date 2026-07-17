# 08 Code Review 规范

按照本规范

Review 当前所有修改。

如果有任何违反规范的地方，请全部修改。

直到达到 90 分以上。

再停止。


Rule 1

Architecture

有没有违反：

目录结构。

例如：

Router

调用：

Service

✔

Router

调用：

Repository

❌
Rule 2

Dependency

有没有：

循环依赖。

Rule 3

Naming

命名：

是否：

统一。

例如：

user_service.py

✔

UserService.py

❌

service.py

❌
Rule 4

SQLAlchemy

例如：

禁止：

session.commit()

写：

十几处。

应该：

统一。

事务。

Rule 5

Logging

禁止：

print()

必须：

logger.info()
Rule 6

Exception

禁止：

except:

必须：

明确。

异常。

Rule 7

Magic Number

例如：

86400

禁止。

必须：

JWT_EXPIRE_SECONDS
Rule 8

Config

禁止：

os.getenv()

到处。

写。

必须：

统一：

Settings。

Rule 9

FastAPI

Router。

禁止：

写：

业务。

例如：

@router.post()

里面：

200 行。

直接。

Fail。

Rule 10

Service

禁止：

返回：

ORM。

应该：

DTO。

或者：

Schema。

Rule 11

Repository

禁止：

业务。

Repository。

只能：

SQL。

Rule 12

Documentation

新增：

API。

必须：

更新：

docs。

Rule 13

Test

新增：

业务。

必须：

测试。

Rule 14

Docker

禁止：

latest。

Rule 15

Compose

环境变量。

不能：

写：

密码。

Rule 16

Commit

一个：

Commit。

一个：

功能。

Rule 17

TODO

禁止：

超过：

Sprint。

Rule 18

AI Review

Review。

必须：

输出：

例如：

Architecture

★★★★★

Naming

★★★★★

Maintainability

★★★★☆

Performance

★★★★★

Security

★★★★★

Overall

93/100
