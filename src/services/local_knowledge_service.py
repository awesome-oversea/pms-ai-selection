"""
本地 SQLite 知识库服务
=====================

用于 PostgreSQL 不可用时的最小真实持久化降级方案：
- 文档/Chunk 持久化到本地 SQLite
- 复用现有 Embedding / Qdrant / Retriever 逻辑
- 支撑 Phase 3 在当前机器上的真实上传/查询/重启后查询验收
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from src.core.logging import get_logger
from src.infrastructure.qdrant import _QDRANT_AVAILABLE, QdrantService, get_qdrant_client
from src.infrastructure.qdrant import models as qdrant_models
from src.infrastructure.redis import CacheService, get_redis_connection
from src.rag.chunkers import DocumentChunker
from src.rag.collections import LOCAL_KNOWLEDGE_QDRANT_COLLECTION_NAME
from src.rag.retriever import HybridRetriever
from src.services.embedding import EmbeddingProvider

logger = get_logger(__name__)

_QUERY_CACHE_FALLBACK: dict[str, dict[str, str]] = {}
_DB_PATH = Path("data/local_knowledge.db")


class LocalKnowledgeRepository:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path or _DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    doc_type TEXT,
                    file_size INTEGER DEFAULT 0,
                    content_hash TEXT,
                    status TEXT NOT NULL,
                    chunk_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    extra_data TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    vector_id TEXT,
                    created_at TEXT NOT NULL,
                    extra_data TEXT,
                    FOREIGN KEY(document_id) REFERENCES knowledge_documents(id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_hash ON knowledge_documents(content_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_doc_idx ON knowledge_chunks(document_id, chunk_index)"
            )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _loads(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _dumps(value: dict[str, Any] | None) -> str:
        return json.dumps(value or {}, ensure_ascii=False)

    def get_document_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM knowledge_documents
                WHERE content_hash = ? AND is_deleted = 0
                ORDER BY created_at DESC LIMIT 1
                """,
                (content_hash,),
            ).fetchone()
        return self._row_to_document(row) if row else None

    def create_document(
        self,
        title: str,
        doc_type: str,
        file_size: int,
        content_hash: str,
        status: str,
        extra_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        doc_id = str(uuid4())
        now = self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_documents
                (id, title, doc_type, file_size, content_hash, status, chunk_count, created_at, updated_at, is_deleted, extra_data)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 0, ?)
                """,
                (doc_id, title, doc_type, file_size, content_hash, status, now, now, self._dumps(extra_data)),
            )
        return self.get_document(doc_id)

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_documents WHERE id = ? AND is_deleted = 0",
                (doc_id,),
            ).fetchone()
        return self._row_to_document(row) if row else None

    def update_document_status(
        self,
        doc_id: str,
        status: str,
        chunk_count: int | None = None,
        reason: str | None = None,
        provider_mode: str | None = None,
        vector_status: str | None = None,
    ) -> bool:
        document = self.get_document(doc_id)
        if document is None:
            return False

        extra = dict(document.get("extra_data") or {})
        history = list(extra.get("status_history", []))
        history.append(
            {
                "status": status,
                "reason": reason,
                "provider_mode": provider_mode,
                "vector_status": vector_status,
            }
        )
        extra["status_history"] = history[-50:]
        if reason is not None:
            extra["status_reason"] = reason
        if provider_mode is not None:
            extra["provider_mode"] = provider_mode
        if vector_status is not None:
            extra["vector_status"] = vector_status

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE knowledge_documents
                SET status = ?,
                    chunk_count = COALESCE(?, chunk_count),
                    updated_at = ?,
                    extra_data = ?
                WHERE id = ?
                """,
                (status, chunk_count, self._now_iso(), self._dumps(extra), doc_id),
            )
        return True

    def create_chunk(
        self,
        document_id: str,
        content: str,
        chunk_index: int,
        vector_id: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chunk_id = str(uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_chunks (id, document_id, chunk_index, content, vector_id, created_at, extra_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, document_id, chunk_index, content, vector_id, self._now_iso(), self._dumps(extra_data)),
            )
        return {
            "id": chunk_id,
            "document_id": document_id,
            "chunk_index": chunk_index,
            "content": content,
            "vector_id": vector_id,
            "extra_data": extra_data or {},
        }

    def list_chunks_by_document(self, document_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_chunks WHERE document_id = ? ORDER BY chunk_index ASC",
                (document_id,),
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def list_indexed_chunks(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*
                FROM knowledge_chunks c
                JOIN knowledge_documents d ON d.id = c.document_id
                WHERE d.is_deleted = 0 AND d.status = 'indexed'
                ORDER BY d.created_at DESC, c.chunk_index ASC
                """
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def list_documents(self, status: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        params: list[Any] = []
        where = "WHERE is_deleted = 0"
        if status:
            where += " AND status = ?"
            params.append(status)

        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM knowledge_documents {where}",
                params,
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM knowledge_documents {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [self._row_to_document(row) for row in rows], int(total)

    def soft_delete_document(self, doc_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE knowledge_documents SET is_deleted = 1, updated_at = ? WHERE id = ?",
                (self._now_iso(), doc_id),
            )
        return result.rowcount > 0

    def get_stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            total_docs = conn.execute(
                "SELECT COUNT(*) FROM knowledge_documents WHERE is_deleted = 0"
            ).fetchone()[0]
            total_chunks = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
            total_size = conn.execute(
                "SELECT COALESCE(SUM(file_size), 0) FROM knowledge_documents WHERE is_deleted = 0"
            ).fetchone()[0]
            indexed_docs = conn.execute(
                "SELECT COUNT(*) FROM knowledge_documents WHERE is_deleted = 0 AND status = 'indexed'"
            ).fetchone()[0]

        return {
            "total_documents": int(total_docs),
            "total_chunks": int(total_chunks),
            "total_size_bytes": int(total_size),
            "total_size_mb": round((total_size or 0) / (1024 * 1024), 2),
            "indexed_documents": int(indexed_docs),
            "average_chunks_per_doc": round(total_chunks / max(total_docs, 1), 1),
        }

    def _row_to_document(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "doc_type": row["doc_type"],
            "file_size": row["file_size"] or 0,
            "content_hash": row["content_hash"],
            "status": row["status"],
            "chunk_count": row["chunk_count"] or 0,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "extra_data": self._loads(row["extra_data"]),
        }

    def _row_to_chunk(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "document_id": row["document_id"],
            "chunk_index": row["chunk_index"],
            "content": row["content"],
            "vector_id": row["vector_id"],
            "created_at": row["created_at"],
            "extra_data": self._loads(row["extra_data"]),
        }


class LocalKnowledgeService:
    QUERY_CACHE_TTL_SECONDS = 3600
    QUERY_CACHE_SIMILARITY_THRESHOLD = 0.95
    QDRANT_COLLECTION_NAME = LOCAL_KNOWLEDGE_QDRANT_COLLECTION_NAME
    SELECTION_CASE_PREFIX = "selection_case_"
    SELECTION_CASE_TYPE = "selection_history_case"
    REVIEW_CASE_PREFIX = "crm_review_case_"
    REVIEW_CASE_TYPE = "crm_review_case"

    def __init__(self, repo: LocalKnowledgeRepository | None = None):
        self.repo = repo or LocalKnowledgeRepository()
        self.embedding_provider = EmbeddingProvider.get_instance()

    @staticmethod
    def _detect_doc_type(filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    @staticmethod
    def _hash_content(content: bytes) -> str:
        import hashlib

        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _build_qdrant_point_id(document_id: str, chunk_index: int) -> str:
        try:
            namespace = UUID(str(document_id))
        except ValueError:
            namespace = NAMESPACE_URL
        return str(uuid5(namespace, f"chunk:{chunk_index}"))

    @staticmethod
    def _should_reindex_existing_document(detail: dict[str, Any], provider_mode: str) -> bool:
        if detail.get("status") != "indexed":
            return True
        if int(detail.get("chunk_count") or 0) <= 0:
            return True
        if str(detail.get("provider_mode") or "") != str(provider_mode or ""):
            return True

        vector_status = str(detail.get("vector_status") or "").strip()
        if vector_status == "indexed":
            return False
        return _QDRANT_AVAILABLE

    @staticmethod
    def _build_citation(item: dict[str, Any]) -> dict[str, Any]:
        content = str(item.get("content") or "")
        metadata = item.get("metadata") or {}
        return {
            "document_id": item.get("document_id") or metadata.get("document_id"),
            "chunk_index": item.get("chunk_index") if item.get("chunk_index") is not None else metadata.get("chunk_index"),
            "source": item.get("source") or metadata.get("source") or metadata.get("filename"),
            "snippet": content[:160],
        }

    @classmethod
    def _enrich_query_results(cls, results: list[dict[str, Any]], *, ranking_stage: str) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for rank, item in enumerate(results, 1):
            current = dict(item)
            current["citation"] = current.get("citation") or cls._build_citation(current)
            current["ranking_stage"] = current.get("ranking_stage") or ranking_stage
            current["ranking_meta"] = {
                "vector_score": current.get("vector_score"),
                "keyword_score": current.get("keyword_score"),
                "rerank_score": current.get("rerank_score"),
                "final_rank": rank,
            }
            enriched.append(current)
        return enriched

    @staticmethod
    def _serialize_document(document: dict[str, Any]) -> dict[str, Any]:
        extra = document.get("extra_data") or {}
        return {
            "doc_id": document["id"],
            "filename": document["title"],
            "file_size": document.get("file_size", 0),
            "chunk_count": document.get("chunk_count", 0),
            "status": document["status"],
            "uploaded_at": document.get("created_at"),
            "content_preview": extra.get("content_preview", ""),
            "vector_status": extra.get("vector_status", "unknown"),
            "provider_mode": extra.get("provider_mode", "unknown"),
            "status_reason": extra.get("status_reason"),
            "status_history": extra.get("status_history", []),
        }

    async def _search_qdrant(
        self,
        collection_name: str,
        query: str,
        top_k: int,
        threshold: float,
        provider_mode: str,
    ) -> list[dict[str, Any]]:
        if not _QDRANT_AVAILABLE:
            return []
        try:
            query_vector = await self.embedding_provider.embed_query(query)
            client = get_qdrant_client()
            qdrant = QdrantService(client)
            results = await qdrant.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k,
                score_threshold=threshold,
            )
            return [
                {
                    "content": (item.get("payload") or {}).get("content", ""),
                    "score": item.get("score", 0.0),
                    "source": (item.get("payload") or {}).get("filename") or (item.get("payload") or {}).get("source"),
                    "document_id": (item.get("payload") or {}).get("document_id"),
                    "chunk_index": (item.get("payload") or {}).get("chunk_index"),
                    "provider_mode": (item.get("payload") or {}).get("provider_mode", provider_mode),
                    "metadata": item.get("payload") or {},
                }
                for item in results
            ]
        except Exception as e:
            logger.warning(f"本地知识库 Qdrant 检索失败，回退 BM25: {e}")
            return []

    async def upload_document(self, filename: str, content: bytes) -> dict[str, Any]:
        text_content = content.decode("utf-8")
        provider_mode = self.embedding_provider.provider_mode
        content_hash = self._hash_content(content)

        existing = self.repo.get_document_by_hash(content_hash)
        if existing is not None:
            detail = self._serialize_document(existing)
            if self._should_reindex_existing_document(detail, provider_mode):
                logger.info(
                    "local knowledge document requires rebuild | doc_id=%s | vector_status=%s | stored_provider=%s | current_provider=%s",
                    detail["doc_id"],
                    detail.get("vector_status"),
                    detail.get("provider_mode"),
                    provider_mode,
                )
                await self.delete_document(detail["doc_id"])
            else:
                return {
                    "doc_id": detail["doc_id"],
                    "filename": detail["filename"],
                    "status": detail["status"],
                "message": f"文档已存在，复用已有索引: {detail['filename']}",
                    "chunk_count": detail["chunk_count"],
                    "provider_mode": detail["provider_mode"],
                    "vector_status": detail["vector_status"],
                    "qdrant_indexed": detail["vector_status"] == "indexed",
                    "collection_name": self.QDRANT_COLLECTION_NAME,
                }

        document = self.repo.create_document(
            title=filename,
            doc_type=self._detect_doc_type(filename),
            file_size=len(content),
            content_hash=content_hash,
            status="pending",
            extra_data={
                "content_preview": text_content[:500],
                "provider_mode": provider_mode,
                "vector_status": "pending",
                "status_history": [],
            },
        )
        self.repo.update_document_status(
            document["id"],
            status="processing",
            reason="开始切片与索引",
            provider_mode=provider_mode,
            vector_status="processing",
        )

        chunker = DocumentChunker(chunk_size=200, chunk_overlap=20, strategy="recursive")
        chunks = chunker.split_text(
            text_content,
            metadata={
                "source": filename,
                "document_id": document["id"],
                "provider_mode": provider_mode,
            },
        )
        vectors = await self.embedding_provider.embed_texts([chunk.text for chunk in chunks]) if chunks else []

        vector_status = "mock-indexed"
        qdrant_indexed = False
        point_ids: list[str] = []
        collection_name = self.QDRANT_COLLECTION_NAME

        if _QDRANT_AVAILABLE and vectors:
            try:
                client = get_qdrant_client()
                qdrant = QdrantService(client)
                await qdrant.ensure_collection(collection_name=collection_name, vector_size=len(vectors[0]))
                if hasattr(client, "upsert"):
                    from qdrant_client.models import PointStruct

                    points = []
                    candidate_point_ids: list[str] = []
                    for idx, (chunk, vector) in enumerate(zip(chunks, vectors, strict=False)):
                        point_id = self._build_qdrant_point_id(document["id"], idx)
                        candidate_point_ids.append(point_id)
                        points.append(
                            PointStruct(
                                id=point_id,
                                vector=vector,
                                payload={
                                    "document_id": document["id"],
                                    "filename": filename,
                                    "content": chunk.text,
                                    "chunk_index": idx,
                                    "provider_mode": provider_mode,
                                },
                            )
                        )
                    await qdrant.upsert_points(collection_name, points)
                    point_ids = candidate_point_ids
                    qdrant_indexed = True
                    vector_status = "indexed"
            except Exception as e:
                logger.warning(f"本地知识库 Qdrant 写入失败，降级 BM25: {e}")
                vector_status = f"failed:{e}"

        for idx, chunk in enumerate(chunks):
            vector_id = point_ids[idx] if idx < len(point_ids) else None
            self.repo.create_chunk(
                document_id=document["id"],
                content=chunk.text,
                chunk_index=idx,
                vector_id=vector_id,
                extra_data={
                    **chunk.metadata.to_dict(),
                    "token_count": chunk.token_count,
                    "provider_mode": provider_mode,
                    "vector_status": "indexed" if qdrant_indexed and vector_id else (vector_status if vectors else "not-indexed"),
                },
            )

        final_status = "indexed" if chunks else "failed"
        reason = "文档已完成索引" if chunks else "文档切片为空"
        self.repo.update_document_status(
            document["id"],
            status=final_status,
            chunk_count=len(chunks),
            reason=reason,
            provider_mode=provider_mode,
            vector_status=vector_status,
        )
        logger.info(
            f"本地知识库文档处理完成 | doc_id={document['id']} | status={final_status} | provider_mode={provider_mode} | vector_status={vector_status} | chunks={len(chunks)}"
        )
        return {
            "doc_id": document["id"],
            "filename": document["title"],
            "status": final_status,
            "message": f"文档已{'成功' if final_status == 'indexed' else '未能'}索引，共{len(chunks)}个文本块",
            "chunk_count": len(chunks),
            "provider_mode": provider_mode,
            "vector_status": vector_status,
            "qdrant_indexed": qdrant_indexed,
            "collection_name": collection_name,
        }

    async def list_documents(self, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        docs, total = self.repo.list_documents(status=status, limit=limit, offset=offset)
        return {"total": total, "documents": [self._serialize_document(doc) for doc in docs]}

    async def get_document_detail(self, doc_id: str) -> dict[str, Any] | None:
        document = self.repo.get_document(doc_id)
        if document is None:
            return None
        detail = self._serialize_document(document)
        detail["chunks"] = [
            {
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "vector_id": chunk["vector_id"],
                "metadata": chunk.get("extra_data") or {},
            }
            for chunk in self.repo.list_chunks_by_document(doc_id)
        ]
        return detail

    async def delete_document(self, doc_id: str) -> dict[str, Any] | None:
        document = self.repo.get_document(doc_id)
        if document is None:
            return None

        if _QDRANT_AVAILABLE and qdrant_models is not None:
            try:
                client = get_qdrant_client()
                qdrant = QdrantService(client)
                await qdrant.delete_by_filter(
                    collection_name=self.QDRANT_COLLECTION_NAME,
                    filter_=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="document_id",
                                match=qdrant_models.MatchValue(value=doc_id),
                            )
                        ]
                    ),
                )
            except Exception as e:
                logger.warning(f"本地知识库删除 Qdrant 清理失败: {e}")

        self.repo.soft_delete_document(doc_id)
        return {"doc_id": doc_id, "status": "deleted", "message": f"文档已成功删除: {document['title']}"}

    @classmethod
    def _build_selection_case_filename(cls, task_id: str) -> str:
        return f"{cls.SELECTION_CASE_PREFIX}{task_id}.md"

    @classmethod
    def _build_selection_case_document(cls, task: dict[str, Any]) -> tuple[str, bytes]:
        task_id = str(task.get("task_id") or "unknown")
        decision_output = task.get("decision_output") if isinstance(task.get("decision_output"), dict) else {}
        adoption = task.get("adoption") if isinstance(task.get("adoption"), dict) else {}
        result_payload = task.get("result") if isinstance(task.get("result"), dict) else {}
        execution_feedback = decision_output.get("execution_feedback") if isinstance(decision_output.get("execution_feedback"), dict) else {}
        execution_feedback_snapshot = result_payload.get("execution_feedback_snapshot") if isinstance(result_payload.get("execution_feedback_snapshot"), dict) else {}
        rescore_summary = decision_output.get("rescore_summary") if isinstance(decision_output.get("rescore_summary"), dict) else {}
        product = decision_output.get("product") if isinstance(decision_output.get("product"), dict) else {}
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        profitability = decision_output.get("profitability") if isinstance(decision_output.get("profitability"), dict) else {}
        supply_chain = decision_output.get("supply_chain") if isinstance(decision_output.get("supply_chain"), dict) else {}
        decision_meta = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}
        recommendation_reasons = decision_output.get("recommendation_reasons") if isinstance(decision_output.get("recommendation_reasons"), list) else []
        risks = decision_output.get("risks") if isinstance(decision_output.get("risks"), list) else []
        case_summary = {
            "case_type": cls.SELECTION_CASE_TYPE,
            "task_id": task_id,
            "query": task.get("query"),
            "category": task.get("category"),
            "target_market": task.get("target_market"),
            "decision": decision_meta.get("decision"),
            "recommended_price": pricing.get("recommended_price"),
            "supplier": supply_chain.get("primary_supplier") or adoption.get("supplier_code"),
            "sales_7d": ((execution_feedback.get("sales") or {}).get("sales_7d")) or execution_feedback_snapshot.get("sales", {}).get("orders", {}).get("units"),
            "review_rating": ((execution_feedback.get("reviews") or {}).get("rating")) or execution_feedback_snapshot.get("reviews", {}).get("avg_rating"),
            "review_count": ((execution_feedback.get("reviews") or {}).get("count")) or execution_feedback_snapshot.get("reviews", {}).get("review_count"),
            "gross_profit": ((execution_feedback.get("profit") or {}).get("gross_profit")) or execution_feedback_snapshot.get("profit", {}).get("gross_profit_total"),
            "inventory_available": ((execution_feedback.get("inventory") or {}).get("available_inventory")) or execution_feedback_snapshot.get("inventory", {}).get("summary", {}).get("available_quantity_total"),
            "rescore_decision": rescore_summary.get("decision"),
            "rescore_score": rescore_summary.get("score"),
        }
        lines = [
            f"# 历史选品案例 {task_id}",
            "",
            f"- case_type: {cls.SELECTION_CASE_TYPE}",
            f"- query: {task.get('query') or '-'}",
            f"- category: {task.get('category') or '-'}",
            f"- target_market: {task.get('target_market') or '-'}",
            f"- product_name: {product.get('name') or product.get('product_name') or '-'}",
            f"- asin: {product.get('asin') or product.get('external_product_id') or '-'}",
            f"- decision: {decision_meta.get('decision') or '-'}",
            f"- recommended_price: {pricing.get('recommended_price') or '-'}",
            f"- expected_margin: {profitability.get('expected_margin') or profitability.get('margin_rate') or '-'}",
            f"- primary_supplier: {supply_chain.get('primary_supplier') or adoption.get('supplier_code') or '-'}",
            f"- sales_7d: {case_summary.get('sales_7d') or 0}",
            f"- review_rating: {case_summary.get('review_rating') or '-'}",
            f"- review_count: {case_summary.get('review_count') or 0}",
            f"- gross_profit: {case_summary.get('gross_profit') or 0}",
            f"- inventory_available: {case_summary.get('inventory_available') or 0}",
            f"- rescore_decision: {rescore_summary.get('decision') or '-'}",
            f"- rescore_score: {rescore_summary.get('score') or '-'}",
            "",
            "## 推荐理由",
        ]
        lines.extend([f"- {reason}" for reason in recommendation_reasons[:8]] or ["- 无"])
        lines.extend(["", "## 风险清单"])
        lines.extend([f"- {risk.get('name') or risk.get('category')}: {risk.get('score') or '-'}" for risk in risks[:8] if isinstance(risk, dict)] or ["- 无"])
        lines.extend(["", "## 结构化摘要JSON", json.dumps(case_summary, ensure_ascii=False)])
        return cls._build_selection_case_filename(task_id), "\n".join(lines).encode("utf-8")

    async def ingest_selection_case(self, task: dict[str, Any]) -> dict[str, Any]:
        filename, content = self._build_selection_case_document(task)
        result = await self.upload_document(filename, content)
        result["case_type"] = self.SELECTION_CASE_TYPE
        result["task_id"] = str(task.get("task_id") or "")
        result["query"] = task.get("query")
        return result

    async def query_selection_cases(self, query: str, top_k: int, threshold: float) -> dict[str, Any]:
        result = await self.query_knowledge(query=query, top_k=max(top_k * 2, 10), threshold=threshold)
        filtered = [
            item
            for item in result.get("results", [])
            if str((item.get("metadata") or {}).get("source") or item.get("source") or "").startswith(self.SELECTION_CASE_PREFIX)
            or (item.get("content") or "").startswith("# 历史选品案例")
            or (item.get("content") or "").find(f"case_type: {self.SELECTION_CASE_TYPE}") >= 0
        ][:top_k]
        result["results"] = filtered
        result["total_found"] = len(filtered)
        result["case_type"] = self.SELECTION_CASE_TYPE
        return result

    @classmethod
    def _build_review_case_filename(cls, review_id: str) -> str:
        return f"{cls.REVIEW_CASE_PREFIX}{review_id}.md"

    @classmethod
    def _build_review_case_document(cls, review: dict[str, Any]) -> tuple[str, bytes]:
        review_id = str(review.get("id") or review.get("review_id") or review.get("ticket_id") or "unknown")
        feedback_text = str(review.get("feedback") or review.get("comment") or review.get("review_text") or "").strip()
        review_count = int(review.get("review_count") or 1)
        rating = review.get("customer_score") or review.get("rating")
        rating_value = float(rating) if rating is not None else None
        complaint_keywords = ["refund", "complaint", "issue", "bad", "broken", "退货", "投诉", "问题", "差评", "破损"]
        sentiment = "negative" if any(keyword in feedback_text.lower() for keyword in complaint_keywords) or (rating_value is not None and rating_value < 3.5) else "positive"
        case_summary = {
            "case_type": cls.REVIEW_CASE_TYPE,
            "review_id": review_id,
            "task_id": review.get("task_id"),
            "product_id": review.get("product_id"),
            "product_name": review.get("product_name") or review.get("name"),
            "asin": review.get("asin"),
            "rating": rating_value,
            "review_count": review_count,
            "sentiment": sentiment,
            "ticket_id": review.get("ticket_id"),
            "customer_id": review.get("customer_id"),
        }
        lines = [
            f"# CRM评价案例 {review_id}",
            "",
            f"- case_type: {cls.REVIEW_CASE_TYPE}",
            f"- review_id: {review_id}",
            f"- task_id: {review.get('task_id') or '-'}",
            f"- product_id: {review.get('product_id') or '-'}",
            f"- product_name: {review.get('product_name') or review.get('name') or '-'}",
            f"- asin: {review.get('asin') or '-'}",
            f"- rating: {rating_value if rating_value is not None else '-'}",
            f"- review_count: {review_count}",
            f"- sentiment: {sentiment}",
            "",
            "## 评价内容",
            feedback_text or "-",
            "",
            "## 结构化摘要JSON",
            json.dumps(case_summary, ensure_ascii=False),
        ]
        return cls._build_review_case_filename(review_id), "\n".join(lines).encode("utf-8")

    async def ingest_review_case(self, review: dict[str, Any]) -> dict[str, Any]:
        filename, content = self._build_review_case_document(review)
        result = await self.upload_document(filename, content)
        result["case_type"] = self.REVIEW_CASE_TYPE
        result["review_id"] = str(review.get("id") or review.get("review_id") or review.get("ticket_id") or "")
        result["product_id"] = str(review.get("product_id") or "")
        result["asin"] = review.get("asin")
        result["vector_sync"] = {
            "embedding_provider_mode": result.get("provider_mode"),
            "vector_status": result.get("vector_status"),
            "qdrant_indexed": bool(result.get("qdrant_indexed")),
            "collection_name": result.get("collection_name"),
            "chunk_count": int(result.get("chunk_count") or 0),
            "is_incremental": True,
        }
        return result

    async def query_review_cases(self, query: str, top_k: int, threshold: float) -> dict[str, Any]:
        result = await self.query_knowledge(query=query, top_k=max(top_k * 2, 10), threshold=threshold)
        filtered = [
            item
            for item in result.get("results", [])
            if str((item.get("metadata") or {}).get("source") or item.get("source") or "").startswith(self.REVIEW_CASE_PREFIX)
            or (item.get("content") or "").startswith("# CRM评价案例")
            or (item.get("content") or "").find(f"case_type: {self.REVIEW_CASE_TYPE}") >= 0
        ][:top_k]
        result["results"] = filtered
        result["total_found"] = len(filtered)
        result["case_type"] = self.REVIEW_CASE_TYPE
        return result

    @staticmethod
    def _normalize_cache_query(query: str) -> str:
        return "".join(str(query).lower().split())

    @classmethod
    def _compute_query_similarity(cls, left: str, right: str) -> float:
        return round(SequenceMatcher(a=cls._normalize_cache_query(left), b=cls._normalize_cache_query(right)).ratio(), 6)

    @staticmethod
    def _build_corpus_fingerprint(chunks: list[dict[str, Any]]) -> str:
        source = [
            {
                "id": chunk.get("id"),
                "document_id": chunk.get("document_id"),
                "chunk_index": chunk.get("chunk_index"),
                "content": chunk.get("content"),
                "metadata": chunk.get("extra_data") or {},
            }
            for chunk in chunks
        ]
        return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _query_cache_hash_name() -> str:
        return "knowledge:query-cache:local"

    async def _load_query_cache_entries(self) -> tuple[dict[str, str], str]:
        hash_name = self._query_cache_hash_name()
        try:
            redis_client = get_redis_connection()
            cache = CacheService(redis_client)
            payload = await cache.hgetall(hash_name)
            return payload if isinstance(payload, dict) else {}, "redis"
        except Exception:
            return dict(_QUERY_CACHE_FALLBACK.get(hash_name, {})), "memory"

    async def _write_query_cache_entry(self, *, cache_key: str, payload: dict[str, Any]) -> str:
        hash_name = self._query_cache_hash_name()
        serialized = json.dumps(payload, ensure_ascii=False)
        try:
            redis_client = get_redis_connection()
            cache = CacheService(redis_client)
            await cache.hset(hash_name, cache_key, serialized)
            await cache.expire(hash_name, self.QUERY_CACHE_TTL_SECONDS)
            return "redis"
        except Exception:
            _QUERY_CACHE_FALLBACK.setdefault(hash_name, {})[cache_key] = serialized
            return "memory"

    async def _read_query_cache(
        self,
        *,
        query: str,
        top_k: int,
        threshold: float,
        corpus_fingerprint: str,
    ) -> tuple[dict[str, Any] | None, str]:
        entries, backend = await self._load_query_cache_entries()
        now = datetime.now(UTC)
        best_match: dict[str, Any] | None = None
        best_similarity = 0.0
        normalized_query = self._normalize_cache_query(query)
        threshold_key = round(float(threshold), 6)
        for raw in entries.values():
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            expires_at_raw = payload.get("expires_at")
            if not expires_at_raw:
                continue
            try:
                expires_at = datetime.fromisoformat(expires_at_raw)
            except Exception:
                continue
            if expires_at < now:
                continue
            if int(payload.get("top_k") or 0) != int(top_k):
                continue
            if round(float(payload.get("threshold") or 0.0), 6) != threshold_key:
                continue
            if payload.get("corpus_fingerprint") != corpus_fingerprint:
                continue
            similarity = round(SequenceMatcher(a=normalized_query, b=str(payload.get("normalized_query") or "")).ratio(), 6)
            if similarity >= self.QUERY_CACHE_SIMILARITY_THRESHOLD and similarity > best_similarity:
                best_match = payload
                best_similarity = similarity
        if best_match is None:
            return None, backend
        result = dict(best_match.get("result") or {})
        result["cache_hit"] = True
        result["cache_backend"] = backend
        result["cache_similarity"] = best_similarity
        result["cached_query"] = best_match.get("query")
        return result, backend

    async def _cache_query_result(
        self,
        *,
        query: str,
        top_k: int,
        threshold: float,
        result: dict[str, Any],
        corpus_fingerprint: str,
    ) -> dict[str, Any]:
        cache_key = hashlib.sha256(
            f"local:{corpus_fingerprint}:{query}:{top_k}:{round(float(threshold), 6)}".encode()
        ).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(seconds=self.QUERY_CACHE_TTL_SECONDS)
        cache_payload = {
            "query": query,
            "normalized_query": self._normalize_cache_query(query),
            "top_k": int(top_k),
            "threshold": round(float(threshold), 6),
            "corpus_fingerprint": corpus_fingerprint,
            "expires_at": expires_at.isoformat(),
            "result": {
                "query": result.get("query"),
                "results": result.get("results", []),
                "total_found": result.get("total_found", 0),
                "processing_time_ms": result.get("processing_time_ms", 0.0),
            },
        }
        backend = await self._write_query_cache_entry(cache_key=cache_key, payload=cache_payload)
        enriched = dict(result)
        enriched["cache_hit"] = False
        enriched["cache_backend"] = backend
        enriched["cache_similarity"] = None
        enriched["cached_query"] = None
        return enriched

    async def query_knowledge(self, query: str, top_k: int, threshold: float) -> dict[str, Any]:
        start = datetime.now(UTC)
        chunks = self.repo.list_indexed_chunks()
        if not chunks:
            raise ValueError("knowledge base is empty; upload a document first")
        if False:
            raise ValueError("鐭ヨ瘑搴撲负绌猴紝璇峰厛涓婁紶鏂囨。")

        corpus_fingerprint = self._build_corpus_fingerprint(chunks)
        cached, _ = await self._read_query_cache(
            query=query,
            top_k=top_k,
            threshold=threshold,
            corpus_fingerprint=corpus_fingerprint,
        )
        if cached is not None:
            cached["processing_time_ms"] = round((datetime.now(UTC) - start).total_seconds() * 1000, 2)
            return cached

        provider_mode = self.embedding_provider.provider_mode
        candidate_top_k = max(top_k * 2, 10)

        qdrant_results = await self._search_qdrant(
            collection_name=self.QDRANT_COLLECTION_NAME,
            query=query,
            top_k=candidate_top_k,
            threshold=threshold,
            provider_mode=provider_mode,
        )
        indexed_doc_ids = {str(chunk.get("document_id") or "") for chunk in chunks}
        qdrant_results = [
            item
            for item in qdrant_results
            if str(item.get("document_id") or (item.get("metadata") or {}).get("document_id") or "") in indexed_doc_ids
        ]

        def _result_key(item: dict[str, Any]) -> str:
            metadata = item.get("metadata") or {}
            doc_id = str(item.get("document_id") or metadata.get("document_id") or "")
            chunk_index = item.get("chunk_index") if item.get("chunk_index") is not None else metadata.get("chunk_index")
            if doc_id and chunk_index is not None:
                return f"{doc_id}:{chunk_index}"
            return hashlib.sha256(str(item.get("content") or "").encode("utf-8")).hexdigest()

        qdrant_by_key = {_result_key(item): item for item in qdrant_results}
        if not chunks:
            raise ValueError("知识库为空，请先上传文档")

        retriever = HybridRetriever(
            fusion_top_k=candidate_top_k,
            keyword_top_k=candidate_top_k,
            qdrant_collection_name=self.QDRANT_COLLECTION_NAME,
            enable_qdrant_vector_search=False,
            cache_enabled=False,
        )
        retriever.add_documents(
            [
                {
                    "id": chunk["id"],
                    "content": chunk["content"],
                    "metadata": {
                        "document_id": chunk["document_id"],
                        "chunk_index": chunk["chunk_index"],
                        **(chunk.get("extra_data") or {}),
                    },
                }
                for chunk in chunks
            ]
        )
        results = await retriever.retrieve(query, top_k=candidate_top_k)
        normalized = []
        for item in results:
            item_dict = {
                "content": item.content,
                "score": item.score,
                "vector_score": getattr(item, "vector_score", None),
                "keyword_score": getattr(item, "keyword_score", None),
                "source": item.source or (item.metadata or {}).get("source"),
                "document_id": (item.metadata or {}).get("document_id"),
                "chunk_index": (item.metadata or {}).get("chunk_index"),
                "provider_mode": (item.metadata or {}).get("provider_mode", provider_mode),
                "metadata": item.metadata,
            }
            qdrant_item = qdrant_by_key.pop(_result_key(item_dict), None)
            if qdrant_item is not None:
                item_dict["vector_score"] = qdrant_item.get("score")
                item_dict["score"] = max(float(item_dict.get("score") or 0.0), float(qdrant_item.get("score") or 0.0))
            if item_dict["score"] >= threshold:
                normalized.append(item_dict)

        for qdrant_item in qdrant_by_key.values():
            if float(qdrant_item.get("score") or 0.0) < threshold:
                continue
            normalized.append(
                {
                    **qdrant_item,
                    "vector_score": qdrant_item.get("score"),
                    "keyword_score": None,
                    "provider_mode": qdrant_item.get("provider_mode", provider_mode),
                }
            )

        normalized = sorted(normalized, key=lambda item: float(item.get("score") or 0.0), reverse=True)[:top_k]
        normalized = self._enrich_query_results(normalized, ranking_stage="hybrid")
        result = {
            "query": query,
            "results": normalized,
            "total_found": len(normalized),
            "processing_time_ms": round((datetime.now(UTC) - start).total_seconds() * 1000, 2),
        }
        return await self._cache_query_result(
            query=query,
            top_k=top_k,
            threshold=threshold,
            result=result,
            corpus_fingerprint=corpus_fingerprint,
        )

    async def get_stats(self) -> dict[str, Any]:
        return self.repo.get_stats()
