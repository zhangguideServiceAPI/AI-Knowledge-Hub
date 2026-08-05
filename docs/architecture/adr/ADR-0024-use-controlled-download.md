# ADR-0024: LocalStorage 与 MinIO 使用受控代理下载，预留短期 Signed URL

## 状态

已接受（2026-08-04，2026-08-05 补充 MinIO 决策）

## 背景

文件下载必须先验证当前用户是否拥有 `READY` 资源，同时不能向客户端暴露本地路径、Bucket、Object Key 或 Provider 凭据。LocalStorage 没有独立对象存储服务可签发 URL；未来 MinIO 可以生成 Presigned URL，但 URL 在有效期内属于临时授权凭据。

## 决策

- Story 3.6 的 LocalStorage 下载由 FastAPI 代理，使用 `StreamingResponse` 按 Chunk 输出。
- FileService 在打开对象前验证 `file_id + owner_id + READY + deleted_at IS NULL`。
- FileService 返回文件流和已校验 Metadata；Router 只构造 HTTP 流、MIME、长度和下载文件名。
- 文件流在响应完成或失败后关闭，不一次读取完整对象。
- 当前不向客户端返回 Object Key、本地路径或长期下载 URL。
- Story 3.7 的 MinIO 下载继续复用相同的 FastAPI 代理流，不扩展 Provider 的厂商特有接口。
- 当文件规模、下载并发或应用带宽数据证明代理流成为瓶颈时，再在权限验证后评估短期 Presigned URL。
- Presigned URL 不能替代业务权限检查，并且不得进入日志或使用过长 TTL。

## 原因

- LocalStorage 代理流可以在现有 Provider 能力上完成真实下载，不需要伪造 Signed URL 抽象。
- 权限检查发生在获得文件内容之前，其他用户与不存在资源统一返回 404。
- 分块读取限制单次业务内存占用，并适合当前 PDF、图片等文件资源。
- 保留结构化 `FileDownload` 结果，使 HTTP Header 不需要再次查询 Metadata，也不让 Service 返回 `StreamingResponse` 这类 Web 类型。
- Local 与 MinIO 共用一条下载业务流程，可以先验证 Provider 可替换性，不在没有容量数据时增加分支契约。

## 影响

- FastAPI 实例承担 LocalStorage 与当前 MinIO 下载的带宽和连接生命周期，不适合无限扩大文件规模。
- `Content-Disposition` 必须安全编码文件名，日志不得记录 Object Key、路径或 Signed URL。
- Metadata 存在但对象缺失时需要进入 `CLEANUP_REQUIRED`，不能持续把资源当作 READY。
- 当前 MinIO 的 `StreamingBody` 通过既有 `StreamingResponse` 分块输出，并在完成或异常后关闭。
- 未来 MinIO Presigned URL 会减少应用带宽，但客户端在 URL 过期前可以重复使用，因此必须使用短 TTL 并在签发前完成授权。

## 未采用方案

- 一次性 `read()` 后返回完整 `bytes`：大文件会放大内存占用。
- 直接暴露 LocalStorage 路径：泄露服务器结构，也绕过应用权限。
- 当前统一假设所有 Provider 都支持 Signed URL：LocalStorage 没有该能力，会造成过度抽象。
- 让 Router 直接调用 Provider：会绕过 FileService 的 Owner 权限和状态检查。
