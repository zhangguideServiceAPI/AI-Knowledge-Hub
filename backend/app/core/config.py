from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

JwtKeyId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    ),
]

JwtSigningSecret = Annotated[
    SecretStr,
    Field(min_length=32),
]


class AIProviderConfig(BaseModel):
    provider_type: Literal["openai_compatible"]
    api_key: SecretStr = Field(min_length=1)
    base_url: AnyHttpUrl
    connect_timeout_seconds: PositiveFloat = 5.0
    read_timeout_seconds: PositiveFloat = 60.0


AIModelAlias = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    ),
]


EmbeddingModelAlias = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    ),
]


class AIModelPricingConfig(BaseModel):
    """某个模型在指定价格版本下的成本配置。"""

    # 单价统一按一百万 Token 表达；Decimal 避免金额先经过二进制 float。
    input_price_per_million_tokens: Decimal = Field(ge=0)
    output_price_per_million_tokens: Decimal = Field(ge=0)
    currency: str = Field(
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )
    version: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )


class AIModelConfig(BaseModel):
    # 关联哪个 Provider
    provider_key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    # Provider 使用的真实模型名
    provider_model: str = Field(
        min_length=1,
        max_length=128,
    )
    # 客户端未提交时的默认值
    default_temperature: float = Field(
        ge=0.0,
        le=2.0,
    )
    default_max_output_tokens: PositiveInt  # 客户端未提交时的默认输出预算
    max_output_tokens: PositiveInt  # 服务端允许的最大输出预算
    context_window_tokens: PositiveInt  # 输入与输出共同使用的上下文上限
    # 未配置 Pricing 或 Provider 没有返回完整 Token 时，Usage 成本保持未知。
    pricing: AIModelPricingConfig | None = None

    @model_validator(mode="after")
    def validate_token_limits(self) -> Self:
        if self.default_max_output_tokens > self.max_output_tokens:
            raise ValueError(
                "default_max_output_tokens must be less than or equal "
                "to max_output_tokens."
            )

        if self.max_output_tokens >= self.context_window_tokens:
            raise ValueError(
                "max_output_tokens must be less than context_window_tokens."
            )

        return self


