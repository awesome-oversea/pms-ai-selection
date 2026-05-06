"""
任务 4.2 验收测试：请求速率限制
===============================

验收标准:
- [x] 连续快速发送 11 次 POST /selection/tasks → 第 11 次返回 429
- [x] 正常速率访问不受影响
- [x] 限流中间件已集成到应用
"""

import pytest
from fastapi.testclient import TestClient
from src.core.auth import create_access_token
from src.core.rate_limit import SlidingWindowCounter
from src.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_access_token({"sub": "testuser", "user_id": "test-uid-001"})
    return {"Authorization": f"Bearer {token}"}


class TestSlidingWindowCounter:
    def test_allows_within_limit(self):
        """限制内的请求应被允许。"""
        counter = SlidingWindowCounter(max_calls=5, period_seconds=60)
        for _ in range(5):
            assert counter.is_allowed("client1") is True

    def test_blocks_over_limit(self):
        """超过限制的请求应被拒绝。"""
        counter = SlidingWindowCounter(max_calls=3, period_seconds=60)
        for _ in range(3):
            counter.is_allowed("client1")
        assert counter.is_allowed("client1") is False

    def test_different_keys_independent(self):
        """不同 key 的限制互相独立。"""
        counter = SlidingWindowCounter(max_calls=2, period_seconds=60)
        assert counter.is_allowed("client1") is True
        assert counter.is_allowed("client1") is True
        assert counter.is_allowed("client1") is False
        # client2 不受影响
        assert counter.is_allowed("client2") is True

    def test_remaining_count(self):
        """remaining() 返回正确的剩余次数。"""
        counter = SlidingWindowCounter(max_calls=5, period_seconds=60)
        assert counter.remaining("c1") == 5
        counter.is_allowed("c1")
        assert counter.remaining("c1") == 4


class TestRateLimitMiddleware:
    def test_selection_tasks_rate_limit(self, client, auth_headers):
        """连续 11 次创建任务 → 第 11 次返回 429。"""
        payload = {"query": "限流测试", "category": "test"}

        statuses = []
        for i in range(11):
            resp = client.post(
                "/api/v1/selection/tasks",
                json=payload,
                headers=auth_headers,
            )
            statuses.append(resp.status_code)

        # 前 10 次应成功 (200/201)
        assert all(s in (200, 201) for s in statuses[:10]), \
            f"前10次应成功: {statuses[:10]}"
        # 第 11 次应被限流
        assert statuses[10] == 429, f"第11次应返回429，实际: {statuses[10]}"

    def test_normal_get_not_limited(self, client):
        """正常 GET 请求在全局限制内不受影响。"""
        for _ in range(20):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_429_response_format(self, client, auth_headers):
        """429 响应包含正确的错误格式和 Retry-After 头。"""
        payload = {"query": "限流格式测试", "category": "test"}

        # 先消耗完限额
        for _ in range(10):
            client.post(
                "/api/v1/selection/tasks",
                json=payload,
                headers=auth_headers,
            )

        # 第 11 次触发限流
        resp = client.post(
            "/api/v1/selection/tasks",
            json=payload,
            headers=auth_headers,
        )

        assert resp.status_code == 429
        data = resp.json()
        assert "detail" in data
        assert "RATE_LIMIT_EXCEEDED" in data.get("error_code", "")
        assert "Retry-After" in resp.headers

    def test_middleware_integrated_in_app(self, app):
        """限流中间件已注册在应用中。"""
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "RateLimitMiddleware" in middleware_names
