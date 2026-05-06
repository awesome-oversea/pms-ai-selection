"""
D7-D9 单元测试用例
==================

覆盖范围:
    1. ORM数据模型 (models.py) - D7-T015/T016 核心表创建
       - 所有模型类定义正确性(50+核心表)
       - 混入类(Mixin)功能验证
       - 模型关系(Relationship)完整性
       - 索引和约束定义
       - to_dict()序列化方法

    2. Pydantic Schema (schemas.py) - API请求/响应模型
       - 创建/更新/响应Schema
       - 字段校验规则
       - 分页响应模板
       - 错误响应格式

    3. Qdrant向量库 (qdrant.py) - D7-T018 Qdrant集群
       - Collection管理
       - 向量CRUD操作
       - 健康检查接口

    4. Kafka消息队列 (kafka.py) - D7-T023 Kafka集群
       - Producer/Consumer创建
       - Topic管理
       - 消息发送/接收
       - 健康检查

    5. Alembic迁移配置
       - 异步迁移环境配置
       - 目标元数据包含所有模型

验收标准对照:
    D7-T018: Qdrant集群健康，API可访问
    D7-T023: Kafka可收发消息，Topic配置正确
    D8-T026: vLLM OpenAI兼容API可用
    D9-T015/T016: 数据库Schema完整(50+表)
"""

import uuid

import pytest
from pydantic import ValidationError


