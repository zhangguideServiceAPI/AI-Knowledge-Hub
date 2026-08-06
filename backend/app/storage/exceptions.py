class StorageError(Exception):
    """所有存储 Provider 异常的基类."""


class InvalidObjectKeyError(StorageError):
    """Object Key 非法或试图逃出 Storage Root."""


class StorageObjectNotFoundError(StorageError):
    """指定对象不存在."""


class StorageOperationError(StorageError):
    """底层文件系统或 Provider 操作失败."""


class InvalidFileNameError(Exception):
    """文件展示名称不符合上传规则，对外映射为 400."""


class EmptyFileError(Exception):
    """上传内容为空，对外映射为 400."""


class FileTooLargeError(Exception):
    """实际上传字节超过大小限制，对外映射为 413."""


class UnsupportedFileTypeError(Exception):
    """MIME、扩展名或文件签名不符合策略，对外映射为 415."""


class StorageUnavailableError(Exception):
    """Provider 暂时不可用，对外映射为 503."""


class FileUploadFailedError(Exception):
    """数据库提交或补偿流程发生内部故障，对外映射为 500."""


class FileResourceNotFoundError(Exception):
    """文件不存在，或当前用户无权访问。"""


class FileDeleteFailedError(Exception):
    """文件删除的数据库状态提交或补偿流程失败。"""


class FileContentUnavailableError(Exception):
    """Metadata 存在，但对应的文件内容不可用。"""


class FileCleanupFailedError(Exception):
    """文件清理的数据库状态提交或补偿流程失败。"""
