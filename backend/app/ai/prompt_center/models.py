"""Prompt Center 对内提供的数据契约。

这里的类只描述数据，不负责读取文件、校验配置或渲染模板。把数据契约和业务逻辑
分开后，调用方只需要关心字段含义，不需要知道 Prompt 在磁盘上如何保存。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    """已经加载并校验、但尚未填充变量的 Prompt 模板。

    ``@dataclass`` 会根据下面声明的字段自动生成 ``__init__``、``__eq__`` 等方法；
    ``frozen=True`` 表示实例创建后不能再修改字段。这样，缓存中的模板不会被某次
    请求意外篡改。

    ``frozenset[str]`` 是不可变的字符串集合。变量顺序对契约没有意义，而不可变集合
    既能表达“不能重复”，也能避免缓存对象被修改。
    """

    prompt_key: str
    version: str
    required_variables: frozenset[str]
    template: str


@dataclass(frozen=True)
class RenderedPrompt:
    """一次 ``render()`` 调用得到的最终 Prompt。

    ``content`` 已经完成变量替换，可以由 ChatService 作为 SYSTEM 消息发送给
    AIGateway。保留 ``prompt_key`` 和 ``version``，是为了让业务层记录本次实际采用
    的模板身份，而不需要保存可能含敏感信息的 Prompt 正文。
    """

    prompt_key: str
    version: str
    content: str
