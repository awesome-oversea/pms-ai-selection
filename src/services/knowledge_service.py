"""
知识库应用服务
==============

承接知识库上传、切片、向量化、查询与状态流转逻辑，
避免 endpoint 直接处理内存态和底层基础设施细节。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authorization import require_permission
from src.core.logging import get_logger
from src.core.rbac import ACTION_MANAGE, RESOURCE_KNOWLEDGE, build_permission
from src.core.tenant import get_default_tenant_id
from src.infrastructure.qdrant import _QDRANT_AVAILABLE, QdrantService, get_qdrant_client
from src.infrastructure.qdrant import models as qdrant_models
from src.infrastructure.redis import CacheService, get_redis_connection
from src.infrastructure.search_backend import get_search_backend
from src.infrastructure.tracing import get_request_id, get_trace_id
from src.rag.chunkers import DocumentChunker
from src.repositories.knowledge_repository import KnowledgeRepository
from src.services.embedding import EmbeddingProvider

logger = get_logger(__name__)

_QUERY_CACHE_FALLBACK: dict[str, dict[str, str]] = {}


class KnowledgeService:
    """知识库应用服务。"""

    QUERY_CACHE_TTL_SECONDS = 3600
    QUERY_CACHE_SIMILARITY_THRESHOLD = 0.95
    SELECTION_CASE_PREFIX = "selection_case_"
    SELECTION_CASE_TYPE = "selection_history_case"
    REVIEW_CASE_PREFIX = "crm_review_case_"
    REVIEW_CASE_TYPE = "crm_review_case"

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.actor = actor or {}
        self.tenant_id = tenant_id or self.actor.get("tenant_id") or get_default_tenant_id()
        self.repo = KnowledgeRepository(session, tenant_id=self.tenant_id)
        self.embedding_provider = EmbeddingProvider.get_instance()

    @staticmethod
    def _detect_doc_type(filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    @staticmethod
    def _hash_content(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def _search_qdrant(
        self,
        collection_name: str,
        query: str,
        top_k: int,
        threshold: float,
        provider_mode: str,
        tenant_id: str,
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
                filter_=(
                    qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="tenant_id",
                                match=qdrant_models.MatchValue(value=tenant_id),
                            )
                        ]
                    )
                    if qdrant_models is not None
                    else None
                ),
            )

            normalized = []
            for item in results:
                payload = item.get("payload") or {}
                normalized.append(
                    {
                        "content": payload.get("content", ""),
                        "score": item.get("score", 0.0),
                        "source": payload.get("filename") or payload.get("source"),
                        "document_id": payload.get("document_id"),
                        "chunk_index": payload.get("chunk_index"),
                        "provider_mode": payload.get("provider_mode", provider_mode),
                        "metadata": payload,
                    }
                )

            if normalized:
                logger.info(
                    f"知识库Qdrant检索完成 | provider_mode={provider_mode} | top_k={top_k} | hit={len(normalized)}"
                )
            return normalized
        except Exception as e:
            logger.warning(f"Qdrant 检索失败，回退 DB/BM25 检索: {e}")
            return []

    async def upload_document(self, filename: str, content: bytes) -> dict[str, Any]:
        text_content = content.decode("utf-8")
        kb = await self.repo.get_or_create_default_knowledge_base()
        provider_mode = self.embedding_provider.provider_mode
        content_hash = self._hash_content(content)

        existing = await self.repo.get_document_by_hash(kb.id, content_hash, title=filename)
        if existing is not None:
            logger.info(
                f"知识库文档命中幂等 | doc_id={existing.id} | provider_mode={provider_mode} | filename={filename}"
            )
            detail = self._serialize_document(existing)
            return {
                "doc_id": detail["doc_id"],
                "filename": detail["filename"],
                "status": detail["status"],
                "message": f"文档已存在，复用已有索引: {detail['filename']}",
                "chunk_count": detail["chunk_count"],
                "provider_mode": detail["provider_mode"],
                "vector_status": detail["vector_status"],
                "qdrant_indexed": detail["vector_status"] == "indexed",
                "collection_name": kb.collection_name or "product_knowledge",
                "version": detail["version"],
                "index_version": detail["index_version"],
                "is_current_version": detail["is_current_version"],
                "previous_document_id": detail["previous_document_id"],
            }

        current_version_doc = await self.repo.get_current_document_by_title(kb.id, filename)
        version = 1
        previous_document_id = None
        if current_version_doc is not None:
            previous_extra = current_version_doc.extra_data or {}
            version = int(previous_extra.get("version", 1)) + 1
            previous_document_id = str(current_version_doc.id)
            await self.repo.mark_document_not_current(current_version_doc.id)

        document = await self.repo.create_document(
            knowledge_base_id=kb.id,
            title=filename,
            doc_type=self._detect_doc_type(filename),
            file_size=len(content),
            content_hash=content_hash,
            status="pending",
            extra_data={
                "document_key": filename,
                "version": version,
                "is_current_version": True,
                "index_version": version,
                "index_status": "pending",
                "rebuild_status": "pending",
                "previous_document_id": previous_document_id,
                "content_preview": text_content[:500],
                "provider_mode": provider_mode,
                "vector_status": "pending",
                "status_history": [],
                "request_id": get_request_id(),
                "trace_id": get_trace_id(),
            },
        )
        await self.repo.update_document_status(
            document.id,
            status="processing",
            reason="开始切片与索引",
            provider_mode=provider_mode,
            vector_status="processing",
        )

        chunker = DocumentChunker(
            chunk_size=kb.chunk_size or 200,
            chunk_overlap=kb.chunk_overlap or 20,
            strategy="recursive",
        )
        chunks = chunker.split_text(
            text_content,
            metadata={
                "source": filename,
                "document_id": str(document.id),
                "knowledge_base_id": str(kb.id),
                "provider_mode": provider_mode,
                "tenant_id": self.tenant_id,
            },
        )

        vectors = await self.embedding_provider.embed_texts([chunk.text for chunk in chunks]) if chunks else []

        vector_status = "mock-indexed"
        qdrant_indexed = False
        point_ids: list[str] = []

        if _QDRANT_AVAILABLE and vectors:
            try:
                client = get_qdrant_client()
                qdrant = QdrantService(client)
                await qdrant.ensure_collection(
                    collection_name=kb.collection_name or "product_knowledge",
                    vector_size=len(vectors[0]),
                )
                if hasattr(client, "upsert"):
                    from qdrant_client.models import PointStruct

                    points = []
                    for idx, (chunk, vector) in enumerate(zip(chunks, vectors, strict=False)):
                        point_id = str(UUID(int=(document.id.int + idx + 1) % (1 << 128)))
                        point_ids.append(point_id)
                        points.append(
                            PointStruct(
                                id=point_id,
                                vector=vector,
                                payload={
                                    "tenant_id": self.tenant_id,
                                    "document_id": str(document.id),
                                    "knowledge_base_id": str(kb.id),
                                    "filename": filename,
                                    "content": chunk.text,
                                    "chunk_index": idx,
                                    "provider_mode": provider_mode,
                                },
                            )
                        )
                    await qdrant.upsert_points(kb.collection_name or "product_knowledge", points)
                    qdrant_indexed = True
                    vector_status = "indexed"
            except Exception as e:
                logger.warning(f"Qdrant 写入失败，降级为数据库/BM25 检索: {e}")
                vector_status = f"failed:{e}"

        for idx, chunk in enumerate(chunks):
            vector_id = point_ids[idx] if idx < len(point_ids) else None
            await self.repo.create_chunk(
                document_id=document.id,
                content=chunk.text,
                chunk_index=idx,
                vector_id=vector_id,
                extra_data={
                    **chunk.metadata.to_dict(),
                    "token_count": chunk.token_count,
                    "provider_mode": provider_mode,
                    "vector_status": "indexed" if vector_id else ("mock-indexed" if vectors else "not-indexed"),
                },
            )

        final_status = "indexed" if chunks else "failed"
        reason = "文档已完成索引" if chunks else "文档切片为空"
        await self.repo.update_document_status(
            document.id,
            status=final_status,
            chunk_count=len(chunks),
            reason=reason,
            provider_mode=provider_mode,
            vector_status=vector_status,
        )
        await self.session.commit()
        await self.session.refresh(document)

        logger.info(
            f"知识库文档处理完成 | doc_id={document.id} | status={final_status} | provider_mode={provider_mode} | vector_status={vector_status} | chunks={len(chunks)}"
        )

        return {
            "doc_id": str(document.id),
            "filename": document.title,
            "status": final_status,
            "message": f"文档已{'成功' if final_status == 'indexed' else '未能'}索引，共{len(chunks)}个文本块",
            "chunk_count": len(chunks),
            "provider_mode": provider_mode,
            "vector_status": vector_status,
            "qdrant_indexed": qdrant_indexed,
            "collection_name": kb.collection_name or "product_knowledge",
            "version": version,
            "index_version": version,
            "is_current_version": True,
            "previous_document_id": previous_document_id,
        }

    def _serialize_document(self, document: Any) -> dict[str, Any]:
        extra = document.extra_data or {}
        return {
            "doc_id": str(document.id),
            "filename": document.title,
            "file_size": document.file_size or 0,
            "chunk_count": document.chunk_count or 0,
            "status": document.status,
            "uploaded_at": document.created_at.isoformat() if document.created_at else None,
            "content_preview": extra.get("content_preview", ""),
            "vector_status": extra.get("vector_status", "unknown"),
            "provider_mode": extra.get("provider_mode", "unknown"),
            "status_reason": extra.get("status_reason"),
            "status_history": extra.get("status_history", []),
            "document_key": extra.get("document_key", document.title),
            "version": extra.get("version", 1),
            "index_version": extra.get("index_version"),
            "index_status": extra.get("index_status", extra.get("vector_status", "unknown")),
            "rebuild_status": extra.get("rebuild_status", "unknown"),
            "is_current_version": extra.get("is_current_version", True),
            "previous_document_id": extra.get("previous_document_id"),
        }

    async def list_documents(self, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        docs, total = await self.repo.list_documents(status=status, limit=limit, offset=offset)
        return {"total": total, "documents": [self._serialize_document(doc) for doc in docs]}

    async def list_document_versions(self, doc_id: str) -> dict[str, Any] | None:
        try:
            document = await self.repo.get_document(UUID(doc_id))
        except ValueError:
            return None
        if document is None:
            return None
        versions = await self.repo.list_document_versions(document.knowledge_base_id, document.title)
        return {
            "document_key": document.title,
            "total": len(versions),
            "versions": [self._serialize_document(doc) for doc in versions],
        }

    async def rollback_document_version(self, doc_id: str) -> dict[str, Any] | None:
        require_permission(
            self.actor,
            build_permission(RESOURCE_KNOWLEDGE, ACTION_MANAGE),
            resource="knowledge_document",
        )
        try:
            document = await self.repo.switch_current_version(UUID(doc_id))
        except ValueError:
            return None
        if document is None:
            return None
        if self.session is not None:
            await self.session.commit()
            await self.session.refresh(document)
        detail = self._serialize_document(document)
        return {
            "doc_id": detail["doc_id"],
            "version": detail["version"],
            "status": "rolled_back",
            "message": f"文档当前版本已切换到 v{detail['version']}",
        }

    async def compare_document_versions(self, baseline_doc_id: str, target_doc_id: str) -> dict[str, Any] | None:
        try:
            baseline = await self.repo.get_document(UUID(baseline_doc_id))
            target = await self.repo.get_document(UUID(target_doc_id))
        except ValueError:
            return None
        if baseline is None or target is None:
            return None
        if baseline.knowledge_base_id != target.knowledge_base_id or baseline.title != target.title:
            raise ValueError("仅支持对同一知识库下同名文档进行版本对比")

        baseline_detail = await self.get_document_detail(baseline_doc_id)
        target_detail = await self.get_document_detail(target_doc_id)
        if baseline_detail is None or target_detail is None:
            return None

        baseline_text = "\n".join(chunk.get("content", "") for chunk in baseline_detail.get("chunks", []))
        target_text = "\n".join(chunk.get("content", "") for chunk in target_detail.get("chunks", []))
        similarity = SequenceMatcher(None, baseline_text, target_text).ratio()
        baseline_lines = [line.strip() for line in baseline_text.splitlines() if line.strip()]
        target_lines = [line.strip() for line in target_text.splitlines() if line.strip()]
        added_lines = [line for line in target_lines if line not in baseline_lines]
        removed_lines = [line for line in baseline_lines if line not in target_lines]
        shared_lines = [line for line in target_lines if line in baseline_lines]

        return {
            "document_key": baseline_detail.get("document_key") or baseline_detail.get("filename"),
            "baseline": {
                "doc_id": baseline_detail.get("doc_id"),
                "version": baseline_detail.get("version"),
                "chunk_count": baseline_detail.get("chunk_count"),
                "is_current_version": baseline_detail.get("is_current_version"),
            },
            "target": {
                "doc_id": target_detail.get("doc_id"),
                "version": target_detail.get("version"),
                "chunk_count": target_detail.get("chunk_count"),
                "is_current_version": target_detail.get("is_current_version"),
            },
            "summary": {
                "similarity": round(similarity, 4),
                "baseline_characters": len(baseline_text),
                "target_characters": len(target_text),
                "added_line_count": len(added_lines),
                "removed_line_count": len(removed_lines),
                "shared_line_count": len(shared_lines),
            },
            "difference_items": [
                {"type": "added", "content": line}
                for line in added_lines[:50]
            ]
            + [
                {"type": "removed", "content": line}
                for line in removed_lines[:50]
            ],
        }

    async def get_document_detail(self, doc_id: str) -> dict[str, Any] | None:
        try:
            document = await self.repo.get_document(UUID(doc_id))
        except ValueError:
            return None
        if document is None:
            return None
        detail = self._serialize_document(document)
        detail["chunks"] = [
            {
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "vector_id": chunk.vector_id,
                "metadata": chunk.extra_data or {},
            }
            for chunk in await self.repo.list_chunks_by_document(document.id)
        ]
        return detail

    async def delete_document(self, doc_id: str) -> dict[str, Any] | None:
        require_permission(
            self.actor,
            build_permission(RESOURCE_KNOWLEDGE, ACTION_MANAGE),
            resource="knowledge_document",
        )
        try:
            document_uuid = UUID(doc_id)
        except ValueError:
            return None

        document = await self.repo.get_document(document_uuid)
        if document is None:
            return None

        filename = document.title
        kb = await self.repo.get_or_create_default_knowledge_base()
        if _QDRANT_AVAILABLE and qdrant_models is not None:
            try:
                client = get_qdrant_client()
                qdrant = QdrantService(client)
                await qdrant.delete_by_filter(
                    collection_name=kb.collection_name or "product_knowledge",
                    filter_=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="document_id",
                                match=qdrant_models.MatchValue(value=str(document_uuid)),
                            ),
                            qdrant_models.FieldCondition(
                                key="tenant_id",
                                match=qdrant_models.MatchValue(value=self.tenant_id),
                            ),
                        ]
                    ),
                )
            except Exception as e:
                logger.warning(f"Qdrant 删除失败，继续执行软删除: {e}")

        backend = get_search_backend()
        index_name = backend.build_index_name(self.tenant_id)
        await backend.delete_by_document(index_name=index_name, document_id=str(document_uuid), tenant_id=self.tenant_id)

        await self.repo.soft_delete_document(document_uuid)
        if self.session is not None:
            await self.session.commit()
        logger.info(f"知识库文档删除完成 | doc_id={doc_id} | filename={filename}")
        return {"doc_id": doc_id, "status": "deleted", "message": f"文档已成功删除: {filename}"}

    async def _search_db_keyword(self, query: str, top_k: int, threshold: float, provider_mode: str) -> list[dict[str, Any]]:
        chunks = await self.repo.list_indexed_chunks()
        if not chunks:
            return []

        documents = [
            {
                "id": str(chunk.id),
                "content": chunk.content,
                "metadata": {
                    "tenant_id": self.tenant_id,
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    **(chunk.extra_data or {}),
                },
            }
            for chunk in chunks
        ]

        backend = get_search_backend()
        index_name = f"{backend.settings.index_prefix}{self.tenant_id.replace('-', '')}"
        await backend.index_documents(index_name, documents)
        search_results = await backend.keyword_search(
            index_name=index_name,
            query=query,
            top_k=top_k,
            filters={"tenant_id": self.tenant_id},
        )

        if search_results:
            normalized_results = []
            for item in search_results:
                item_dict = {
                    "content": item.get("content", ""),
                    "score": item.get("score", 0.0),
                    "vector_score": None,
                    "keyword_score": item.get("score", 0.0),
                    "source": item.get("source") or (item.get("metadata") or {}).get("source"),
                    "document_id": item.get("document_id") or (item.get("metadata") or {}).get("document_id"),
                    "chunk_index": item.get("chunk_index") if item.get("chunk_index") is not None else (item.get("metadata") or {}).get("chunk_index"),
                    "provider_mode": provider_mode,
                    "metadata": item.get("metadata") or {},
                }
                if item_dict["score"] >= threshold:
                    normalized_results.append(item_dict)
            if normalized_results:
                return normalized_results

        from src.rag.retriever import HybridRetriever

        retriever = HybridRetriever(fusion_top_k=top_k, keyword_top_k=max(top_k * 2, 10))
        retriever.add_documents(documents)
        results = await retriever.retrieve(
            query,
            top_k=top_k,
            filters={"tenant_id": self.tenant_id},
        )

        normalized_results = []
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
            if item_dict["score"] >= threshold:
                normalized_results.append(item_dict)
        return normalized_results

    async def reindex_search_backend(self) -> dict[str, Any]:
        chunks = await self.repo.list_indexed_chunks()
        documents = [
            {
                "id": str(chunk.id),
                "content": chunk.content,
                "metadata": {
                    "tenant_id": self.tenant_id,
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    **(chunk.extra_data or {}),
                },
            }
            for chunk in chunks
        ]
        backend = get_search_backend()
        index_name = backend.build_index_name(self.tenant_id)
        result = await backend.reindex_documents(index_name=index_name, documents=documents)
        result["tenant_id"] = self.tenant_id
        return result

    @staticmethod
    def _build_citation(item: dict[str, Any]) -> dict[str, Any]:
        content = item.get("content", "") or ""
        return {
            "document_id": item.get("document_id"),
            "chunk_index": item.get("chunk_index"),
            "source": item.get("source"),
            "snippet": content[:160],
        }

    @staticmethod
    def _normalize_cache_query(query: str) -> str:
        return "".join(str(query).lower().split())

    @classmethod
    def _compute_query_similarity(cls, left: str, right: str) -> float:
        return round(SequenceMatcher(a=cls._normalize_cache_query(left), b=cls._normalize_cache_query(right)).ratio(), 6)

    def _query_cache_hash_name(self) -> str:
        return f"knowledge:query-cache:{self.tenant_id}"

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

    async def _read_query_cache(self, *, query: str, top_k: int, threshold: float) -> tuple[dict[str, Any] | None, str]:
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
            cached_query = str(payload.get("normalized_query") or "")
            similarity = round(SequenceMatcher(a=normalized_query, b=cached_query).ratio(), 6)
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

    async def _cache_query_result(self, *, query: str, top_k: int, threshold: float, result: dict[str, Any]) -> dict[str, Any]:
        cache_key = hashlib.sha256(f"{self.tenant_id}:{query}:{top_k}:{threshold}".encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(seconds=self.QUERY_CACHE_TTL_SECONDS)
        cache_payload = {
            "query": query,
            "normalized_query": self._normalize_cache_query(query),
            "top_k": int(top_k),
            "threshold": round(float(threshold), 6),
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

    @staticmethod
    def _fuse_hybrid_results(
        vector_results: list[dict[str, Any]],
        keyword_results: list[dict[str, Any]],
        top_k: int,
        provider_mode: str,
    ) -> list[dict[str, Any]]:
        fused: dict[str, dict[str, Any]] = {}
        rrf_k = 60

        for rank, item in enumerate(vector_results, 1):
            key = f"{item.get('document_id')}:{item.get('chunk_index')}"
            current = fused.setdefault(
                key,
                {
                    "content": item.get("content", ""),
                    "score": 0.0,
                    "vector_score": None,
                    "keyword_score": None,
                    "source": item.get("source"),
                    "document_id": item.get("document_id"),
                    "chunk_index": item.get("chunk_index"),
                    "provider_mode": item.get("provider_mode", provider_mode),
                    "metadata": item.get("metadata", {}),
                },
            )
            current["score"] += 1.0 / (rrf_k + rank)
            current["vector_score"] = item.get("score")

        for rank, item in enumerate(keyword_results, 1):
            key = f"{item.get('document_id')}:{item.get('chunk_index')}"
            current = fused.setdefault(
                key,
                {
                    "content": item.get("content", ""),
                    "score": 0.0,
                    "vector_score": None,
                    "keyword_score": None,
                    "source": item.get("source"),
                    "document_id": item.get("document_id"),
                    "chunk_index": item.get("chunk_index"),
                    "provider_mode": item.get("provider_mode", provider_mode),
                    "metadata": item.get("metadata", {}),
                },
            )
            current["score"] += 1.0 / (rrf_k + rank)
            current["keyword_score"] = item.get("score")

        ranked = sorted(fused.values(), key=lambda x: x["score"], reverse=True)[:top_k]
        if ranked:
            max_score = ranked[0]["score"]
            for idx, item in enumerate(ranked, 1):
                item["score"] = round(item["score"] / max(max_score, 1e-10), 6)
                item["citation"] = KnowledgeService._build_citation(item)
                item["ranking_meta"] = {
                    "vector_score": item.get("vector_score"),
                    "keyword_score": item.get("keyword_score"),
                    "rerank_score": None,
                    "final_rank": idx,
                }
                item["ranking_stage"] = "fusion"
        return ranked

    @staticmethod
    def _apply_rerank(query: str, results: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if not results:
            return []
        from src.services.rerank import RerankService

        reranker = RerankService(top_k=top_k)
        reranked = reranker.rerank(query, [item.get("content", "") for item in results], top_k=top_k)
        ordered: list[dict[str, Any]] = []
        for rank, item in enumerate(reranked, 1):
            base = dict(results[item["index"]])
            base["rerank_score"] = item["score"]
            base["score"] = item["score"]
            base["ranking_stage"] = "rerank"
            base["citation"] = KnowledgeService._build_citation(base)
            base["ranking_meta"] = {
                "vector_score": base.get("vector_score"),
                "keyword_score": base.get("keyword_score"),
                "rerank_score": item["score"],
                "final_rank": rank,
            }
            ordered.append(base)
        return ordered

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
        market_summary = decision_output.get("market_summary") if isinstance(decision_output.get("market_summary"), dict) else {}
        customer_feedback = decision_output.get("customer_feedback") if isinstance(decision_output.get("customer_feedback"), dict) else {}
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
            "purchase_order_id": adoption.get("purchase_order_id") or ((adoption.get("execution_status") or {}).get("scm") or {}).get("purchase_order_id"),
            "listing_draft_id": ((adoption.get("listing_draft") or {}).get("listing_draft_id")) or ((adoption.get("execution_status") or {}).get("oms") or {}).get("listing_draft_id"),
            "rescore_decision": rescore_summary.get("decision"),
            "rescore_score": rescore_summary.get("score"),
            "review_rating": ((execution_feedback.get("reviews") or {}).get("rating")) or execution_feedback_snapshot.get("reviews", {}).get("avg_rating"),
            "review_count": ((execution_feedback.get("reviews") or {}).get("count")) or execution_feedback_snapshot.get("reviews", {}).get("review_count"),
            "sales_7d": ((execution_feedback.get("sales") or {}).get("sales_7d")) or execution_feedback_snapshot.get("sales", {}).get("orders", {}).get("units"),
            "gross_profit": ((execution_feedback.get("profit") or {}).get("gross_profit")) or execution_feedback_snapshot.get("profit", {}).get("gross_profit_total"),
            "inventory_available": ((execution_feedback.get("inventory") or {}).get("available_inventory")) or execution_feedback_snapshot.get("inventory", {}).get("summary", {}).get("available_quantity_total"),
        }

        lines = [
            f"# 历史选品案例 {task_id}",
            "",
            "## 案例元数据",
            f"- case_type: {cls.SELECTION_CASE_TYPE}",
            f"- task_id: {task_id}",
            f"- query: {task.get('query') or '-'}",
            f"- category: {task.get('category') or '-'}",
            f"- target_market: {task.get('target_market') or '-'}",
            f"- status: {task.get('status') or '-'}",
            f"- completed_at: {task.get('completed_at') or '-'}",
            "",
            "## 决策摘要",
            f"- decision: {decision_meta.get('decision') or '-'}",
            f"- recommended_price: {pricing.get('recommended_price') or '-'}",
            f"- expected_margin: {profitability.get('expected_margin') or profitability.get('margin_rate') or '-'}",
            f"- primary_supplier: {supply_chain.get('primary_supplier') or '-'}",
            f"- trend_direction: {market_summary.get('trend_direction') or '-'}",
            f"- product_name: {product.get('name') or product.get('product_name') or '-'}",
            f"- asin: {product.get('asin') or product.get('external_product_id') or '-'}",
            "",
            "## 采纳执行",
            f"- adoption_status: {adoption.get('status') or '-'}",
            f"- quantity: {adoption.get('quantity') or '-'}",
            f"- purchase_order_id: {case_summary.get('purchase_order_id') or '-'}",
            f"- reservation_id: {((adoption.get('warehouse_reservation') or {}).get('reservation_id')) or ((adoption.get('execution_status') or {}).get('wms') or {}).get('reservation_id') or '-'}",
            f"- listing_draft_id: {case_summary.get('listing_draft_id') or '-'}",
            "",
            "## 执行反馈",
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
        lines.extend(["", "## 客户反馈摘要", f"- {customer_feedback}", "", "## 结构化摘要JSON", str(case_summary)])
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
            if str((item.get("metadata") or {}).get("filename") or item.get("source") or "").startswith(self.SELECTION_CASE_PREFIX)
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
            "## 案例元数据",
            f"- case_type: {cls.REVIEW_CASE_TYPE}",
            f"- review_id: {review_id}",
            f"- task_id: {review.get('task_id') or '-'}",
            f"- product_id: {review.get('product_id') or '-'}",
            f"- product_name: {review.get('product_name') or review.get('name') or '-'}",
            f"- asin: {review.get('asin') or '-'}",
            f"- rating: {rating_value if rating_value is not None else '-'}",
            f"- review_count: {review_count}",
            f"- sentiment: {sentiment}",
            f"- ticket_id: {review.get('ticket_id') or '-'}",
            f"- customer_id: {review.get('customer_id') or '-'}",
            "",
            "## 评价内容",
            feedback_text or "-",
            "",
            "## 结构化摘要JSON",
            str(case_summary),
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
            if str((item.get("metadata") or {}).get("filename") or item.get("source") or "").startswith(self.REVIEW_CASE_PREFIX)
            or (item.get("content") or "").startswith("# CRM评价案例")
            or (item.get("content") or "").find(f"case_type: {self.REVIEW_CASE_TYPE}") >= 0
        ][:top_k]
        result["results"] = filtered
        result["total_found"] = len(filtered)
        result["case_type"] = self.REVIEW_CASE_TYPE
        return result

    async def query_knowledge(self, query: str, top_k: int, threshold: float) -> dict[str, Any]:
        start = perf_counter()
        cached, cache_backend = await self._read_query_cache(query=query, top_k=top_k, threshold=threshold)
        if cached is not None:
            cached["processing_time_ms"] = round((perf_counter() - start) * 1000, 2)
            return cached

        kb = await self.repo.get_or_create_default_knowledge_base()
        provider_mode = self.embedding_provider.provider_mode

        qdrant_results = await self._search_qdrant(
            collection_name=kb.collection_name or "product_knowledge",
            query=query,
            top_k=max(top_k * 2, 10),
            threshold=threshold,
            provider_mode=provider_mode,
            tenant_id=self.tenant_id,
        )
        db_results = await self._search_db_keyword(
            query=query,
            top_k=max(top_k * 2, 10),
            threshold=threshold,
            provider_mode=provider_mode,
        )

        if not qdrant_results and not db_results:
            raise ValueError("知识库为空，请先上传文档")

        fused_results = self._fuse_hybrid_results(
            qdrant_results,
            db_results,
            top_k=top_k,
            provider_mode=provider_mode,
        )

        reranked_results = self._apply_rerank(query, fused_results, top_k=top_k)

        logger.info(
            f"知识库混合检索完成 | provider_mode={provider_mode} | top_k={top_k} | vector_hit={len(qdrant_results)} | keyword_hit={len(db_results)} | fused={len(fused_results)} | reranked={len(reranked_results)}"
        )

        result = {
            "query": query,
            "results": reranked_results,
            "total_found": len(reranked_results),
            "processing_time_ms": round((perf_counter() - start) * 1000, 2),
        }
        return await self._cache_query_result(query=query, top_k=top_k, threshold=threshold, result=result)

    async def get_stats(self) -> dict[str, Any]:
        return await self.repo.get_stats()
