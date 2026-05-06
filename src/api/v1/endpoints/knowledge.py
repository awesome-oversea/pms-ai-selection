"""
知识库管理 API 端点
===================

通过 KnowledgeService 管理文档上传、状态流转、持久化检索与统计，
避免 endpoint 直接依赖进程内文档缓存。
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.business_defaults import get_rag_evaluation_config
from src.config.settings import get_settings
from src.core.metrics import KNOWLEDGE_QUERY_HIT_RATE, KNOWLEDGE_QUERY_TOTAL
from src.core.security import add_audit_log, get_actor, require_superuser
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.search_backend import get_search_backend
from src.services.knowledge_service import KnowledgeService
from src.services.llamaindex_rag_service import LlamaIndexRAGService
from src.services.local_knowledge_service import LocalKnowledgeService
from src.services.rag_evaluation import RAGEvalCase, RAGEvaluationService
from src.services.service_gateway import get_service_gateway

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["知识库(RAG)"])


class DocumentUploadResponse(BaseModel):
    """文档上传响应。"""

    doc_id: str
    filename: str
    status: str
    message: str


class KnowledgeQueryRequest(BaseModel):
    """知识库查询请求。"""

    query: str = Field(..., min_length=2, description="查询问题")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数量")
    threshold: float = Field(0.5, ge=0.0, le=1.0, description="相似度阈值")


class SelectionCaseIngestRequest(BaseModel):
    task: dict = Field(..., description="已完成选品任务详情，用于沉淀为历史案例")


class SelectionCaseQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, description="历史案例查询问题")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数量")
    threshold: float = Field(0.1, ge=0.0, le=1.0, description="相似度阈值")


class ReviewCaseIngestRequest(BaseModel):
    review: dict = Field(..., description="CRM评价/投诉记录，用于沉淀为好评差评案例")


class ReviewCaseQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, description="评价案例查询问题")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数量")
    threshold: float = Field(0.1, ge=0.0, le=1.0, description="相似度阈值")


class KnowledgeQueryResponse(BaseModel):
    """知识库查询响应。"""

    query: str
    results: list[dict]
    total_found: int
    processing_time_ms: float
    case_type: str | None = None
    cache_hit: bool | None = None
    cache_backend: str | None = None
    cache_similarity: float | None = None
    cached_query: str | None = None


class DocumentListResponse(BaseModel):
    """文档列表响应。"""

    total: int
    documents: list[dict]


class RAGEvalCaseRequest(BaseModel):
    query: str = Field(..., min_length=1)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    top_k: int = Field(5, ge=1, le=20)
    threshold: float = Field(0.1, ge=0.0, le=1.0)


class RAGEvalRequest(BaseModel):
    cases: list[RAGEvalCaseRequest] = Field(default_factory=list)
    use_default_baseline: bool = Field(default=True, description="当 cases 为空时是否自动使用默认评测基线")


class RAGFeedbackLearningRequest(BaseModel):
    query: str = Field(..., min_length=1)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    top_k: int = Field(5, ge=1, le=20)
    threshold: float = Field(0.1, ge=0.0, le=1.0)


class LlamaIndexCompareRequest(BaseModel):
    query: str = Field(..., min_length=1)
    documents: list[dict] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)


async def _get_db_session() -> AsyncSession | None:
    try:
        factory = get_async_session_factory()
        return factory()
    except Exception:
        return None


def _create_service(
    session: AsyncSession | None,
    tenant_id: str | None = None,
    actor: dict | None = None,
) -> KnowledgeService | LocalKnowledgeService:
    if session is None:
        return LocalKnowledgeService()
    return KnowledgeService(session, tenant_id=tenant_id, actor=actor)


@router.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_superuser),
):
    """上传文档到知识库。"""
    allowed_extensions = {".txt", ".md", ".csv"}
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}，支持: {allowed_extensions}",
        )

    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        content = await file.read()
        result = await service.upload_document(file.filename or "unknown.txt", content)
        add_audit_log(
            action="knowledge.document.upload",
            actor=current_user,
            target_type="document",
            target_id=result["doc_id"],
            result="success",
            detail={"filename": result["filename"], "status": result["status"]},
        )
        return DocumentUploadResponse(**{k: result[k] for k in ("doc_id", "filename", "status", "message")})
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"文档编码错误，当前仅支持 UTF-8: {e}")
    except Exception as e:
        logger.exception("文档上传失败")
        raise HTTPException(status_code=503, detail=f"文档处理失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    status: str | None = Query(None, description="按状态筛选"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor: dict = Depends(get_actor),
):
    """获取知识库文档列表。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        result = await service.list_documents(status=status, limit=limit, offset=offset)
        return DocumentListResponse(**result)
    except Exception as e:
        logger.exception("查询文档列表失败")
        raise HTTPException(status_code=503, detail=f"查询文档列表失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.get("/documents/{doc_id}/versions", response_model=dict)
async def list_document_versions(doc_id: str, actor: dict = Depends(get_actor)):
    """获取文档版本列表。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        result = await service.list_document_versions(doc_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("查询文档版本失败")
        raise HTTPException(status_code=503, detail=f"查询文档版本失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.post("/documents/{doc_id}/rollback", response_model=dict)
async def rollback_document_version(doc_id: str, current_user: dict = Depends(require_superuser)):
    """回滚到指定文档版本为当前版本。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.rollback_document_version(doc_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")
        add_audit_log(
            action="knowledge.document.rollback",
            actor=current_user,
            target_type="document",
            target_id=doc_id,
            result="success",
            detail={"version": result.get("version")},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("回滚文档版本失败")
        raise HTTPException(status_code=503, detail=f"回滚文档版本失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.get("/documents/compare", response_model=dict)
async def compare_document_versions(
    baseline_doc_id: str = Query(..., min_length=1),
    target_doc_id: str = Query(..., min_length=1),
    actor: dict = Depends(get_actor),
):
    """对比同名文档两个版本的差异。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        result = await service.compare_document_versions(baseline_doc_id, target_doc_id)
        if result is None:
            raise HTTPException(status_code=404, detail="文档版本不存在")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("对比文档版本失败")
        raise HTTPException(status_code=503, detail=f"对比文档版本失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.get("/documents/{doc_id}", response_model=dict)
async def get_document_detail(doc_id: str, actor: dict = Depends(get_actor)):
    """获取文档详情。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        detail = await service.get_document_detail(doc_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("查询文档详情失败")
        raise HTTPException(status_code=503, detail=f"查询文档详情失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.delete("/documents/{doc_id}", response_model=dict)
async def delete_document(doc_id: str, current_user: dict = Depends(require_superuser)):
    """删除知识库中的文档。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.delete_document(doc_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")
        add_audit_log(
            action="knowledge.document.delete",
            actor=current_user,
            target_type="document",
            target_id=doc_id,
            result="success",
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("删除文档失败")
        raise HTTPException(status_code=503, detail=f"删除文档失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.post("/selection-cases/ingest", response_model=dict)
async def ingest_selection_case(request: SelectionCaseIngestRequest, current_user: dict = Depends(require_superuser)):
    """将已完成选品任务沉淀为历史案例并写入知识库。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.ingest_selection_case(request.task)
        add_audit_log(
            action="knowledge.selection_case.ingest",
            actor=current_user,
            target_type="selection_case",
            target_id=result.get("task_id"),
            result="success",
            detail={"doc_id": result.get("doc_id"), "query": result.get("query")},
        )
        return result
    except Exception as e:
        logger.exception("历史选品案例入库失败")
        raise HTTPException(status_code=503, detail=f"历史选品案例入库失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.post("/selection-cases/query", response_model=KnowledgeQueryResponse)
async def query_selection_cases(request: SelectionCaseQueryRequest, actor: dict = Depends(get_actor)):
    """检索历史选品案例。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        result = await service.query_selection_cases(
            query=request.query,
            top_k=request.top_k,
            threshold=request.threshold,
        )
        return KnowledgeQueryResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("历史选品案例检索失败")
        raise HTTPException(status_code=503, detail=f"历史选品案例检索失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.post("/review-cases/ingest", response_model=dict)
async def ingest_review_case(request: ReviewCaseIngestRequest, current_user: dict = Depends(require_superuser)):
    """将 CRM 好评/差评沉淀为评价案例并写入知识库。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.ingest_review_case(request.review)
        add_audit_log(
            action="knowledge.review_case.ingest",
            actor=current_user,
            target_type="review_case",
            target_id=result.get("review_id"),
            result="success",
            detail={"doc_id": result.get("doc_id"), "product_id": result.get("product_id")},
        )
        return result
    except Exception as e:
        logger.exception("CRM评价案例入库失败")
        raise HTTPException(status_code=503, detail=f"CRM评价案例入库失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.post("/review-cases/query", response_model=KnowledgeQueryResponse)
async def query_review_cases(request: ReviewCaseQueryRequest, actor: dict = Depends(get_actor)):
    """检索 CRM 好评/差评案例。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        result = await service.query_review_cases(
            query=request.query,
            top_k=request.top_k,
            threshold=request.threshold,
        )
        return KnowledgeQueryResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("CRM评价案例检索失败")
        raise HTTPException(status_code=503, detail=f"CRM评价案例检索失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.post("/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(request: KnowledgeQueryRequest, actor: dict = Depends(get_actor)):
    """查询知识库。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        gateway = get_service_gateway()
        auth_header = None
        authorization = actor.get("authorization")
        if authorization:
            auth_header = authorization
        result = await gateway.route_rag_query(
            query=request.query,
            top_k=request.top_k,
            threshold=request.threshold,
            token=auth_header,
            fallback=lambda: service.query_knowledge(
                query=request.query,
                top_k=request.top_k,
                threshold=request.threshold,
            ),
        )
        hit = 1.0 if result.get("total_found", 0) > 0 else 0.0
        KNOWLEDGE_QUERY_TOTAL.labels(mode="hybrid", status="success").inc()
        KNOWLEDGE_QUERY_HIT_RATE.set(hit)
        return KnowledgeQueryResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("知识库查询失败")
        raise HTTPException(status_code=503, detail=f"查询失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.post("/evaluate", response_model=dict)
async def evaluate_knowledge(request: RAGEvalRequest, current_user: dict = Depends(require_superuser)):
    """执行最小 RAG 评测集。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        if hasattr(service, "evaluate"):
            result = await service.evaluate(request.model_dump())
        else:
            evaluator = RAGEvaluationService(service)
            cases = [
                RAGEvalCase(
                    query=case.query,
                    expected_document_ids=case.expected_document_ids,
                    expected_keywords=case.expected_keywords,
                    top_k=case.top_k,
                    threshold=case.threshold,
                )
                for case in request.cases
            ]
            if not cases and request.use_default_baseline:
                cases = evaluator.build_default_cases()
            result = await evaluator.run_cases(cases)
        add_audit_log(
            action="knowledge.evaluate",
            actor=current_user,
            target_type="knowledge_evaluation",
            result="success",
            detail={"total_cases": result.get("total_cases", 0)},
        )
        return result
    except Exception as e:
        logger.exception("知识库评测失败")
        raise HTTPException(status_code=503, detail=f"知识库评测失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.post("/feedback-learning", response_model=dict)
async def ingest_rag_feedback_learning(request: RAGFeedbackLearningRequest, current_user: dict = Depends(require_superuser)):
    """将人工反馈/评测命中结果沉淀为下一轮 RAG 基线。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        evaluator = RAGEvaluationService(service)
        result = await evaluator.ingest_feedback_learning(request.model_dump())
        add_audit_log(
            action="knowledge.feedback_learning.ingest",
            actor=current_user,
            target_type="knowledge_feedback_learning",
            result="success",
            detail={"query": request.query, "total_cases": result.get("total_cases", 0)},
        )
        return result
    except Exception as e:
        logger.exception("RAG 反馈学习沉淀失败")
        raise HTTPException(status_code=503, detail=f"RAG 反馈学习沉淀失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.get("/quality-dashboard", response_model=dict)
async def get_quality_dashboard(current_user: dict = Depends(get_actor)):
    """获取知识库质量运营看板数据。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        if hasattr(service, "get_quality_dashboard"):
            return await asyncio.wait_for(service.get_quality_dashboard(), timeout=5)
        evaluator = RAGEvaluationService(service)
        try:
            return await asyncio.wait_for(evaluator.build_dashboard(), timeout=5)
        except TimeoutError:
            logger.warning("知识库质量看板构建超时，回退到 artifact 快照")
            feedback_payload = evaluator._load_feedback_learning_payload()
            feedback_cases = list(feedback_payload.get("cases", []))
            baseline_result = evaluator._load_latest_evaluation_artifact()
            config = get_rag_evaluation_config()
            static_cases = list(config.get("baseline_cases", []) if isinstance(config, dict) else [])
            baseline_cases = evaluator.build_default_cases()
            return {
                "knowledge_health": {
                    "total_documents": 0,
                    "indexed_documents": 0,
                    "total_chunks": 0,
                    "index_coverage": 0.0,
                },
                "retrieval_quality": {
                    "status": "degraded-artifact",
                    "metrics": ["hit_at_k", "mrr", "citation_match_rate", "avg_score"],
                    "default_evaluation": baseline_result,
                    "artifact_path": (baseline_result or {}).get("artifact_path"),
                },
                "feedback_learning": {
                    "status": "available",
                    "feedback_case_count": len(feedback_cases),
                    "static_baseline_case_count": len(static_cases),
                    "combined_baseline_case_count": len(baseline_cases),
                    "latest_updated_at": feedback_payload.get("updated_at"),
                    "artifact_path": feedback_payload.get("artifact_path"),
                    "coverage_ratio": round(len(feedback_cases) / max(len(baseline_cases), 1), 4) if baseline_cases else 0.0,
                },
            }
    except Exception as e:
        logger.exception("知识库质量看板失败")
        raise HTTPException(status_code=503, detail=f"知识库质量看板失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.get("/search-backend/status", response_model=dict)
async def get_search_backend_status(current_user: dict = Depends(get_actor)):
    """获取正式关键词检索后端状态。"""
    backend = get_search_backend()
    return backend.build_status()


@router.post("/search-backend/reindex", response_model=dict)
async def reindex_search_backend(current_user: dict = Depends(require_superuser)):
    """重建当前租户的关键词检索索引。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.reindex_search_backend()
        add_audit_log(
            action="knowledge.search_backend.reindex",
            actor=current_user,
            target_type="search_index",
            result="success",
            detail=result,
        )
        return result
    except Exception as e:
        logger.exception("重建关键词检索索引失败")
        raise HTTPException(status_code=503, detail=f"重建关键词检索索引失败: {e}")
    finally:
        if session is not None:
            await session.close()


@router.get("/service-mode", response_model=dict)
async def get_knowledge_service_mode(current_user: dict = Depends(get_actor)):
    settings = get_settings().service_mode
    gateway = get_service_gateway()
    return {
        "mode": settings.rag_mode,
        "base_url": settings.rag_base_url,
        "timeout_seconds": settings.rag_timeout_seconds,
        "fallback_enabled": settings.enable_fallback,
        "gateway": gateway.build_status()["rag"],
    }


@router.get("/llamaindex/status", response_model=dict)
async def get_llamaindex_rag_status(current_user: dict = Depends(require_superuser)):
    return LlamaIndexRAGService().build_status()


@router.post("/llamaindex/compare", response_model=dict)
async def compare_llamaindex_rag(request: LlamaIndexCompareRequest, current_user: dict = Depends(require_superuser)):
    service = LlamaIndexRAGService()
    result = await service.compare_with_hybrid(query=request.query, documents=request.documents, top_k=request.top_k)
    add_audit_log(
        action="knowledge.llamaindex.compare",
        actor=current_user,
        target_type="rag_pipeline",
        result="success",
        detail={"mode": result.get("mode"), "top_k": request.top_k},
    )
    return result


@router.get("/stats", response_model=dict)
async def get_knowledge_stats(current_user: dict = Depends(get_actor)):
    """获取知识库统计信息。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        return await service.get_stats()
    except Exception as e:
        logger.exception("知识库统计失败")
        raise HTTPException(status_code=503, detail=f"知识库统计失败: {e}")
    finally:
        if session is not None:
            await session.close()
