"""基于 tiktoken 的本地 Token 计数实现。"""

from functools import lru_cache

import tiktoken


class TokenizerNotAvailableError(ValueError):
    """配置的 tokenizer encoding 不存在或当前 tiktoken 版本不支持。"""


@lru_cache(maxsize=None)
def _get_encoding(encoding_name: str) -> tiktoken.Encoding:
    """按名称加载并缓存 tiktoken 编码表，避免每次计算 Token 都重复初始化。"""

    try:
        return tiktoken.get_encoding(encoding_name)
    except (OSError, ValueError) as error:
        # tiktoken 在本地还没有词表缓存时会下载 encoding；网络或缓存错误统一转为领域错误。
        raise TokenizerNotAvailableError(
            f"Tokenizer encoding is not available: {encoding_name}."
        ) from error


class TiktokenTokenCounter:
    """将指定 tiktoken encoding 适配为 Chunker 所需的 TokenCounter 能力。"""

    def __init__(self, *, encoding_name: str) -> None:
        """保存服务器配置的 encoding 名称，并在创建时尽早验证它可用。"""

        self._encoding_name = encoding_name
        # 此处主动加载，能在应用组装阶段发现错误，而非分块到一半才失败。
        _get_encoding(encoding_name)

    def count(self, text: str) -> int:
        """返回文本在当前 encoding 下的 Token 数；特殊标记按普通文本处理。"""

        # disallowed_special=() 避免用户文档中的 '<|...|>' 文本被误判为模型控制标记。
        return len(
            _get_encoding(self._encoding_name).encode(text, disallowed_special=())
        )
