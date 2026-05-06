from __future__ import annotations

from typing import Any

from src.core.metrics import INFERENCE_ROUTE_HEALTH
from src.services.gpu_resource_pool_service import GPUResourcePoolService
from src.services.ollama_status_service import OllamaStatusService
from src.services.triton_status_service import TritonStatusService
from src.services.vllm_status_service import VLLMStatusService


class InferenceHealthService:
    LATENCY_THRESHOLDS_MS = {"vllm": 3000.0, "triton": 100.0, "ollama": 5000.0}

    @classmethod
    def _estimate_latency_ms(cls, name: str, status: dict[str, Any]) -> float | None:
        if name == "vllm":
            cluster = status.get("cluster") or {}
            nodes = cluster.get("nodes") or []
            latencies = [float(node.get("avg_latency_ms") or 0.0) for node in nodes if float(node.get("avg_latency_ms") or 0.0) > 0]
            return max(latencies) if latencies else None
        if name == "triton":
            probe = status.get("runtime_probe") or {}
            for key in ("latency_ms", "avg_latency_ms", "p95_latency_ms"):
                value = probe.get(key)
                if value is not None:
                    return float(value)
            return None
        if name == "ollama":
            runtime = status.get("runtime") or {}
            value = runtime.get("latency_ms")
            return float(value) if value is not None else None
        return None

    @staticmethod
    def _build_route(name: str, *, ready: bool, degraded: bool, latency_ms: float | None, heartbeat_ok: bool, gpu_blocked: bool = False, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        threshold = InferenceHealthService.LATENCY_THRESHOLDS_MS.get(name)
        alerts: list[dict[str, Any]] = []
        if gpu_blocked:
            alerts.append({"severity": "high", "code": "gpu_blocked", "message": "gpu resource pool marked route as blocked"})
        if latency_ms is not None and threshold is not None and latency_ms > threshold:
            alerts.append({"severity": "high", "code": "latency_threshold_exceeded", "message": f"latency {latency_ms}ms > threshold {threshold}ms"})
        auto_evicted = gpu_blocked or not heartbeat_ok or not ready or (latency_ms is not None and threshold is not None and latency_ms > threshold)
        status = "healthy"
        if auto_evicted:
            status = "evicted"
        elif degraded:
            status = "degraded"
        metric_value = 0.0 if auto_evicted else (0.5 if degraded else 1.0)
        INFERENCE_ROUTE_HEALTH.labels(route=name).set(metric_value)
        return {
            "ready": ready,
            "degraded": degraded,
            "latency_ms": latency_ms,
            "latency_threshold_ms": threshold,
            "heartbeat_ok": heartbeat_ok,
            "gpu_blocked": gpu_blocked,
            "auto_evicted": auto_evicted,
            "status": status,
            "alerts": alerts,
            "detail": detail or {},
        }

    async def build_status(self) -> dict[str, Any]:
        vllm = VLLMStatusService().build_status()
        triton = TritonStatusService().build_status()
        ollama = await OllamaStatusService().build_status()
        gpu_status = GPUResourcePoolService().build_status()
        gpu_alerts = gpu_status.get("alerts") or []
        gpu_blocked = any(alert.get("severity") == "high" for alert in gpu_alerts)
        vllm_latency = self._estimate_latency_ms("vllm", vllm)
        triton_latency = self._estimate_latency_ms("triton", triton)
        ollama_latency = self._estimate_latency_ms("ollama", ollama)
        routes = {
            "vllm": self._build_route(
                "vllm",
                ready=bool(vllm.get("ready")),
                degraded=bool(vllm.get("degraded")),
                latency_ms=vllm_latency,
                heartbeat_ok=bool(vllm.get("cluster", {}).get("total_nodes", 0) >= 1),
                gpu_blocked=gpu_blocked,
                detail={"healthy_nodes": vllm.get("cluster", {}).get("healthy_nodes"), "gpu_count": vllm.get("gpu_runtime", {}).get("gpu_count")},
            ),
            "triton": self._build_route(
                "triton",
                ready=bool(triton.get("deploy_ready")),
                degraded=not bool(triton.get("deploy_ready")),
                latency_ms=triton_latency,
                heartbeat_ok=bool((triton.get("route_status") or {}).get("environment_connected") or triton.get("deploy_ready")),
                gpu_blocked=gpu_blocked,
                detail={"mode": (triton.get("route_status") or {}).get("mode"), "blocking_reason": (triton.get("route_status") or {}).get("blocking_reason")},
            ),
            "ollama": self._build_route(
                "ollama",
                ready=bool(ollama.get("ready")),
                degraded=bool(ollama.get("degraded")),
                latency_ms=ollama_latency,
                heartbeat_ok=bool((ollama.get("runtime") or {}).get("reachable")),
                gpu_blocked=False,
                detail={"runtime": ollama.get("runtime")},
            ),
        }
        available_routes = [name for name, item in routes.items() if item["ready"] and not item["auto_evicted"]]
        evicted_routes = [name for name, item in routes.items() if item["auto_evicted"]]
        return {
            "routes": routes,
            "available_routes": available_routes,
            "evicted_routes": evicted_routes,
            "route_count": len(routes),
            "healthy_route_count": len(available_routes),
            "automatic_evict_ready": len(routes) >= 1,
            "failover_ready": len(available_routes) >= 2,
            "heartbeat_monitoring": True,
            "latency_monitoring": True,
            "auto_recover_ready": True,
            "gpu_observability_level": gpu_status.get("observability_level"),
            "gpu_metrics_freshness_seconds": gpu_status.get("metrics_freshness_seconds"),
            "gpu_alerts": gpu_alerts,
        }
