import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, Protocol

from app.knowledge.parsing import ParsedBlock, ParsedDocument, SourceLocator


class ChunkingError(ValueError):
    """Base error for invalid chunking configuration or input."""


class TokenCounter(Protocol):
    """Counts text with the tokenizer selected by the embedding profile."""

    def count(self, text: str) -> int:
        """返回文本按当前 Embedding 模型 tokenizer 计算出的 Token 数。"""

        ...


# dataclass 自动生成构造方法；frozen=True 保证创建配置后不会被运行中途改写。
@dataclass(frozen=True)
class ChunkingConfig:
    max_tokens: int
    overlap_tokens: int

    # __post_init__ 会在 dataclass 自动生成的 __init__ 赋值后自动调用。
    # 这里限制配置，避免生成永远放不下内容或完全重复的 Chunk。
    def __post_init__(self) -> None:
        """创建配置后校验 Token 上限和 overlap 的合法组合。"""

        if self.max_tokens <= 0:
            raise ChunkingError("Chunk maximum tokens must be greater than zero.")
        if self.overlap_tokens < 0:
            raise ChunkingError("Chunk overlap tokens must not be negative.")
        if self.overlap_tokens >= self.max_tokens:
            raise ChunkingError(
                "Chunk overlap tokens must be less than maximum tokens."
            )


# ChunkDraft 是尚未写入 MySQL 的内存结果；KnowledgeService 将来会把它变成 DocumentChunk。
@dataclass(frozen=True)
class ChunkDraft:
    content: str
    token_count: int
    source_locator: SourceLocator

    # __post_init__ 在实例创建时自动校验，防止无效数据进入持久化层。
    def __post_init__(self) -> None:
        """创建草稿后阻止空内容、负 Token 或缺失来源进入持久化步骤。"""

        if not self.content.strip():
            raise ChunkingError("Chunk content must not be empty.")
        if self.token_count < 0:
            raise ChunkingError("Chunk token count must not be negative.")
        if not self.source_locator:
            raise ChunkingError("Chunk source locator must not be empty.")


# 私有类型只在本文件使用。它保存某段文本及它来自哪个 ParsedBlock，
# 让最终 Chunk 即使包含多个段落也能保留 Citation 所需来源。
@dataclass(frozen=True)
class _ChunkUnit:
    text: str
    block_index: int
    source_locator: SourceLocator


class Chunker(Protocol):
    """Capability boundary between ParsedDocument and persistence orchestration."""

    chunker_name: ClassVar[str]
    chunker_version: ClassVar[str]

    def chunk(self, document: ParsedDocument) -> tuple[ChunkDraft, ...]:
        """将统一解析结果拆成按原文顺序排列的内存 ChunkDraft。"""

        ...


# 以句号、问号、感叹号或空白行作为优先切分点；长文本只有超过 max_tokens 才会继续切。
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s*|\n{2,}")


