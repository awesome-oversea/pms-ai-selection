from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.infrastructure.security_backup import BackupManager, RecoveryTester


class HATopologyService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.k8s_dir = self.root / "k8s"
        self.gateway_dir = self.k8s_dir / "gateway"
        self.overlays_dir = self.k8s_dir / "overlays"

    def _read_text(self, relative_path: str) -> str:
        path = self.root / relative_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _extract_named_replicas(content: str, resource_name: str) -> int:
        pattern = rf"name:\s*{re.escape(resource_name)}[\s\S]*?replicas:\s*(\d+)"
        match = re.search(pattern, content)
        return int(match.group(1)) if match else 0

    def _read_artifact_json(self, relative_path: str) -> dict[str, Any] | None:
        path = self.root / relative_path
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def build_status(self) -> dict[str, Any]:
        postgres_content = self._read_text("k8s/postgresql.yml")
        redis_content = self._read_text("k8s/redis.yml")
        rag_content = self._read_text("k8s/rag-service.yml")
        llm_content = self._read_text("k8s/llm-service.yml")

        environments = {
            "test": {
                "overlay": "k8s/overlays/test/kustomization.yaml",
                "configured": (self.overlays_dir / "test" / "kustomization.yaml").exists(),
            },
            "preprod": {
                "overlay": "k8s/overlays/preprod/kustomization.yaml",
                "configured": (self.overlays_dir / "preprod" / "kustomization.yaml").exists(),
            },
            "prod": {
                "overlay": "k8s/overlays/prod/kustomization.yaml",
                "configured": (self.overlays_dir / "prod" / "kustomization.yaml").exists(),
            },
        }

        postgres_ha = {
            "manifest": "k8s/postgresql.yml",
            "primary_count": self._extract_named_replicas(postgres_content, "pms-pg-primary"),
            "replica_count": self._extract_named_replicas(postgres_content, "pms-pg-replica"),
            "pooler_enabled": "name: pms-pgbouncer" in postgres_content,
            "status": "ready" if postgres_content else "missing",
        }

        redis_ha = {
            "manifest": "k8s/redis.yml",
            "master_count": self._extract_named_replicas(redis_content, "pms-redis-master"),
            "replica_count": self._extract_named_replicas(redis_content, "pms-redis-slave"),
            "sentinel_count": self._extract_named_replicas(redis_content, "pms-redis-sentinel"),
            "pdb_enabled": "kind: PodDisruptionBudget" in redis_content,
            "status": "ready" if redis_content else "missing",
        }

        gateway_ha = {
            "manifest": "k8s/gateway/kong.yml",
            "split_config": all(
                (self.gateway_dir / name).exists()
                for name in [
                    "kong.yml",
                    "kong-routes.yml",
                    "kong-services.yml",
                    "kong-plugins.yml",
                    "kong-consumers.yml",
                ]
            ),
            "status": "ready" if (self.gateway_dir / "kong.yml").exists() else "missing",
        }

        ai_services = {
            "rag": {
                "manifest": "k8s/rag-service.yml",
                "replica_count": self._extract_named_replicas(rag_content, "pms-rag-service"),
                "status": "ready" if rag_content else "missing",
            },
            "llm": {
                "manifest": "k8s/llm-service.yml",
                "replica_count": self._extract_named_replicas(llm_content, "pms-llm-service"),
                "status": "ready" if llm_content else "missing",
            },
        }

        monitoring_stack = {
            "prometheus": "compatible",
            "grafana": "compatible",
            "alertmanager": "compatible",
            "efk": "compatible",
        }
        backup_manager = BackupManager(root=self.root, persist_state=True)
        recovery_tester = RecoveryTester(root=self.root, persist_state=True)
        backup_stats = backup_manager.get_stats()
        recovery_stats = recovery_tester.get_stats()
        latest_backup_jobs = backup_stats.get("jobs", [])[-3:]
        latest_recovery_tests = recovery_stats.get("tests", [])[-4:]
        qdrant_recovery = next((test for test in reversed(latest_recovery_tests) if test.get("scenario") == "Qdrant数据丢失"), None)
        backup_recovery = {
            "artifact_dir": backup_stats.get("artifact_dir"),
            "backup_snapshot": backup_stats.get("latest_snapshot"),
            "recovery_snapshot": recovery_stats.get("latest_snapshot"),
            "scheduled_targets": ["postgresql", "redis", "qdrant"],
            "backup_ready": len(latest_backup_jobs) >= 3 and all(job.get("status") == "completed" for job in latest_backup_jobs),
            "recovery_ready": len(latest_recovery_tests) >= 4 and all(test.get("passed") is True for test in latest_recovery_tests),
            "qdrant_recovery_ready": bool(qdrant_recovery and qdrant_recovery.get("passed") is True),
            "qdrant_recovery_evidence": (qdrant_recovery or {}).get("evidence", {}),
            "status": "ready"
            if len(latest_backup_jobs) >= 3
            and len(latest_recovery_tests) >= 4
            and all(job.get("status") == "completed" for job in latest_backup_jobs)
            and all(test.get("passed") is True for test in latest_recovery_tests)
            else "partial",
            "latest_backup_jobs": latest_backup_jobs,
            "latest_recovery_tests": latest_recovery_tests,
        }

        release_record_path = self.root / "artifacts" / "release" / "latest_release.json"
        drill_record = None
        if release_record_path.exists():
            try:
                import json
                drill_record = json.loads(release_record_path.read_text(encoding="utf-8"))
            except Exception:
                drill_record = None

        disaster_recovery = {
            "overlay_ready": all(item["configured"] for item in environments.values()),
            "rollback_script_ready": (self.root / "scripts" / "release_rollback.py").exists(),
            "deploy_script_ready": (self.root / "scripts" / "release_deploy.py").exists(),
            "drill_record_present": drill_record is not None,
            "latest_drill": drill_record,
            "drill_ready": drill_record is not None and drill_record.get("status") in {"deployed", "rolled_back"},
            "evidence_paths": [
                "k8s/overlays/test/kustomization.yaml",
                "k8s/overlays/preprod/kustomization.yaml",
                "k8s/overlays/prod/kustomization.yaml",
                "scripts/release_deploy.py",
                "scripts/release_rollback.py",
                "artifacts/release/latest_release.json",
            ],
        }

        gpu_manifest_path = self.root / "k8s" / "gpu.yml"
        gpu_manifest = gpu_manifest_path.read_text(encoding="utf-8") if gpu_manifest_path.exists() else ""
        gpu_scheduling = {
            "manifest": "k8s/gpu.yml",
            "device_plugin_ready": "nvidia-device-plugin-daemonset" in gpu_manifest,
            "resource_quota_ready": "requests.nvidia.com/gpu" in gpu_manifest,
            "priority_class_ready": "pms-gpu-high-priority" in gpu_manifest,
            "scheduler_targets": ["A100", "A10"],
            "status": "ready" if gpu_manifest else "missing",
        }
        harbor_status = self._read_artifact_json("artifacts/ops/harbor_status.json") or {}
        terraform_status = self._read_artifact_json("artifacts/ops/terraform_status.json") or {}
        metallb_status = self._read_artifact_json("artifacts/ops/metallb_status.json") or {}
        calico_status = self._read_artifact_json("artifacts/ops/calico_status.json") or {}
        return {
            "environments": environments,
            "postgres_ha": postgres_ha,
            "redis_ha": redis_ha,
            "gateway_ha": gateway_ha,
            "ai_services": ai_services,
            "gpu_scheduling": gpu_scheduling,
            "harbor": harbor_status,
            "terraform": terraform_status,
            "metallb": metallb_status,
            "calico": calico_status,
            "monitoring_stack": monitoring_stack,
            "backup_recovery": backup_recovery,
            "disaster_recovery": disaster_recovery,
            "validation_script": "scripts/check_ha_topology.py",
            "overall_status": "ready"
            if all(item["configured"] for item in environments.values())
            and postgres_ha["replica_count"] >= 2
            and redis_ha["sentinel_count"] >= 3
            and gateway_ha["split_config"]
            else "partial",
        }
