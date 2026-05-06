from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from src.agents.product_planner import ProductPlannerAgent
from src.services.graph_rag_service import GraphRAGService
from src.services.local_knowledge_service import LocalKnowledgeRepository, LocalKnowledgeService


def _run(coro):
    return asyncio.run(coro)


def test_local_knowledge_service_query_includes_citation(monkeypatch, tmp_path):
    monkeypatch.setattr("src.services.local_knowledge_service.get_redis_connection", lambda: (_ for _ in ()).throw(RuntimeError("redis unavailable")))
    repo = LocalKnowledgeRepository(tmp_path / "local_knowledge.db")
    service = LocalKnowledgeService(repo=repo)

    _run(service.upload_document("earbuds.txt", "蓝牙耳机具备ANC主动降噪和40小时续航".encode()))
    result = _run(service.query_knowledge("蓝牙耳机 ANC 续航", top_k=3, threshold=0.1))

    assert result["total_found"] >= 1
    top = result["results"][0]
    assert top["citation"]["document_id"]
    assert top["citation"]["source"] == "earbuds.txt"
    assert top["citation"]["snippet"]
    assert top["ranking_meta"]["final_rank"] == 1


def test_product_planner_agent_echoes_external_knowledge_and_graph(monkeypatch):
    async def _fake_compare_1688_specs(self, product_keyword, product_spec=None, max_suppliers=5):
        return {
            "source": "ali1688_spec_comparison",
            "product_keyword": product_keyword,
            "supplier_count": 1,
            "target_feature_count": 1,
            "suppliers": [],
            "difference_items": [],
            "recommended_alignment": [],
        }

    async def _fake_fetch_crm_reviews(self, crm_api_endpoint, crm_api_key=None, crm_inbound_path="/customer-feedback", product_id=None, product_name=None, asin=None):
        return {
            "source": "crm_review_insights",
            "matched_review_count": 1,
            "avg_rating": 4.8,
            "complaint_count": 0,
            "reviews": [{"asin": asin or "B0LOCALKB001", "feedback": "降噪效果稳定", "customer_score": 4.8}],
            "summary": {"avg_rating": 4.8, "complaint_count": 0, "review_count": 12},
        }

    monkeypatch.setattr("src.agents.product_planner.ProductPlannerAgent._compare_1688_specs", _fake_compare_1688_specs)
    monkeypatch.setattr("src.agents.product_planner.ProductPlannerAgent._fetch_crm_reviews", _fake_fetch_crm_reviews)

    agent = ProductPlannerAgent()
    result = _run(
        agent.execute(
            {
                "query": "蓝牙耳机 ANC 40小时续航",
                "category": "electronics",
                "target_market": "US",
                "budget_range": [29, 89],
                "use_mock": True,
                "knowledge_query_results": [
                    {
                        "content": "SoundMax Earbuds Pro 具备 ANC 主动降噪和 40 小时续航",
                        "score": 0.96,
                        "source": "earbuds_strategy.md",
                        "document_id": "doc-kb-001",
                        "chunk_index": 0,
                        "citation": {
                            "document_id": "doc-kb-001",
                            "chunk_index": 0,
                            "source": "earbuds_strategy.md",
                            "snippet": "SoundMax Earbuds Pro 具备 ANC 主动降噪和 40 小时续航",
                        },
                    }
                ],
                "graph_query_result": {
                    "total": 1,
                    "results": [{"neighbor": {"name": "AudioPeak", "type": "Brand"}}],
                    "evidence_sources": ["graph_entities", "graph_relations", "vector_context"],
                    "business_summary": {"query_focus": "competitor_analysis"},
                },
                "reviews": ["主动降噪稳定，续航优秀"],
                "asin": "B0LOCALKB001",
            }
        )
    )

    assert result["context_sources"] == 1
    assert result["knowledge_citations"][0]["document_id"] == "doc-kb-001"
    assert result["reference_summary"]["citation_count"] == 1
    assert "graph_entities" in result["graph_context"]["evidence_sources"]
    assert result["graph_context"]["business_summary"]["query_focus"] == "competitor_analysis"


def test_graph_rag_service_supports_custom_camel_case_brands(tmp_path):
    service = GraphRAGService(store_path=tmp_path / "local_graph_store.json")
    build_result = _run(
        service.build_graph_from_text(
            text=(
                "SoundMax 和 AudioPeak 是蓝牙耳机品牌竞争对手。"
                "SoundMax Earbuds Pro 属于蓝牙耳机品类。"
            ),
            doc_id="doc-graph-001",
        )
    )
    query_result = _run(service.query_graph(query="SoundMax 的竞品有哪些", max_hops=2, top_k=5))

    assert build_result["relations_count"] >= 1
    assert query_result["total"] >= 1
    assert any(item["neighbor"]["name"] == "AudioPeak" for item in query_result["results"])
    assert query_result["business_summary"]["query_focus"] == "competitor_analysis"


def test_local_knowledge_graph_agent_script_generates_accepted_artifact(tmp_path):
    env = os.environ.copy()
    env.setdefault("SEC_SECRET_KEY", "test-local-knowledge-graph-agent-32chars")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_local_knowledge_graph_agent_acceptance.py",
            "--output-root",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    summary_candidates = sorted(tmp_path.glob("*/summary.json"))
    assert summary_candidates, result.stdout
    summary_payload = json.loads(summary_candidates[-1].read_text(encoding="utf-8"))
    assert summary_payload["accepted"] is True
    assert summary_payload["status"] == "passed"
    assert len(summary_payload["doc_ids"]) == 2
