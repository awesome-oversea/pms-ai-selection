"""RAG检索增强生成框架: 切片/检索/Prompt。"""
from src.rag.chunkers import (
    ChunkMetadata,
    DocumentChunk,
    DocumentChunker,
    RecursiveCharacterTextSplitter,
    SemanticBoundarySplitter,
    create_chunker,
)
from src.rag.prompts import (
    PromptTemplate,
    get_competitor_prompt,
    get_rag_qa_prompt,
    get_selection_prompt,
    get_trend_prompt,
)
from src.rag.retriever import (
    BM25Scorer,
    HybridRetriever,
    RetrievalResult,
    RRFusion,
    create_hybrid_retriever,
)

__all__ = [
    "DocumentChunker",
    "RecursiveCharacterTextSplitter",
    "SemanticBoundarySplitter",
    "DocumentChunk",
    "ChunkMetadata",
    "create_chunker",
    "HybridRetriever",
    "BM25Scorer",
    "RRFusion",
    "RetrievalResult",
    "create_hybrid_retriever",
    "PromptTemplate",
    "get_selection_prompt",
    "get_trend_prompt",
    "get_competitor_prompt",
    "get_rag_qa_prompt",
]
