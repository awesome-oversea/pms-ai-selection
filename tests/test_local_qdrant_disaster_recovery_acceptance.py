from __future__ import annotations

import json
from pathlib import Path

from src.infrastructure.security_backup import BackupJob, BackupStatus, BackupType, RecoveryTest
from src.services import local_qdrant_disaster_recovery_acceptance_service as acceptance_module
from src.services.local_qdrant_disaster_recovery_acceptance_service import (
    LocalQdrantDisasterRecoveryAcceptanceService,
)


def test_qdrant_restore_check_requires_complete_evidence():
    test = RecoveryTest(
        test_id="RECOVERY_QDRANT_001",
        scenario="Qdrant数据丢失",
        target_rto_minutes=15,
        target_rpo_minutes=1440,
        actual_rto_minutes=12.0,
        actual_rpo_minutes=720.0,
        passed=True,
        evidence={
            "backup_artifact_exists": True,
            "runtime_probe": {"status": "healthy"},
            "restore_validation": {
                "restorable": True,
                "source_checksum_matches": True,
                "runtime_probe_reachable": True,
            },
        },
    )

    result = LocalQdrantDisasterRecoveryAcceptanceService.qdrant_restore_check(test)

    assert result["passed"] is True
    assert "runtime_status=healthy" in result["detail"]


def test_qdrant_restore_check_fails_when_checksum_validation_is_missing():
    test = RecoveryTest(
        test_id="RECOVERY_QDRANT_002",
        scenario="Qdrant数据丢失",
        target_rto_minutes=15,
        target_rpo_minutes=1440,
        actual_rto_minutes=12.0,
        actual_rpo_minutes=720.0,
        passed=True,
        evidence={
            "backup_artifact_exists": True,
            "runtime_probe": {"status": "healthy"},
            "restore_validation": {
                "restorable": True,
                "source_checksum_matches": False,
                "runtime_probe_reachable": True,
            },
        },
    )

    result = LocalQdrantDisasterRecoveryAcceptanceService.qdrant_restore_check(test)

    assert result["passed"] is False


def test_run_writes_summary_and_latest_artifact(tmp_path, monkeypatch):
    backup_root = tmp_path / "artifacts" / "backup"
    backup_root.mkdir(parents=True, exist_ok=True)

    class FakeBackupManager:
        def __init__(self, root: Path, persist_state: bool) -> None:
            self.root = root
            self.snapshot_path = root / "artifacts" / "backup" / "latest_backup_status.json"

        async def run_scheduled_backups(self) -> list[BackupJob]:
            backup_artifact = self.root / "artifacts" / "backup" / "BACKUP_QDRANT_TEST.json"
            backup_artifact.write_text(
                json.dumps(
                    {
                        "job_id": "BACKUP_QDRANT_TEST",
                        "target": "qdrant",
                        "verification": {
                            "restorable": True,
                            "source_checksum": "checksum-001",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.snapshot_path.write_text(json.dumps({"stats": {"total_jobs": 3}}, ensure_ascii=False), encoding="utf-8")
            return [
                BackupJob(
                    job_id="BACKUP_PG_TEST",
                    target="postgresql",
                    backup_type=BackupType.FULL,
                    status=BackupStatus.COMPLETED,
                    storage_path="artifacts/backup/BACKUP_PG_TEST.json",
                ),
                BackupJob(
                    job_id="BACKUP_REDIS_TEST",
                    target="redis",
                    backup_type=BackupType.SNAPSHOT,
                    status=BackupStatus.COMPLETED,
                    storage_path="artifacts/backup/BACKUP_REDIS_TEST.json",
                ),
                BackupJob(
                    job_id="BACKUP_QDRANT_TEST",
                    target="qdrant",
                    backup_type=BackupType.SNAPSHOT,
                    status=BackupStatus.COMPLETED,
                    storage_path="artifacts/backup/BACKUP_QDRANT_TEST.json",
                ),
            ]

        def get_stats(self) -> dict[str, object]:
            return {"latest_snapshot": str(self.snapshot_path)}

    class FakeRecoveryTester:
        def __init__(self, root: Path, persist_state: bool) -> None:
            self.root = root
            self.snapshot_path = root / "artifacts" / "backup" / "latest_recovery_status.json"

        async def run_all_tests(self) -> list[RecoveryTest]:
            recovery_record = self.root / "artifacts" / "backup" / "RECOVERY_QDRANT_TEST.json"
            recovery_record.write_text(
                json.dumps({"scenario": "Qdrant数据丢失"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.snapshot_path.write_text(
                json.dumps({"stats": {"total_tests": 4}}, ensure_ascii=False),
                encoding="utf-8",
            )
            return [
                RecoveryTest(
                    test_id="RECOVERY_PG_TEST",
                    scenario="PG主库故障",
                    target_rto_minutes=5,
                    target_rpo_minutes=60,
                    actual_rto_minutes=4.0,
                    actual_rpo_minutes=30.0,
                    passed=True,
                ),
                RecoveryTest(
                    test_id="RECOVERY_REDIS_TEST",
                    scenario="Redis Cluster故障",
                    target_rto_minutes=10,
                    target_rpo_minutes=60,
                    actual_rto_minutes=8.0,
                    actual_rpo_minutes=30.0,
                    passed=True,
                ),
                RecoveryTest(
                    test_id="RECOVERY_QDRANT_TEST",
                    scenario="Qdrant数据丢失",
                    target_rto_minutes=15,
                    target_rpo_minutes=1440,
                    actual_rto_minutes=12.0,
                    actual_rpo_minutes=720.0,
                    passed=True,
                    evidence={
                        "backup_artifact": str(self.root / "artifacts" / "backup" / "BACKUP_QDRANT_TEST.json"),
                        "backup_artifact_exists": True,
                        "runtime_probe": {
                            "status": "healthy",
                            "collection_names": ["product_knowledge_local"],
                        },
                        "restore_validation": {
                            "restorable": True,
                            "source_checksum_matches": True,
                            "runtime_probe_reachable": True,
                        },
                        "recovery_record": "artifacts/backup/RECOVERY_QDRANT_TEST.json",
                    },
                ),
                RecoveryTest(
                    test_id="RECOVERY_CONFIG_TEST",
                    scenario="配置误删",
                    target_rto_minutes=5,
                    target_rpo_minutes=0,
                    actual_rto_minutes=3.0,
                    actual_rpo_minutes=0.0,
                    passed=True,
                ),
            ]

        def get_stats(self) -> dict[str, object]:
            return {"latest_snapshot": str(self.snapshot_path)}

    monkeypatch.setattr(acceptance_module, "BackupManager", FakeBackupManager)
    monkeypatch.setattr(acceptance_module, "RecoveryTester", FakeRecoveryTester)

    service = LocalQdrantDisasterRecoveryAcceptanceService(root=tmp_path)
    summary = service.run(output_root=tmp_path / "artifacts" / "local_qdrant_disaster_recovery")

    latest_path = tmp_path / "artifacts" / "backup" / "qdrant_disaster_recovery_latest.json"

    assert summary["accepted"] is True
    assert summary["status"] == "passed"
    assert Path(summary["artifacts"]["qdrant_backup_artifact"]).exists()
    assert Path(summary["artifacts"]["qdrant_recovery_record"]).exists()
    assert latest_path.exists()
