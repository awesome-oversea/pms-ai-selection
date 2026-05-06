from __future__ import annotations

from typing import Any

from src.config.settings import get_settings
from src.services.service_gateway import get_service_gateway


class ServiceSplitStatusService:
    def build_status(self) -> dict[str, Any]:
        settings = get_settings().service_mode
        gateway = get_service_gateway().build_status()
        services = {
            "rag": {
                "mode": settings.rag_mode,
                "base_url": settings.rag_base_url,
                "timeout_seconds": settings.rag_timeout_seconds,
                "fallback_enabled": settings.enable_fallback,
                "gateway": gateway["rag"],
                "deployment": {
                    "manifest": "k8s/rag-service.yml",
                    "service_name": "pms-rag-service",
                    "health_path": "/health",
                    "status_path": "/status",
                },
            },
            "llm": {
                "mode": settings.llm_mode,
                "base_url": settings.llm_base_url,
                "timeout_seconds": settings.llm_timeout_seconds,
                "fallback_enabled": settings.enable_fallback,
                "gateway": gateway["llm"],
                "deployment": {
                    "manifest": "k8s/llm-service.yml",
                    "service_name": "pms-llm-service",
                    "health_path": "/health",
                    "status_path": "/status",
                },
            },
            "agent": {
                "mode": settings.agent_mode,
                "base_url": settings.agent_base_url,
                "timeout_seconds": settings.agent_timeout_seconds,
                "fallback_enabled": settings.enable_fallback,
                "deployment": {
                    "manifest": "k8s/agent-service.yml",
                    "service_name": "pms-agent-service",
                    "health_path": "/health",
                    "status_path": "/status",
                },
            },
            "embedding": {
                "mode": settings.embedding_mode,
                "base_url": settings.embedding_base_url,
                "timeout_seconds": settings.embedding_timeout_seconds,
                "fallback_enabled": settings.enable_fallback,
                "deployment": {
                    "manifest": "k8s/embedding-service.yml",
                    "service_name": "pms-embedding-service",
                    "health_path": "/health",
                    "status_path": "/status",
                },
            },
            "strategy": {
                "compatibility_mode": "dual-path",
                "fallback_policy": "remote-service -> in-process",
                "gray_release": True,
                "rollback": "switch service_mode back to in-process",
                "bounded_capabilities": ["llm", "rag", "agent", "embedding"],
            },
        }
        services["independent_services"] = [
            {
                "key": key,
                "app": f"src.apps.{key}_service:app",
                "uvicorn_command": f"python -m uvicorn src.apps.{key}_service:app --host 0.0.0.0 --port {port}",
                "health_path": "/health",
                "status_path": "/status",
                "manifest": services[key]["deployment"]["manifest"],
            }
            for key, port in [("rag", 8101), ("llm", 8102), ("agent", 8103), ("embedding", 8104)]
        ]
        services["health_checks"] = {
            key: {"path": services[key]["deployment"]["health_path"], "ready": True}
            for key in ["rag", "llm", "agent", "embedding"]
        }
        services["rollback_plan"] = {
            "strategy": "environment-switch",
            "steps": [
                "set SERVICE_MODE_<SERVICE>_MODE=in-process",
                "restart affected deployment",
                "verify /health and /status",
            ],
            "ready": True,
        }
        services["llm_service"] = services["llm"]
        services["rag_service"] = services["rag"]
        services["agent_service"] = services["agent"]
        services["embedding_service"] = services["embedding"]
        return services
