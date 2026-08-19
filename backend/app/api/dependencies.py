from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from qdrant_client import AsyncQdrantClient
from sqlalchemy.orm import Session

from app.ai.embedding_gateway import EmbeddingGateway
from app.ai.factory import get_chat_provider, get_embedding_provider
from app.ai.gateway import AIGateway
from app.ai.prompt_center import PromptCenter, get_prompt_center
from app.knowledge import (
    ChunkingConfig,
    StructureAwareChunker,
    TiktokenTokenCounter,
    build_default_parser_registry,
    resolve_default_embedding_profile,
)
from app.knowledge.qdrant_vector_store import QdrantVectorStore
from app.knowledge.vector_store import VectorStore
from app.core.config import settings
from app.core.exceptions import InvalidAccessTokenError
from app.db.redis_client import redis_client
from app.db.repositories.session_repository import SessionRepository
from app.db.session import SessionLocal, get_db
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.knowledge_service import (
    KnowledgeIndexingComponents,
    KnowledgeService,
)
from app.services.login_rate_limiter import LoginRateLimiter
from app.storage.factory import get_storage_bucket, get_storage_provider
from app.storage.provider import StorageProvider
from app.services.chat_service import ChatService

bearer_scheme = HTTPBearer(auto_error=False)


def get_access_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> str:
    if credentials is None:
        raise InvalidAccessTokenError()

    return credentials.credentials


def get_session_repository() -> SessionRepository:
    return SessionRepository(redis_client)


def get_current_user(
    token: Annotated[str, Depends(get_access_token)],
    session: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    return AuthService(session).get_current_user(token)


def get_login_rate_limiter() -> LoginRateLimiter:
    return LoginRateLimiter(
        client=redis_client,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    )


def get_file_service(
    session: Annotated[Session, Depends(get_db)],
    storage_provider: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> FileService:
    return FileService(
        session,
        storage_provider,
        storage_provider_name=settings.STORAGE_PROVIDER,
        bucket=get_storage_bucket(),
        max_upload_size=settings.MAX_UPLOAD_SIZE_BYTES,
        chunk_size=settings.UPLOAD_CHUNK_SIZE_BYTES,
    )


def get_knowledge_service(
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeService:
    """用请求级数据库 Session 创建 KnowledgeService，供知识库 API 注入。"""

    return KnowledgeService(session)


async def get_knowledge_indexing_components(
    storage_provider: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> AsyncIterator[KnowledgeIndexingComponents]:
    """
    从 Settings、Storage Provider 与 Qdrant Client 组装知识索引运行时组件。

    此函数是 Token、Chunk、Embedding Profile 与 VectorStore 的唯一服务器来源；
    客户端不能自行选择这些索引配置。AsyncQdrantClient 是请求级资源，离开请求后
    无论业务成功或失败都会关闭其 HTTP 连接；本函数本身不向 Qdrant 执行写入。
    """

    embedding_profile = resolve_default_embedding_profile(
        model_configs=settings.EMBEDDING_MODELS,
        default_model_alias=settings.EMBEDDING_DEFAULT_MODEL_ALIAS,
    )
    chunking_config = ChunkingConfig(
        max_tokens=settings.KNOWLEDGE_CHUNK_MAX_TOKENS,
        overlap_tokens=settings.KNOWLEDGE_CHUNK_OVERLAP_TOKENS,
    )
    token_counter = TiktokenTokenCounter(
        encoding_name=embedding_profile.tokenizer_encoding,
    )
    chunker = StructureAwareChunker(
        config=chunking_config,
        token_counter=token_counter,
    )
    qdrant_client = AsyncQdrantClient(
        url=str(settings.QDRANT_URL),
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )
    vector_store: VectorStore = QdrantVectorStore(
        client=qdrant_client,
        collection_name=settings.QDRANT_COLLECTION_NAME,
        vector_dimension=embedding_profile.dimension,
    )
    components = KnowledgeIndexingComponents(
        storage_provider=storage_provider,
        parser_registry=build_default_parser_registry(),
        chunker=chunker,
        chunking_config=chunking_config,
        embedding_profile=embedding_profile,
        embedding_batch_size=settings.KNOWLEDGE_EMBEDDING_BATCH_SIZE,
        embedding_gateway=EmbeddingGateway(
            model_configs=settings.EMBEDDING_MODELS,
            default_model_alias=settings.EMBEDDING_DEFAULT_MODEL_ALIAS,
            provider_factory=get_embedding_provider,
            total_deadline_seconds=settings.AI_TOTAL_DEADLINE_SECONDS,
        ),
        vector_store=vector_store,
    )
    try:
        yield components
    finally:
        # AsyncQdrantClient 持有 HTTP 连接池；请求结束必须关闭，避免长期运行时泄漏连接。
        await qdrant_client.close()


def get_ai_gateway() -> AIGateway:
    return AIGateway(
        model_configs=settings.AI_MODELS,
        default_model_alias=settings.AI_DEFAULT_MODEL_ALIAS,
        provider_factory=get_chat_provider,
        max_retry_attempts=settings.AI_MAX_RETRY_ATTEMPTS,
        retry_backoff_seconds=settings.AI_RETRY_BACKOFF_SECONDS,
        total_deadline_seconds=settings.AI_TOTAL_DEADLINE_SECONDS,
        stream_idle_timeout_seconds=(settings.AI_STREAM_IDLE_TIMEOUT_SECONDS),
        stream_total_deadline_seconds=(settings.AI_STREAM_TOTAL_DEADLINE_SECONDS),
    )


def get_usage_session_factory() -> Callable[[], Session]:
    """返回短事务 Session 工厂，并允许测试替换为隔离数据库。"""

    return SessionLocal


def get_chat_service(
    # FastAPI 先解析三个 Depends，再把结果作为参数注入此函数。
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
    prompt_center: Annotated[
        PromptCenter,
        Depends(get_prompt_center),
    ],
    usage_session_factory: Annotated[
        Callable[[], Session],
        Depends(get_usage_session_factory),
    ],
) -> ChatService:
    return ChatService(
        gateway,
        prompt_center,
        usage_session_factory=usage_session_factory,
        model_configs=settings.AI_MODELS,
        default_model_alias=settings.AI_DEFAULT_MODEL_ALIAS,
    )
