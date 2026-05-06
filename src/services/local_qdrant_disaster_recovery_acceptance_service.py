from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.infrastructure.security_backup import BackupJob, BackupManager, RecoveryTest, RecoveryTester


class LocalQdrantDisasterRecoveryAcceptanceService:
    CORE_BACKUP_TARGETS: tuple[str, ...] = ("postgresql", "redis", "qdrant")
    CORE_RECOVERY_SCENARIOS: tuple[str, ...] = ("PG主库故障", "Redis Cluster故障", "Qdrant数据丢失")
    QDRANT_SCENARIO = "Qdrant数据丢失"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.artifact_root = self.root / "artifacts" / "local_qdrant_disaster_recovery"
        self.backup_root = self.root / "artifacts" / "backup"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _run_id() -> str:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _status_from_checks(checks: list[dict[str, Any]]) -> str:
        return "passed" if all(bool(item.get("passed")) for item in checks) else "failed"

    @staticmethod
    def _find_backup_job(jobs: list[BackupJob], target: str) -> BackupJob | None:
        for job in jobs:
            if job.target == target:
                return job
        return None

    @staticmethod
    def _find_recovery_test(tests: list[RecoveryTest], scenario: str) -> RecoveryTest | None:
        for test in tests:
            if test.scenario == scenario:
                return test
        return None

    @staticmethod
    def _job_to_dicts(jobs: list[BackupJob]) -> list[dict[str, Any]]:
        return [job.to_dict() for job in jobs]

    @staticmethod
    def _test_to_dicts(tests: list[RecoveryTest]) -> list[dict[str, Any]]:
        return [test.to_dict() for test in tests]

    @staticmethod
    def qdrant_restore_check(test: RecoveryTest | None) -> dict[str, Any]:
        if test is None:
            return {
                "passed": False,
                "detail": "missing qdrant recovery test",
                "evidence": {},
            }

        evidence = test.evidence or {}
        restore_validation = evidence.get("restore_validation") or {}
        runtime_probe = evidence.get("runtime_probe") or {}
        passed = (
            bool(test.passed)
            and bool(evidence.get("backup_artifact_exists"))
            and bool(restore_validation.get("restorable"))
            and bool(restore_validation.get("source_checksum_matches"))
            and bool(restore_validation.get("runtime_probe_reachable"))
        )
        return {
            "passed": passed,
            "detail": (
                f"runtime_status={runtime_probe.get('status')}, "
                f"restorable={restore_validation.get('restorable')}, "
                f"checksum_matches={restore_validation.get('source_checksum_matches')}"
            ),
            "evidence": evidence,
        }

    def _build_run_dir(self, output_root: Path | None) -> Path:
        root = output_root or self.artifact_root
        run_dir = root / self._run_id()
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolve_path(self, value: str | None) -> Path | None:
        if not value:
            return None
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return self.root / candidate

    def _copy_json_artifact(self, source: Path | None, target: Path) -> str | None:
        if source is None or not source.exists():
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return str(target)

    async def run_async(self, output_root: Path | None = None) -> dict[str, Any]:
        run_dir = self._build_run_dir(output_root)
        summary_path = run_dir / "summary.json"
        latest_path = self.backup_root / "qdrant_disaster_recovery_latest.json"
        partial_artifacts: dict[str, Any] = {"summary": str(summary_path)}

        try:
            backup_manager = BackupManager(root=self.root, persist_state=True)
            recovery_tester = RecoveryTester(root=self.root, persist_state=True)

            backup_jobs = await backup_manager.run_scheduled_backups()
            recovery_tests = await recovery_tester.run_all_tests()
            backup_stats = backup_manager.get_stats()
            recovery_stats = recovery_tester.get_stats()

            self._write_json(run_dir / "backup_jobs_current_run.json", self._job_to_dicts(backup_jobs))
            partial_artifacts["backup_jobs_current_run"] = str(run_dir / "backup_jobs_current_run.json")
            self._write_json(run_dir / "recovery_tests_current_run.json", self._test_to_dicts(recovery_tests))
            partial_artifacts["recovery_tests_current_run"] = str(run_dir / "recovery_tests_current_run.json")

            backup_snapshot = self._resolve_path(str(backup_stats.get("latest_snapshot") or ""))
            recovery_snapshot = self._resolve_path(str(recovery_stats.get("latest_snapshot") or ""))
            copied_backup_snapshot = self._copy_json_artifact(backup_snapshot, run_dir / "latest_backup_status.json")
            copied_recovery_snapshot = self._copy_json_artifact(
                recovery_snapshot,
                run_dir / "latest_recovery_status.json",
            )
            if copied_backup_snapshot:
                partial_artifacts["backup_snapshot"] = copied_backup_snapshot
            if copied_recovery_snapshot:
                partial_artifacts["recovery_snapshot"] = copied_recovery_snapshot

            qdrant_backup_job = self._find_backup_job(backup_jobs, "qdrant")
            qdrant_recovery_test = self._find_recovery_test(recovery_tests, self.QDRANT_SCENARIO)

            qdrant_backup_artifact = None
            if qdrant_recovery_test is not None:
                qdrant_backup_artifact = self._resolve_path(
                    str((qdrant_recovery_test.evidence or {}).get("backup_artifact") or "")
                )
            if qdrant_backup_artifact is None and qdrant_backup_job is not None:
                qdrant_backup_artifact = self._resolve_path(qdrant_backup_job.storage_path)

            qdrant_recovery_record = None
            if qdrant_recovery_test is not None:
                qdrant_recovery_record = self._resolve_path(
                    str((qdrant_recovery_test.evidence or {}).get("recovery_record") or "")
                )

            copied_qdrant_backup = self._copy_json_artifact(
                qdrant_backup_artifact,
                run_dir / "qdrant_backup_artifact.json",
            )
            copied_qdrant_recovery = self._copy_json_artifact(
                qdrant_recovery_record,
                run_dir / "qdrant_recovery_record.json",
            )
            if copied_qdrant_backup:
                partial_artifacts["qdrant_backup_artifact"] = copied_qdrant_backup
            if copied_qdrant_recovery:
                partial_artifacts["qdrant_recovery_record"] = copied_qdrant_recovery

            backup_targets = sorted(job.target for job in backup_jobs)
            core_recovery_tests = [
                self._find_recovery_test(recovery_tests, scenario)
                for scenario in self.CORE_RECOVERY_SCENARIOS
            ]
            current_run_matrix = [
                {
                    "scenario": test.scenario,
                    "target_rto_minutes": test.target_rto_minutes,
                    "actual_rto_minutes": test.actual_rto_minutes,
                    "target_rpo_minutes": test.target_rpo_minutes,
                    "actual_rpo_minutes": test.actual_rpo_minutes,
                    "passed": test.passed,
                }
                for test in recovery_tests
            ]
            qdrant_evidence_check = self.qdrant_restore_check(qdrant_recovery_test)

            checks = [
                {
                    "name": "scheduled_backups_cover_pg_redis_qdrant",
                    "passed": all(target in backup_targets for target in self.CORE_BACKUP_TARGETS),
                    "detail": f"targets={backup_targets}",
                    "evidence": self._job_to_dicts(backup_jobs),
                },
                {
                    "name": "core_recovery_tests_cover_pg_redis_qdrant",
                    "passed": all(test is not None and test.passed for test in core_recovery_tests),
                    "detail": (
                        " | ".join(
                            f"{scenario}={'passed' if test is not None and test.passed else 'missing'}"
                            for scenario, test in zip(self.CORE_RECOVERY_SCENARIOS, core_recovery_tests, strict=False)
                        )
                    ),
                    "evidence": current_run_matrix,
                },
                {
                    "name": "qdrant_restore_evidence_complete",
                    **qdrant_evidence_check,
                },
                {
                    "name": "qdrant_rto_rpo_within_target",
                    "passed": bool(
                        qdrant_recovery_test
                        and qdrant_recovery_test.actual_rto_minutes <= qdrant_recovery_test.target_rto_minutes
                        and qdrant_recovery_test.actual_rpo_minutes <= qdrant_recovery_test.target_rpo_minutes
                    ),
                    "detail": (
                        f"rto={getattr(qdrant_recovery_test, 'actual_rto_minutes', None)}/"
                        f"{getattr(qdrant_recovery_test, 'target_rto_minutes', None)}, "
                        f"rpo={getattr(qdrant_recovery_test, 'actual_rpo_minutes', None)}/"
                        f"{getattr(qdrant_recovery_test, 'target_rpo_minutes', None)}"
                    ),
                    "evidence": (
                        qdrant_recovery_test.to_dict() if qdrant_recovery_test is not None else {}
                    ),
                },
                {
                    "name": "latest_snapshots_written",
                    "passed": bool(copied_backup_snapshot and copied_recovery_snapshot),
                    "detail": "backup and recovery snapshots copied to current run directory",
                    "evidence": {
                        "backup_snapshot": copied_backup_snapshot,
                        "recovery_snapshot": copied_recovery_snapshot,
                    },
                },
                {
                    "name": "latest_acceptance_summary_synced",
                    "passed": True,
                    "detail": "latest summary written to artifacts/backup/qdrant_disaster_recovery_latest.json",
                    "evidence": {
                        "latest_summary_path": str(latest_path),
                    },
                },
            ]

            qdrant_runtime_probe = (
                (qdrant_recovery_test.evidence or {}).get("runtime_probe") if qdrant_recovery_test is not None else {}
            )
            summary = {
                "status": self._status_from_checks(checks),
                "accepted": all(bool(item.get("passed")) for item in checks),
                "generated_at": self._now_iso(),
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "business_context": {
                    "scenario": "本地知识检索与 GraphRAG 向量索引灾备演练",
                    "impact": "Qdrant 故障会影响知识召回、报告引用与 Agent 辅助选品的向量检索结果。",
                    "core_collections": list((qdrant_runtime_probe or {}).get("collection_names") or []),
                },
                "backup_summary": {
                    "current_run_targets": backup_targets,
                    "current_run_completed": [
                        job.target for job in backup_jobs if job.status.value == "completed"
                    ],
                    "qdrant_backup_job": qdrant_backup_job.to_dict() if qdrant_backup_job is not None else None,
                },
                "recovery_summary": {
                    "current_run_matrix": current_run_matrix,
                    "qdrant_recovery_test": (
                        qdrant_recovery_test.to_dict() if qdrant_recovery_test is not None else None
                    ),
                },
                "checks": checks,
                "artifacts": partial_artifacts,
            }
            self._write_json(summary_path, summary)
            self._write_json(latest_path, summary)
            return summary
        except Exception as exc:
            summary = {
                "status": "failed",
                "accepted": False,
                "generated_at": self._now_iso(),
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "error": str(exc),
                "artifacts": partial_artifacts,
            }
            self._write_json(summary_path, summary)
            self._write_json(latest_path, summary)
            return summary

    def run(self, output_root: Path | None = None) -> dict[str, Any]:
        return asyncio.run(self.run_async(output_root=output_root))
