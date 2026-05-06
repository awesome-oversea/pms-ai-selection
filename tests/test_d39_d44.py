"""D39-D44 单元测试: LLM Gateway + WebSocket + ERP网关 + 报告API"""

import sys

import httpx
import pytest
from src.infrastructure.llm_gateway import (
    CircuitBreaker,
    CircuitState,
    GatewayConfig,
    LLMGateway,
    ModelNode,
    ModelTier,
)
from src.infrastructure.ws_gateway import (
    ERPGateway,
    ERPSyncEvent,
    WebSocketManager,
    WSMessage,
    WSMessageType,
)


class TestModelNode:
    """测试ModelNode"""

    def test_node_creation(self):
        node = ModelNode(
            node_id="test_1",
            model_name="Qwen2.5-1.5B",
            tier=ModelTier.HEAVY,
        )
        assert node.node_id == "test_1"
        assert node.model_name == "Qwen2.5-1.5B"
        assert node.healthy is True
        assert node.request_count == 0

    def test_error_rate_calc(self):
        node = ModelNode(node_id="n1", model_name="M1", tier=ModelTier.LIGHT)
        node.request_count = 10
        node.error_count = 2
        assert node.error_rate == 0.2

    def test_error_rate_zero_requests(self):
        node = ModelNode(node_id="n1", model_name="M1", tier=ModelTier.LIGHT)
        assert node.error_rate == 0.0


