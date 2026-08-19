from collections.abc import Iterable
from typing import BinaryIO, Callable

from app.knowledge.parsing import (
    DocumentParser,
    InvalidDocumentError,
    NoParseableTextError,
    ParsedBlock,
    ParsedDocument,
)


def _decode_utf8(source: BinaryIO) -> str:
    """读取二进制文本并按 UTF-8 解码，失败时转换为解析领域错误。"""

    try:
        return source.read().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InvalidDocumentError("Document is not valid UTF-8 text.") from error


def _paragraph_blocks(
    lines: Iterable[str],
    *,
    source_locator_factory: Callable[[int, int], dict[str, object]],
) -> tuple[ParsedBlock, ...]:
    """将 TXT 行按空行聚合为段落，并记录起止行号供 Citation 使用。"""

    blocks: list[ParsedBlock] = []
    current_lines: list[str] = []
    start_line: int | None = None

    def flush(end_line: int) -> None:
        """把当前段落写入结果，并清空正在累积的行。"""

        # nonlocal 让内部函数能重置外层函数保存的当前段落状态；
        # 不写 nonlocal 会创建新的局部变量，外层状态不会被清空。
        nonlocal current_lines, start_line
        if not current_lines or start_line is None:
            return
        blocks.append(
            ParsedBlock(
                text="\n".join(current_lines).strip(),
                block_index=len(blocks),
                source_locator=source_locator_factory(start_line, end_line),
            )
        )
        current_lines = []
        start_line = None

    last_line_number = 0
    for line_number, line in enumerate(lines, start=1):
        last_line_number = line_number
        if line.strip():
            if start_line is None:
                start_line = line_number
            current_lines.append(line.rstrip())
        else:
            flush(line_number - 1)

    flush(last_line_number)
    if not blocks:
        raise NoParseableTextError("Document contains no parseable text.")
    return tuple(blocks)


class TextParser(DocumentParser):
    parser_name = "txt"
    # v1 是我们定义的解析输出契约版本，不会自动增长；改变分块或来源定位语义时手动升到 v2。
    parser_version = "v1"
    supported_content_types = frozenset({"text/plain"})

    def parse(
        self,
        source: BinaryIO,
        *,
        content_type: str,
        original_filename: str,
    ) -> ParsedDocument:
        """解析 TXT 字节流为按段落组织的 ParsedDocument。"""

        # Protocol 统一要求 filename；TXT 第一版不按文件名决定解析逻辑，del 只删除当前函数的局部变量绑定。
        del original_filename
        if content_type not in self.supported_content_types:
            raise InvalidDocumentError(
                f"TextParser does not support content type: {content_type}."
            )

        text = _decode_utf8(source)
        blocks = _paragraph_blocks(
            text.splitlines(),
            source_locator_factory=lambda start, end: {
                "line_start": start,
                "line_end": end,
            },
        )
        return ParsedDocument(
            blocks=blocks,
            metadata={"content_type": content_type},
            parser_name=self.parser_name,
            parser_version=self.parser_version,
        )