class EmbeddingModelConfig(BaseModel):
    """一个可用于知识索引的 Embedding 模型配置。"""

    # Embedding 与 Chat 共用已配置的 AI Provider；它们只是在 Provider 侧使用不同模型。
    provider_key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    provider_model: str = Field(min_length=1, max_length=128)
    # tiktoken 的编码表名称，例如 cl100k_base；不能从 Provider 模型名猜测。
    tokenizer_encoding: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    # 向量维度是 Qdrant Collection 与 DocumentVersion 的固定契约，必须为正数。
    dimension: PositiveInt


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "AI Knowledge Hub"
    APP_ENV: str = "dev"

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "ai_knowledge_hub"

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535)
    REDIS_DB: int = Field(default=0, ge=0)
    REDIS_PASSWORD: SecretStr = Field(min_length=16)
    REDIS_CONNECT_TIMEOUT_SECONDS: PositiveFloat = 1.0
    REDIS_SOCKET_TIMEOUT_SECONDS: PositiveFloat = 1.0

    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: PositiveInt = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: PositiveInt = 60

    JWT_ACTIVE_KEY_ID: JwtKeyId
    JWT_SIGNING_KEYS: dict[JwtKeyId, JwtSigningSecret] = Field(
        min_length=1,
    )
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: PositiveInt = 30

    SESSION_EXPIRATION_MODE: Literal["absolute", "sliding"] = "absolute"
    SESSION_TTL_DAYS: PositiveInt = 7
    SESSION_ABSOLUTE_MAX_DAYS: PositiveInt = 30

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    STORAGE_PROVIDER: Literal["local", "minio"] = "local"
    STORAGE_LOCAL_ROOT: Path = Path("./data/storage")
    STORAGE_MINIO_ENDPOINT: AnyHttpUrl | None = None
    STORAGE_MINIO_ACCESS_KEY: str | None = Field(
        default=None,
        min_length=3,
    )
    STORAGE_MINIO_SECRET_KEY: SecretStr | None = Field(
        default=None,
        min_length=8,
    )
    STORAGE_MINIO_BUCKET: str | None = Field(
        default=None,
        min_length=3,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$",
    )
    MAX_UPLOAD_SIZE_BYTES: PositiveInt = 20 * 1024 * 1024
    UPLOAD_CHUNK_SIZE_BYTES: PositiveInt = 1024 * 1024

    AI_PROVIDERS: dict[str, AIProviderConfig] = Field(
        default_factory=dict,
    )

    AI_DEFAULT_MODEL_ALIAS: AIModelAlias | None = None

    AI_MODELS: dict[AIModelAlias, AIModelConfig] = Field(
        default_factory=dict,
    )

    # Embedding 模型与 Chat 模型配置分开：两者用途、Token 计费和输出类型不同。
    # None/空字典允许尚未进入索引阶段的环境正常启动。
    EMBEDDING_DEFAULT_MODEL_ALIAS: EmbeddingModelAlias | None = None
    EMBEDDING_MODELS: dict[EmbeddingModelAlias, EmbeddingModelConfig] = Field(
        default_factory=dict,
    )

    # 分块大小来自服务器配置，避免 Router、Service 或 Chunker 内散落魔法数字。
    KNOWLEDGE_CHUNK_MAX_TOKENS: PositiveInt = 800
    KNOWLEDGE_CHUNK_OVERLAP_TOKENS: int = Field(default=120, ge=0)
    # 一次发送给 Embedding Provider 的 Chunk 数；批大小不改变向量内容，因此不参与 Version 指纹。
    KNOWLEDGE_EMBEDDING_BATCH_SIZE: PositiveInt = 32
    # 一次写入 Qdrant 的 Point 数；它独立于模型 API 限制，也不参与 Version 指纹。
    KNOWLEDGE_VECTOR_UPSERT_BATCH_SIZE: PositiveInt = 128
    # 每次公开检索最多返回的有效 Chunk；客户端不能自行放大 Context 与 Provider 成本。
    KNOWLEDGE_RETRIEVAL_TOP_K: PositiveInt = 5
    # 因为 Qdrant 候选仍须被 MySQL 的 active Version 校验，先额外获取候选以减少过滤后的空洞。
    KNOWLEDGE_RETRIEVAL_CANDIDATE_MULTIPLIER: PositiveInt = 4
    # 当前 Collection 使用 Cosine 距离，分数范围为 [-1, 1]；低于阈值的候选不返回。
    KNOWLEDGE_RETRIEVAL_SCORE_THRESHOLD: float = Field(
        default=0.2,
        ge=-1.0,
        le=1.0,
    )

    # Qdrant 是独立的向量检索服务；业务真相仍保存在 MySQL。
    QDRANT_URL: AnyHttpUrl = "http://127.0.0.1:6333"
    # Collection 名是所有 Knowledge Chunk 向量的物理容器，不能由客户端指定。
    QDRANT_COLLECTION_NAME: str = Field(
        default="knowledge_chunks",
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    QDRANT_TIMEOUT_SECONDS: PositiveFloat = 5.0

    # ge=0：greater than or equal，必须 >= 0
    # le=3：less than or equal，必须 <= 3
    # gt=0.0：greater than，必须 > 0.0
    # 表示首次调用失败后还能重试几次；1 代表 Provider 最多被调用两次。
    AI_MAX_RETRY_ATTEMPTS: int = Field(default=1, ge=0, le=3)

    # 两次 Provider 调用之间的基础等待时间。
    AI_RETRY_BACKOFF_SECONDS: float = Field(
        default=0.2,
        ge=0.0,
        le=5.0,
    )

    # 包含首次调用、等待和所有重试在内的总时间上限。
    AI_TOTAL_DEADLINE_SECONDS: float = Field(
        default=65.0,
        gt=0.0,
        le=300.0,
    )

    # 流式：
    # 等待下一个 Event 的上限
    AI_STREAM_IDLE_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
    )
    # 整条流的硬上限
    AI_STREAM_TOTAL_DEADLINE_SECONDS: float = Field(
        default=300.0,
        gt=0.0,
        le=1800.0,
    )

    @model_validator(mode="after")
    def validate_session_expiration(self) -> Self:
        if (
            self.SESSION_EXPIRATION_MODE == "sliding"
            and self.SESSION_ABSOLUTE_MAX_DAYS < self.SESSION_TTL_DAYS
        ):
            raise ValueError(
                "SESSION_ABSOLUTE_MAX_DAYS must be greater than or equal "
                "to SESSION_TTL_DAYS in sliding mode."
            )

        return self

    @model_validator(mode="after")
    def validate_jwt_key_ring(self) -> Self:
        if self.JWT_ACTIVE_KEY_ID not in self.JWT_SIGNING_KEYS:
            raise ValueError("JWT_ACTIVE_KEY_ID must exist in JWT_SIGNING_KEYS.")

        return self

    @model_validator(mode="after")
    def chunk_upload_config(self) -> Self:
        if self.UPLOAD_CHUNK_SIZE_BYTES > self.MAX_UPLOAD_SIZE_BYTES:
            raise ValueError(
                "UPLOAD_CHUNK_SIZE_BYTES must be less than or equal to "
                "MAX_UPLOAD_SIZE_BYTES."
            )

        return self

    @model_validator(mode="after")
    def validate_minio_config(self) -> Self:
        if self.STORAGE_PROVIDER != "minio":
            return self

        required_fields = {
            "STORAGE_MINIO_ENDPOINT": self.STORAGE_MINIO_ENDPOINT,
            "STORAGE_MINIO_ACCESS_KEY": self.STORAGE_MINIO_ACCESS_KEY,
            "STORAGE_MINIO_SECRET_KEY": self.STORAGE_MINIO_SECRET_KEY,
            "STORAGE_MINIO_BUCKET": self.STORAGE_MINIO_BUCKET,
        }
        missing_fields = [
            field_name for field_name, value in required_fields.items() if value is None
        ]

        if missing_fields:
            raise ValueError("MinIO storage requires: " + ", ".join(missing_fields))

        return self

    @model_validator(mode="after")
    def validate_ai_model_registry(self) -> Self:
        """校验 Chat 与 Embedding 模型别名均引用已配置的 AI Provider。"""

        if (
            self.AI_DEFAULT_MODEL_ALIAS is not None
            and self.AI_DEFAULT_MODEL_ALIAS not in self.AI_MODELS
        ):
            raise ValueError("AI_DEFAULT_MODEL_ALIAS must exist in AI_MODELS.")

        for model_alias, model_config in self.AI_MODELS.items():
            if model_config.provider_key not in self.AI_PROVIDERS:
                raise ValueError(
                    f"AI_MODELS[{model_alias!r}].provider_key "
                    "must exist in AI_PROVIDERS."
                )

        if (
            self.EMBEDDING_DEFAULT_MODEL_ALIAS is not None
            and self.EMBEDDING_DEFAULT_MODEL_ALIAS not in self.EMBEDDING_MODELS
        ):
            raise ValueError(
                "EMBEDDING_DEFAULT_MODEL_ALIAS must exist in EMBEDDING_MODELS."
            )

        for model_alias, model_config in self.EMBEDDING_MODELS.items():
            if model_config.provider_key not in self.AI_PROVIDERS:
                raise ValueError(
                    f"EMBEDDING_MODELS[{model_alias!r}].provider_key "
                    "must exist in AI_PROVIDERS."
                )

        return self

    @model_validator(mode="after")
    def validate_ai_stream_timeouts(self) -> Self:
        if self.AI_STREAM_TOTAL_DEADLINE_SECONDS < self.AI_STREAM_IDLE_TIMEOUT_SECONDS:
            raise ValueError(
                "AI_STREAM_TOTAL_DEADLINE_SECONDS must be greater than "
                "or equal to AI_STREAM_IDLE_TIMEOUT_SECONDS."
            )

        return self

    @model_validator(mode="after")
    def validate_knowledge_chunking_config(self) -> Self:
        """确认 overlap 小于单个 Chunk 上限，避免生成完全重复的分块。"""

        if self.KNOWLEDGE_CHUNK_OVERLAP_TOKENS >= self.KNOWLEDGE_CHUNK_MAX_TOKENS:
            raise ValueError(
                "KNOWLEDGE_CHUNK_OVERLAP_TOKENS must be less than "
                "KNOWLEDGE_CHUNK_MAX_TOKENS."
            )

        return self

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
