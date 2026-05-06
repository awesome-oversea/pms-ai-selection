from __future__ import annotations

from fastapi.testclient import TestClient
from src.apps.agent_service import app as agent_app
from src.apps.embedding_service import app as embedding_app
from src.apps.llm_service import app as llm_app
from src.apps.rag_service import app as rag_app


def test_rag_service_health_and_status():
    with TestClient(rag_app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "rag-service"

        status = client.get("/status")
        assert status.status_code == 200
        data = status.json()
        assert data["service"] == "rag-service"
        assert data["deployment"] == "k8s/rag-service.yml"
        assert "knowledge-query" in data["capabilities"]


def test_llm_service_health_and_status():
    with TestClient(llm_app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "llm-service"

        status = client.get("/status")
        assert status.status_code == 200
        data = status.json()
        assert data["service"] == "llm-service"
        assert data["deployment"] == "k8s/llm-service.yml"
        assert "llm-route" in data["capabilities"]


def test_agent_service_health_and_status():
    with TestClient(agent_app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "agent-service"

        status = client.get("/status")
        assert status.status_code == 200
        data = status.json()
        assert data["service"] == "agent-service"
        assert data["deployment"] == "k8s/agent-service.yml"
        assert "agent-orchestration" in data["capabilities"]


def test_embedding_service_health_status_and_embed():
    with TestClient(embedding_app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "embedding-service"

        status = client.get("/status")
        assert status.status_code == 200
        data = status.json()
        assert data["service"] == "embedding-service"
        assert data["deployment"] == "k8s/embedding-service.yml"
        assert "embedding" in data["capabilities"]

        resp = client.post("/embed", json={"texts": ["蓝牙耳机"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "embedding-service"
        assert body["dimension"] == 1024
        assert len(body["vectors"]) == 1
