"""D56-D60 单元测试: GraphRAG知识图谱"""


import pytest
from src.infrastructure.graph_rag import (
    Entity,
    EntityType,
    GraphRAGEngine,
    Neo4jMock,
    NERExtractor,
    Relation,
    RelationExtractor,
    RelationType,
)


class TestEntity:
    """测试实体"""

    def test_entity_creation(self):
        entity = Entity(
            entity_id="pro_001",
            entity_type=EntityType.PRODUCT,
            name="户外储能电源",
        )
        assert entity.entity_id == "pro_001"
        assert entity.entity_type == EntityType.PRODUCT
        assert entity.name == "户外储能电源"

    def test_entity_to_dict(self):
        entity = Entity(
            entity_id="bra_001",
            entity_type=EntityType.BRAND,
            name="EcoFlow",
            properties={"country": "China"},
        )
        d = entity.to_dict()
        assert d["id"] == "bra_001"
        assert d["type"] == "Brand"
        assert d["properties"]["country"] == "China"


class TestRelation:
    """测试关系"""

    def test_relation_creation(self):
        relation = Relation(
            relation_id="rel_001",
            relation_type=RelationType.BRANDED_BY,
            source_id="pro_001",
            target_id="bra_001",
            confidence=0.95,
        )
        assert relation.relation_type == RelationType.BRANDED_BY
        assert relation.confidence == 0.95

    def test_relation_to_dict(self):
        relation = Relation(
            relation_id="rel_001",
            relation_type=RelationType.BELONGS_TO,
            source_id="pro_001",
            target_id="cat_001",
        )
        d = relation.to_dict()
        assert d["type"] == "BELONGS_TO"
        assert d["source"] == "pro_001"


class TestNeo4jMock:
    """测试Neo4j模拟(D56)"""

    def setup_method(self):
        self.neo4j = Neo4jMock()

    def test_create_node(self):
        entity = Entity(entity_id="n1", entity_type=EntityType.PRODUCT, name="测试产品")
        result = self.neo4j.create_node(entity)
        assert result.entity_id == "n1"
        assert len(self.neo4j._nodes) == 1

    def test_create_edge(self):
        self.neo4j.create_node(Entity("n1", EntityType.PRODUCT, "产品A"))
        self.neo4j.create_node(Entity("n2", EntityType.BRAND, "品牌B"))
        relation = Relation("r1", RelationType.BRANDED_BY, "n1", "n2")
        self.neo4j.create_edge(relation)
        assert len(self.neo4j._edges) == 1

    def test_get_node(self):
        self.neo4j.create_node(Entity("n1", EntityType.PRODUCT, "产品"))
        node = self.neo4j.get_node("n1")
        assert node.name == "产品"

    def test_get_nodes_by_type(self):
        self.neo4j.create_node(Entity("n1", EntityType.PRODUCT, "产品A"))
        self.neo4j.create_node(Entity("n2", EntityType.PRODUCT, "产品B"))
        self.neo4j.create_node(Entity("n3", EntityType.BRAND, "品牌"))
        nodes = self.neo4j.get_nodes_by_type(EntityType.PRODUCT)
        assert len(nodes) == 2

    def test_find_nodes(self):
        self.neo4j.create_node(Entity("n1", EntityType.PRODUCT, "户外储能电源"))
        self.neo4j.create_node(Entity("n2", EntityType.PRODUCT, "蓝牙耳机"))
        results = self.neo4j.find_nodes("储能")
        assert len(results) == 1
        assert results[0].name == "户外储能电源"

    def test_get_neighbors_1hop(self):
        self.neo4j.create_node(Entity("p1", EntityType.PRODUCT, "产品"))
        self.neo4j.create_node(Entity("b1", EntityType.BRAND, "品牌"))
        self.neo4j.create_edge(Relation("r1", RelationType.BRANDED_BY, "p1", "b1"))
        neighbors = self.neo4j.get_neighbors("p1", max_hops=1)
        assert len(neighbors) == 1
        assert neighbors[0][0].name == "品牌"

    def test_get_neighbors_2hop(self):
        self.neo4j.create_node(Entity("p1", EntityType.PRODUCT, "产品"))
        self.neo4j.create_node(Entity("b1", EntityType.BRAND, "品牌"))
        self.neo4j.create_node(Entity("c1", EntityType.CATEGORY, "品类"))
        self.neo4j.create_edge(Relation("r1", RelationType.BRANDED_BY, "p1", "b1"))
        self.neo4j.create_edge(Relation("r2", RelationType.BELONGS_TO, "p1", "c1"))
        neighbors = self.neo4j.get_neighbors("p1", max_hops=2)
        assert len(neighbors) == 2

    def test_get_subgraph(self):
        self.neo4j.create_node(Entity("n1", EntityType.PRODUCT, "产品"))
        self.neo4j.create_node(Entity("n2", EntityType.BRAND, "品牌"))
        self.neo4j.create_edge(Relation("r1", RelationType.BRANDED_BY, "n1", "n2"))
        subgraph = self.neo4j.get_subgraph(["n1", "n2"])
        assert len(subgraph["nodes"]) == 2
        assert len(subgraph["edges"]) == 1

    def test_get_stats(self):
        self.neo4j.create_node(Entity("n1", EntityType.PRODUCT, "产品"))
        self.neo4j.create_node(Entity("n2", EntityType.BRAND, "品牌"))
        stats = self.neo4j.get_stats()
        assert stats["node_count"] == 2
        assert "Product" in stats["node_types"]


