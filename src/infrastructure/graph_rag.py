"""
GraphRAG知识图谱引擎
===================

提供知识图谱构建与检索能力(D56-D60):
    - Neo4j图数据库模拟
    - 实体识别(NER)
    - 关系抽取(RE)
    - 多跳邻居查询
    - 与向量检索融合

使用方式:
    from src.infrastructure.graph_rag import GraphRAGEngine

    engine = GraphRAGEngine()
    await engine.build_graph("户外储能电源产品介绍...")
    results = await engine.query("EcoFlow的竞品有哪些？")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError
except Exception:  # pragma: no cover - 依赖缺失时优雅降级
    GraphDatabase = None  # type: ignore[assignment]

    class Neo4jError(Exception):
        pass

from src.core.logging import get_logger

logger = get_logger(__name__)


class EntityType(StrEnum):
    """实体类型。"""
    PRODUCT = "Product"
    CATEGORY = "Category"
    BRAND = "Brand"
    SUPPLIER = "Supplier"
    FEATURE = "Feature"


class RelationType(StrEnum):
    """关系类型。"""
    BELONGS_TO = "BELONGS_TO"
    BRANDED_BY = "BRANDED_BY"
    SUPPLIED_BY = "SUPPLIED_BY"
    COMPETES_WITH = "COMPETES_WITH"
    HAS_FEATURE = "HAS_FEATURE"
    RELATED_TO = "RELATED_TO"


@dataclass
class Entity:
    """实体节点。"""
    entity_id: str
    entity_type: EntityType
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.entity_id,
            "type": self.entity_type.value,
            "name": self.name,
            "properties": self.properties,
        }


@dataclass
class Relation:
    """关系边。"""
    relation_id: str
    relation_type: RelationType
    source_id: str
    target_id: str
    confidence: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.relation_id,
            "type": self.relation_type.value,
            "source": self.source_id,
            "target": self.target_id,
            "confidence": self.confidence,
        }


@dataclass
class Triple:
    """三元组(实体-关系-实体)。"""
    head: Entity
    relation: Relation
    tail: Entity

    def to_dict(self) -> dict[str, Any]:
        return {
            "head": self.head.to_dict(),
            "relation": self.relation.to_dict(),
            "tail": self.tail.to_dict(),
        }


class Neo4jMock:
    """
    Neo4j图数据库模拟(D56)。

    功能:
        - 节点CRUD
        - 边CRUD
        - 多跳查询
        - 子图匹配
    """

    def __init__(self, uri: str = "bolt://localhost:17687"):
        self._uri = uri
        self._nodes: dict[str, Entity] = {}
        self._edges: dict[str, Relation] = {}
        self._outgoing: dict[str, set[str]] = {}
        self._incoming: dict[str, set[str]] = {}
        self._type_index: dict[EntityType, set[str]] = {}
        logger.info(f"Neo4j模拟初始化: {uri}")

    def create_node(self, entity: Entity) -> Entity:
        """创建节点。"""
        self._nodes[entity.entity_id] = entity
        if entity.entity_type not in self._type_index:
            self._type_index[entity.entity_type] = set()
        self._type_index[entity.entity_type].add(entity.entity_id)
        logger.debug(f"创建节点: {entity.entity_type.value} - {entity.name}")
        return entity

    def create_edge(self, relation: Relation) -> Relation:
        """创建边。"""
        self._edges[relation.relation_id] = relation
        if relation.source_id not in self._outgoing:
            self._outgoing[relation.source_id] = set()
        self._outgoing[relation.source_id].add(relation.relation_id)
        if relation.target_id not in self._incoming:
            self._incoming[relation.target_id] = set()
        self._incoming[relation.target_id].add(relation.relation_id)
        return relation

    def get_node(self, node_id: str) -> Entity | None:
        return self._nodes.get(node_id)

    def get_nodes_by_type(self, entity_type: EntityType) -> list[Entity]:
        ids = self._type_index.get(entity_type, set())
        return [self._nodes[i] for i in ids if i in self._nodes]

    def find_nodes(self, name_pattern: str, entity_type: EntityType | None = None) -> list[Entity]:
        """按名称模式查找节点。"""
        pattern = re.compile(name_pattern, re.IGNORECASE)
        results = []
        for node in self._nodes.values():
            if pattern.search(node.name) and (entity_type is None or node.entity_type == entity_type):
                results.append(node)
        return results

    def get_neighbors(
        self,
        node_id: str,
        relation_types: list[RelationType] | None = None,
        max_hops: int = 1,
        direction: str = "both",
    ) -> list[tuple[Entity, list[Relation]]]:
        """获取邻居节点(D60核心)。"""
        if node_id not in self._nodes:
            return []

        visited = {node_id}
        current_level = [(node_id, [])]
        results = []

        for _ in range(max_hops):
            next_level = []
            for curr_id, path in current_level:
                edge_ids = set()
                if direction in ("out", "both"):
                    edge_ids.update(self._outgoing.get(curr_id, set()))
                if direction in ("in", "both"):
                    edge_ids.update(self._incoming.get(curr_id, set()))

                for edge_id in edge_ids:
                    edge = self._edges.get(edge_id)
                    if not edge:
                        continue
                    if relation_types and edge.relation_type not in relation_types:
                        continue

                    neighbor_id = edge.target_id if edge.source_id == curr_id else edge.source_id
                    if neighbor_id in visited:
                        continue

                    neighbor = self._nodes.get(neighbor_id)
                    if neighbor:
                        new_path = path + [edge]
                        results.append((neighbor, new_path))
                        visited.add(neighbor_id)
                        next_level.append((neighbor_id, new_path))

            current_level = next_level

        return results

    def get_subgraph(self, node_ids: list[str]) -> dict[str, Any]:
        """获取子图。"""
        nodes = [self._nodes[n].to_dict() for n in node_ids if n in self._nodes]
        edges = []
        for edge in self._edges.values():
            if edge.source_id in node_ids and edge.target_id in node_ids:
                edges.append(edge.to_dict())
        return {"nodes": nodes, "edges": edges}

    def get_stats(self) -> dict[str, Any]:
        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "node_types": {entity_type.value: len(ids) for entity_type, ids in self._type_index.items()},
        }


class LocalGraphStore(Neo4jMock):
    """本地图索引持久化实现，用 JSON 作为等价真实图存储。"""

    def __init__(self, store_path: str | Path = "artifacts/graph_rag/local_graph_store.json"):
        self._store_path = Path(store_path)
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(uri=f"file://{self._store_path.as_posix()}")
        self._load()

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        data = json.loads(self._store_path.read_text(encoding="utf-8"))
        self._nodes = {
            item["id"]: Entity(
                entity_id=item["id"],
                entity_type=EntityType(item["type"]),
                name=item["name"],
                properties=item.get("properties", {}),
                created_at=item.get("created_at", datetime.now(UTC).isoformat()),
            )
            for item in data.get("nodes", [])
        }
        self._edges = {
            item["id"]: Relation(
                relation_id=item["id"],
                relation_type=RelationType(item["type"]),
                source_id=item["source"],
                target_id=item["target"],
                confidence=float(item.get("confidence", 1.0)),
                properties=item.get("properties", {}),
            )
            for item in data.get("edges", [])
        }
        self._outgoing = {}
        self._incoming = {}
        self._type_index = {}
        for entity in self._nodes.values():
            self._type_index.setdefault(entity.entity_type, set()).add(entity.entity_id)
        for relation in self._edges.values():
            self._outgoing.setdefault(relation.source_id, set()).add(relation.relation_id)
            self._incoming.setdefault(relation.target_id, set()).add(relation.relation_id)

    def _persist(self) -> None:
        payload = {
            "nodes": [
                {
                    **entity.to_dict(),
                    "created_at": entity.created_at,
                }
                for entity in self._nodes.values()
            ],
            "edges": [
                {
                    **relation.to_dict(),
                    "properties": relation.properties,
                }
                for relation in self._edges.values()
            ],
        }
        self._store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_node(self, entity: Entity) -> Entity:
        result = super().create_node(entity)
        self._persist()
        return result

    def create_edge(self, relation: Relation) -> Relation:
        result = super().create_edge(relation)
        self._persist()
        return result


class Neo4jGraphStore(Neo4jMock):
    """Neo4j 真实图数据库存储，接口与 Neo4jMock/LocalGraphStore 保持一致。"""

    def __init__(
        self,
        uri: str,
        username: str | None = None,
        password: str | None = None,
        database: str = "neo4j",
        timeout_seconds: float = 5.0,
    ):
        if GraphDatabase is None:
            raise RuntimeError("neo4j-driver 未安装")
        auth = (username, password) if username and password else None
        self._driver = GraphDatabase.driver(uri, auth=auth, connection_timeout=timeout_seconds)
        self._database = database
        super().__init__(uri=uri)
        self._bootstrap_indexes()

    def _bootstrap_indexes(self) -> None:
        with self._driver.session(database=self._database) as session:
            session.run("CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE")
            session.run("CREATE INDEX entity_name_index IF NOT EXISTS FOR (n:Entity) ON (n.name)")

    def ping(self) -> dict[str, Any]:
        with self._driver.session(database=self._database) as session:
            record = session.run("RETURN 1 AS ok").single()
            return {
                "reachable": bool(record and record.get("ok") == 1),
                "database": self._database,
                "uri": self._uri,
            }

    def close(self) -> None:
        self._driver.close()

    def create_node(self, entity: Entity) -> Entity:
        query = """
        MERGE (n:Entity {entity_id: $entity_id})
        SET n.entity_type = $entity_type,
            n.name = $name,
            n.properties = $properties,
            n.created_at = $created_at
        RETURN n.entity_id AS entity_id
        """
        with self._driver.session(database=self._database) as session:
            session.run(
                query,
                entity_id=entity.entity_id,
                entity_type=entity.entity_type.value,
                name=entity.name,
                properties=json.dumps(entity.properties, ensure_ascii=False),
                created_at=entity.created_at,
            ).consume()
        return entity

    def create_edge(self, relation: Relation) -> Relation:
        query = """
        MATCH (source:Entity {entity_id: $source_id})
        MATCH (target:Entity {entity_id: $target_id})
        MERGE (source)-[r:RELATION {relation_id: $relation_id}]->(target)
        SET r.relation_type = $relation_type,
            r.confidence = $confidence,
            r.properties = $properties
        RETURN r.relation_id AS relation_id
        """
        with self._driver.session(database=self._database) as session:
            session.run(
                query,
                relation_id=relation.relation_id,
                relation_type=relation.relation_type.value,
                source_id=relation.source_id,
                target_id=relation.target_id,
                confidence=relation.confidence,
                properties=json.dumps(relation.properties, ensure_ascii=False),
            ).consume()
        return relation

    def get_node(self, node_id: str) -> Entity | None:
        query = "MATCH (n:Entity {entity_id: $entity_id}) RETURN n LIMIT 1"
        with self._driver.session(database=self._database) as session:
            record = session.run(query, entity_id=node_id).single()
        if not record:
            return None
        return self._record_to_entity(record["n"])

    def get_nodes_by_type(self, entity_type: EntityType) -> list[Entity]:
        query = "MATCH (n:Entity {entity_type: $entity_type}) RETURN n"
        with self._driver.session(database=self._database) as session:
            records = session.run(query, entity_type=entity_type.value)
            return [self._record_to_entity(record["n"]) for record in records]

    def find_nodes(self, name_pattern: str, entity_type: EntityType | None = None) -> list[Entity]:
        query = "MATCH (n:Entity) WHERE n.name =~ $name_pattern"
        params: dict[str, Any] = {"name_pattern": name_pattern}
        if entity_type is not None:
            query += " AND n.entity_type = $entity_type"
            params["entity_type"] = entity_type.value
        query += " RETURN n LIMIT 50"
        with self._driver.session(database=self._database) as session:
            records = session.run(query, **params)
            return [self._record_to_entity(record["n"]) for record in records]

    def get_neighbors(
        self,
        node_id: str,
        relation_types: list[RelationType] | None = None,
        max_hops: int = 1,
        direction: str = "both",
    ) -> list[tuple[Entity, list[Relation]]]:
        if direction == "in":
            pattern = f"(neighbor:Entity)-[rels:RELATION*1..{max_hops}]->(start:Entity {{entity_id: $entity_id}})"
        elif direction == "out":
            pattern = f"(start:Entity {{entity_id: $entity_id}})-[rels:RELATION*1..{max_hops}]->(neighbor:Entity)"
        else:
            pattern = f"(start:Entity {{entity_id: $entity_id}})-[rels:RELATION*1..{max_hops}]-(neighbor:Entity)"
        query = f"MATCH p={pattern} RETURN neighbor, rels LIMIT 100"
        results: list[tuple[Entity, list[Relation]]] = []
        with self._driver.session(database=self._database) as session:
            records = session.run(query, entity_id=node_id)
            for record in records:
                neighbor = self._record_to_entity(record["neighbor"])
                path_relations = [self._record_to_relation(rel) for rel in record["rels"]]
                if relation_types and any(rel.relation_type not in relation_types for rel in path_relations):
                    continue
                results.append((neighbor, path_relations))
        return results

    def get_subgraph(self, node_ids: list[str]) -> dict[str, Any]:
        query = """
        MATCH (n:Entity)
        WHERE n.entity_id IN $node_ids
        OPTIONAL MATCH (n)-[r:RELATION]-(m:Entity)
        WHERE m.entity_id IN $node_ids
        RETURN collect(DISTINCT n) AS nodes, collect(DISTINCT r) AS edges
        """
        with self._driver.session(database=self._database) as session:
            record = session.run(query, node_ids=node_ids).single()
        nodes = [self._record_to_entity(node).to_dict() for node in (record["nodes"] if record else []) if node is not None]
        edges = [self._record_to_relation(edge).to_dict() for edge in (record["edges"] if record else []) if edge is not None]
        return {"nodes": nodes, "edges": edges}

    def get_stats(self) -> dict[str, Any]:
        query = """
        MATCH (n:Entity)
        OPTIONAL MATCH ()-[r:RELATION]->()
        RETURN count(DISTINCT n) AS node_count, count(DISTINCT r) AS edge_count, collect(DISTINCT n.entity_type) AS node_types
        """
        with self._driver.session(database=self._database) as session:
            record = session.run(query).single()
        node_types = {item: len(self.get_nodes_by_type(EntityType(item))) for item in (record["node_types"] if record else []) if item}
        return {
            "node_count": int(record["node_count"] if record else 0),
            "edge_count": int(record["edge_count"] if record else 0),
            "node_types": node_types,
            "backend": "neo4j",
            "database": self._database,
            "uri": self._uri,
        }

    @staticmethod
    def _record_to_entity(node: Any) -> Entity:
        properties = node.get("properties")
        if isinstance(properties, str):
            try:
                properties = json.loads(properties)
            except json.JSONDecodeError:
                properties = {}
        return Entity(
            entity_id=node.get("entity_id"),
            entity_type=EntityType(node.get("entity_type")),
            name=node.get("name"),
            properties=properties or {},
            created_at=node.get("created_at") or datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _record_to_relation(rel: Any) -> Relation:
        properties = rel.get("properties")
        if isinstance(properties, str):
            try:
                properties = json.loads(properties)
            except json.JSONDecodeError:
                properties = {}
        return Relation(
            relation_id=rel.get("relation_id"),
            relation_type=RelationType(rel.get("relation_type")),
            source_id=rel.start_node.get("entity_id"),
            target_id=rel.end_node.get("entity_id"),
            confidence=float(rel.get("confidence") or 1.0),
            properties=properties or {},
        )


class NERExtractor:
    """
    实体识别器(D57)。

    支持的实体类型:
        - PRODUCT: 商品名
        - CATEGORY: 品类
        - BRAND: 品牌
        - SUPPLIER: 供应商
    """

    ENTITY_PATTERNS = {
        EntityType.PRODUCT: [
            r"([\u4e00-\u9fff]+储能电源)",
            r"([\u4e00-\u9fff]+充电宝)",
            r"([\u4e00-\u9fff]+耳机)",
            r"([\u4e00-\u9fff]+音箱)",
            r"(EcoFlow\s*\w+)",
            r"(Jackery\s*\w+)",
        ],
        EntityType.BRAND: [
            r"(EcoFlow)",
            r"(Jackery)",
            r"(Anker)",
            r"(小米)",
            r"(华为)",
            r"(Apple)",
            r"(Sony)",
            r"(?<![A-Za-z0-9])([A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)+)(?![A-Za-z0-9])",
        ],
        EntityType.CATEGORY: [
            r"(储能设备)",
            r"(便携电源)",
            r"(蓝牙耳机)",
            r"(智能音箱)",
            r"(户外装备)",
        ],
        EntityType.SUPPLIER: [
            r"(1688供应商[^\s，。]+)",
            r"(供应商[^\s，。]+)",
        ],
    }

    def __init__(self):
        self._compiled_patterns = {
            etype: [re.compile(p) for p in patterns]
            for etype, patterns in self.ENTITY_PATTERNS.items()
        }
        logger.info("NERExtractor初始化完成")

    def extract(self, text: str) -> list[Entity]:
        """从文本中提取实体。"""
        entities = []
        seen = set()

        for entity_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    name = match.group(1).strip()
                    key = (entity_type, name)
                    if key not in seen:
                        entity_id = f"{entity_type.value[:3]}_{hash(name) % 100000:05d}"
                        entities.append(Entity(
                            entity_id=entity_id,
                            entity_type=entity_type,
                            name=name,
                            properties={"source_text": text[max(0, match.start() - 20):match.end() + 20]},
                        ))
                        seen.add(key)

        logger.debug(f"NER提取: {len(entities)}个实体")
        return entities


class RelationExtractor:
    """
    关系抽取器(D58)。

    支持的关系类型:
        - BELONGS_TO: 品类归属
        - BRANDED_BY: 品牌关联
        - SUPPLIED_BY: 供应关系
        - COMPETES_WITH: 竞争关系
    """

    RELATION_KEYWORDS = {
        RelationType.BELONGS_TO: ["属于", "归类为", "是", "是一款"],
        RelationType.BRANDED_BY: ["品牌", "出品", "生产", "旗下"],
        RelationType.SUPPLIED_BY: ["供应商", "供货", "采购自", "来自"],
        RelationType.COMPETES_WITH: ["竞品", "竞争对手", "对标", "竞争"],
    }

    def __init__(self):
        self._compiled_keywords = {
            rtype: keywords for rtype, keywords in self.RELATION_KEYWORDS.items()
        }
        logger.info("RelationExtractor初始化完成")

    def extract(
        self,
        text: str,
        entities: list[Entity],
    ) -> list[Triple]:
        """从文本和实体中抽取关系。"""
        triples = []

        products = [e for e in entities if e.entity_type == EntityType.PRODUCT]
        brands = [e for e in entities if e.entity_type == EntityType.BRAND]
        categories = [e for e in entities if e.entity_type == EntityType.CATEGORY]
        suppliers = [e for e in entities if e.entity_type == EntityType.SUPPLIER]

        for product in products:
            for brand in brands:
                if self._has_relation(text, product.name, brand.name, RelationType.BRANDED_BY):
                    relation = self._create_relation(
                        product.entity_id, brand.entity_id, RelationType.BRANDED_BY
                    )
                    triples.append(Triple(head=product, relation=relation, tail=brand))

            for category in categories:
                if self._has_relation(text, product.name, category.name, RelationType.BELONGS_TO):
                    relation = self._create_relation(
                        product.entity_id, category.entity_id, RelationType.BELONGS_TO
                    )
                    triples.append(Triple(head=product, relation=relation, tail=category))

            for supplier in suppliers:
                if self._has_relation(text, product.name, supplier.name, RelationType.SUPPLIED_BY):
                    relation = self._create_relation(
                        product.entity_id, supplier.entity_id, RelationType.SUPPLIED_BY
                    )
                    triples.append(Triple(head=product, relation=relation, tail=supplier))

        if len(brands) >= 2:
            for i, b1 in enumerate(brands):
                for b2 in brands[i + 1:]:
                    if self._has_relation(text, b1.name, b2.name, RelationType.COMPETES_WITH):
                        relation = self._create_relation(
                            b1.entity_id, b2.entity_id, RelationType.COMPETES_WITH
                        )
                        triples.append(Triple(head=b1, relation=relation, tail=b2))

        logger.debug(f"RE抽取: {len(triples)}个三元组")
        return triples

    def _has_relation(
        self,
        text: str,
        head_name: str,
        tail_name: str,
        relation_type: RelationType,
    ) -> bool:
        keywords = self._compiled_keywords.get(relation_type, [])
        for kw in keywords:
            if kw in text:
                head_pos = text.find(head_name)
                tail_pos = text.find(tail_name)
                if head_pos >= 0 and tail_pos >= 0:
                    return True
        return False

    def _create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
    ) -> Relation:
        import hashlib

        rid = hashlib.md5(f"{source_id}:{relation_type.value}:{target_id}".encode()).hexdigest()[:12]
        return Relation(
            relation_id=f"rel_{rid}",
            relation_type=relation_type,
            source_id=source_id,
            target_id=target_id,
            confidence=0.85,
        )


class GraphRAGEngine:
    """
    GraphRAG引擎(D56-D60核心)。

    功能:
        1. 文档→图谱构建Pipeline
        2. 多跳邻居查询
        3. 子图检索
        4. 与向量检索融合
    """

    def __init__(self, neo4j: Neo4jMock | None = None):
        self._neo4j = neo4j or Neo4jMock()
        self._ner = NERExtractor()
        self._re = RelationExtractor()
        self._stats = {
            "documents_processed": 0,
            "entities_extracted": 0,
            "relations_extracted": 0,
            "queries_executed": 0,
        }
        logger.info("GraphRAGEngine初始化完成")

    async def build_graph(self, text: str, doc_id: str | None = None) -> dict[str, Any]:
        """
        从文本构建图谱(D59)。

        流程:
            1. NER实体识别
            2. RE关系抽取
            3. Neo4j导入
        """
        entities = self._ner.extract(text)
        triples = self._re.extract(text, entities)

        entity_map = {}
        for entity in entities:
            existing = self._neo4j.find_nodes(f"^{re.escape(entity.name)}$", entity.entity_type)
            if existing:
                entity_map[entity.entity_id] = existing[0]
            else:
                self._neo4j.create_node(entity)
                entity_map[entity.entity_id] = entity

        for triple in triples:
            head = entity_map.get(triple.head.entity_id)
            tail = entity_map.get(triple.tail.entity_id)
            if head and tail:
                relation = Relation(
                    relation_id=triple.relation.relation_id,
                    relation_type=triple.relation.relation_type,
                    source_id=head.entity_id,
                    target_id=tail.entity_id,
                    confidence=triple.relation.confidence,
                )
                self._neo4j.create_edge(relation)

        self._stats["documents_processed"] += 1
        self._stats["entities_extracted"] += len(entities)
        self._stats["relations_extracted"] += len(triples)

        return {
            "doc_id": doc_id,
            "entities_count": len(entities),
            "relations_count": len(triples),
            "entities": [e.to_dict() for e in entities],
            "triples": [t.to_dict() for t in triples],
        }

    async def query(
        self,
        query_text: str,
        max_hops: int = 2,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """
        图检索查询(D60)。

        支持的查询类型:
            - 实体邻居查询
            - 关系路径查询
            - 竞品分析
        """
        self._stats["queries_executed"] += 1
        entities = self._ner.extract(query_text)

        if not entities:
            return {
                "query": query_text,
                "results": [],
                "message": "未识别到实体",
            }

        all_neighbors = []
        for entity in entities:
            existing = self._neo4j.find_nodes(f"^{re.escape(entity.name)}$", entity.entity_type)
            for node in existing:
                neighbors = self._neo4j.get_neighbors(
                    node.entity_id,
                    max_hops=max_hops,
                )
                all_neighbors.extend([(node, n, path) for n, path in neighbors])

        all_neighbors.sort(key=lambda x: len(x[2]))
        results = []
        seen = set()
        for start, neighbor, path in all_neighbors[:top_k]:
            key = neighbor.entity_id
            if key not in seen:
                results.append({
                    "start_entity": start.to_dict(),
                    "neighbor": neighbor.to_dict(),
                    "path_length": len(path),
                    "path": [r.to_dict() for r in path],
                })
                seen.add(key)

        return {
            "query": query_text,
            "recognized_entities": [e.to_dict() for e in entities],
            "results": results,
            "total": len(results),
        }

    async def get_competitors(self, brand_name: str) -> dict[str, Any]:
        """获取竞品品牌。"""
        brands = self._neo4j.find_nodes(f"^{re.escape(brand_name)}$", EntityType.BRAND)
        if not brands:
            return {"brand": brand_name, "competitors": [], "found": False}

        brand = brands[0]
        neighbors = self._neo4j.get_neighbors(
            brand.entity_id,
            relation_types=[RelationType.COMPETES_WITH],
        )
        competitors = [n for n, path in neighbors if n.entity_type == EntityType.BRAND]

        return {
            "brand": brand_name,
            "competitors": [c.to_dict() for c in competitors],
            "found": True,
        }

    async def get_product_graph(self, product_name: str, max_hops: int = 2) -> dict[str, Any]:
        """获取产品关联图谱。"""
        products = self._neo4j.find_nodes(f"^{re.escape(product_name)}", EntityType.PRODUCT)
        if not products:
            return {"product": product_name, "graph": None, "found": False}

        product = products[0]
        neighbors = self._neo4j.get_neighbors(product.entity_id, max_hops=max_hops)
        node_ids = [product.entity_id] + [n.entity_id for n, _ in neighbors]
        subgraph = self._neo4j.get_subgraph(node_ids)

        return {
            "product": product.to_dict(),
            "graph": subgraph,
            "found": True,
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "neo4j": self._neo4j.get_stats(),
        }
