from __future__ import annotations

import pytest
from src.config.settings import get_settings
from src.services.graph_rag_service import GraphRAGService


@pytest.mark.asyncio
async def test_graph_rag_service_build_query_and_status():
    class _FakeEngine:
        async def build_graph(self, text, doc_id=None):
            return {"doc_id": doc_id, "entities_count": 2, "relations_count": 1}

        async def query(self, query, max_hops=2, top_k=10):
            return {
                "query": query,
                "recognized_entities": [{"name": "EcoFlow", "type": "Brand"}],
                "results": [
                    {
                        "neighbor": {"name": "Jackery", "type": "Brand"},
                        "path_length": 1,
                        "path": [{"type": "COMPETES_WITH"}],
                    },
                    {
                        "neighbor": {"name": "Portable Power Station", "type": "Category"},
                        "path_length": 1,
                        "path": [{"type": "BELONGS_TO"}],
                    },
                ],
                "total": 2,
            }

        async def get_competitors(self, brand_name):
            return {
                "brand": brand_name,
                "competitors": [{"name": "Jackery"}, {"name": "Anker"}],
                "found": True,
            }

        async def get_product_graph(self, product_name, max_hops=2):
            return {
                "product": {"name": product_name},
                "graph": {
                    "nodes": [
                        {"id": "p1", "name": product_name, "type": "Product"},
                        {"id": "b1", "name": "EcoFlow", "type": "Brand"},
                        {"id": "s1", "name": "Shenzhen Supplier", "type": "Supplier"},
                        {"id": "f1", "name": "fast charging", "type": "Feature"},
                        {"id": "c1", "name": "Portable Power Station", "type": "Category"},
                    ],
                    "edges": [
                        {"id": "e1", "type": "BRANDED_BY", "source": "p1", "target": "b1"},
                        {"id": "e2", "type": "SUPPLIED_BY", "source": "p1", "target": "s1"},
                        {"id": "e3", "type": "HAS_FEATURE", "source": "p1", "target": "f1"},
                        {"id": "e4", "type": "BELONGS_TO", "source": "p1", "target": "c1"},
                    ],
                },
                "found": True,
            }

        def get_stats(self):
            return {
                "documents_processed": 1,
                "entities_extracted": 2,
                "relations_extracted": 1,
                "queries_executed": 1,
                "neo4j": {"node_count": 5, "edge_count": 4},
            }

    service = GraphRAGService(engine=_FakeEngine())
    built = await service.build_graph_from_text(text="EcoFlow和Jackery是竞争对手", doc_id="doc-1")
    queried = await service.query_graph(query="EcoFlow的竞品有哪些")
    competitors = await service.get_competitor_graph(brand_name="EcoFlow")
    product = await service.get_product_graph(product_name="EcoFlow Delta 2")
    status = service.get_status()

    assert built["entities_count"] == 2
    assert queried["total"] == 2
    assert queried["evidence_sources"] == ["graph_entities", "graph_relations", "vector_context"]
    assert queried["business_summary"]["query_focus"] == "competitor_analysis"
    assert queried["business_summary"]["top_related_entities"] == ["Jackery", "Portable Power Station"]
    assert queried["business_signals"][0]["signal_type"] == "competitor_link"
    assert queried["graph_query_metrics"]["neighbor_type_breakdown"]["Brand"] == 1
    assert queried["graph_query_metrics"]["relation_type_breakdown"]["COMPETES_WITH"] == 1

    assert competitors["found"] is True
    assert competitors["fusion_summary"]["fusion_mode"] == "graph-first"
    assert competitors["competitive_landscape"]["competitor_count"] == 2
    assert competitors["business_summary"]["competition_signal_strength"] == "medium"

    assert product["found"] is True
    assert product["evidence_sources"] == ["graph_entities", "graph_relations", "knowledge_base"]
    assert product["graph_metrics"]["supplier_count"] == 1
    assert product["business_summary"]["supply_signal_strength"] == "medium"
    assert product["business_signals"][0]["signal_type"] == "supply_linked"

    assert status["graph_ready"] is True
    assert status["retrieval_fusion_ready"] is True
    assert status["business_query_ready"] is True
    assert status["business_summary_version"] == "2026-04-19"
    assert status["neo4j"]["node_count"] == 5


