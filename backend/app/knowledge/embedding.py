"""Embedding 模型配置在 Knowledge 域中的不可变运行时快照。"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.core.config import EmbeddingModelConfig


class EmbeddingProfileNotConfiguredError(ValueError):
    """当前环境没有为知识索引配置默认 Embedding 模型。"""


@dataclass(frozen=True)
class EmbeddingProfile:
    """一次索引所使用的 Embedding 模型身份与向量维度快照。"""

    alias: str
    provider_key: str
    provider_model: str
    dimension: int

    def fingerprint_payload(self) -> dict[str, object]:
        """
        返回参与 processing_fingerprint 计算的稳定 Embedding 配置。

        该值由 Service 与文件、Parser、Chunker 配置一起序列化并哈希；
        因此同一个 alias 改到不同 Provider 模型时，也会形成新的 Version。
        """

        return {
            "alias": self.alias,
            "provider_key": self.provider_key,
            "provider_model": self.provider_model,
            "dimension": self.dimension,
        }


def resolve_default_embedding_profile(
    *,
    model_configs: Mapping[str, EmbeddingModelConfig],
    default_model_alias: str | None,
) -> EmbeddingProfile:
    """
    从服务器已校验的 Embedding 配置中解析默认 Profile。

    输入是 Settings 提供的模型注册表与默认别名；返回不可变 Profile。
    当前没有默认配置时抛出明确异常，防止未来索引误用未声明的模型或维度。
    """

    if default_model_alias is None:
        raise EmbeddingProfileNotConfiguredError(
            "No default embedding model is configured."
        )

    model_config = model_configs.get(default_model_alias)
    if model_config is None:
        # Settings 理论上已阻止此状态；保留防御性检查，支持独立调用或测试注入。
        raise EmbeddingProfileNotConfiguredError(
            "The default embedding model is not registered."
        )

    return EmbeddingProfile(
        alias=default_model_alias,
        provider_key=model_config.provider_key,
        provider_model=model_config.provider_model,
        dimension=model_config.dimension,
    )
