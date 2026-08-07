class ProviderError(Exception):
    """所有可预期 AI 模型 Provider 调用异常的基类。"""


class ProviderRateLimitError(ProviderError):
    """Provider 因速率、并发或配额限制拒绝本次调用。"""


class ProviderTimeoutError(ProviderError):
    """连接 Provider、等待响应或读取结果时超过允许时间。"""


class ProviderUnavailableError(ProviderError):
    """Provider 因网络故障或服务异常暂时无法完成调用。"""


class ProviderStreamError(ProviderError):
    """Provider 流已经建立，但在正常终态前异常中断。"""