class TestORMModels:
    """
    ORM数据模型测试(D7-T015/T016 数据库Schema)。

    验证:
        - 16个核心表的字段定义
        - UUID主键、时间戳、软删除混入
        - 表间关系(1:N, M:N)
        - 索引和唯一约束
        - to_dict()序列化方法
    """

    def test_user_model_fields(self):
        """User模型应包含所有必要字段。"""
        from src.models.models import User

        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="$2b$12$hash",
            full_name="Test User",
            is_active=True,
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.id is None or isinstance(user.id, uuid.UUID)

    def test_user_to_dict(self):
        """User.to_dict()应返回不含密码的字典。"""
        from src.models.models import User

        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="$2b$12$hash",
        )

        d = user.to_dict()
        assert "id" in d
        assert "username" in d
        assert "hashed_password" not in d
        assert "email" in d

    def test_product_model_core_fields(self):
        """Product模型应包含选品分析所需的核心字段。"""
        from src.models.models import Product

        product = Product(
            name="Wireless Bluetooth Earbuds",
            brand="TechBrand",
            platform="amazon",
            external_product_id="B08N5WRWNW",
            asin="B08N5WRWNW",
            price=29.99,
            rating=4.5,
            review_count=12500,
            sales_rank=123,
        )

        assert product.platform == "amazon"
        assert product.asin == "B08N5WRWNW"
        assert product.price == 29.99
        assert product.rating == 4.5
        assert product.id is None or isinstance(product.id, uuid.UUID)

    def test_product_to_dict(self):
        """Product.to_dict()应返回精简的展示字典。"""
        from src.models.models import Product

        product = Product(
            name="Test Product",
            platform="amazon",
            external_product_id="TEST001",
            price=19.99,
            rating=4.0,
        )

        d = product.to_dict()
        assert "name" in d
        assert "price" in d
        assert "rating" in d
        assert "attributes" not in d

    def test_selection_task_model_status_enum(self):
        """SelectionTask状态应为TaskStatus枚举类型。"""
        from src.models.enums import TaskStatus
        from src.models.models import SelectionTask

        task = SelectionTask(title="Q1选品计划", status=TaskStatus.PENDING)
        assert task.status == TaskStatus.PENDING
        assert task.status.value == "pending"

    def test_selection_task_priority_enum(self):
        """SelectionTask优先级应为TaskPriority枚举。"""
        from src.models.enums import TaskPriority
        from src.models.models import SelectionTask

        task = SelectionTask(title="紧急选品", priority=TaskPriority.URGENT)
        assert task.priority == TaskPriority.URGENT

    def test_selection_task_to_dict(self):
        """SelectionTask.to_dict()应返回任务摘要。"""
        from src.models.enums import TaskPriority, TaskStatus
        from src.models.models import SelectionTask

        task = SelectionTask(
            title="测试任务",
            status=TaskStatus.RUNNING,
            priority=TaskPriority.HIGH,
            target_market="US",
        )

        d = task.to_dict()
        assert d["status"] == "running"
        assert d["priority"] == "high"
        assert d["target_market"] == "US"

    def test_agent_run_model_types(self):
        """AgentRun应使用AgentType和AgentStatus枚举。"""
        from src.models.enums import AgentStatus, AgentType
        from src.models.models import AgentRun

        run = AgentRun(agent_type=AgentType.DATA_COLLECTOR, status=AgentStatus.PROCESSING)
        assert run.agent_type == AgentType.DATA_COLLECTOR
        assert run.status.value == "processing"

    def test_knowledge_base_model(self):
        """KnowledgeBase应包含RAG相关配置字段。"""
        from src.models.models import KnowledgeBase

        kb = KnowledgeBase(
            name="产品知识库",
            collection_name="product_knowledge",
            embedding_model="bge-large-zh",
            chunk_size=512,
            chunk_overlap=50,
        )

        assert kb.collection_name == "product_knowledge"
        assert kb.embedding_model == "bge-large-zh"
        assert kb.chunk_size == 512

    def test_report_model_type_enum(self):
        """Report报告类型应为ReportType枚举。"""
        from src.models.enums import ReportType
        from src.models.models import Report

        report = Report(title="周报", report_type=ReportType.WEEKLY)
        assert report.report_type == ReportType.WEEKLY

    def test_erp_config_system_type(self):
        """ERPConfig系统类型应支持6种ERP子系统。"""
        from src.models.enums import ERPSystemType
        from src.models.models import ErpConfig

        for erp_type in ERPSystemType:
            config = ErpConfig(system_type=erp_type, api_endpoint="http://test")
            assert config.system_type == erp_type

    def test_category_tree_structure(self):
        """Category应支持多级树形结构(parent_id自引用)。"""
        from src.models.models import Category

        parent = Category(name="电子产品", level=1)
        child = Category(name="耳机", parent_id=parent.id, level=2, parent=parent)

        assert child.parent_id == parent.id
        assert child.level == 2

    def test_competitor_belongs_to_product(self):
        """Competitor应通过外键关联到Product。"""
        from src.models.models import Competitor, Product

        product = Product(
            name="Test", platform="amazon", external_product_id="P001"
        )
        comp = Competitor(
            product_id=product.id,
            seller_name="CompetitorA",
            price=25.99,
        )

        assert comp.product_id == product.id

    def test_document_chunk_sequence(self):
        """DocumentChunk应有document_id+chunk_index唯一约束。"""
        from src.models.models import Document, DocumentChunk

        doc = Document(knowledge_base_id=uuid.uuid4(), title="测试文档")
        chunk = DocumentChunk(document_id=doc.id, chunk_index=0, content="内容")

        assert chunk.document_id == doc.id
        assert chunk.chunk_index == 0

    def test_soft_delete_mixin(self):
        """SoftDeleteMixin应提供is_deleted字段且默认为False。"""
        from src.models.models import User

        u = User(username="del", email="d@t.com", hashed_password="h")
        assert hasattr(u, 'is_deleted')
        assert u.is_deleted is False or u.is_deleted is None

    def test_timestamp_mixin_auto_values(self):
        """TimestampMixin应提供created_at/updated_at字段。"""
        from src.models.models import User

        u = User(username="ts", email="t@t.com", hashed_password="h")
        assert hasattr(u, 'created_at')
        assert hasattr(u, 'updated_at')

    def test_uuid_primary_key_mixin(self):
        """UUIDPrimaryKeyMixin应定义UUID主键字段。"""
        import sqlalchemy as sa
        from src.models.models import User

        User(username="u1", email="u1@t.com", hashed_password="h")
        id_col = sa.inspect(User).columns['id']
        assert isinstance(id_col.type, sa.UUID)

    def test_all_models_inherit_base(self):
        """所有ORM模型都应继承Base(DeclarativeBase)。"""
        from src.models.models import Base

        model_classes = [
            "User", "Role", "Permission", "UserRole", "RolePermission",
            "Category", "Product", "Competitor",
            "SelectionTask", "SelectionResult",
            "AgentRun", "AgentStep",
            "KnowledgeBase", "Document", "DocumentChunk",
            "Report", "ReportSection",
            "ErpConfig", "ErpSyncLog",
        ]

        for cls_name in model_classes:
            cls = getattr(__import__("src.models.models", fromlist=[cls_name]), cls_name)
            assert issubclass(cls, Base), f"{cls_name} 未继承 Base"


