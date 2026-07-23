# ADR-0011 使用 bcrypt 保存密码哈希

## 状态

已接受（2026-07-20）

## 背景

用户认证需要验证密码，但数据库不能保存可直接使用或可逆恢复的原始密码。密码哈希算法还需要具备随机 salt 和可调节计算成本，降低数据库泄露后的离线破解风险。

bcrypt 5.0 对输入密码设置了 72 bytes 上限。直接截断超长密码会让不同密码共享相同有效前缀，产生认证风险。

## 决策

- 使用 bcrypt 5.0 生成和验证密码哈希。
- 密码安全函数放在 `app/core/security.py`。
- `hash_password()` 接收原始密码并返回可保存到数据库的字符串 hash。
- `verify_password()` 接收本次输入的原始密码和数据库中的 `password_hash`，返回布尔结果。
- bcrypt 生成的 hash 已包含算法版本、成本因子和随机 salt，不单独保存 salt。
- 密码最大长度为 72 UTF-8 bytes，不按字符数量计算。
- 哈希时遇到超长密码抛出明确错误，验证时遇到超长输入直接返回 `False`。
- 禁止截断密码，禁止记录原始密码或密码 hash 日志。

## 原因

- bcrypt 是专门用于密码存储的慢哈希算法，能够提高暴力破解成本。
- 随机 salt 保证相同密码每次生成不同 hash，避免通过相同 hash 识别相同密码。
- 集中安全能力可以避免 Repository、Router 和 Service 重复实现密码处理。

## 影响

- User Repository 只保存 `password_hash`，不负责哈希或验证密码。
- Register Service 在创建 User 前调用 `hash_password()`。
- Login Service 查询 User 后调用 `verify_password()`。
- Register 和 Login Schema 需要验证密码 UTF-8 编码后的长度不超过 72 bytes。
- 密码最小长度和其他业务规则在 Register Schema 设计阶段确定。

## 未采用方案

- 保存原始密码：数据库泄露后会直接暴露用户凭据。
- 可逆加密密码：应用持有的解密密钥一旦泄露，所有密码都可以被恢复。
- 直接截断超过 72 bytes 的密码：可能让不同密码产生相同有效输入。
- 当前引入 SHA-256 预处理：会增加组合算法和格式升级复杂度，留作未来密码算法升级方案评估。
