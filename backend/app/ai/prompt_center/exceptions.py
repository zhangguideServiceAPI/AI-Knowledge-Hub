"""Prompt Center 的独立异常体系。

这些异常不继承 ``AIError`` 或 ``ProviderError``。Prompt 文件和变量的问题发生在
调用模型之前，不属于模型供应商故障，因此应由上层单独映射和记录。

调用方通常只捕获 ``PromptError``；需要区分配置故障、模板不存在或变量错误时，
再捕获具体子类。异常消息必须保持通用，不能包含 Prompt 正文、变量值或磁盘路径。
"""


class PromptError(Exception):
    """所有可预期 Prompt Center 异常的基类，便于上层统一捕获。"""


class PromptNotFoundError(PromptError):
    """指定的 Prompt Key 不存在，或 Key 的格式不符合安全规则。"""


class PromptVersionNotFoundError(PromptError):
    """Prompt Key 存在，但指定版本不存在或版本格式不合法。"""


class PromptConfigurationError(PromptError):
    """Prompt 目录、元数据或模板配置不一致，属于服务端配置故障。"""


class PromptVariableError(PromptError):
    """渲染变量缺少、多余或不是字符串，属于调用方违反模板契约。"""