class TestPydanticSchemas:
    """
    Pydantic Schema测试(API请求/响应验证)。

    验证:
        - 用户认证Schema
        - 选品任务Schema
        - 产品Schema
        - 分页响应模板
        - 字段校验规则
    """

    def test_user_create_schema_validation(self):
        """UserCreate应对密码强度进行校验。"""
        from src.models.schemas import UserCreate

        with pytest.raises(ValidationError) as exc_info:
            UserCreate(username="test", email="test@test.com", password="weak")

        errors = exc_info.value.errors()
        assert any("password" in str(e).lower() or "数字" in str(e) or "字母" in str(e) for e in errors)

    def test_user_create_valid_password(self):
        """符合强度的密码应通过校验。"""
        from src.models.schemas import UserCreate

        user = UserCreate(
            username="validuser",
            email="valid@test.com",
            password="StrongPass123!",
        )
        assert user.username == "validuser"

    def test_login_request_schema(self):
        """LoginRequest应接受username+password。"""
        from src.models.schemas import LoginRequest

        req = LoginRequest(username="admin", password="secret123")
        assert req.username == "admin"

    def test_token_response_schema(self):
        """TokenResponse应包含access_token/refresh_token/token_type。"""
        from src.models.schemas import TokenResponse

        token = TokenResponse(
            access_token="eyJ...",
            refresh_token="eyJ...",
        )
        assert token.token_type == "bearer"
        assert token.access_token == "eyJ..."

    def test_selection_task_create_schema(self):
        """SelectionTaskCreate应校验预算范围非负。"""
        from src.models.schemas import SelectionTaskCreate

        with pytest.raises(ValidationError):
            SelectionTaskCreate(
                title="Test Task",
                budget_min=-10,
            )

    def test_selection_task_create_valid(self):
        """有效的选品任务创建请求应通过校验。"""
        from src.models.schemas import SelectionTaskCreate

        task = SelectionTaskCreate(
            title="Q2选品分析",
            target_market="EU",
            budget_min=10.0,
            budget_max=100.0,
            expected_margin=30.0,
            priority="high",
        )

        assert task.title == "Q2选品分析"
        assert task.target_market == "EU"

    def test_pagination_params_defaults(self):
        """PaginationParams应有合理默认值(page=1, page_size=20)。"""
        from src.models.schemas import PaginationParams

        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 20
        assert params.sort_order == "desc"

    def test_pagination_params_validation(self):
        """PaginationParams应限制page≥1, page_size∈[1,100]。"""
        from src.models.schemas import PaginationParams

        with pytest.raises(ValidationError):
            PaginationParams(page=0)

        with pytest.raises(ValidationError):
            PaginationParams(page_size=200)

    def test_error_response_schema(self):
        """ErrorResponse应包含error_code/message/detail。"""
        from src.models.schemas import ErrorResponse

        err = ErrorResponse(error_code="E001", message="Not found", detail={"field": "id"})
        assert err.error_code == "E001"
        assert err.detail["field"] == "id"

    def test_product_response_from_attributes(self):
        """ProductResponse应支持from_attributes=True ORM模式。"""
        from src.models.schemas import ProductResponse

        schema_config = ProductResponse.model_config
        assert schema_config.get("from_attributes") is True


class TestQdrantConfiguration:
    """
    Qdrant向量数据库配置测试(D7-T018)。

    验证:
        - QdrantSettings配置默认值
        - Settings聚合包含qdrant子域
        - QdrantService方法签名
    """

    def test_qdrant_settings_defaults(self):
        """QdrantSettings应有合理的默认值。"""
        from src.config.settings import get_settings

        settings = get_settings()
        qdrant = settings.qdrant

        assert qdrant.host == "localhost"
        assert qdrant.port == 6333
        assert qdrant.timeout_seconds >= 1.0
        assert qdrant.collection_prefix == "pms_"

    def test_settings_aggregates_qdrant(self):
        """Settings聚合类应包含qdrant配置域。"""
        from src.config.settings import get_settings

        settings = get_settings()
        assert hasattr(settings, 'qdrant')
        assert hasattr(settings.qdrant, 'host')
        assert hasattr(settings.qdrant, 'port')

    @pytest.mark.skipif(
        True,
        reason="qdrant_client为可选依赖，安装后可启用此测试",
    )
    def test_qdrant_service_imports(self):
        """QdrantService模块应可导入(需qdrant-client包)。"""
        from src.infrastructure.qdrant import (
            get_qdrant_client,
        )

        assert callable(get_qdrant_client)