class TestCircuitBreaker:
    """测试熔断器(D40)"""

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_record_success(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.successes == 1
        assert cb.state == CircuitState.CLOSED

    def test_record_failure(self):
        cb = CircuitBreaker()
        for _ in range(15):
            cb.record_failure()
        assert cb.failures > 0
        assert cb.state == CircuitState.OPEN

    def test_open_blocks_requests(self):
        cb = CircuitBreaker()
        cb.state = CircuitState.OPEN
        assert cb.allow_request() is False

    def test_half_open_allows_probes(self):
        cb = CircuitBreaker()
        cb.state = CircuitState.HALF_OPEN
        assert cb.allow_request() is True
        cb.record_success()
        assert cb.allow_request() is True
        cb.record_success()
        assert cb.allow_request() is True
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_success_closes(self):
        cb = CircuitBreaker()
        cb.state = CircuitState.HALF_OPEN
        for _ in range(cb.half_open_max_probes):
            cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestLLMGateway:
    """测试LLM Gateway(D39-D40)"""

    def setup_method(self):
        self.gateway = LLMGateway()

    def test_gateway_initialization(self):
        assert len(self.gateway._nodes) == 4

    def test_cluster_has_heavy_nodes(self):
        heavy_nodes = [n for n in self.gateway._nodes if n.tier == ModelTier.HEAVY]
        assert len(heavy_nodes) == 2

    def test_cluster_has_light_node(self):
        light_nodes = [n for n in self.gateway._nodes if n.tier == ModelTier.LIGHT]
        assert len(light_nodes) == 1

    def test_cluster_has_filter_node(self):
        filter_nodes = [n for n in self.gateway._nodes if n.tier == ModelTier.FILTER]
        assert len(filter_nodes) == 1

    def test_complexity_estimation_heavy(self):
        tier, tokens = self.gateway._estimate_complexity("请详细分析蓝牙耳机市场的竞争格局和未来发展趋势")
        assert tier == ModelTier.HEAVY

    def test_complexity_estimation_light(self):
        tier, tokens = self.gateway._estimate_complexity("什么是蓝牙耳机")
        assert tier == ModelTier.LIGHT

    def test_complexity_estimation_filter(self):
        tier, tokens = self.gateway._estimate_complexity("请进行敏感词过滤检测")
        assert tier == ModelTier.FILTER

    def test_select_node_returns_node(self):
        node = self.gateway._select_node(ModelTier.LIGHT)
        assert node is not None
        assert node.tier == ModelTier.LIGHT

    def test_select_node_load_balancing(self):
        for _ in range(10):
            node = self.gateway._select_node(ModelTier.HEAVY)
            if node:
                node.request_count += 1
        heavy_nodes = [n for n in self.gateway._nodes if n.tier == ModelTier.HEAVY]
        counts = [n.request_count for n in heavy_nodes]
        assert max(counts) - min(counts) <= 2

    @pytest.mark.asyncio
    async def test_route_basic(self):
        result = await self.gateway.route("测试查询")
        assert result.response != ""
        assert result.tokens_used > 0
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_route_force_tier(self):
        result = await self.gateway.route("简单问题", force_tier=ModelTier.HEAVY)
        assert result.tier == ModelTier.HEAVY.value

    @pytest.mark.asyncio
    async def test_route_cost_calculation(self):
        result = await self.gateway.route("分析市场趋势")
        assert result.cost_usd >= 0

    def test_get_cluster_status(self):
        status = self.gateway.get_cluster_status()
        assert status["total_nodes"] == 4
        assert "nodes" in status
        assert "circuit_breakers" in status

    @pytest.mark.asyncio
    async def test_get_route_stats(self):
        for _ in range(5):
            await self.gateway.route("测试")
        stats = self.gateway.get_route_stats()
        assert stats["sample_size"] == 5
        assert "avg_latency_ms" in stats

    @pytest.mark.asyncio
    async def test_call_vllm_real_uses_openai_payload(self, monkeypatch):
        gateway = LLMGateway(GatewayConfig(
            use_mock=False,
            provider_mode="real",
            vllm_endpoint="http://llm.local/v1",
            api_key="secret-token",
            api_model_name="qwen-test",
        ))
        node = gateway._nodes[0]
        captured: dict[str, object] = {}

        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [{"message": {"content": "真实响应"}}],
                    "usage": {"total_tokens": 321},
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                captured["timeout"] = kwargs.get("timeout")

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json=None, headers=None):
                captured["url"] = url
                captured["json"] = json
                captured["headers"] = headers
                return _Response()

        monkeypatch.setattr("src.infrastructure.llm_gateway.httpx.AsyncClient", _Client)

        content, tokens, timed_out = await gateway._call_vllm_real(node, "请分析市场", 12.5)

        assert timed_out is False
        assert content == "真实响应"
        assert tokens == 321
        assert captured["url"] == "http://llm.local/v1/chat/completions"
        assert captured["json"]["model"] == "qwen-test"
        assert captured["json"]["messages"][1]["content"] == "请分析市场"
        assert captured["headers"]["Authorization"] == "Bearer secret-token"

    @pytest.mark.asyncio
    async def test_degrade_to_ollama_real_calls_generate_api(self, monkeypatch):
        gateway = LLMGateway(GatewayConfig(
            use_mock=False,
            provider_mode="real",
            ollama_endpoint="http://ollama.local:11434",
        ))
        captured: dict[str, object] = {}

        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"response": "降级成功", "eval_count": 88}

        class _Client:
            def __init__(self, *args, **kwargs):
                captured["timeout"] = kwargs.get("timeout")

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json=None):
                captured["url"] = url
                captured["json"] = json
                return _Response()

        monkeypatch.setattr("src.infrastructure.llm_gateway.httpx.AsyncClient", _Client)

        content, tokens = await gateway._degrade_to_ollama_real("请降级处理")

        assert content == "降级成功"
        assert tokens == 88
        assert captured["url"] == "http://ollama.local:11434/api/generate"
        assert captured["json"]["prompt"] == "请降级处理"
        assert captured["json"]["stream"] is False

    @pytest.mark.asyncio
    async def test_call_vllm_real_retries_and_records_failure(self, monkeypatch):
        gateway = LLMGateway(GatewayConfig(
            use_mock=False,
            provider_mode="real",
            vllm_endpoint="http://llm.local/v1",
            retry_count=1,
        ))
        node = gateway._nodes[0]
        attempts = {"count": 0}

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json=None, headers=None):
                attempts["count"] += 1
                request = httpx.Request("POST", url)
                response = httpx.Response(500, request=request)
                raise httpx.HTTPStatusError("boom", request=request, response=response)

        monkeypatch.setattr("src.infrastructure.llm_gateway.httpx.AsyncClient", lambda *args, **kwargs: _Client())

        content, tokens, timed_out = await gateway._call_vllm_real(node, "请分析失败重试", 5.0)

        assert attempts["count"] == 2
        assert timed_out is True
        assert content == ""
        assert tokens == 0
        assert node.error_count == 1
        assert gateway._circuit_breakers[node.node_id].failures == 1