@pytest.mark.asyncio
async def test_graph_rag_service_handles_graph_gap_with_business_guidance():
    class _EmptyEngine:
        async def build_graph(self, text, doc_id=None):
            return {"doc_id": doc_id, "entities_count": 0, "relations_count": 0}

        async def query(self, query, max_hops=2, top_k=10):
            return {"query": query, "results": [], "recognized_entities": [], "total": 0, "message": "未识别到实体"}

        async def get_competitors(self, brand_name):
            return {"brand": brand_name, "competitors": [], "found": False}

        async def get_product_graph(self, product_name, max_hops=2):
            return {"product": product_name, "graph": None, "found": False}

        def get_stats(self):
            return {"documents_processed": 0, "entities_extracted": 0, "relations_extracted": 0, "queries_executed": 0, "neo4j": {"node_count": 0, "edge_count": 0}}

    service = GraphRAGService(engine=_EmptyEngine())
    queried = await service.query_graph(query="未知品牌有什么关系")
    competitors = await service.get_competitor_graph(brand_name="Unknown Brand")
    product = await service.get_product_graph(product_name="Unknown Product")

    assert queried["business_summary"]["signal_strength"] == "low"
    assert "补图谱样本" in queried["business_summary"]["next_action"]
    assert competitors["competitive_landscape"]["coverage_status"] == "graph_gap"
    assert "增强图谱覆盖" in competitors["business_summary"]["next_action"]
    assert "导入产品说明" in product["business_summary"]["next_action"]


@pytest.mark.asyncio
async def test_graph_rag_service_persists_local_graph_store(tmp_path):
    store_path = tmp_path / "graph_store.json"
    service = GraphRAGService(store_path=store_path)
    await service.build_graph_from_text(text="EcoFlow和Jackery是竞争对手品牌", doc_id="doc-1")

    reloaded = GraphRAGService(store_path=store_path)
    status = reloaded.get_status()
    assert status["graph_ready"] is True
    assert status["business_query_ready"] is True
    assert status["neo4j"]["node_count"] >= 2
    assert store_path.exists()


@pytest.mark.asyncio
async def test_graph_rag_service_falls_back_to_local_when_neo4j_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("NEO4J_ENABLED", "true")
    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:17687")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")
    monkeypatch.setenv("NEO4J_PREFER_LOCAL_FALLBACK", "true")
    get_settings.cache_clear()
    try:
        service = GraphRAGService(store_path=tmp_path / "graph_store.json")
        status = service.get_status()
        assert status["storage_backend"] == "LocalGraphStore"
        assert status["neo4j"]["enabled"] is True
        assert status["neo4j"]["configured_uri"] == "bolt://127.0.0.1:17687"
        assert status["neo4j"]["prefer_local_fallback"] is True
        assert status["neo4j"]["fallback_reason"]
        assert status["neo4j"]["connection_verified"] is False
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_graph_rag_service_uses_neo4j_backend_when_enabled(tmp_path, monkeypatch):
    from src.infrastructure.graph_rag import LocalGraphStore

    class _Neo4jStoreDouble(LocalGraphStore):
        def __init__(
            self,
            uri: str,
            username: str | None = None,
            password: str | None = None,
            database: str = "neo4j",
            timeout_seconds: float = 5.0,
        ) -> None:
            super().__init__(store_path=tmp_path / "neo4j_store.json")
            self._uri = uri
            self._database = database
            self._username = username
            self._password = password
            self._timeout_seconds = timeout_seconds

        def ping(self) -> dict[str, object]:
            return {"reachable": True, "database": self._database, "uri": self._uri}

        def get_stats(self) -> dict[str, object]:
            stats = super().get_stats()
            return {
                **stats,
                "backend": "neo4j",
                "database": self._database,
                "uri": self._uri,
            }

    _Neo4jStoreDouble.__name__ = "Neo4jGraphStore"

    monkeypatch.setenv("NEO4J_ENABLED", "true")
    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:17687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "pms_graph_dev")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")
    monkeypatch.setenv("NEO4J_PREFER_LOCAL_FALLBACK", "true")
    monkeypatch.setattr("src.services.graph_rag_service.Neo4jGraphStore", _Neo4jStoreDouble)
    get_settings.cache_clear()
    try:
        service = GraphRAGService(store_path=tmp_path / "local_graph_store.json")
        build_result = await service.build_graph_from_text(
            text="EcoFlowDELTA 是一款便携电源，品牌 EcoFlow，供应商 1688供应商华东仓，与 Jackery 是竞争对手。",
            doc_id="doc-1",
        )
        competitor_result = await service.get_competitor_graph(brand_name="EcoFlow")
        product_result = await service.get_product_graph(product_name="EcoFlowDELTA")
        status = service.get_status()

        assert build_result["entities_count"] >= 4
        assert build_result["relations_count"] >= 3
        assert competitor_result["found"] is True
        assert product_result["found"] is True
        assert status["storage_backend"] == "Neo4jGraphStore"
        assert status["neo4j"]["enabled"] is True
        assert status["neo4j"]["connection_verified"] is True
        assert status["neo4j"]["configured_uri"] == "bolt://127.0.0.1:17687"
        assert status["neo4j"]["active_backend"] == "Neo4jGraphStore"
        assert status["neo4j"]["fallback_reason"] is None
        assert status["neo4j"]["runtime"]["reachable"] is True
    finally:
        get_settings.cache_clear()
