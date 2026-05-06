"""
文档切片策略
============

提供多种文档分块能力(D13-T049):
    - 递归字符切片(RecursiveCharacterTextSplitter)
    - 按语义边界切片(段落/章节)
    - 元数据保留(来源/时间/类别)
    - 自定义分隔符支持

使用方式:
    from src.rag.chunkers import DocumentChunker

    chunker = DocumentChunker(chunk_size=512, chunk_overlap=50)
    chunks = chunker.split_text("长文档内容...", metadata={"source": "report.pdf"})
"""

import re
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChunkMetadata:
    """
    文档块元数据。

    保留原始文档的上下文信息，
    用于RAG检索时的过滤和溯源。
    """

    source: str = ""
    page: int | None = None
    chunk_index: int = 0
    total_chunks: int = 0
    created_at: str = ""
    document_type: str = ""
    language: str = "zh"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "created_at": self.created_at,
            "document_type": self.document_type,
            "language": self.language,
            **self.extra,
        }


@dataclass
class DocumentChunk:
    """
    文档块数据结构。

    包含切片后的文本内容和元数据，
    可直接用于Embedding和向量存储。
    """

    text: str
    metadata: ChunkMetadata
    token_count: int = 0

    @property
    def char_length(self) -> int:
        return len(self.text)


