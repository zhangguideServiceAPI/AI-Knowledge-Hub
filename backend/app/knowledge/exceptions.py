class KnowledgeBaseNotFoundError(Exception):
    """KnowledgeBase does not exist or does not belong to the current user."""


class KnowledgeBaseWriteError(Exception):
    """KnowledgeBase metadata could not be committed to the database."""


class KnowledgeDocumentWriteError(Exception):
    """KnowledgeDocument metadata could not be committed to the database."""


class KnowledgeDocumentNotFoundError(Exception):
    """KnowledgeDocument does not exist or is outside the current user's scope."""


class KnowledgeVersionWriteError(Exception):
    """DocumentVersion or its chunks could not be committed."""


class KnowledgeVersionNotFoundError(Exception):
    """DocumentVersion does not exist or is outside the current user's document scope."""


class KnowledgeVersionRetryError(Exception):
    """DocumentVersion cannot be retried safely because vector cleanup is unavailable."""


class VectorStoreInputError(Exception):
    """写入向量库的 Point、向量维度或 Version ID 不符合存储契约。"""


class VectorStoreUnavailableError(Exception):
    """向量数据库暂时不可连接、超时或无法处理响应。"""


class VectorStoreOperationError(Exception):
    """向量库拒绝执行写入、删除或 Collection 初始化操作。"""


class VectorStoreConfigurationError(Exception):
    """已存在的 Collection 配置与当前 Embedding 模型维度不兼容。"""


class VectorStoreCleanupRequiredError(Exception):
    """向量写入失败后，按 DocumentVersion 清理已写入向量也失败。"""