class TestWebSocketManager:
    """测试WebSocket管理器(D42)"""

    def setup_method(self):
        self.manager = WebSocketManager()

    @pytest.mark.asyncio
    async def test_connect(self):
        conn = await self.manager.connect("conn_1", "task_123")
        assert conn.conn_id == "conn_1"
        assert conn.task_id == "task_123"

    @pytest.mark.asyncio
    async def test_disconnect(self):
        await self.manager.connect("conn_1")
        await self.manager.disconnect("conn_1")
        assert "conn_1" not in self.manager._connections

    @pytest.mark.asyncio
    async def test_subscribe_task(self):
        await self.manager.connect("conn_1")
        await self.manager.subscribe("conn_1", "task_999")
        assert "conn_1" in self.manager._task_subscribers.get("task_999", set())

    @pytest.mark.asyncio
    async def test_send_agent_status(self):
        await self.manager.connect("conn_1", "task_123")
        count = await self.manager.send_agent_status(
            task_id="task_123",
            agent_name="DataCollectionAgent",
            status="running",
            progress=0.5,
            step_name="collecting",
        )
        assert count >= 1

    @pytest.mark.asyncio
    async def test_send_task_progress(self):
        await self.manager.connect("conn_1", "task_123")
        count = await self.manager.send_task_progress(
            task_id="task_123",
            phase="analysis",
            progress_pct=75.0,
            message="正在分析数据",
        )
        assert count >= 1

    @pytest.mark.asyncio
    async def test_heartbeat(self):
        await self.manager.connect("conn_1")
        result = await self.manager.heartbeat("conn_1")
        assert result is True

    @pytest.mark.asyncio
    async def test_heartbeat_unknown_conn(self):
        result = await self.manager.heartbeat("unknown")
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast(self):
        await self.manager.connect("conn_1")
        await self.manager.connect("conn_2")
        msg = WSMessage(msg_type=WSMessageType.SYSTEM_NOTIFICATION, payload={"msg": "test"})
        count = await self.manager.broadcast(msg)
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_status(self):
        await self.manager.connect("conn_1")
        await self.manager.connect("conn_2")
        status = self.manager.get_status()
        assert status["total_connections"] == 2


class TestERPGateway:
    """测试ERP集成网关(D42)"""

    def setup_method(self):
        self.gateway = ERPGateway()

    def test_supported_systems(self):
        assert "SCM" in self.gateway.SUPPORTED_SYSTEMS
        assert "OMS" in self.gateway.SUPPORTED_SYSTEMS
        assert "WMS" in self.gateway.SUPPORTED_SYSTEMS

    @pytest.mark.asyncio
    async def test_scm_adapter(self):
        event = ERPSyncEvent(
            event_type="po_create",
            source_system="FMS",
            target_system="SCM",
            data={"supplier_id": "SUP-12345"},
        )
        result = await self.gateway.sync(event)
        assert result["success"] is True
        assert "po_number" in result["result"]

    @pytest.mark.asyncio
    async def test_oms_adapter(self):
        event = ERPSyncEvent(
            event_type="order_sync",
            source_system="FMS",
            target_system="OMS",
            data={"order_id": "ORD-123456"},
        )
        result = await self.gateway.sync(event)
        assert result["success"] is True
        assert result["result"]["system"] == "OMS"

    @pytest.mark.asyncio
    async def test_wms_adapter(self):
        event = ERPSyncEvent(
            event_type="inventory_update",
            source_system="FMS",
            target_system="WMS",
            data={"sku": "SKU-12345", "quantity_change": 100},
        )
        result = await self.gateway.sync(event)
        assert result["success"] is True
        assert result["result"]["system"] == "WMS"

    @pytest.mark.asyncio
    async def test_unsupported_system(self):
        event = ERPSyncEvent(
            event_type="test",
            source_system="FMS",
            target_system="UNKNOWN",
            data={},
        )
        result = await self.gateway.sync(event)
        assert result["success"] is False
        assert "不支持" in result["error"]

    def test_create_selection_sync_event(self):
        events = self.gateway.create_selection_sync_event(
            task_id="task_123",
            product_data={"product_name": "TestProduct"},
            target_systems=["SCM", "OMS"],
        )
        assert len(events) == 2
        assert events[0].target_system == "SCM"
        assert events[1].target_system == "OMS"

    def test_get_status(self):
        status = self.gateway.get_status()
        assert "supported_systems" in status
        assert "registered_adapters" in status


class TestWSMessage:
    """测试WS消息"""

    def test_message_creation(self):
        msg = WSMessage(
            msg_type=WSMessageType.AGENT_STATUS,
            payload={"agent": "test"},
        )
        assert msg.msg_type == WSMessageType.AGENT_STATUS
        assert msg.payload["agent"] == "test"

    def test_message_to_json(self):
        msg = WSMessage(
            msg_type=WSMessageType.TASK_PROGRESS,
            payload={"progress": 50},
        )
        json_str = msg.to_json()
        assert "task_progress" in json_str
        assert "progress" in json_str


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        gateway = LLMGateway()
        ws_manager = WebSocketManager()
        erp_gateway = ERPGateway()

        await ws_manager.connect("conn_1", "task_999")

        result = await gateway.route("分析蓝牙耳机市场趋势")
        assert result.response != ""

        await ws_manager.send_agent_status(
            task_id="task_999",
            agent_name="MarketInsightAgent",
            status="completed",
            progress=1.0,
        )

        events = erp_gateway.create_selection_sync_event(
            task_id="task_999",
            product_data={"category": "bluetooth_earbuds"},
        )
        assert len(events) > 0

        ws_status = ws_manager.get_status()
        assert ws_status["total_connections"] == 1


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
