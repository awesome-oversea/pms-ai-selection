from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from src.core.auth import create_access_token
from src.main import create_app


def _build_headers(*roles: str, user_id: str, username: str) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": username,
            "user_id": user_id,
            "is_superuser": False,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": list(roles),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_bff_create_selection_task_dispatches_background_execution(monkeypatch):
    async def _noop_init_db():
        return None

    async def _healthy_db():
        return {"status": "healthy"}

    async def _healthy_redis():
        return {"status": "healthy"}

    async def _healthy_qdrant():
        return {"status": "healthy"}

    monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
    monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy_db)
    monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy_redis)
    monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant)

    app = create_app()
    captured: dict[str, object] = {}

    class _DummySession:
        async def close(self):
            return None

    async def _fake_session():
        return _DummySession()

    async def _fake_create_task(self, payload, created_by=None, tenant_id=None):
        captured["create"] = {
            "payload": payload,
            "created_by": created_by,
            "tenant_id": tenant_id,
        }
        return {
            "task_id": "task-bff-create-001",
            "query": payload["query"],
            "tenant_id": tenant_id,
            "created_at": "2026-04-21T00:00:00+00:00",
        }

    async def _fake_submit(self, context):
        captured["submit"] = {
            "task_id": context.task_id,
            "tenant_id": context.tenant_id,
            "query": context.query,
            "category": context.category,
            "target_market": context.target_market,
        }

    monkeypatch.setattr("src.api.v1.endpoints.bff._get_db_session", _fake_session)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.create_task", _fake_create_task)
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService.submit_task_for_execution", _fake_submit)
    monkeypatch.setattr(
        "src.api.v1.endpoints.bff.get_settings",
        lambda: SimpleNamespace(selection_execution=SimpleNamespace(enable_api_background_dispatch=True)),
    )

    headers = _build_headers("operator", user_id="00000000-0000-0000-0000-000000000011", username="operator-1")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/bff/workbench/selection/tasks",
            headers=headers,
            json={
                "query": "蓝牙耳机",
                "category": "electronics",
                "target_market": "US",
                "investment_budget": 50000,
                "priority": "high",
                "auto_approve": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "task-bff-create-001"
    assert "已由 API 后台任务启动执行" in payload["message"]
    assert captured["create"]["payload"]["query"] == "蓝牙耳机"
    assert captured["submit"] == {
        "task_id": "task-bff-create-001",
        "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
        "query": "蓝牙耳机",
        "category": "electronics",
        "target_market": "US",
    }


def test_local_selection_main_chain_script_generates_accepted_artifact(tmp_path):
    env = os.environ.copy()
    env.setdefault("SEC_SECRET_KEY", "test-local-selection-main-chain-32chars")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_local_selection_main_chain_acceptance.py",
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
    summary_path = summary_candidates[-1]
    assert summary_path.exists()
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["accepted"] is True
    assert summary_payload["status"] == "passed"
