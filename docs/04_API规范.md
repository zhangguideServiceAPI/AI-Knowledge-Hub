# 04 API 规范

## Health Check

健康检查分为 Liveness 和 Readiness。Liveness 只表示 FastAPI 进程可以响应，Readiness 表示应用所需依赖已经可用。

### Liveness

```http
GET /health/live
```

成功响应：HTTP 200

```json
{
  "status": "ok"
}
```

Liveness 不访问 MySQL、Redis 等外部依赖。请求超时、连接失败或非 2xx 状态均表示当前实例不存活。

### Readiness

```http
GET /health/ready
```

依赖正常：HTTP 200

```json
{
  "status": "ready",
  "database": "ok"
}
```

必要依赖不可用：HTTP 503

```json
{
  "status": "not_ready",
  "database": "unavailable"
}
```

Jenkins 蓝绿发布使用 Readiness 判断新实例是否可以接收流量。未来 Kubernetes 分别使用 Liveness 和 Readiness 探针。
