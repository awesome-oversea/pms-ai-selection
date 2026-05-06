from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from src.config.settings import get_settings
from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway


class VLLMStatusService:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[2]

    def _read_gpu_manifest(self) -> dict[str, Any]:
        path = self.root / "k8s" / "gpu.yml"
        if not path.exists():
            return {"manifest_exists": False}
        text = path.read_text(encoding="utf-8")
        requested_gpu = 0
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("nvidia.com/gpu:"):
                try:
                    requested_gpu = max(requested_gpu, int(stripped.split(":", 1)[1].strip().strip('"')))
                except ValueError:
                    continue
        return {
            "manifest_exists": True,
            "manifest": "k8s/gpu.yml",
            "requested_gpu_per_pod": requested_gpu,
            "has_device_plugin": "nvidia-device-plugin-daemonset" in text,
            "has_vllm_deployment": "pms-vllm-inference" in text,
            "uses_qwen_72b": "Qwen/Qwen2.5-72B-Instruct" in text,
            "readiness_probe": "/health" if "/health" in text else None,
            "tensor_parallel_ready": requested_gpu >= 2,
            "gpu_node_selector": "pool: llm" if "pool: llm" in text else None,
        }

    def _run_nvidia_smi(self) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=False,
                cwd=self.root,
            )
        except Exception as exc:
            return {"available": False, "reachable": False, "error": str(exc), "gpu_count": 0, "gpus": []}

        if result.returncode != 0:
            return {
                "available": False,
                "reachable": False,
                "error": (result.stderr or result.stdout).strip() or "nvidia-smi failed",
                "gpu_count": 0,
                "gpus": [],
            }

        gpus: list[dict[str, Any]] = []
        for index, line in enumerate(result.stdout.splitlines()):
            parts = [item.strip() for item in line.split(",")]
            if len(parts) < 4:
                continue
            total = float(parts[1] or 0)
            used = float(parts[2] or 0)
            util = float(parts[3] or 0)
            gpus.append(
                {
                    "gpu_index": index,
                    "name": parts[0],
                    "memory_total_mb": total,
                    "memory_used_mb": used,
                    "memory_free_mb": max(total - used, 0),
                    "memory_usage_percent": round((used / total) * 100, 2) if total else 0.0,
                    "utilization_gpu_percent": util,
                }
            )
        return {"available": True, "reachable": True, "gpu_count": len(gpus), "gpus": gpus}

    def build_status(self) -> dict[str, Any]:
        settings = get_settings().llm
        gateway = LLMGateway(
            GatewayConfig(
                use_mock=False,
                provider_mode="real",
                vllm_endpoint=settings.vllm_endpoint,
                ollama_endpoint=settings.ollama_endpoint,
                vllm_timeout_seconds=settings.request_timeout_seconds,
                ollama_timeout_seconds=min(settings.request_timeout_seconds, 15.0),
                api_key=settings.api_key,
                api_auth_header=settings.api_auth_header,
                api_auth_scheme=settings.api_auth_scheme,
                api_model_name=settings.api_model_name,
                retry_count=settings.request_retry_count,
            )
        )
        cluster = gateway.get_cluster_status()
        gpu_runtime = self._run_nvidia_smi()
        manifest = self._read_gpu_manifest()
        healthy_nodes = int(cluster.get("healthy_nodes", 0))
        total_nodes = int(cluster.get("total_nodes", 0))
        return {
            "provider": "vllm",
            "endpoint": settings.vllm_endpoint,
            "primary_model": settings.primary_model,
            "cluster": cluster,
            "gpu_runtime": gpu_runtime,
            "deployment_manifest": manifest,
            "tensor_parallel_ready": bool(manifest.get("tensor_parallel_ready")),
            "single_card_failover_ready": healthy_nodes >= 2 or total_nodes >= 2,
            "ready": total_nodes >= 1,
            "degraded": healthy_nodes < max(total_nodes, 1),
        }
