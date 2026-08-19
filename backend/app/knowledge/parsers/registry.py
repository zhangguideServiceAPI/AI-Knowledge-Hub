from collections.abc import Iterable

from app.knowledge.parsing import (
    DocumentParser,
    UnsupportedContentTypeError,
)
from app.knowledge.parsers.markdown import MarkdownParser
from app.knowledge.parsers.pdf import PdfParser
from app.knowledge.parsers.text import TextParser


class ParserRegistry:
    def __init__(self, parsers: Iterable[DocumentParser]) -> None:
        """注册一组 Parser，并拒绝同一 MIME 类型的重复实现。"""

        # Registry 创建时为空；循环到第二个及以后 Parser 时，这里可发现同一 MIME 被重复注册。
        self._parsers: dict[str, DocumentParser] = {}
        for parser in parsers:
            for content_type in parser.supported_content_types:
                if content_type in self._parsers:
                    # 一个 MIME 只能有一个 Parser，否则同一文件会得到不确定的解析结果。
                    raise ValueError(
                        f"Multiple parsers support content type: {content_type}."
                    )
                self._parsers[content_type] = parser

    def get(self, content_type: str) -> DocumentParser:
        """按保存的 MIME 类型取得 Parser；没有实现时抛出明确的类型错误。"""

        try:
            return self._parsers[content_type]
        except KeyError as error:
            raise UnsupportedContentTypeError(
                f"No parser supports content type: {content_type}."
            ) from error


def build_default_parser_registry() -> ParserRegistry:
    """创建当前支持 PDF、TXT 和 Markdown 的默认 Parser 注册表。"""

    # 这不是全局单例注册。未来在 FastAPI dependency 或 KnowledgeService 组装时调用一次，
    # 把返回的 Registry 注入 Service；当前仅提供默认组合，尚未接入 API 生命周期。
    return ParserRegistry((PdfParser(), TextParser(), MarkdownParser()))