class TestNERExtractor:
    """测试实体识别(D57)"""

    def setup_method(self):
        self.ner = NERExtractor()

    def test_extract_product(self):
        text = "这款户外储能电源非常适合露营使用"
        entities = self.ner.extract(text)
        product_entities = [e for e in entities if e.entity_type == EntityType.PRODUCT]
        assert len(product_entities) >= 1

    def test_extract_brand(self):
        text = "EcoFlow和Jackery是两个知名品牌"
        entities = self.ner.extract(text)
        brand_entities = [e for e in entities if e.entity_type == EntityType.BRAND]
        assert len(brand_entities) >= 2

    def test_extract_category(self):
        text = "储能设备市场正在快速增长"
        entities = self.ner.extract(text)
        category_entities = [e for e in entities if e.entity_type == EntityType.CATEGORY]
        assert len(category_entities) >= 1

    def test_extract_multiple_types(self):
        text = "EcoFlow户外储能电源属于储能设备品类"
        entities = self.ner.extract(text)
        types = {e.entity_type for e in entities}
        assert EntityType.BRAND in types or EntityType.PRODUCT in types


class TestRelationExtractor:
    """测试关系抽取(D58)"""

    def setup_method(self):
        self.re = RelationExtractor()
        self.ner = NERExtractor()

    def test_extract_branded_by(self):
        text = "EcoFlow户外储能电源是EcoFlow品牌出品的"
        entities = self.ner.extract(text)
        triples = self.re.extract(text, entities)
        branded_triples = [t for t in triples if t.relation.relation_type == RelationType.BRANDED_BY]
        assert len(branded_triples) >= 1

    def test_extract_belongs_to(self):
        text = "户外储能电源属于储能设备品类"
        entities = self.ner.extract(text)
        triples = self.re.extract(text, entities)
        belongs_triples = [t for t in triples if t.relation.relation_type == RelationType.BELONGS_TO]
        assert len(belongs_triples) >= 1

    def test_extract_no_relations(self):
        text = "这是一段无关的文本"
        entities = self.ner.extract(text)
        triples = self.re.extract(text, entities)
        assert len(triples) == 0


class TestGraphRAGEngine:
    """测试GraphRAG引擎(D59-D60)"""

    def setup_method(self):
        self.engine = GraphRAGEngine()

    @pytest.mark.asyncio
    async def test_build_graph(self):
        text = "EcoFlow户外储能电源是EcoFlow品牌出品的储能设备"
        result = await self.engine.build_graph(text)
        assert result["entities_count"] >= 1

    @pytest.mark.asyncio
    async def test_query_with_entity(self):
        text = "EcoFlow户外储能电源是EcoFlow品牌出品的储能设备"
        await self.engine.build_graph(text)
        result = await self.engine.query("EcoFlow的关联产品")
        assert "results" in result

    @pytest.mark.asyncio
    async def test_query_no_entity(self):
        result = await self.engine.query("这是一段没有实体的查询")
        assert "results" in result
        assert len(result["results"]) == 0

    @pytest.mark.asyncio
    async def test_get_competitors(self):
        text = "EcoFlow和Jackery是竞争对手品牌"
        await self.engine.build_graph(text)
        result = await self.engine.get_competitors("EcoFlow")
        assert "competitors" in result

    @pytest.mark.asyncio
    async def test_get_product_graph(self):
        text = "EcoFlow户外储能电源是EcoFlow品牌出品的储能设备"
        await self.engine.build_graph(text)
        result = await self.engine.get_product_graph("EcoFlow")
        assert "graph" in result

    @pytest.mark.asyncio
    async def test_get_stats(self):
        text = "EcoFlow户外储能电源"
        await self.engine.build_graph(text)
        stats = self.engine.get_stats()
        assert stats["documents_processed"] == 1
        assert stats["entities_extracted"] >= 1


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        engine = GraphRAGEngine()

        docs = [
            "EcoFlow户外储能电源是EcoFlow品牌出品的储能设备",
            "Jackery便携电源是Jackery品牌的竞品",
            "Anker蓝牙耳机属于智能音箱品类",
        ]
        for doc in docs:
            await engine.build_graph(doc)

        stats = engine.get_stats()
        assert stats["documents_processed"] == 3

        result = await engine.query("储能电源", max_hops=2)
        assert "results" in result


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