class RecursiveCharacterTextSplitter:
    """
    递归字符文本分割器(D13-T049)。

    按优先级尝试不同分隔符进行分割:
        1. \n\n (段落)
        2. \n (换行)
        3. 。 (中文句号)
        4. . (英文句号)
        5. ， (逗号)
        6. 空格
        7. 字符级别(最后手段)

    Attributes:
        separators: 分隔符优先级列表
        chunk_size: 目标块大小(字符数)
        chunk_overlap: 块间重叠字符数
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", "。", ".", "，", ",", " ", ""]

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
        length_function: Any = None,
    ):
        if chunk_overlap >= chunk_size:
            raise ValueError(f"chunk_overlap({chunk_overlap}) 必须小于 chunk_size({chunk_size})")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or list(self.DEFAULT_SEPARATORS)
        self.length_function = length_function or len

    def split_text(self, text: str) -> list[str]:
        """
        递归分割文本为多个块。

        Args:
            text: 原始文本

        Returns:
            list[str]: 切片后的文本块列表
        """
        if not text or not text.strip():
            return []

        return self._split_text_recursive(text, self.separators)

    def _split_text_recursive(self, text: str, separators: list[str]) -> list[str]:
        """递归分割核心逻辑。"""
        if not separators:
            return self._split_by_char(text)

        separator = separators[0]
        remaining_separators = separators[1:]

        if separator == "":
            return self._split_by_char(text)

        splits = text.split(separator)

        merged_splits = []
        for i, split in enumerate(splits):
            if split:
                if i > 0 and separator.strip():
                    merged_splits[-1] += separator + split
                else:
                    merged_splits.append(split)

        final_chunks = []
        current_chunk = ""

        for split in merged_splits:
            test_chunk = current_chunk + (separator if current_chunk else "") + split

            if self.length_function(test_chunk) <= self.chunk_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    final_chunks.append(current_chunk)

                if self.length_function(split) <= self.chunk_size:
                    current_chunk = split
                else:
                    sub_chunks = self._split_text_recursive(split, remaining_separators)

                    for sub in sub_chunks:
                        if self.length_function(sub) <= self.chunk_size:
                            if current_chunk:
                                combined = current_chunk + separator + sub
                                if self.length_function(combined) <= self.chunk_size:
                                    current_chunk = combined
                                    continue
                                final_chunks.append(current_chunk)

                            current_chunk = sub
                        else:
                            if current_chunk:
                                final_chunks.append(current_chunk)
                            final_chunks.append(sub[:self.chunk_size])
                            current_chunk = ""

        if current_chunk:
            final_chunks.append(current_chunk)

        return self._apply_overlap(final_chunks)

    def _split_by_char(self, text: str) -> list[str]:
        """按字符级别分割(最后的兜底方案)。"""
        chunks = []
        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunks.append(text[i:i + self.chunk_size])
        return chunks

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """应用块间重叠。"""
        if self.chunk_overlap <= 0 or len(chunks) <= 1:
            return chunks

        result = [chunks[0]]

        for i in range(1, len(chunks)):
            prev = result[-1]
            curr = chunks[i]

            overlap_start = max(0, len(prev) - self.chunk_overlap)
            overlap_text = prev[overlap_start:]

            if curr.startswith(overlap_text):
                result.append(curr)
            elif overlap_text and len(overlap_text) > 5:
                merged = overlap_text + curr[len(overlap_text):] if curr.startswith(overlap_text[-10:]) else curr
                result.append(merged)
            else:
                result.append(curr)

        return result


class SemanticBoundarySplitter:
    """
    语义边界分割器(D13-T049)。

    基于文档结构特征进行智能切片:
        - Markdown标题(# ## ###)
        - HTML标签(<p> <div> <section>)
        - JSON/YAML结构
        - 代码块(```)
    """

    MARKDOWN_HEADERS = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)
    CODE_BLOCK = re.compile(r"```[\s\S]*?```")

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 100,
        respect_headers: bool = True,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.respect_headers = respect_headers
        self._fallback = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split_text(self, text: str) -> list[str]:
        """基于语义边界分割文本。"""
        if not self.respect_headers or not self.MARKDOWN_HEADERS.search(text):
            return self._fallback.split_text(text)

        header_positions = [m.start() for m in self.MARKDOWN_HEADERS.finditer(text)]

        if not header_positions:
            return self._fallback.split_text(text)

        sections = []
        prev_pos = 0

        for pos in header_positions:
            section = text[prev_pos:pos].strip()
            if section:
                sections.append(section)
            prev_pos = pos

        last_section = text[prev_pos:].strip()
        if last_section:
            sections.append(last_section)

        result = []
        for section in sections:
            if len(section) <= self.chunk_size:
                result.append(section)
            else:
                sub_chunks = self._fallback.split_text(section)
                result.extend(sub_chunks)

        return result


class DocumentChunker:
    """
    文档切片管理器(D13-T049)。

    统一接口，支持多种切片策略:
        - recursive: 递归字符切片(默认)
        - semantic: 语义边界切片
        - fixed: 固定长度切片

    自动添加元数据和token计数。
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        strategy: str = "recursive",
        metadata: dict[str, Any] | None = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy
        self.base_metadata = metadata or {}

        if strategy == "semantic":
            self._splitter = SemanticBoundarySplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        else:
            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

    def split_text(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[DocumentChunk]:
        """
        切分文本并生成DocumentChunk列表。

        Args:
            text: 原始文本
            metadata: 额外元数据(与base_metadata合并)

        Returns:
            list[DocumentChunk]: 切片结果
        """
        from datetime import datetime

        raw_texts = self._splitter.split_text(text)
        merged_meta = {**self.base_metadata, **(metadata or {})}

        chunks = []
        total = len(raw_texts)

        for idx, chunk_text in enumerate(raw_texts):
            meta = ChunkMetadata(
                source=merged_meta.get("source", ""),
                page=merged_meta.get("page"),
                chunk_index=idx,
                total_chunks=total,
                created_at=datetime.now(UTC).isoformat(),
                document_type=merged_meta.get("document_type", ""),
                language=merged_meta.get("language", "zh"),
                extra={k: v for k, v in merged_meta.items()
                       if k not in ("source", "page", "document_type", "language")},
            )

            chunk = DocumentChunk(
                text=chunk_text,
                metadata=meta,
                token_count=self._estimate_tokens(chunk_text),
            )
            chunks.append(chunk)

        logger.info(f"📄 文档切分完成: {len(chunks)} 个chunks (strategy={self.strategy})")
        return chunks

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        估算Token数量。

        中文约1.5字符/token，英文约4字符/token。
        """
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        other_chars = len(text) - chinese_chars

        return int(chinese_chars / 1.5 + other_chars / 4)

    def split_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> list[DocumentChunk]:
        """
        批量切分多个文档。

        Args:
            documents: 文档列表，每项包含text和可选metadata

        Returns:
            list[DocumentChunk]: 所有文档的切片合并
        """
        all_chunks = []

        for doc in documents:
            text = doc.get("text", "")
            doc_meta = doc.get("metadata", {})
            chunks = self.split_text(text, metadata=doc_meta)
            all_chunks.extend(chunks)

        return all_chunks


def create_chunker(
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    strategy: str = "recursive",
) -> DocumentChunker:
    """创建DocumentChunker工厂函数。"""
    return DocumentChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        strategy=strategy,
    )
