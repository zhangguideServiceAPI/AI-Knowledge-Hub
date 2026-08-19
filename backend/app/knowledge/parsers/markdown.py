import re
from typing import BinaryIO

from app.knowledge.parsing import (
    DocumentParser,
    InvalidDocumentError,
    NoParseableTextError,
    ParsedBlock,
    ParsedDocument,
)
from app.knowledge.parsers.text import _decode_utf8

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class MarkdownParser(DocumentParser):
    parser_name = "markdown"
    # v1 是我们定义的解析输出契约版本，不会自动增长；标题、段落或 locator 语义改变时手动升级。
    parser_version = "v1"
    supported_content_types = frozenset({"text/markdown"})

    def parse(
        self,
        source: BinaryIO,
        *,
        content_type: str,
        original_filename: str,
    ) -> ParsedDocument:
        """解析 Markdown 标题和段落，并把标题路径写入来源定位。"""

        # Protocol 统一要求 filename；Markdown 第一版不依赖文件名，del 不会修改真实文件或调用方变量。
        del original_filename
        if content_type not in self.supported_content_types:
            raise InvalidDocumentError(
                f"MarkdownParser does not support content type: {content_type}."
            )

        lines = _decode_utf8(source).splitlines()
        blocks: list[ParsedBlock] = []
        current_lines: list[str] = []
        current_start: int | None = None
        heading_path: list[str] = []
        in_fence = False

        def append_block(end_line: int) -> None:
            # nonlocal 用于更新外层累积的 Markdown 段落，处理完后从空段落继续。
            nonlocal current_lines, current_start
            if not current_lines or current_start is None:
                return
            blocks.append(
                ParsedBlock(
                    text="\n".join(current_lines).strip(),
                    block_index=len(blocks),
                    source_locator={
                        "line_start": current_start,
                        "line_end": end_line,
                        "heading_path": list(heading_path),
                    },
                )
            )
            current_lines = []
            current_start = None

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            is_fence = stripped.startswith("```") or stripped.startswith("~~~")
            heading_match = None if in_fence else _HEADING_PATTERN.match(line)

            if heading_match:
                append_block(line_number - 1)
                level = len(heading_match.group(1))
                heading = heading_match.group(2).strip()
                heading_path[:] = heading_path[: level - 1]
                heading_path.append(heading)
                blocks.append(
                    ParsedBlock(
                        text=heading,
                        block_index=len(blocks),
                        source_locator={
                            "line_start": line_number,
                            "line_end": line_number,
                            "heading_level": level,
                            "heading_path": list(heading_path),
                            "block_type": "heading",
                        },
                    )
                )
                continue

            if is_fence:
                in_fence = not in_fence

            if stripped:
                if current_start is None:
                    current_start = line_number
                current_lines.append(line.rstrip())
            else:
                append_block(line_number - 1)

        append_block(len(lines))
        if not blocks:
            raise NoParseableTextError("Markdown document contains no parseable text.")

        return ParsedDocument(
            blocks=tuple(blocks),
            metadata={"content_type": content_type},
            parser_name=self.parser_name,
            parser_version=self.parser_version,
        )
