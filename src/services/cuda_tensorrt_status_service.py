from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from src.services.gpu_resource_pool_service import GPUResourcePoolService
from src.services.triton_status_service import TritonStatusService


class CudaTensorRTStatusService:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[2]

    def _detect_tool(self, command: list[str]) -> dict[str, Any]:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=self.root)
        except Exception as exc:
            return {"available": False, "error": str(exc)}
        if result.returncode != 0:
            return {"available": False, "error": (result.stderr or result.stdout).strip() or "command failed"}
        return {"available": True, "output": (result.stdout or "").strip()[:500]}

    def build_status(self) -> dict[str, Any]:
        gpu = GPUResourcePoolService(self.root).build_status()
        triton = TritonStatusService(self.root).build_status()
        cuda_probe = self._detect_tool(["nvidia-smi"])
        tensorrt_probe = self._detect_tool(["python", "-c", "import tensorrt as trt; print(trt.__version__)"])
        gpu_manifest = self.root / "k8s" / "gpu.yml"
        return {
            "acceleration_stack": "cuda-tensorrt",
            "cuda": {
                "available": cuda_probe.get("available", False),
                "probe": cuda_probe,
            },
            "tensorrt": {
                "available": tensorrt_probe.get("available", False),
                "probe": tensorrt_probe,
            },
            "gpu_pool": gpu,
            "triton": triton,
            "deployment": {
                "gpu_manifest": str(gpu_manifest.relative_to(self.root)).replace("\\", "/"),
                "gpu_manifest_exists": gpu_manifest.exists(),
                "optimization_targets": ["llava-13b", "bge-reranker", "phi-3-mini"],
                "runtime_path": "cuda -> tensorrt -> triton",
            },
            "ready": bool(gpu.get("ready")) and bool(triton.get("deploy_ready")),
        }
