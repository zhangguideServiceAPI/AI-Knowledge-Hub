from typing import BinaryIO

import pypdf
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.knowledge.parsing import (
    DocumentParser,
    InvalidDocumentError,
    NoParseableTextError,
    ParsedBlock,
    ParsedDocument,
)


class PdfParser(DocumentParser):
    parser_name = "pdf"
    # pypdf.__version__ 是已安装 pypdf 包自己的发布版本（当前为 6.16.1），
    # 它随依赖升级变化，用于识别 PDF 提取引擎的版本，不是我们的 DocumentVersion 编号。
    parser_version = pypdf.__version__
    supported_content_types = frozenset({"application/pdf"})

    def parse(
        self,
        source: BinaryIO,
        *,
        content_type: str,
        original_filename: str,
    ) -> ParsedDocument:
        """逐页读取 PDF 文本，保留页码定位并返回统一解析结果。"""

        # Protocol 统一要求 filename；PDF 第一版不依赖文件名，del 只删除局部变量绑定。
        del original_filename
        if content_type not in self.supported_content_types:
            raise InvalidDocumentError(
                f"PdfParser does not support content type: {content_type}."
            )

        try:
            reader = PdfReader(source)
            blocks = []
            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    blocks.append(
                        ParsedBlock(
                            text=text,
                            block_index=len(blocks),
                            source_locator={"page": page_number},
                        )
                    )
        except PdfReadError as error:
            raise InvalidDocumentError("PDF document cannot be read.") from error
        except Exception as error:
            raise InvalidDocumentError("PDF text extraction failed.") from error

        if not blocks:
            raise NoParseableTextError("PDF document contains no parseable text.")

        return ParsedDocument(
            blocks=tuple(blocks),
            metadata={"content_type": content_type, "page_count": len(reader.pages)},
            parser_name=self.parser_name,
            parser_version=self.parser_version,
        )
