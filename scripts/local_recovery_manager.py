from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SEC_SECRET_KEY", "local-recovery-manager-32chars")
sys.stdout.reconfigure(encoding="utf-8")

from src.services.local_feedback_loop_service import LocalFeedbackLoopService


DEFAULT_RECOVERY_ROOT = PROJECT_ROOT / "artifacts" / "local_recovery"
BASELINE_ERP_LOCAL = PROJECT_ROOT / "artifacts" / "erp_local"

RESET_TARGETS: dict[str, str] = {
    "feature_store": "data/local_feature_store.db",
    "knowledge_store": "data/local_knowledge.db",
    "report_state": "artifacts/report_center/state.json",
    "qdrant_local": "artifacts/runtime/qdrant_local",
}

STATUS_TARGETS: dict[str, str] = {
    "env_file": ".env",
    "feature_store": "data/local_feature_store.db",
    "knowledge_store": "data/local_knowledge.db",
    "report_state": "artifacts/report_center/state.json",
    "erp_local_root": "artifacts/erp_local",
    "erp_orders": "artifacts/erp_local/oms/orders.json",
    "crm_feedback": "artifacts/erp_local/crm/feedback.json",
    "qdrant_local": "artifacts/runtime/qdrant_local",
}


@dataclass
class ActionResult:
    name: str
    ok: bool
    detail: str
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.evidence is None:
            payload.pop("evidence")
        return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_within_workspace(workspace_root: Path, relative_path: str) -> Path:
    root = workspace_root.resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Target path escapes workspace root: {target}") from exc
    return target


def _collect_path_status(path: Path) -> dict[str, Any]:
    exists = path.exists()
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "is_dir": path.is_dir() if exists else False,
    }
    if exists and path.is_file():
        payload["size_bytes"] = path.stat().st_size
    if exists and path.is_dir():
        payload["entries"] = len(list(path.iterdir()))
    return payload


def collect_local_status(workspace_root: Path) -> dict[str, Any]:
    root = workspace_root.resolve()
    targets = {
        name: _collect_path_status(_ensure_within_workspace(root, relative_path))
        for name, relative_path in STATUS_TARGETS.items()
    }
    acceptance_root = _ensure_within_workspace(root, "artifacts/local_acceptance")
    recovery_root = _ensure_within_workspace(root, "artifacts/local_recovery")
    acceptance_runs = sorted(
        [item.name for item in acceptance_root.iterdir() if item.is_dir()],
        reverse=True,
    ) if acceptance_root.exists() else []
    recovery_runs = sorted(
        [item.name for item in recovery_root.iterdir() if item.is_dir()],
        reverse=True,
    ) if recovery_root.exists() else []
    return {
        "workspace_root": str(root),
        "targets": targets,
        "acceptance_run_count": len(acceptance_runs),
        "latest_acceptance_run": acceptance_runs[0] if acceptance_runs else None,
        "recovery_run_count": len(recovery_runs),
        "latest_recovery_run": recovery_runs[0] if recovery_runs else None,
    }


def reset_local_state(
    workspace_root: Path,
    *,
    include_report_state: bool = False,
    include_qdrant_local: bool = False,
) -> dict[str, Any]:
    root = workspace_root.resolve()
    results: list[ActionResult] = []
    target_names = ["feature_store", "knowledge_store"]
    if include_report_state:
        target_names.append("report_state")
    if include_qdrant_local:
        target_names.append("qdrant_local")

    for target_name in target_names:
        target = _ensure_within_workspace(root, RESET_TARGETS[target_name])
        if not target.exists():
            results.append(ActionResult(target_name, True, f"Skipped missing target: {target}"))
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        results.append(ActionResult(target_name, True, f"Removed {target}"))

    return {
        "workspace_root": str(root),
        "status": "passed" if all(item.ok for item in results) else "failed",
        "actions": [item.to_dict() for item in results],
    }


def restore_baseline_artifacts(
    workspace_root: Path,
    *,
    restore_erp_local: bool = True,
) -> dict[str, Any]:
    root = workspace_root.resolve()
    results: list[ActionResult] = []

    if restore_erp_local:
        target = _ensure_within_workspace(root, "artifacts/erp_local")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(BASELINE_ERP_LOCAL, target)
        results.append(
            ActionResult(
                "restore_erp_local",
                True,
                f"Restored ERP local baseline into {target}",
                {"source": str(BASELINE_ERP_LOCAL), "target": str(target)},
            )
        )

    return {
        "workspace_root": str(root),
        "status": "passed" if all(item.ok for item in results) else "failed",
        "actions": [item.to_dict() for item in results],
    }


@contextmanager
def _pushd(path: Path) -> Iterator[None]:
    current = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current)


async def rebuild_local_feedback_state(workspace_root: Path, *, task_id: str) -> dict[str, Any]:
    root = workspace_root.resolve()
    artifact_root = _ensure_within_workspace(root, "artifacts/erp_local")
    with _pushd(root):
        service = LocalFeedbackLoopService()
        result = await service.run_local_loop(task_id=task_id, artifact_root=artifact_root.as_posix())
    checks = [
        ActionResult("closed_loop_ready", bool(result.get("closed_loop_ready")), f"closed_loop_ready={result.get('closed_loop_ready')}"),
        ActionResult("feature_store_rebuilt", _ensure_within_workspace(root, RESET_TARGETS["feature_store"]).exists(), RESET_TARGETS["feature_store"]),
        ActionResult("knowledge_store_rebuilt", _ensure_within_workspace(root, RESET_TARGETS["knowledge_store"]).exists(), RESET_TARGETS["knowledge_store"]),
    ]
    return {
        "workspace_root": str(root),
        "status": "passed" if all(item.ok for item in checks) else "failed",
        "result": result,
        "checks": [item.to_dict() for item in checks],
    }


