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


class AIError(Exception):
    """AI Gateway 对业务层暴露的稳定异常基类。"""


class AIInvalidModelError(AIError):
    """请求的模型别名不存在或没有可用默认模型。"""


class AIInvalidRequestError(AIError):
    """AI 请求中的生成参数不符合服务端策略。"""


class AIProviderError(AIError):
    """AI Provider 调用失败的稳定领域异常基类。"""


class AIProviderRateLimitError(AIProviderError):
    """AI Provider 暂时拒绝请求，通常由速率或配额限制导致。"""


class AIProviderTimeoutError(AIProviderError):
    """AI Provider 调用超过 Gateway 允许的时间。"""


class AIProviderUnavailableError(AIProviderError):
    """AI Provider 当前无法完成调用。"""
