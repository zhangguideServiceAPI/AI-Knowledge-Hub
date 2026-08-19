"""Qdrant 对 Knowledge VectorStore 协议的异步实现。"""

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.knowledge.exceptions import (
    VectorStoreConfigurationError,
    VectorStoreInputError,
    VectorStoreOperationError,
    VectorStoreUnavailableError,
)
from app.knowledge.vector_store import VectorPoint

_KNOWLEDGE_BASE_PAYLOAD_KEY = "knowledge_base_id"
_DOCUMENT_VERSION_PAYLOAD_KEY = "document_version_id"


class QdrantVectorStore:
    """
    将 Knowledge 域的 VectorPoint 转换为 Qdrant Point 与 payload 操作。

    Service 只依赖 VectorStore 协议；本类是唯一理解 Qdrant Collection、Point 与
    Filter SDK 类型的地方。一个实例绑定一个 Collection 和固定向量维度，不能混用
    不同 Embedding 模型维度的版本。
    """

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection_name: str,
        vector_dimension: int,
    ) -> None:
        """
        保存已配置的异步 Client、Collection 名和 Embedding 固定维度。

        此方法不进行网络 I/O；Collection 的创建或维度核对延迟到首次 `upsert()`，
        使应用启动不因暂时未启动 Qdrant 而失败。
        """

        if not collection_name.strip() or vector_dimension <= 0:
            raise VectorStoreInputError(
                "Collection name must be non-empty and vector dimension must be positive."
            )

        self._client = client
        self._collection_name = collection_name
        self._vector_dimension = vector_dimension
        self._collection_initialized = False

    async def upsert(self, *, points: tuple[VectorPoint, ...]) -> None:
        """
        新建或覆盖一批以 Chunk ID 为稳定标识的 Qdrant 向量点。

        输入的所有向量必须与构造时的维度一致；空批次不执行网络请求。
        首次写入会创建 Collection 并建立过滤 payload 索引。网络、超时和 Qdrant
        响应异常会转换为稳定 Knowledge 异常，调用方无需理解 SDK 异常。
        """

        if not points:
            return

        self._validate_points(points)
        await self._ensure_collection()
        try:
            await self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    models.PointStruct(
                        id=point.chunk_id,
                        vector=list(point.vector),
                        payload={
                            _KNOWLEDGE_BASE_PAYLOAD_KEY: point.knowledge_base_id,
                            _DOCUMENT_VERSION_PAYLOAD_KEY: point.document_version_id,
                        },
                    )
                    for point in points
                ],
                wait=True,
            )
        except ResponseHandlingException as error:
            raise VectorStoreUnavailableError(
                "Qdrant upsert request failed."
            ) from error
        except UnexpectedResponse as error:
            raise VectorStoreOperationError(
                "Qdrant rejected vector point upsert."
            ) from error

    async def delete_by_document_version(self, *, document_version_id: str) -> None:
        """
        删除一个 DocumentVersion 已写入的全部 Qdrant 向量点。

        输入是需要补偿或删除的 Version ID；当 Collection 尚不存在时，说明尚未写入
        任何点，因此直接成功返回。删除失败必须抛出异常，由未来 Service 标记
        `cleanup_required`，不能错误地声明清理完成。
        """

        if not document_version_id.strip():
            raise VectorStoreInputError("Document version ID must be non-empty.")

        try:
            if not await self._client.collection_exists(
                collection_name=self._collection_name
            ):
                return
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key=_DOCUMENT_VERSION_PAYLOAD_KEY,
                                match=models.MatchValue(value=document_version_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except ResponseHandlingException as error:
            raise VectorStoreUnavailableError(
                "Qdrant delete request failed."
            ) from error
        except UnexpectedResponse as error:
            raise VectorStoreOperationError(
                "Qdrant rejected version cleanup."
            ) from error

    def _validate_points(self, points: tuple[VectorPoint, ...]) -> None:
        """
        确认 Point ID、过滤 metadata 与向量长度可安全写入固定维度 Collection。

        这是纯内存校验，不访问 Qdrant；尽早拒绝错误输入，防止一个批次中出现部分点
        成功、部分点因无效 ID 或维度失败的难以补偿状态。
        """

        for point in points:
            if not (
                point.chunk_id.strip()
                and point.knowledge_base_id.strip()
                and point.document_version_id.strip()
            ):
                raise VectorStoreInputError(
                    "Chunk, knowledge base, and document version IDs must be non-empty."
                )
            if len(point.vector) != self._vector_dimension:
                raise VectorStoreInputError(
                    "Vector dimension does not match the configured Qdrant collection."
                )

    async def _ensure_collection(self) -> None:
        """
        创建或核对当前 Collection 的向量维度和检索过滤索引。

        同时到达的两个索引流程都可能尝试创建 Collection；若其中一个已创建成功，
        另一个会重新读取并继续校验。已有 Collection 的维度不同则明确失败，避免
        破坏旧模型对应的向量空间。
        """

        if self._collection_initialized:
            return

        try:
            exists = await self._client.collection_exists(
                collection_name=self._collection_name
            )
            if not exists:
                try:
                    await self._client.create_collection(
                        collection_name=self._collection_name,
                        vectors_config=models.VectorParams(
                            size=self._vector_dimension,
                            distance=models.Distance.COSINE,
                        ),
                    )
                except UnexpectedResponse:
                    # 可能是并发调用已经建好 Collection；下一次读取决定是否可继续。
                    if not await self._client.collection_exists(
                        collection_name=self._collection_name
                    ):
                        raise

            collection = await self._client.get_collection(
                collection_name=self._collection_name
            )
            vectors_config = collection.config.params.vectors
            if (
                not isinstance(vectors_config, models.VectorParams)
                or vectors_config.size != self._vector_dimension
            ):
                raise VectorStoreConfigurationError(
                    "Qdrant collection vector dimension does not match the embedding model."
                )

            for payload_key in (
                _KNOWLEDGE_BASE_PAYLOAD_KEY,
                _DOCUMENT_VERSION_PAYLOAD_KEY,
            ):
                await self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=payload_key,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
        except ResponseHandlingException as error:
            raise VectorStoreUnavailableError(
                "Qdrant collection initialization request failed."
            ) from error
        except UnexpectedResponse as error:
            raise VectorStoreOperationError(
                "Qdrant rejected collection initialization."
            ) from error

        self._collection_initialized = True
