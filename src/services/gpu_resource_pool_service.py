from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class GPUResourcePoolService:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[2]

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

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
            return {"available": False, "error": str(exc), "gpu_count": 0, "gpus": []}

        if result.returncode != 0:
            return {
                "available": False,
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
            model_class = "a100-class" if "a100" in parts[0].lower() else "a10-class" if "a10" in parts[0].lower() else "generic"
            gpus.append(
                {
                    "gpu_index": index,
                    "name": parts[0],
                    "model_class": model_class,
                    "memory_total_mb": total,
                    "memory_used_mb": used,
                    "memory_free_mb": max(total - used, 0),
                    "memory_usage_percent": round((used / total) * 100, 2) if total else 0.0,
                    "utilization_gpu_percent": util,
                    "allocatable": max(total - used, 0) > 4096,
                }
            )
        allocatable = [gpu for gpu in gpus if gpu["allocatable"]]
        return {
            "available": True,
            "gpu_count": len(gpus),
            "allocatable_gpu_count": len(allocatable),
            "gpus": gpus,
            "pool_ready": len(gpus) > 0,
        }

    def build_status(self) -> dict[str, Any]:
        runtime = self._run_nvidia_smi()
        dcgm_exporter_available = shutil.which("dcgm-exporter") is not None
        metrics_ready = dcgm_exporter_available and bool(runtime.get("available"))
        observability_level = "none"
        if bool(runtime.get("available")):
            observability_level = "nvidia-smi"
        if metrics_ready:
            observability_level = "dcgm-exporter"
        alerts: list[dict[str, Any]] = []
        if not runtime.get("available"):
            alerts.append({"severity": "high", "code": "gpu_runtime_unavailable", "message": runtime.get("error") or "nvidia-smi unavailable"})
        if runtime.get("available") and not dcgm_exporter_available:
            alerts.append({"severity": "medium", "code": "dcgm_not_installed", "message": "dcgm-exporter not installed"})
        for gpu in runtime.get("gpus", []):
            if float(gpu.get("memory_usage_percent") or 0.0) >= 90.0:
                alerts.append({
                    "severity": "high",
                    "code": "gpu_memory_pressure",
                    "gpu_index": gpu.get("gpu_index"),
                    "message": f"GPU {gpu.get('gpu_index')} memory pressure >= 90%",
                })
            if float(gpu.get("utilization_gpu_percent") or 0.0) >= 95.0:
                alerts.append({
                    "severity": "medium",
                    "code": "gpu_utilization_hot",
                    "gpu_index": gpu.get("gpu_index"),
                    "message": f"GPU {gpu.get('gpu_index')} utilization >= 95%",
                })
        return {
            "resource_pool": "nvidia-gpu",
            "runtime": runtime,
            "ready": runtime.get("pool_ready", False),
            "observability_level": observability_level,
            "metrics_freshness_seconds": 0 if runtime.get("available") else None,
            "observed_at": self._now_iso(),
            "alerts": alerts,
            "alert_count": len(alerts),
            "dcgm_exporter": {
                "installed": dcgm_exporter_available,
                "metrics_ready": metrics_ready,
                "recommended_metric_path": "/metrics",
                "blocking_reason": None if dcgm_exporter_available else "dcgm-exporter not installed",
            },
            "scheduler": {
                "strategy": "memory-aware-first-fit",
                "priority_classes": ["pms-gpu-high-priority"],
                "allocation_dimensions": ["memory_total_mb", "memory_free_mb", "utilization_gpu_percent"],
            },
        }
