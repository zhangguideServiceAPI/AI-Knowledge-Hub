from collections.abc import Mapping
from dataclasses import dataclass
from typing import BinaryIO, ClassVar, Protocol


# type 是 Python 3.12+ 的类型别名语法；它只帮助类型检查，不会创建运行时对象。
type SourceLocator = dict[str, object]


class ParsingError(ValueError):
    """Base error for parser input or output failures."""


class UnsupportedContentTypeError(ParsingError):
    """Raised when no parser supports the requested content type."""


class InvalidDocumentError(ParsingError):
    """Raised when a document cannot be decoded or structurally read."""


class NoParseableTextError(ParsingError):
    """Raised when a valid container contains no usable text."""


# dataclass 自动生成构造方法；frozen=True 禁止创建后重新赋值字段，
# 让解析结果在传给 Chunker 后不被意外替换。
@dataclass(frozen=True)
class ParsedBlock:
    """One parser-produced block that retains enough information for citation."""

    text: str
    block_index: int
    source_locator: SourceLocator

    # dataclass 会在自动生成的 __init__ 完成字段赋值后自动调用 __post_init__。
    # 这里集中校验内存中的契约，避免无效 Block 进入后续 Chunker 或数据库。
    def __post_init__(self) -> None:
        """校验单个解析块的文本、顺序索引和 Citation 来源都有效。"""

        if not self.text.strip():
            raise ValueError("Parsed block text must not be empty.")
        if self.block_index < 0:
            raise ValueError("Parsed block index must not be negative.")
        if not self.source_locator:
            raise ValueError("Parsed block source locator must not be empty.")


# ParsedDocument 也保持创建后不可重新赋值，确保 Parser 输出可稳定追溯。
@dataclass(frozen=True)
class ParsedDocument:
    """Format-neutral parser output consumed by the future Chunker."""

    blocks: tuple[ParsedBlock, ...]
    metadata: Mapping[str, object]
    parser_name: str
    parser_version: str

    # __post_init__ 不是另一个手动调用的方法；构造 ParsedDocument 时会自动执行。
    def __post_init__(self) -> None:
        """校验解析结果至少包含一个连续编号的块及 Parser 身份信息。"""

        if not self.blocks:
            raise ValueError("Parsed document must contain at least one block.")
        if tuple(block.block_index for block in self.blocks) != tuple(
            range(len(self.blocks))
        ):
            raise ValueError("Parsed block indexes must be contiguous and zero-based.")
        if not self.parser_name.strip():
            raise ValueError("Parser name must not be empty.")
        if not self.parser_version.strip():
            raise ValueError("Parser version must not be empty.")


class DocumentParser(Protocol):
    """Capability boundary shared by PDF, Markdown, TXT, and future parsers."""

    # ClassVar 表示这是 Parser 类的固定能力声明，不是每次 parse 的业务数据。
    parser_name: ClassVar[str]
    parser_version: ClassVar[str]
    supported_content_types: ClassVar[frozenset[str]]

    def parse(
        self,
        source: BinaryIO,
        *,
        content_type: str,
        original_filename: str,
    ) -> ParsedDocument:
        """读取二进制源文件并返回格式统一、可追溯的 ParsedDocument。"""

        ...
