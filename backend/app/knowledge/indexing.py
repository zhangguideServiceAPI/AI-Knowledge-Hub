"""索引处理配置的稳定标识计算。"""

import json
from collections.abc import Mapping
from hashlib import sha256

from app.knowledge.embedding import EmbeddingProfile


# 指纹的 JSON 结构或字段语义改变时提升版本，避免旧规则与新规则意外碰撞。
_PROCESSING_FINGERPRINT_SCHEMA_VERSION = "v1"
_SHA256_HEX_LENGTH = 64
_SHA256_HEX_CHARACTERS = frozenset("0123456789abcdef")


class ProcessingFingerprintInputError(ValueError):
    """构建处理指纹时收到空值、非法文件摘要或不可序列化配置。"""


def build_processing_fingerprint(
    *,
    file_sha256: str,
    parser_name: str,
    parser_version: str,
    chunker_name: str,
    chunker_config: Mapping[str, object],
    embedding_profile: EmbeddingProfile,
) -> str:
    """
    根据文件内容和完整处理配置生成稳定的 SHA-256 指纹。

    输入来自 FileResource、Parser、Chunker 和服务器内部 EmbeddingProfile；
    返回 64 位十六进制字符串，供同一 Document 判断 Version 是否可复用。
    该函数没有 I/O 或数据库副作用，不能由 API 客户端直接决定其结果。
    """

    _validate_file_sha256(file_sha256)
    _require_non_blank("parser_name", parser_name)
    _require_non_blank("parser_version", parser_version)
    _require_non_blank("chunker_name", chunker_name)

    payload = {
        "schema_version": _PROCESSING_FINGERPRINT_SCHEMA_VERSION,
        "file_sha256": file_sha256,
        "parser": {
            "name": parser_name,
            "version": parser_version,
        },
        "chunker": {
            "name": chunker_name,
            # dict(...) 固化 Mapping 当前的键值，避免调用方随后修改其外层映射。
            "config": dict(chunker_config),
        },
        "embedding": embedding_profile.fingerprint_payload(),
    }
    try:
        # sort_keys 与紧凑分隔符让相同配置总得到完全相同的字节序列。
        serialized_payload = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ProcessingFingerprintInputError(
            "Processing configuration must be JSON serializable."
        ) from error

    return sha256(serialized_payload.encode("utf-8")).hexdigest()


def _validate_file_sha256(file_sha256: str) -> None:
    """确认 FileResource 摘要是 64 位小写十六进制 SHA-256 字符串。"""

    if len(file_sha256) != _SHA256_HEX_LENGTH or not set(file_sha256).issubset(
        _SHA256_HEX_CHARACTERS
    ):
        raise ProcessingFingerprintInputError(
            "File SHA-256 must be a 64-character lowercase hexadecimal string."
        )


def _require_non_blank(field_name: str, value: str) -> None:
    """拒绝参与指纹的空白身份字段，避免不同无效配置产生可复用指纹。"""

    if not value.strip():
        raise ProcessingFingerprintInputError(f"{field_name} must not be blank.")