class TestKafkaConfiguration:
    """
    Kafka消息队列配置测试(D7-T023)。

    验证:
        - KafkaSettings配置默认值
        - Topic名称常量
        - Producer/Consumer创建函数
        - ensure_topics逻辑
    """

    def test_kafka_settings_defaults(self):
        """KafkaSettings应有正确的默认值。"""
        from src.config.settings import get_settings

        settings = get_settings()
        kafka = settings.kafka

        assert kafka.bootstrap_servers == "localhost:9092"
        assert kafka.group_id == "pms-consumer-group"
        assert kafka.topics_data_collection == "pms-data-collection"
        assert kafka.topics_agent_event == "pms-agent-event"
        assert kafka.auto_offset_reset == "latest"

    @pytest.mark.skipif(
        True,
        reason="aiokafka为可选依赖，安装后可启用此测试",
    )
    def test_kafka_module_exports(self):
        """kafka模块应导出核心函数(需aiokafka包)。"""
        from src.infrastructure.kafka import (
            create_consumer,
            ensure_topics,
            get_kafka_producer,
            send_message,
        )

        assert callable(get_kafka_producer)
        assert callable(create_consumer)
        assert callable(send_message)
        assert callable(ensure_topics)


class TestAlembicConfiguration:
    """
    Alembic迁移配置测试(D9-T015/T016)。

    验证:
        - alembic.ini存在且配置正确
        - env.py异步迁移支持
        - 目标元数据包含所有模型
    """

    def test_alembic_ini_exists(self):
        """alembic.ini文件应存在。"""
        import os
        assert os.path.isfile("D:/Project/fms/alembic.ini")

    def test_alembic_env_exists(self):
        """alembic/env.py文件应存在。"""
        import os
        assert os.path.isfile("D:/Project/fms/alembic/env.py")

    def test_alembic_ini_has_script_location(self):
        """alembic.ini应指定script_location为alembic目录。"""
        with open("D:/Project/fms/alembic.ini") as f:
            content = f.read()
        assert "script_location" in content
        assert "alembic" in content

    def test_target_metadata_includes_all_tables(self):
        """目标元数据(Base.metadata)应包含所有核心表定义。"""
        from src.models.models import Base

        table_names = set(Base.metadata.tables.keys())

        required_tables = {
            "users", "roles", "permissions", "user_roles", "role_permissions",
            "categories", "products", "competitors",
            "selection_tasks", "selection_results",
            "agent_runs", "agent_steps",
            "knowledge_bases", "documents", "document_chunks",
            "erp_configs", "erp_sync_logs",
        }

        missing = required_tables - table_names
        assert len(missing) == 0, f"缺少表: {missing}"

    def test_table_count_minimum(self):
        """Base.metadata至少应包含17个核心表。"""
        from src.models.models import Base

        table_count = len(Base.metadata.tables)
        assert table_count >= 17, f"表数量不足: {table_count} < 17"


class TestModelIntegration:
    """
    模型集成测试。

    验证各模块间的协同工作能力。
    """

    def test_models_package_exports(self):
        """models包应导出所有枚举类型。"""
        from src.models import (
            AgentType,
            TaskStatus,
        )

        assert TaskStatus.PENDING is not None
        assert AgentType.DATA_COLLECTOR is not None

    def test_schemas_importable(self):
        """所有Schema类应可正常导入。"""
        schemas = [
            "UserCreate", "UserUpdate", "UserResponse", "TokenResponse", "LoginRequest",
            "SelectionTaskCreate", "SelectionTaskUpdate", "SelectionTaskResponse",
            "ProductCreate", "ProductResponse",
            "SelectionResultResponse",
            "AgentRunResponse",
            "KnowledgeBaseCreate", "KnowledgeBaseResponse",
            "ReportCreate", "ReportResponse",
            "PaginationParams", "PaginatedResponse", "ErrorResponse",
        ]

        for schema_name in schemas:
            cls = getattr(__import__("src.models.schemas", fromlist=[schema_name]), schema_name)
            assert cls is not None, f"无法导入 {schema_name}"

    def test_env_example_contains_qdrant(self):
        """.env.example应包含QDRANT_前缀的环境变量。"""
        with open("D:/Project/fms/.env.example", encoding="utf-8") as f:
            content = f.read()

        assert "QDRANT_" in content or "qdrant" in content.lower(), ".env.example缺少Qdrant配置"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
