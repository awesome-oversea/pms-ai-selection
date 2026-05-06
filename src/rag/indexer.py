"""
文档入库 Pipeline
=================

将原始文本经过 分块 → Embedding编码 → Qdrant写入 三步完成向量化入库。

支持 mock 模式（不依赖真实 Embedding 模型和 Qdrant 服务），
便于开发和测试环境使用。

使用方式:
    from src.rag.indexer import DocumentIndexer, index_documents

    indexer = DocumentIndexer()
    count = await indexer.index_documents(["文档1内容...", "文档2内容..."])
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from src.core.logging import get_logger
from src.rag.chunkers import DocumentChunk, DocumentChunker
from src.services.embedding import EmbeddingService

logger = get_logger(__name__)


@dataclass
class IndexResult:
    """入库结果。"""

    total_documents: int = 0
    total_chunks: int = 0
    total_vectors_upserted: int = 0
    collection_name: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and self.total_vectors_upserted > 0


class MockQdrantBackend:
    """
    Mock Qdrant 后端（qdrant_client 不可用时的降级方案）。

    在内存中存储向量和 payload，支持基本的 upsert 和 cosine search。
    仅用于开发和测试环境。
    """

    def __init__(self):
        self._collections: dict[str, list[dict[str, Any]]] = {}

    async def ensure_collection(self, collection_name: str, vector_size: int = 1024, **kwargs) -> bool:
        if collection_name not in self._collections:
            self._collections[collection_name] = []
            logger.info(f"[MockQdrant] Collection '{collection_name}' 已创建 (dim={vector_size})")
            return True
        return False

    async def upsert_points(self, collection_name: str, points: list, batch_size: int = 100) -> int:
        if collection_name not in self._collections:
            self._collections[collection_name] = []

        for point in points:
            self._collections[collection_name].append({
                "id": getattr(point, "id", str(uuid.uuid4())),
                "vector": getattr(point, "vector", []),
                "payload": getattr(point, "payload", {}),
            })

        logger.info(f"[MockQdrant] upsert {len(points)} points → {collection_name}")
        return len(points)

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float = 0.0,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """基于 cosine similarity 的内存搜索。"""
        import numpy as np

        if collection_name not in self._collections:
            return []

        q_vec = np.array(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []

        scored = []
        for item in self._collections[collection_name]:
            d_vec = np.array(item["vector"], dtype=np.float32)
            d_norm = np.linalg.norm(d_vec)
            if d_norm == 0:
                continue
            cos_sim = float(np.dot(q_vec, d_vec) / (q_norm * d_norm))
            if cos_sim >= score_threshold:
                scored.append({
                    "id": item["id"],
                    "score": cos_sim,
                    "payload": item["payload"],
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    async def count(self, collection_name: str) -> int:
        return len(self._collections.get(collection_name, []))

    def get_all_points(self, collection_name: str) -> list[dict]:
        """测试辅助：获取所有已存储的点。"""
        return list(self._collections.get(collection_name, []))


def _get_qdrant_service():
    """
    获取 QdrantService 实例，qdrant_client 不可用时降级为 MockQdrantBackend。
    """
    try:
        from src.infrastructure.qdrant import QdrantService, get_qdrant_client
        client = get_qdrant_client()
        return QdrantService(client)
    except Exception as e:
        logger.warning(f"⚠️ QdrantService 不可用 ({e})，使用 MockQdrantBackend")
        return MockQdrantBackend()


# 全局 mock 后端实例（用于测试时直接访问）
_mock_backend: MockQdrantBackend | None = None


class DocumentIndexer:
    """
    文档入库 Pipeline。

    流程:
        1. 文本分块 (RecursiveCharacterTextSplitter)
        2. Embedding 编码 (EmbeddingService mock 模式)
        3. 向量写入 (QdrantService / MockQdrantBackend)

    Args:
        collection_name: Qdrant Collection 名称
        chunk_size: 分块大小（字符数）
        chunk_overlap: 分块重叠（字符数）
        embedding_service: 可选的 EmbeddingService 实例
        qdrant_backend: 可选的 Qdrant 后端（None 则自动探测）
    """

    def __init__(
        self,
        collection_name: str = "product_knowledge",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        embedding_service: EmbeddingService | None = None,
        qdrant_backend: Any = None,
    ):
        self.collection_name = collection_name
        self._chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            strategy="recursive",
        )
        self._embedding = embedding_service or EmbeddingService()
        self._qdrant = qdrant_backend or _get_qdrant_service()

    async def index_documents(
        self,
        documents: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> IndexResult:
        """
        将文本列表经过 分块 → Embedding → Qdrant upsert 完成入库。

        Args:
            documents: 原始文本列表
            metadata: 可选的全局元数据（每个文档共享）

        Returns:
            IndexResult: 入库结果统计
        """
        result = IndexResult(
            total_documents=len(documents),
            collection_name=self.collection_name,
        )

        if not documents:
            result.errors.append("文档列表为空")
            return result

        # --- Step 1: 文本分块 ---
        all_chunks: list[DocumentChunk] = []
        for idx, doc_text in enumerate(documents):
            doc_meta = {**(metadata or {}), "doc_index": idx}
            chunks = self._chunker.split_text(doc_text, metadata=doc_meta)
            all_chunks.extend(chunks)

        result.total_chunks = len(all_chunks)
        logger.info(f"📄 分块完成: {len(documents)} 篇文档 → {len(all_chunks)} 个 chunks")

        if not all_chunks:
            result.errors.append("分块结果为空")
            return result

        # --- Step 2: Embedding 编码 ---
        try:
            chunk_texts = [c.text for c in all_chunks]
            vectors = self._embedding.encode(chunk_texts)
        except Exception as e:
            result.errors.append(f"Embedding 编码失败: {e}")
            return result

        logger.info(f"🔢 Embedding 编码完成: {len(vectors)} 个向量 (dim={len(vectors[0]) if vectors else 0})")

        # --- Step 3: 构造 PointStruct 并 upsert ---
        try:
            points = self._build_points(all_chunks, vectors)

            # 确保 Collection 存在
            vector_dim = len(vectors[0]) if vectors else 1024
            await self._qdrant.ensure_collection(
                collection_name=self.collection_name,
                vector_size=vector_dim,
            )

            # 批量写入
            upserted = await self._qdrant.upsert_points(
                collection_name=self.collection_name,
                points=points,
            )
            result.total_vectors_upserted = upserted

        except Exception as e:
            result.errors.append(f"Qdrant 写入失败: {e}")
            return result

        logger.info(
            f"✅ 入库完成: {result.total_documents} 篇文档, "
            f"{result.total_chunks} chunks, "
            f"{result.total_vectors_upserted} vectors → {self.collection_name}"
        )
        return result

    def _build_points(self, chunks: list[DocumentChunk], vectors: list[list[float]]) -> list:
        """
        将 chunks + vectors 组装为 PointStruct 列表。

        优先使用 qdrant_client.models.PointStruct，不可用时用 SimpleNamespace 兼容。
        """
        try:
            from qdrant_client.models import PointStruct
        except ImportError:
            from types import SimpleNamespace as PointStruct  # type: ignore[misc]

        points = []
        for chunk, vector in zip(chunks, vectors, strict=False):
            point_id = str(uuid.uuid4())
            payload = {
                "text": chunk.text,
                "source": chunk.metadata.source,
                "chunk_index": chunk.metadata.chunk_index,
                "total_chunks": chunk.metadata.total_chunks,
                "document_type": chunk.metadata.document_type,
                "language": chunk.metadata.language,
                "token_count": chunk.token_count,
                **chunk.metadata.extra,
            }
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        return points

    async def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        编码查询文本并在已入库的 Collection 中检索。

        Args:
            query: 查询文本
            limit: 返回结果数
            score_threshold: 相似度阈值

        Returns:
            list[dict]: 检索结果 (id, score, payload)
        """
        query_vector = self._embedding.encode_single(query)
        results = await self._qdrant.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )
        return results


async def index_documents(
    documents: list[str],
    collection_name: str = "product_knowledge",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    metadata: dict[str, Any] | None = None,
) -> int:
    """
    便捷函数：将文本列表入库并返回入库向量数。

    Args:
        documents: 原始文本列表
        collection_name: Qdrant Collection 名称
        chunk_size: 分块大小
        chunk_overlap: 分块重叠
        metadata: 可选全局元数据

    Returns:
        int: 成功入库的向量点数量
    """
    indexer = DocumentIndexer(
        collection_name=collection_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    result = await indexer.index_documents(documents, metadata=metadata)
    return result.total_vectors_upserted
