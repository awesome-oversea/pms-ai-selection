"""
迁移治理服务
============

为 T8.4 提供最小 Alembic 治理状态与回滚策略定义。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class MigrationGovernanceService:
    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.alembic_dir = self.project_root / "alembic"
        self.alembic_ini = self.project_root / "alembic.ini"
        self.versions_dir = self.alembic_dir / "versions"

    def build_status(self) -> dict[str, Any]:
        version_files = sorted([p.name for p in self.versions_dir.glob("*.py")]) if self.versions_dir.exists() else []
        return {
            "alembic_ini_exists": self.alembic_ini.exists(),
            "env_exists": (self.alembic_dir / "env.py").exists(),
            "version_files": version_files,
            "baseline_present": any("baseline" in name or "0001" in name for name in version_files),
            "runtime_init_mode": {
                "development": "create_all + schema_patch (temporary convenience)",
                "production": "alembic_only",
            },
            "rollback_strategy": {
                "policy": "expand-contract",
                "compatibility_window": "at least one application version",
                "destructive_change_rule": "two-step rollout required",
                "rollback_method": "alembic downgrade to previous compatible revision",
            },
        }
