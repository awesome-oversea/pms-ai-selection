"""
知识库 Repository
=================

封装 KnowledgeBase / Document / Chunk 的最小持久化操作，
为知识库上传、检索与状态管理提供数据库访问能力。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.repositories.base import TenantScopedRepository

logger = get_logger(__name__)


class KnowledgeRepository(TenantScopedRepository):
    """知识库数据访问层。"""

    def __init__(self, session: AsyncSession, tenant_id: str | None = None):
        super().__init__(session, tenant_id=tenant_id, require_tenant=True)

    async def get_or_create_default_knowledge_base(self) -> Any:
        from src.models.models import KnowledgeBase

        tenant_uuid = uuid.UUID(self.tenant_id)
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.tenant_id == tenant_uuid,
            KnowledgeBase.name == "default",
            KnowledgeBase.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt.order_by(KnowledgeBase.created_at.desc()))
        kb = result.scalars().first()
        if kb is not None:
            return kb

        kb = KnowledgeBase(
            name="default",
            description="默认知识库",
            kb_type="product",
            collection_name=f"product_knowledge_{self.tenant_id.replace('-', '_')}",
            embedding_model="bge-large-zh",
            chunk_size=200,
            chunk_overlap=20,
            config={"provider_mode": "local-mock"},
            is_active=True,
            tenant_id=tenant_uuid,
        )
        self.session.add(kb)
        await self.session.flush()
        logger.info(f"✅ 创建默认知识库: {kb.id}")
        return kb

    async def get_current_document_by_title(
        self,
        knowledge_base_id: uuid.UUID,
        title: str,
    ) -> Any | None:
        from src.models.models import Document

        result = await self.session.execute(
            select(Document)
            .where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.knowledge_base_id == knowledge_base_id,
                Document.title == title,
                Document.is_deleted == False,  # noqa: E712
            )
            .order_by(Document.created_at.desc())
        )
        documents = list(result.scalars().all())
        for doc in documents:
            extra = doc.extra_data or {}
            if extra.get("is_current_version", True):
                return doc
        return documents[0] if documents else None

    async def list_document_versions(self, knowledge_base_id: uuid.UUID, title: str) -> list[Any]:
        from src.models.models import Document

        result = await self.session.execute(
            select(Document)
            .where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.knowledge_base_id == knowledge_base_id,
                Document.title == title,
                Document.is_deleted == False,  # noqa: E712
            )
            .order_by(Document.created_at.asc())
        )
        return list(result.scalars().all())

    async def mark_document_not_current(self, document_id: uuid.UUID) -> bool:
        document = await self.get_document(document_id)
        if document is None:
            return False
        extra = dict(document.extra_data or {})
        extra["is_current_version"] = False
        document.extra_data = extra
        await self.session.flush()
        return True

    async def switch_current_version(self, document_id: uuid.UUID) -> Any | None:
        document = await self.get_document(document_id)
        if document is None:
            return None
        versions = await self.list_document_versions(document.knowledge_base_id, document.title)
        for version_doc in versions:
            extra = dict(version_doc.extra_data or {})
            extra["is_current_version"] = False
            version_doc.extra_data = extra
        target_extra = dict(document.extra_data or {})
        target_extra["is_current_version"] = True
        document.extra_data = target_extra
        await self.session.flush()
        return document

    async def create_document(
        self,
        knowledge_base_id: uuid.UUID,
        title: str,
        doc_type: str,
        file_size: int,
        content_hash: str,
        status: str = "pending",
        extra_data: dict[str, Any] | None = None,
    ) -> Any:
        from src.models.models import Document

        document = Document(
            tenant_id=uuid.UUID(self.tenant_id),
            knowledge_base_id=knowledge_base_id,
            title=title,
            doc_type=doc_type,
            file_size=file_size,
            content_hash=content_hash,
            status=status,
            chunk_count=0,
            extra_data=extra_data or {},
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def get_document(self, document_id: uuid.UUID) -> Any | None:
        from src.models.models import Document

        result = await self.session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_document_by_hash(
        self,
        knowledge_base_id: uuid.UUID,
        content_hash: str,
        title: str | None = None,
    ) -> Any | None:
        from src.models.models import Document

        query = (
            select(Document)
            .where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.knowledge_base_id == knowledge_base_id,
                Document.content_hash == content_hash,
                Document.is_deleted == False,  # noqa: E712
            )
            .order_by(Document.created_at.desc())
        )
        if title is not None:
            query = query.where(Document.title == title)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_documents(
        self,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Any], int]:
        from src.models.models import Document

        query = select(Document).where(
            Document.tenant_id == self.tenant_uuid(),
            Document.is_deleted == False,  # noqa: E712
        )
        count_query = select(func.count()).select_from(Document).where(
            Document.tenant_id == self.tenant_uuid(),
            Document.is_deleted == False,  # noqa: E712
        )

        if status:
            query = query.where(Document.status == status)
            count_query = count_query.where(Document.status == status)

        query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        docs = list(result.scalars().all())

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0
        return docs, total

    async def create_chunk(
        self,
        document_id: uuid.UUID,
        content: str,
        chunk_index: int,
        vector_id: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> Any:
        from src.models.models import Chunk

        chunk = Chunk(
            tenant_id=uuid.UUID(self.tenant_id),
            document_id=document_id,
            content=content,
            chunk_index=chunk_index,
            vector_id=vector_id,
            extra_data=extra_data or {},
        )
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def list_chunks_by_document(self, document_id: uuid.UUID) -> list[Any]:
        from src.models.models import Chunk

        result = await self.session.execute(
            select(Chunk)
            .where(
                Chunk.document_id == document_id,
                Chunk.tenant_id == uuid.UUID(self.tenant_id),
            )
            .order_by(Chunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def list_indexed_chunks(self) -> list[Any]:
        from src.models.models import Chunk, Document

        result = await self.session.execute(
            select(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Chunk.tenant_id == uuid.UUID(self.tenant_id),
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
                Document.status == "indexed",
            )
            .order_by(Document.created_at.desc(), Chunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def update_document_status(
        self,
        document_id: uuid.UUID,
        status: str,
        chunk_count: int | None = None,
        reason: str | None = None,
        provider_mode: str | None = None,
        vector_status: str | None = None,
    ) -> bool:
        document = await self.get_document(document_id)
        if document is None:
            return False

        document.status = status
        if chunk_count is not None:
            document.chunk_count = chunk_count

        extra = document.extra_data or {}
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
        document.extra_data = extra

        await self.session.flush()
        return True

    async def soft_delete_document(self, document_id: uuid.UUID) -> bool:
        document = await self.get_document(document_id)
        if document is None:
            return False
        document.is_deleted = True
        await self.session.flush()
        return True

    async def get_stats(self) -> dict[str, Any]:
        from src.models.models import Chunk, Document

        docs_result = await self.session.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
            )
        )
        chunks_result = await self.session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.tenant_id == uuid.UUID(self.tenant_id))
        )
        size_result = await self.session.execute(
            select(func.coalesce(func.sum(Document.file_size), 0)).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
            )
        )
        indexed_result = await self.session.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
                Document.status == "indexed",
            )
        )

        total_docs = docs_result.scalar() or 0
        total_chunks = chunks_result.scalar() or 0
        total_size = size_result.scalar() or 0
        indexed_docs = indexed_result.scalar() or 0

        return {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "indexed_documents": indexed_docs,
            "average_chunks_per_doc": round(total_chunks / max(total_docs, 1), 1),
        }

    async def soft_delete_document(self, document_id: uuid.UUID) -> bool:
        document = await self.get_document(document_id)
        if document is None:
            return False
        document.is_deleted = True
        await self.session.flush()
        return True

    async def get_stats(self) -> dict[str, Any]:
        from src.models.models import Chunk, Document

        docs_result = await self.session.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
            )
        )
        chunks_result = await self.session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.tenant_id == uuid.UUID(self.tenant_id))
        )
        size_result = await self.session.execute(
            select(func.coalesce(func.sum(Document.file_size), 0)).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
            )
        )
        indexed_result = await self.session.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
                Document.status == "indexed",
            )
        )

        total_docs = docs_result.scalar() or 0
        total_chunks = chunks_result.scalar() or 0
        total_size = size_result.scalar() or 0
        indexed_docs = indexed_result.scalar() or 0

        return {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "indexed_documents": indexed_docs,
            "average_chunks_per_doc": round(total_chunks / max(total_docs, 1), 1),
        }

    async def soft_delete_document(self, document_id: uuid.UUID) -> bool:
        document = await self.get_document(document_id)
        if document is None:
            return False
        document.is_deleted = True
        await self.session.flush()
        return True

    async def get_stats(self) -> dict[str, Any]:
        from src.models.models import Chunk, Document

        docs_result = await self.session.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
            )
        )
        chunks_result = await self.session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.tenant_id == uuid.UUID(self.tenant_id))
        )
        size_result = await self.session.execute(
            select(func.coalesce(func.sum(Document.file_size), 0)).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
            )
        )
        indexed_result = await self.session.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == uuid.UUID(self.tenant_id),
                Document.is_deleted == False,  # noqa: E712
                Document.status == "indexed",
            )
        )

        total_docs = docs_result.scalar() or 0
        total_chunks = chunks_result.scalar() or 0
        total_size = size_result.scalar() or 0
        indexed_docs = indexed_result.scalar() or 0

        return {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "indexed_documents": indexed_docs,
            "average_chunks_per_doc": round(total_chunks / max(total_docs, 1), 1),
        }
