from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SEC_SECRET_KEY", "local-knowledge-graph-agent-32chars")
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from scripts.run_local_selection_main_chain_acceptance import (
    CheckResult,
    _build_headers,
    _build_run_dir,
    _status_from_checks,
    _write_json,
)
from src.core.auth import create_access_token
from src.agents.product_planner import ProductPlannerAgent
from src.core.security import clear_audit_logs, list_audit_logs
from src.main import create_app
from src.services.graph_rag_service import GraphRAGService


ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "local_knowledge_chain"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local knowledge -> graph -> agent acceptance.")
    parser.add_argument("--output-root", default=str(ARTIFACT_ROOT), help="Artifact root directory")
    return parser.parse_args()


def _safe_json(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return {"text": response.text}


def _json_data(response: Any) -> dict[str, Any]:
    payload = _safe_json(response)
    return payload["data"] if isinstance(payload, dict) and "data" in payload else payload


def _build_superuser_headers(username: str, user_id: str) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": username,
            "user_id": user_id,
            "is_superuser": True,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": ["tenant_admin", "platform_admin"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


class _LocalGateway:
    async def route_rag_query(
        self,
        *,
        query: str,
        top_k: int,
        threshold: float,
        token: str | None = None,
        fallback: Any = None,
    ) -> dict[str, Any]:
        if fallback is None:
            return {
                "query": query,
                "results": [],
                "total_found": 0,
                "processing_time_ms": 0.0,
            }
        return await fallback()

    def build_status(self) -> dict[str, Any]:
        return {
            "rag": {
                "mode": "local-fallback",
                "ready": True,
                "fallback_enabled": True,
            }
        }


def main() -> int:
    args = parse_args()
    run_dir = _build_run_dir(Path(args.output_root))
    workspace_root = run_dir / "workspace"
    knowledge_db_path = workspace_root / "data" / "local_knowledge.db"
    graph_store_path = workspace_root / "artifacts" / "graph_rag" / "local_graph_store.json"
    knowledge_db_path.parent.mkdir(parents=True, exist_ok=True)
    graph_store_path.parent.mkdir(parents=True, exist_ok=True)

    clear_audit_logs()
    operation_records: list[dict[str, Any]] = []

    async def _noop_init_db() -> None:
        return None

    async def _healthy_db() -> dict[str, str]:
        return {"status": "healthy"}

    async def _healthy_redis() -> dict[str, str]:
        return {"status": "healthy"}

    async def _healthy_qdrant() -> dict[str, str]:
        return {"status": "healthy"}

    async def _noop_persist_audit_log(_entry: dict[str, Any]) -> None:
        return None

    async def _no_db_session() -> None:
        return None

    def _raise_no_redis() -> Any:
        raise RuntimeError("redis disabled for local acceptance")

    async def _fake_compare_1688_specs(
        self,
        product_keyword: str,
        product_spec: dict[str, Any] | None = None,
        max_suppliers: int = 5,
    ) -> dict[str, Any]:
        return {
            "source": "ali1688_spec_comparison",
            "product_keyword": product_keyword,
            "supplier_count": 1,
            "target_feature_count": len((product_spec or {}).get("core_features") or []),
            "suppliers": [
                {
                    "supplier_id": "SUP-LOCAL-001",
                    "supplier_name": "Shenzhen SoundMax Factory",
                    "location": "Shenzhen, Guangdong",
                    "spec_snapshot": {"lead_time_days": 9, "min_qty": 120, "unit_price_usd": 18.6},
                    "matched_features": ["anc主动降噪"],
                    "missing_features": [],
                    "match_score": 1.0,
                }
            ],
            "difference_items": [],
            "recommended_alignment": ["优先对齐 ANC 主动降噪 和 40 小时续航"],
        }

    async def _fake_fetch_crm_reviews(
        self,
        crm_api_endpoint: str,
        crm_api_key: str | None = None,
        crm_inbound_path: str = "/customer-feedback",
        product_id: str | None = None,
        product_name: str | None = None,
        asin: str | None = None,
    ) -> dict[str, Any]:
        return {
            "source": "crm_review_insights",
            "matched_review_count": 2,
            "avg_rating": 4.7,
            "complaint_count": 0,
            "reviews": [
                {"asin": asin or "B0LOCALKB001", "feedback": "降噪稳定，续航优秀", "customer_score": 4.8},
                {"asin": asin or "B0LOCALKB001", "feedback": "佩戴舒适，包装完整", "customer_score": 4.6},
            ],
            "summary": {
                "avg_rating": 4.7,
                "complaint_count": 0,
                "review_count": 16,
            },
        }

    admin_headers = _build_superuser_headers(username="tenant-admin-1", user_id="00000000-0000-0000-0000-000000000041")
    analyst_headers = _build_headers("analyst", user_id="00000000-0000-0000-0000-000000000051", username="analyst-1")

    knowledge_query_first: dict[str, Any]
    knowledge_query_second: dict[str, Any]
    graph_query: dict[str, Any]
    graph_build: dict[str, Any]
    graph_status: dict[str, Any]
    llamaindex_status: dict[str, Any]
    llamaindex_compare: dict[str, Any]
    agent_result: dict[str, Any]
    documents_payload: dict[str, Any]
    knowledge_stats: dict[str, Any]
    document_details: list[dict[str, Any]] = []
    uploaded_doc_ids: list[str] = []
    uploaded_documents: list[dict[str, Any]] = []

    knowledge_doc_text = (
        "# 蓝牙耳机行业知识\n"
        "SoundMax和AudioPeak是竞争对手。\n"
        "SoundMax Earbuds Pro 属于蓝牙耳机品类，具有 ANC 主动降噪、40小时续航和轻量化佩戴优势。\n"
        "该产品适合美国跨境电商市场，主打通勤与运动场景。\n"
    )
    review_doc_text = (
        "# 用户评测摘要\n"
        "蓝牙耳机用户最关注主动降噪、续航和佩戴舒适度。\n"
        "当评价中出现 40 小时续航、ANC、稳定连接 等关键词时，转化率和收藏率更高。\n"
    )

    with ExitStack() as stack:
        stack.enter_context(patch("src.infrastructure.database.init_db", _noop_init_db))
        stack.enter_context(patch("src.infrastructure.database.check_db_health", _healthy_db))
        stack.enter_context(patch("src.infrastructure.redis.check_redis_health", _healthy_redis))
        stack.enter_context(patch("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant))
        stack.enter_context(patch("src.core.security._persist_audit_log", _noop_persist_audit_log))
        stack.enter_context(patch("src.api.v1.endpoints.knowledge._get_db_session", _no_db_session))
        stack.enter_context(patch("src.api.v1.endpoints.knowledge.get_service_gateway", lambda: _LocalGateway()))
        stack.enter_context(patch("src.services.local_knowledge_service._DB_PATH", knowledge_db_path))
        stack.enter_context(patch("src.services.local_knowledge_service.get_redis_connection", _raise_no_redis))
        stack.enter_context(
            patch(
                "src.api.v1.endpoints.graph.GraphRAGService",
                lambda: GraphRAGService(store_path=graph_store_path),
            )
        )
        stack.enter_context(patch("src.agents.product_planner.ProductPlannerAgent._compare_1688_specs", _fake_compare_1688_specs))
        stack.enter_context(patch("src.agents.product_planner.ProductPlannerAgent._fetch_crm_reviews", _fake_fetch_crm_reviews))

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            for filename, content in [
                ("earbuds_strategy.md", knowledge_doc_text),
                ("review_patterns.txt", review_doc_text),
            ]:
                upload_response = client.post(
                    "/api/v1/knowledge/documents",
                    headers=admin_headers,
                    files={"file": (filename, content.encode("utf-8"), "text/plain")},
                )
                upload_payload = _json_data(upload_response)
                uploaded_doc_ids.append(upload_payload["doc_id"])
                uploaded_documents.append(
                    {
                        "id": upload_payload["doc_id"],
                        "content": content,
                        "metadata": {"source": filename, "document_id": upload_payload["doc_id"]},
                    }
                )
                operation_records.append(
                    {
                        "step": f"upload_{filename}",
                        "actor": "tenant-admin-1",
                        "response_status_code": upload_response.status_code,
                        "response_data": upload_payload,
                    }
                )

            documents_response = client.get("/api/v1/knowledge/documents", headers=admin_headers)
            documents_payload = _json_data(documents_response)
            operation_records.append(
                {
                    "step": "list_documents",
                    "actor": "tenant-admin-1",
                    "response_status_code": documents_response.status_code,
                    "response_data": documents_payload,
                }
            )

            for doc_id in uploaded_doc_ids:
                detail_response = client.get(f"/api/v1/knowledge/documents/{doc_id}", headers=admin_headers)
                detail_payload = _json_data(detail_response)
                document_details.append(detail_payload)
                operation_records.append(
                    {
                        "step": f"document_detail_{doc_id}",
                        "actor": "tenant-admin-1",
                        "response_status_code": detail_response.status_code,
                        "response_data": detail_payload,
                    }
                )

            stats_response = client.get("/api/v1/knowledge/stats", headers=admin_headers)
            knowledge_stats = _json_data(stats_response)
            operation_records.append(
                {
                    "step": "knowledge_stats",
                    "actor": "tenant-admin-1",
                    "response_status_code": stats_response.status_code,
                    "response_data": knowledge_stats,
                }
            )

            query_request = {
                "query": "蓝牙耳机 ANC 主动降噪 40小时续航",
                "top_k": 3,
                "threshold": 0.1,
            }
            knowledge_query_first_response = client.post(
                "/api/v1/knowledge/query",
                headers=analyst_headers,
                json=query_request,
            )
            knowledge_query_first = _json_data(knowledge_query_first_response)
            operation_records.append(
                {
                    "step": "knowledge_query_first",
                    "actor": "analyst-1",
                    "response_status_code": knowledge_query_first_response.status_code,
                    "response_data": knowledge_query_first,
                }
            )

            knowledge_query_second_response = client.post(
                "/api/v1/knowledge/query",
                headers=analyst_headers,
                json=query_request,
            )
            knowledge_query_second = _json_data(knowledge_query_second_response)
            operation_records.append(
                {
                    "step": "knowledge_query_second",
                    "actor": "analyst-1",
                    "response_status_code": knowledge_query_second_response.status_code,
                    "response_data": knowledge_query_second,
                }
            )

            llamaindex_status_response = client.get("/api/v1/knowledge/llamaindex/status", headers=admin_headers)
            llamaindex_status = _json_data(llamaindex_status_response)
            operation_records.append(
                {
                    "step": "llamaindex_status",
                    "actor": "tenant-admin-1",
                    "response_status_code": llamaindex_status_response.status_code,
                    "response_data": llamaindex_status,
                }
            )

            llamaindex_compare_response = client.post(
                "/api/v1/knowledge/llamaindex/compare",
                headers=admin_headers,
                json={
                    "query": query_request["query"],
                    "documents": uploaded_documents,
                    "top_k": 3,
                },
            )
            llamaindex_compare = _json_data(llamaindex_compare_response)
            operation_records.append(
                {
                    "step": "llamaindex_compare",
                    "actor": "tenant-admin-1",
                    "response_status_code": llamaindex_compare_response.status_code,
                    "response_data": llamaindex_compare,
                }
            )

            graph_build_response = client.post(
                "/api/v1/graph/build",
                headers=admin_headers,
                json={"text": knowledge_doc_text, "doc_id": uploaded_doc_ids[0]},
            )
            graph_build = _json_data(graph_build_response)
            operation_records.append(
                {
                    "step": "graph_build",
                    "actor": "tenant-admin-1",
                    "response_status_code": graph_build_response.status_code,
                    "response_data": graph_build,
                }
            )

            graph_query_response = client.post(
                "/api/v1/graph/query",
                headers=analyst_headers,
                json={"query": "SoundMax 的竞品有哪些", "max_hops": 2, "top_k": 5},
            )
            graph_query = _json_data(graph_query_response)
            operation_records.append(
                {
                    "step": "graph_query",
                    "actor": "analyst-1",
                    "response_status_code": graph_query_response.status_code,
                    "response_data": graph_query,
                }
            )

            graph_status_response = client.get("/api/v1/graph/status", headers=admin_headers)
            graph_status = _json_data(graph_status_response)
            operation_records.append(
                {
                    "step": "graph_status",
                    "actor": "tenant-admin-1",
                    "response_status_code": graph_status_response.status_code,
                    "response_data": graph_status,
                }
            )

    agent_result = asyncio.run(
        ProductPlannerAgent().execute(
            {
                "query": query_request["query"],
                "category": "electronics",
                "target_market": "US",
                "budget_range": [29, 89],
                "use_mock": True,
                "knowledge_query_results": knowledge_query_first.get("results", []),
                "graph_query_result": graph_query,
                "reviews": [
                    "主动降噪稳定，续航表现优秀",
                    "佩戴舒适，适合通勤和运动场景",
                ],
                "asin": "B0LOCALKB001",
            }
        )
    )

    audit_logs = list_audit_logs(limit=100)
    actions = [log.get("action") for log in audit_logs]

    checks = [
        CheckResult(
            "documents_ingested",
            len(uploaded_doc_ids) == 2
            and documents_response.status_code == 200
            and documents_payload.get("total", 0) >= 2
            and knowledge_stats.get("total_documents", 0) >= 2,
            f"document_total={documents_payload.get('total')}",
            {
                "doc_ids": uploaded_doc_ids,
                "knowledge_stats": knowledge_stats,
            },
        ),
        CheckResult(
            "knowledge_query_with_citations",
            knowledge_query_first_response.status_code == 200
            and knowledge_query_first.get("total_found", 0) >= 1
            and bool((knowledge_query_first.get("results") or [{}])[0].get("citation"))
            and bool(((knowledge_query_first.get("results") or [{}])[0].get("citation") or {}).get("snippet")),
            f"knowledge_total={knowledge_query_first.get('total_found')}",
            {"knowledge_query": knowledge_query_first},
        ),
        CheckResult(
            "knowledge_cache_reused",
            knowledge_query_second_response.status_code == 200
            and knowledge_query_second.get("cache_hit") is True
            and knowledge_query_second.get("cache_backend") in {"memory", "redis"},
            f"cache_backend={knowledge_query_second.get('cache_backend')}",
            {"knowledge_query_cached": knowledge_query_second},
        ),
        CheckResult(
            "llamaindex_compare_ready",
            llamaindex_status_response.status_code == 200
            and llamaindex_compare_response.status_code == 200
            and llamaindex_compare.get("comparison", {}).get("hybrid_count", 0) >= 1
            and len(llamaindex_compare.get("active_results", [])) >= 1,
            f"active_mode={llamaindex_status.get('active_mode')}",
            {
                "llamaindex_status": llamaindex_status,
                "llamaindex_compare": llamaindex_compare,
            },
        ),
        CheckResult(
            "graph_rag_query_ready",
            graph_build_response.status_code == 200
            and graph_query_response.status_code == 200
            and graph_query.get("total", 0) >= 1
            and "graph_entities" in (graph_query.get("evidence_sources") or [])
            and graph_status.get("business_query_ready") is True,
            f"graph_total={graph_query.get('total')}",
            {
                "graph_build": graph_build,
                "graph_query": graph_query,
                "graph_status": graph_status,
            },
        ),
        CheckResult(
            "agent_citation_echo_ready",
            len(agent_result.get("knowledge_citations", [])) >= 1
            and (agent_result.get("reference_summary") or {}).get("citation_count", 0) >= 1
            and "graph_entities" in ((agent_result.get("graph_context") or {}).get("evidence_sources") or [])
            and agent_result.get("context_sources", 0) >= 1,
            f"citation_count={(agent_result.get('reference_summary') or {}).get('citation_count')}",
            {"agent_result": agent_result},
        ),
        CheckResult(
            "audit_logs_captured",
            "knowledge.document.upload" in actions
            and "knowledge.llamaindex.compare" in actions,
            f"audit_count={len(audit_logs)}",
            {"actions": actions},
        ),
    ]

    operation_path = run_dir / "operation_records.json"
    documents_path = run_dir / "documents.json"
    knowledge_query_path = run_dir / "knowledge_query.json"
    cached_query_path = run_dir / "knowledge_query_cached.json"
    llamaindex_path = run_dir / "llamaindex_compare.json"
    graph_query_path = run_dir / "graph_query.json"
    graph_status_path = run_dir / "graph_status.json"
    agent_result_path = run_dir / "agent_result.json"
    audit_logs_path = run_dir / "audit_logs.json"

    _write_json(operation_path, operation_records)
    _write_json(
        documents_path,
        {
            "list": documents_payload,
            "details": document_details,
            "stats": knowledge_stats,
        },
    )
    _write_json(knowledge_query_path, knowledge_query_first)
    _write_json(cached_query_path, knowledge_query_second)
    _write_json(
        llamaindex_path,
        {
            "status": llamaindex_status,
            "compare": llamaindex_compare,
        },
    )
    _write_json(
        graph_query_path,
        {
            "build": graph_build,
            "query": graph_query,
        },
    )
    _write_json(graph_status_path, graph_status)
    _write_json(agent_result_path, agent_result)
    _write_json(audit_logs_path, audit_logs)

    summary = {
        "status": _status_from_checks(checks),
        "accepted": all(item.passed for item in checks),
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "workspace_root": str(workspace_root),
        "doc_ids": uploaded_doc_ids,
        "checks": [item.to_dict() for item in checks],
        "artifacts": {
            "operation_records": str(operation_path),
            "documents": str(documents_path),
            "knowledge_query": str(knowledge_query_path),
            "knowledge_query_cached": str(cached_query_path),
            "llamaindex_compare": str(llamaindex_path),
            "graph_query": str(graph_query_path),
            "graph_status": str(graph_status_path),
            "agent_result": str(agent_result_path),
            "audit_logs": str(audit_logs_path),
            "summary": str(run_dir / "summary.json"),
        },
    }
    _write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
