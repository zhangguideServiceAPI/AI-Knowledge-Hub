from io import BytesIO

import pytest

from app.knowledge.parsing import DocumentParser, ParsedBlock, ParsedDocument


def _build_block(index: int = 0) -> ParsedBlock:
    return ParsedBlock(
        text="The product supports SSO.",
        block_index=index,
        source_locator={"page": index + 1},
    )


def test_parsed_document_contains_citation_ready_blocks() -> None:
    block = _build_block()
    document = ParsedDocument(
        blocks=(block,),
        metadata={"title": "Product manual"},
        parser_name="txt",
        parser_version="v1",
    )

    assert document.blocks == (block,)
    assert document.blocks[0].source_locator == {"page": 1}
    assert document.parser_name == "txt"
    assert document.parser_version == "v1"


def test_document_parser_protocol_defines_binary_input_and_uniform_output() -> None:
    class FakeTextParser:
        parser_name = "txt"
        parser_version = "v1"

        def parse(
            self,
            source: BytesIO,
            *,
            content_type: str,
            original_filename: str,
        ) -> ParsedDocument:
            del source, content_type, original_filename
            return ParsedDocument(
                blocks=(_build_block(),),
                metadata={},
                parser_name=self.parser_name,
                parser_version=self.parser_version,
            )

    parser: DocumentParser = FakeTextParser()
    parsed = parser.parse(
        BytesIO(b"The product supports SSO."),
        content_type="text/plain",
        original_filename="manual.txt",
    )

    assert isinstance(parsed, ParsedDocument)
    assert parsed.blocks[0].text == "The product supports SSO."


@pytest.mark.parametrize(
    ("text", "block_index", "source_locator"),
    [
        ("", 0, {"page": 1}),
        ("   ", 0, {"page": 1}),
        ("text", -1, {"page": 1}),
        ("text", 0, {}),
    ],
)
def test_parsed_block_rejects_invalid_values(
    text: str,
    block_index: int,
    source_locator: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ParsedBlock(
            text=text,
            block_index=block_index,
            source_locator=source_locator,
        )


def test_parsed_document_rejects_empty_blocks() -> None:
    with pytest.raises(ValueError, match="at least one block"):
        ParsedDocument(
            blocks=(),
            metadata={},
            parser_name="txt",
            parser_version="v1",
        )


def test_parsed_document_rejects_non_contiguous_block_indexes() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        ParsedDocument(
            blocks=(_build_block(0), _build_block(2)),
            metadata={},
            parser_name="txt",
            parser_version="v1",
        )


@pytest.mark.parametrize("field", ["parser_name", "parser_version"])
def test_parsed_document_requires_parser_identity(field: str) -> None:
    values = {
        "blocks": (_build_block(),),
        "metadata": {},
        "parser_name": "txt",
        "parser_version": "v1",
    }
    values[field] = "   "

    with pytest.raises(ValueError):
        ParsedDocument(**values)