class StructureAwareChunker(Chunker):
    """Combines parser blocks first, then applies sentence and overlap limits."""

    chunker_name = "structure-aware"
    # 这是本项目的分块规则版本；规则或 locator 语义改变时手动提升为 v2。
    chunker_version = "v1"

    def __init__(
        self,
        *,
        config: ChunkingConfig,
        token_counter: TokenCounter,
    ) -> None:
        """接收不可变分块配置和匹配 Embedding Profile 的 TokenCounter。"""

        self._config = config
        # TokenCounter 由调用方按 Embedding Profile 注入。不同模型的 tokenizer 不同，
        # 因此不能在 Chunker 内用 len(text) 或字节数冒充真实 Token。
        self._token_counter = token_counter

    def chunk(self, document: ParsedDocument) -> tuple[ChunkDraft, ...]:
        """按结构边界、Token 上限与 overlap 策略，将一个 ParsedDocument 生成多个草稿。"""

        units = tuple(
            unit for block in document.blocks for unit in self._units_for_block(block)
        )
        if not units:
            raise ChunkingError("Parsed document contains no chunkable text.")

        drafts: list[ChunkDraft] = []
        current_units: list[_ChunkUnit] = []

        for unit in units:
            candidate = [*current_units, unit]
            if current_units and self._count_units(candidate) > self._config.max_tokens:
                drafts.append(self._make_draft(current_units))
                current_units = self._overlap_for_next_chunk(current_units, unit)

            current_units.append(unit)

        if current_units:
            drafts.append(self._make_draft(current_units))

        return tuple(drafts)

    def _units_for_block(self, block: ParsedBlock) -> tuple[_ChunkUnit, ...]:
        """把一个解析块先按句子切分；单句过长时继续拆为可容纳的单元。"""

        sentence_units = tuple(
            _ChunkUnit(
                text=sentence,
                block_index=block.block_index,
                source_locator=block.source_locator,
            )
            for sentence in self._split_sentences(block.text)
        )

        units: list[_ChunkUnit] = []
        for unit in sentence_units:
            units.extend(self._split_oversized_unit(unit))
        return tuple(units)

    def _split_sentences(self, text: str) -> tuple[str, ...]:
        """优先按句末标点或空行切分文本，保留无法切分时的整段文本。"""

        sentences = tuple(
            sentence.strip()
            for sentence in _SENTENCE_BOUNDARY.split(text)
            if sentence.strip()
        )
        return sentences or (text.strip(),)

    def _split_oversized_unit(self, unit: _ChunkUnit) -> tuple[_ChunkUnit, ...]:
        """将超过 Token 上限的单元按 Unicode 字符边界拆开，并保留来源定位。"""

        if self._token_counter.count(unit.text) <= self._config.max_tokens:
            return (unit,)

        # 句子本身仍过长时，按 Python 字符边界寻找最大可容纳前缀。
        # Python str 按 Unicode code point 工作，不会像 UTF-8 bytes 那样截断一个中文字符。
        pieces: list[_ChunkUnit] = []
        remaining = unit.text
        segment_index = 0
        while remaining:
            prefix = self._longest_fitting_prefix(remaining)
            if not prefix:
                raise ChunkingError(
                    "Token counter cannot fit one character into the configured chunk."
                )
            pieces.append(
                _ChunkUnit(
                    text=prefix,
                    block_index=unit.block_index,
                    source_locator={
                        **unit.source_locator,
                        "segment_index": segment_index,
                    },
                )
            )
            remaining = remaining[len(prefix) :].lstrip()
            segment_index += 1
        return tuple(pieces)

    def _longest_fitting_prefix(self, text: str) -> str:
        """查找 text 中不超过当前 Token 上限的最长前缀。"""

        best_end = 0
        for end in range(1, len(text) + 1):
            candidate = text[:end]
            if self._token_counter.count(candidate) > self._config.max_tokens:
                break
            best_end = end
        return text[:best_end].rstrip()

    def _overlap_for_next_chunk(
        self,
        previous_units: Iterable[_ChunkUnit],
        next_unit: _ChunkUnit,
    ) -> list[_ChunkUnit]:
        """从上一 Chunk 尾部取完整单元作为 overlap，且确保连同下一单元仍不超限。"""

        # overlap 复用上一 Chunk 末尾的完整 Unit；若一个 Unit 已超过 overlap 预算，
        # 不切半复制，避免 Citation 指向半句话和额外的复杂 token 裁剪逻辑。
        overlap: list[_ChunkUnit] = []
        for unit in reversed(tuple(previous_units)):
            candidate = [unit, *overlap]
            if self._count_units(candidate) > self._config.overlap_tokens:
                break
            if self._count_units([*candidate, next_unit]) > self._config.max_tokens:
                break
            overlap = candidate
        return overlap

    def _make_draft(self, units: Iterable[_ChunkUnit]) -> ChunkDraft:
        """合并连续单元为一个 ChunkDraft，并聚合 Citation 所需的来源定位。"""

        materialized_units = tuple(units)
        content = self._join_units(materialized_units)
        return ChunkDraft(
            content=content,
            token_count=self._token_counter.count(content),
            source_locator={
                "block_start": materialized_units[0].block_index,
                "block_end": materialized_units[-1].block_index,
                "sources": [
                    {
                        "block_index": unit.block_index,
                        "locator": unit.source_locator,
                    }
                    for unit in materialized_units
                ],
            },
        )

    def _count_units(self, units: Iterable[_ChunkUnit]) -> int:
        """把多个单元按最终文本形式拼接后，计算总 Token 数。"""

        return self._token_counter.count(self._join_units(units))

    @staticmethod
    def _join_units(units: Iterable[_ChunkUnit]) -> str:
        """以空行连接单元，保留原段落之间的可读结构。"""

        # 空行作为 Unit 间分隔符：阅读时保留段落感，也让模型看到原始结构边界。
        return "\n\n".join(unit.text for unit in units)
