class StorageError(Exception):
    """所有存储 Provider 异常的基类."""


class InvalidObjectKeyError(StorageError):
    """Object Key 非法或试图逃出 Storage Root."""


class StorageObjectNotFoundError(StorageError):
    """指定对象不存在."""


class StorageOperationError(StorageError):
    """底层文件系统或 Provider 操作失败."""
