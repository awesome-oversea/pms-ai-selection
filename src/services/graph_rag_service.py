from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from src.config.settings import get_settings
from src.infrastructure.graph_rag import GraphRAGEngine, LocalGraphStore, Neo4jError, Neo4jGraphStore


class GraphRAGService:
    SUMMARY_VERSION = "2026-04-19"

    def __init__(
        self,
        engine: GraphRAGEngine | None = None,
        store_path: str | Path = "artifacts/graph_rag/local_graph_store.json",
    ) -> None:
        self._storage_backend = "local_graph_store"
        self._fallback_reason: str | None = None
        self._backend_health: dict[str, Any] | None = None
        if engine is not None:
            self.engine = engine
            self._storage_backend = engine.__class__.__name__
            return

        self.engine = GraphRAGEngine(neo4j=self._build_graph_store(store_path))

    def _build_graph_store(self, store_path: str | Path):
        settings = get_settings().neo4j
        if not settings.enabled:
            self._storage_backend = "LocalGraphStore"
            self._backend_health = {
                "reachable": False,
                "mode": "disabled",
                "uri": settings.uri,
                "database": settings.database,
            }
            return LocalGraphStore(store_path)
        try:
            store = Neo4jGraphStore(
                uri=settings.uri,
                username=settings.username,
                password=settings.password,
                database=settings.database,
                timeout_seconds=settings.timeout_seconds,
            )
            self._backend_health = store.ping()
            self._storage_backend = "Neo4jGraphStore"
            return store
        except (RuntimeError, Neo4jError, Exception) as exc:
            if not settings.prefer_local_fallback:
                raise
            self._storage_backend = "LocalGraphStore"
            self._fallback_reason = str(exc)
            self._backend_health = {
                "reachable": False,
                "mode": "fallback",
                "uri": settings.uri,
                "database": settings.database,
                "error": str(exc),
            }
            return LocalGraphStore(store_path)

    @staticmethod
    def _signal_strength(count: int, *, high_threshold: int = 3, medium_threshold: int = 1) -> str:
        if count >= high_threshold:
            return "high"
        if count >= medium_threshold:
            return "medium"
        return "low"

    @staticmethod
    def _unique_names(items: list[dict[str, Any]], *, key: str = "name", limit: int = 5) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for item in items:
            value = str(item.get(key) or "").strip()
            if value and value not in seen:
                seen.add(value)
                names.append(value)
            if len(names) >= limit:
                break
        return names

    @staticmethod
    def _relation_signal_type(neighbor_type: str, relation_types: list[str]) -> str:
        relation_set = set(relation_types)
        if "COMPETES_WITH" in relation_set or neighbor_type == "Brand":
            return "competitor_link"
        if "SUPPLIED_BY" in relation_set or neighbor_type == "Supplier":
            return "supplier_link"
        if "HAS_FEATURE" in relation_set or neighbor_type == "Feature":
            return "feature_link"
        if "BELONGS_TO" in relation_set or neighbor_type == "Category":
            return "category_link"
        return "related_entity"

    @classmethod
    def _signal_hint(cls, signal_type: str, entity_name: str) -> str:
        if signal_type == "competitor_link":
            return f"可将 {entity_name} 纳入竞品对标与差异化复盘。"
        if signal_type == "supplier_link":
            return f"建议核验 {entity_name} 的交期、MOQ 与供货稳定性。"
        if signal_type == "feature_link":
            return f"可围绕 {entity_name} 提炼卖点并评估差异化空间。"
        if signal_type == "category_link":
            return f"建议结合 {entity_name} 类目扩展相近产品池。"
        return f"建议继续补充 {entity_name} 的上下游关系。"

    @classmethod
    def _detect_query_focus(cls, query: str, relation_counter: Counter[str]) -> str:
        normalized = query.lower()
        if any(keyword in normalized for keyword in ("竞品", "竞争", "对手", "competitor", "compete")):
            return "competitor_analysis"
        if any(keyword in normalized for keyword in ("供应", "供货", "supplier")):
            return "supplier_mapping"
        if any(keyword in normalized for keyword in ("卖点", "功能", "feature", "差异化")):
            return "feature_analysis"
        if any(keyword in normalized for keyword in ("类目", "品类", "category")):
            return "category_mapping"
        if relation_counter.get("COMPETES_WITH", 0) > 0:
            return "competitor_analysis"
        if relation_counter.get("SUPPLIED_BY", 0) > 0:
            return "supplier_mapping"
        if relation_counter.get("HAS_FEATURE", 0) > 0:
            return "feature_analysis"
        if relation_counter.get("BELONGS_TO", 0) > 0:
            return "category_mapping"
        return "relationship_discovery"

    @staticmethod
    def _next_action_for_focus(query_focus: str, signal_strength: str) -> str:
        if query_focus == "competitor_analysis":
            return "输出竞品对标清单并补价格、评分与销量对照。"
        if query_focus == "supplier_mapping":
            return "继续核对供应商交期、MOQ 与备货风险。"
        if query_focus == "feature_analysis":
            return "提炼核心卖点并与评论反馈做差异化映射。"
        if query_focus == "category_mapping":
            return "扩展相邻类目并筛选可复制的候选款。"
        if signal_strength == "low":
            return "先补图谱样本或导入更多商品/品牌文本，再重新查询。"
        return "继续补充实体关系并结合利润、趋势数据做联合判断。"

    @classmethod
    def _build_query_business_signals(cls, results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
        signals: list[dict[str, Any]] = []
        relation_counter: Counter[str] = Counter()
        entity_type_counter: Counter[str] = Counter()
        for item in results:
            neighbor = item.get("neighbor") or {}
            neighbor_name = str(neighbor.get("name") or "unknown")
            neighbor_type = str(neighbor.get("type") or "Unknown")
            path = item.get("path") or []
            relation_types = [str(rel.get("type") or "RELATED_TO") for rel in path]
            relation_counter.update(relation_types)
            entity_type_counter[neighbor_type] += 1
            signal_type = cls._relation_signal_type(neighbor_type, relation_types)
            signals.append(
                {
                    "signal_type": signal_type,
                    "entity_name": neighbor_name,
                    "entity_type": neighbor_type,
                    "relation_types": relation_types or ["RELATED_TO"],
                    "path_length": int(item.get("path_length") or len(path) or 0),
                    "signal_strength": "high" if len(relation_types) >= 2 else "medium",
                    "business_hint": cls._signal_hint(signal_type, neighbor_name),
                }
            )
        return signals, relation_counter, entity_type_counter

    @classmethod
    def _augment_query_result(cls, *, query: str, result: dict[str, Any]) -> dict[str, Any]:
        recognized_entities = result.get("recognized_entities") or []
        results = result.get("results") or []
        signals, relation_counter, entity_type_counter = cls._build_query_business_signals(results)
        top_related_entities = [signal["entity_name"] for signal in signals[:5]]
        query_focus = cls._detect_query_focus(query, relation_counter)
        signal_strength = cls._signal_strength(len(signals), high_threshold=4, medium_threshold=1)
        recognized_names = cls._unique_names(recognized_entities)

        result["business_signals"] = signals
        result["graph_query_metrics"] = {
            "recognized_entity_count": len(recognized_entities),
            "result_count": len(results),
            "relation_type_breakdown": dict(relation_counter),
            "neighbor_type_breakdown": dict(entity_type_counter),
        }
        result["business_summary"] = {
            "summary_version": cls.SUMMARY_VERSION,
            "query_focus": query_focus,
            "signal_strength": signal_strength,
            "signal_scorecard": {
                "recognized_entity_count": len(recognized_entities),
                "result_count": len(results),
                "brand_hits": entity_type_counter.get("Brand", 0),
                "supplier_hits": entity_type_counter.get("Supplier", 0),
                "feature_hits": entity_type_counter.get("Feature", 0),
                "category_hits": entity_type_counter.get("Category", 0),
            },
            "top_related_entities": top_related_entities,
            "operations_view": (
                f"图谱围绕 {', '.join(recognized_names) if recognized_names else query} 识别出 {len(results)} 个关联节点，"
                f"当前查询焦点为 {query_focus}。"
            ),
            "procurement_view": (
                f"供应/品牌相关命中 {entity_type_counter.get('Supplier', 0) + entity_type_counter.get('Brand', 0)} 个，"
                "可继续核对供应稳定性与竞品覆盖。"
            ),
            "finance_view": (
                f"竞争与类目信号强度为 {signal_strength}，建议结合价格、毛利与转化数据做二次筛选。"
            ),
            "next_action": cls._next_action_for_focus(query_focus, signal_strength),
            "query": query,
        }
        return result

    @classmethod
    def _augment_competitor_result(cls, *, brand_name: str, result: dict[str, Any]) -> dict[str, Any]:
        competitors = result.get("competitors") or []
        competitor_names = cls._unique_names(competitors)
        competitor_count = len(competitors)
        competition_strength = cls._signal_strength(competitor_count, high_threshold=4, medium_threshold=1)
        result["business_signals"] = [
            {
                "signal_type": "competitor_presence",
                "entity_name": str(item.get("name") or "unknown"),
                "signal_strength": "high" if index < 2 else "medium",
                "business_hint": f"建议将 {item.get('name') or 'unknown'} 纳入价格、评论与渠道对标。",
            }
            for index, item in enumerate(competitors)
        ]
        result["competitive_landscape"] = {
            "competitor_count": competitor_count,
            "top_competitors": competitor_names,
            "pressure_level": competition_strength,
            "coverage_status": "direct_competitor_links" if result.get("found") else "graph_gap",
        }
        result["business_summary"] = {
            "summary_version": cls.SUMMARY_VERSION,
            "brand": brand_name,
            "competition_signal_strength": competition_strength,
            "signal_scorecard": {
                "competitor_count": competitor_count,
                "direct_relation_count": competitor_count,
            },
            "operations_view": (
                f"{brand_name} 当前识别到 {competitor_count} 个直接竞品，"
                f"重点对手包括 {', '.join(competitor_names) if competitor_names else '暂无'}。"
            ),
            "procurement_view": (
                "建议将竞品品牌映射到供应商、交期与起订量维度，补齐供应侧差异。"
            ),
            "finance_view": (
                f"竞品压力等级为 {competition_strength}，可继续补充价格带、毛利带和促销动作对照。"
            ),
            "next_action": (
                "输出竞品价位带与评价对照表。"
                if result.get("found")
                else "先补品牌关系或导入竞品文档，增强图谱覆盖。"
            ),
        }
        return result

    @classmethod
    def _augment_product_result(cls, *, product_name: str, result: dict[str, Any]) -> dict[str, Any]:
        graph = result.get("graph") or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        node_type_counter: Counter[str] = Counter(str(node.get("type") or "Unknown") for node in nodes)
        relation_counter: Counter[str] = Counter(str(edge.get("type") or "RELATED_TO") for edge in edges)
        supplier_count = node_type_counter.get("Supplier", 0)
        feature_count = node_type_counter.get("Feature", 0)
        category_count = node_type_counter.get("Category", 0)
        supply_strength = cls._signal_strength(supplier_count, high_threshold=2, medium_threshold=1)
        feature_strength = cls._signal_strength(feature_count, high_threshold=3, medium_threshold=1)

        business_signals: list[dict[str, Any]] = []
        if supplier_count > 0:
            business_signals.append(
                {
                    "signal_type": "supply_linked",
                    "signal_strength": supply_strength,
                    "count": supplier_count,
                    "business_hint": "产品已建立供应侧节点，可继续核验交期、MOQ 与库存弹性。",
                }
            )
        if feature_count > 0:
            business_signals.append(
                {
                    "signal_type": "feature_mapped",
                    "signal_strength": feature_strength,
                    "count": feature_count,
                    "business_hint": "图谱已沉淀卖点特征，可继续映射评论反馈与差异化策略。",
                }
            )
        if category_count > 0:
            business_signals.append(
                {
                    "signal_type": "category_anchored",
                    "signal_strength": cls._signal_strength(category_count, high_threshold=2, medium_threshold=1),
                    "count": category_count,
                    "business_hint": "产品已挂靠类目节点，可扩展相邻类目与替代款分析。",
                }
            )

        result["business_signals"] = business_signals
        result["graph_metrics"] = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_type_breakdown": dict(node_type_counter),
            "relation_type_breakdown": dict(relation_counter),
            "supplier_count": supplier_count,
            "feature_count": feature_count,
            "category_count": category_count,
        }
        result["business_summary"] = {
            "summary_version": cls.SUMMARY_VERSION,
            "product_name": product_name,
            "supply_signal_strength": supply_strength,
            "feature_signal_strength": feature_strength,
            "signal_scorecard": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "supplier_count": supplier_count,
                "feature_count": feature_count,
                "category_count": category_count,
            },
            "operations_view": (
                f"{product_name} 当前图谱已关联 {len(nodes)} 个节点、{len(edges)} 条关系，"
                f"产品关系覆盖状态为 {'已建立' if result.get('found') else '待补充'}。"
            ),
            "procurement_view": (
                f"供应链信号强度为 {supply_strength}，建议继续补供应商、交期和起订量映射。"
            ),
            "finance_view": (
                f"卖点特征强度为 {feature_strength}，可继续叠加评论与利润数据验证差异化空间。"
            ),
            "next_action": (
                "补充供应商、卖点与类目关系后生成候选款业务画像。"
                if result.get("found")
                else "先导入产品说明、竞品资料或评价文本，补齐基础图谱。"
            ),
        }
        return result

    async def build_graph_from_text(self, *, text: str, doc_id: str | None = None) -> dict[str, Any]:
        return await self.engine.build_graph(text, doc_id=doc_id)

    async def query_graph(self, *, query: str, max_hops: int = 2, top_k: int = 10) -> dict[str, Any]:
        result = await self.engine.query(query, max_hops=max_hops, top_k=top_k)
        result["evidence_sources"] = ["graph_entities", "graph_relations", "vector_context"]
        result["fusion_summary"] = {
            "graph_hits": result.get("total", 0),
            "fusion_mode": "graph+vector",
        }
        return self._augment_query_result(query=query, result=result)

    async def get_competitor_graph(self, *, brand_name: str) -> dict[str, Any]:
        result = await self.engine.get_competitors(brand_name)
        result["evidence_sources"] = ["graph_entities", "graph_relations"]
        result["fusion_summary"] = {
            "graph_hits": len(result.get("competitors", [])),
            "fusion_mode": "graph-first",
        }
        return self._augment_competitor_result(brand_name=brand_name, result=result)

    async def get_product_graph(self, *, product_name: str, max_hops: int = 2) -> dict[str, Any]:
        result = await self.engine.get_product_graph(product_name, max_hops=max_hops)
        result["evidence_sources"] = ["graph_entities", "graph_relations", "knowledge_base"]
        result["fusion_summary"] = {
            "graph_ready": result.get("found", False),
            "fusion_mode": "graph+kb",
        }
        return self._augment_product_result(product_name=product_name, result=result)

    def get_status(self) -> dict[str, Any]:
        stats = self.engine.get_stats()
        neo4j_backend = getattr(self.engine, "_neo4j", None)
        storage_backend = neo4j_backend.__class__.__name__ if neo4j_backend is not None else "UnknownGraphStore"
        settings = get_settings().neo4j
        return {
            "graph_ready": True,
            "retrieval_fusion_ready": True,
            "business_query_ready": True,
            "business_summary_version": self.SUMMARY_VERSION,
            "storage_backend": storage_backend,
            "documents_processed": stats.get("documents_processed", 0),
            "entities_extracted": stats.get("entities_extracted", 0),
            "relations_extracted": stats.get("relations_extracted", 0),
            "queries_executed": stats.get("queries_executed", 0),
            "neo4j": {
                **stats.get("neo4j", {}),
                "enabled": settings.enabled,
                "configured_uri": settings.uri,
                "configured_database": settings.database,
                "prefer_local_fallback": settings.prefer_local_fallback,
                "active_backend": storage_backend,
                "fallback_reason": self._fallback_reason,
                "connection_verified": bool((self._backend_health or {}).get("reachable")),
                "runtime": self._backend_health or {},
            },
        }
