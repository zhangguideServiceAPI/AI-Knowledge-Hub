from io import BytesIO

import pytest
from pypdf.errors import PdfReadError

from app.knowledge.parsing import (
    InvalidDocumentError,
    NoParseableTextError,
    UnsupportedContentTypeError,
)
from app.knowledge.parsers import (
    MarkdownParser,
    ParserRegistry,
    PdfParser,
    TextParser,
    build_default_parser_registry,
)
from app.knowledge.parsers import pdf as pdf_module


def test_text_parser_groups_paragraphs_and_keeps_line_locator() -> None:
    result = TextParser().parse(
        BytesIO("第一段。\n第二行。\n\n第二段。".encode("utf-8")),
        content_type="text/plain",
        original_filename="manual.txt",
    )

    assert [block.text for block in result.blocks] == ["第一段。\n第二行。", "第二段。"]
    assert result.blocks[0].source_locator == {"line_start": 1, "line_end": 2}
    assert result.blocks[1].source_locator == {"line_start": 4, "line_end": 4}


def test_text_parser_rejects_invalid_utf8() -> None:
    with pytest.raises(InvalidDocumentError):
        TextParser().parse(
            BytesIO(b"\xff"),
            content_type="text/plain",
            original_filename="invalid.txt",
        )


def test_markdown_parser_keeps_heading_path_and_heading_blocks() -> None:
    source = "# Guide\n\n## Login\n\nUse SSO.\n".encode("utf-8")

    result = MarkdownParser().parse(
        BytesIO(source),
        content_type="text/markdown",
        original_filename="guide.md",
    )

    assert result.blocks[0].text == "Guide"
    assert result.blocks[0].source_locator["block_type"] == "heading"
    assert result.blocks[2].text == "Use SSO."
    assert result.blocks[2].source_locator["heading_path"] == ["Guide", "Login"]


def test_markdown_parser_rejects_empty_document() -> None:
    with pytest.raises(NoParseableTextError):
        MarkdownParser().parse(
            BytesIO(b"\n\n"),
            content_type="text/markdown",
            original_filename="empty.md",
        )


def test_pdf_parser_extracts_non_empty_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        pages = [FakePage("Page one"), FakePage(""), FakePage("Page three")]

        def __init__(self, source: BytesIO) -> None:
            del source

    monkeypatch.setattr(pdf_module, "PdfReader", FakeReader)

    result = PdfParser().parse(
        BytesIO(b"fake pdf"),
        content_type="application/pdf",
        original_filename="manual.pdf",
    )

    assert [block.text for block in result.blocks] == ["Page one", "Page three"]
    assert [block.source_locator for block in result.blocks] == [
        {"page": 1},
        {"page": 3},
    ]
    assert result.metadata["page_count"] == 3


def test_pdf_parser_wraps_reader_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_reader(source: BytesIO) -> None:
        del source
        raise PdfReadError("invalid pdf")

    monkeypatch.setattr(pdf_module, "PdfReader", raise_reader)

    with pytest.raises(InvalidDocumentError):
        PdfParser().parse(
            BytesIO(b"invalid"),
            content_type="application/pdf",
            original_filename="invalid.pdf",
        )


def test_default_registry_selects_parser_by_content_type() -> None:
    registry = build_default_parser_registry()

    assert isinstance(registry.get("application/pdf"), PdfParser)
    assert isinstance(registry.get("text/plain"), TextParser)
    assert isinstance(registry.get("text/markdown"), MarkdownParser)


def test_registry_rejects_unsupported_content_type() -> None:
    with pytest.raises(UnsupportedContentTypeError):
        build_default_parser_registry().get("image/png")


def test_registry_rejects_duplicate_content_type() -> None:
    with pytest.raises(ValueError, match="Multiple parsers"):
        ParserRegistry((TextParser(), TextParser()))