def _create_dirty_workspace(workspace_root: Path) -> None:
    feature_store = _ensure_within_workspace(workspace_root, RESET_TARGETS["feature_store"])
    knowledge_store = _ensure_within_workspace(workspace_root, RESET_TARGETS["knowledge_store"])
    report_state = _ensure_within_workspace(workspace_root, RESET_TARGETS["report_state"])
    for target in (feature_store, knowledge_store, report_state):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("corrupted-local-state", encoding="utf-8")


async def run_recovery_drill(output_root: Path = DEFAULT_RECOVERY_ROOT) -> dict[str, Any]:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root.resolve() / run_id
    workspace_root = run_dir / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    restore_report = restore_baseline_artifacts(workspace_root)
    _create_dirty_workspace(workspace_root)
    status_before = collect_local_status(workspace_root)
    reset_report = reset_local_state(workspace_root, include_report_state=True)
    status_after_reset = collect_local_status(workspace_root)
    rebuild_report = await rebuild_local_feedback_state(workspace_root, task_id="selection-task-erp-real-001")
    status_after_rebuild = collect_local_status(workspace_root)

    checks = [
        ActionResult("baseline_restored", restore_report["status"] == "passed", "ERP local baseline restored"),
        ActionResult("feature_store_reset", not status_after_reset["targets"]["feature_store"]["exists"], "feature store removed by reset"),
        ActionResult("knowledge_store_reset", not status_after_reset["targets"]["knowledge_store"]["exists"], "knowledge store removed by reset"),
        ActionResult("report_state_reset", not status_after_reset["targets"]["report_state"]["exists"], "report state removed by reset"),
        ActionResult("feedback_rebuild", rebuild_report["status"] == "passed", "feedback loop rebuild completed"),
        ActionResult("feature_store_recovered", status_after_rebuild["targets"]["feature_store"]["exists"], "feature store rebuilt"),
        ActionResult("knowledge_store_recovered", status_after_rebuild["targets"]["knowledge_store"]["exists"], "knowledge store rebuilt"),
    ]

    summary = {
        "status": "passed" if all(item.ok for item in checks) else "failed",
        "accepted": all(item.ok for item in checks),
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "workspace_root": str(workspace_root),
        "steps": {
            "restore": restore_report["status"],
            "reset": reset_report["status"],
            "rebuild": rebuild_report["status"],
        },
        "checks": [item.to_dict() for item in checks],
        "artifacts": {
            "restore_report": str(run_dir / "restore_report.json"),
            "reset_report": str(run_dir / "reset_report.json"),
            "rebuild_report": str(run_dir / "rebuild_report.json"),
            "summary": str(run_dir / "summary.json"),
        },
    }

    _write_json(run_dir / "status_before.json", status_before)
    _write_json(run_dir / "status_after_reset.json", status_after_reset)
    _write_json(run_dir / "status_after_rebuild.json", status_after_rebuild)
    _write_json(run_dir / "restore_report.json", restore_report)
    _write_json(run_dir / "reset_report.json", reset_report)
    _write_json(run_dir / "rebuild_report.json", rebuild_report)
    _write_json(run_dir / "summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage local troubleshooting/reset/recovery workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Inspect local recovery-related targets.")
    status_parser.add_argument("--workspace-root", default=str(PROJECT_ROOT), help="Workspace root to inspect")
    status_parser.add_argument("--output", default=None, help="Optional JSON output path")

    reset_parser = subparsers.add_parser("reset", help="Reset local data stores and optional caches.")
    reset_parser.add_argument("--workspace-root", default=str(PROJECT_ROOT), help="Workspace root to reset")
    reset_parser.add_argument("--include-report-state", action="store_true", help="Also remove report center state")
    reset_parser.add_argument("--include-qdrant-local", action="store_true", help="Also remove local Qdrant runtime data")
    reset_parser.add_argument("--output", default=None, help="Optional JSON output path")

    restore_parser = subparsers.add_parser("restore", help="Restore baseline local artifacts.")
    restore_parser.add_argument("--workspace-root", default=str(PROJECT_ROOT), help="Workspace root to restore into")
    restore_parser.add_argument("--output", default=None, help="Optional JSON output path")

    drill_parser = subparsers.add_parser("drill", help="Run a local reset/recovery drill.")
    drill_parser.add_argument("--output-root", default=str(DEFAULT_RECOVERY_ROOT), help="Root directory for drill artifacts")

    return parser.parse_args()


def _emit_payload(payload: dict[str, Any], output: str | None = None) -> None:
    if output:
        target = Path(output)
        if not target.is_absolute():
            target = PROJECT_ROOT / target
        _write_json(target, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    if args.command == "status":
        payload = collect_local_status(Path(args.workspace_root))
        _emit_payload(payload, args.output)
        return 0
    if args.command == "reset":
        payload = reset_local_state(
            Path(args.workspace_root),
            include_report_state=args.include_report_state,
            include_qdrant_local=args.include_qdrant_local,
        )
        _emit_payload(payload, args.output)
        return 0 if payload["status"] == "passed" else 1
    if args.command == "restore":
        payload = restore_baseline_artifacts(Path(args.workspace_root))
        _emit_payload(payload, args.output)
        return 0 if payload["status"] == "passed" else 1

    summary = asyncio.run(run_recovery_drill(Path(args.output_root)))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
