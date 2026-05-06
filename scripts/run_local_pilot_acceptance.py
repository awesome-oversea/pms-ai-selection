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

os.environ.setdefault("SEC_SECRET_KEY", "run-local-pilot-acceptance-32chars")
sys.stdout.reconfigure(encoding="utf-8")

from pydantic import ValidationError

from scripts.local_runtime_manager import _collect_runtime_report, _load_settings
from src.models.schemas import SelectionTaskRunCreate
from src.services.business_scenario_catalog_service import BusinessScenarioCatalogService
from src.services.local_feedback_loop_service import LocalFeedbackLoopService
from src.services.report_center_service import ReportCenterService


PACKAGE_ROOT = PROJECT_ROOT / "data" / "local_pilot"
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "local_acceptance"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.evidence is None:
            payload.pop("evidence")
        return payload


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_path(package_root: Path, raw_path: str) -> Path:
    target = Path(raw_path)
    if target.is_absolute():
        return target
    return PROJECT_ROOT / target if not str(target).startswith("data/local_pilot") else package_root / target.relative_to("data/local_pilot")


def _status_from_checks(checks: list[CheckResult]) -> str:
    return "passed" if all(check.passed for check in checks) else "failed"


def _build_run_dir(output_root: Path) -> Path:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@contextmanager
def _pushd(path: Path) -> Iterator[None]:
    current = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current)


def validate_local_pilot_package(package_root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    manifest_path = package_root / "manifest.json"
    manifest = _load_json(manifest_path)
    checks: list[CheckResult] = []

    required_domain_names = {
        "selection_task_seed",
        "knowledge_documents",
        "external_mock_expectations",
        "erp_orders",
        "crm_feedback",
        "report_request",
        "report_seed_state",
        "feedback_output_target",
    }
    domain_names = set((manifest.get("domains") or {}).keys())
    checks.append(
        CheckResult(
            "manifest.required_domains",
            required_domain_names.issubset(domain_names),
            f"domains={sorted(domain_names)}",
            {"missing": sorted(required_domain_names - domain_names)},
        )
    )

    selection_seed_path = _resolve_path(package_root, manifest["domains"]["selection_task_seed"]["path"])
    selection_seed = _load_json(selection_seed_path)
    try:
        SelectionTaskRunCreate.model_validate(selection_seed)
        checks.append(CheckResult("selection_task_seed.schema", True, "SelectionTaskRunCreate validation passed"))
    except ValidationError as exc:
        checks.append(CheckResult("selection_task_seed.schema", False, "SelectionTaskRunCreate validation failed", {"errors": exc.errors()}))

    for entry in manifest["domains"]["knowledge_documents"]:
        knowledge_path = _resolve_path(package_root, entry["path"])
        content = knowledge_path.read_text(encoding="utf-8")
        checks.append(CheckResult(f"knowledge.{knowledge_path.name}", bool(content.strip()), "knowledge document is not empty"))

    orders_path = _resolve_path(package_root, manifest["domains"]["erp_orders"]["path"])
    orders_payload = _load_json(orders_path)
    orders = orders_payload.get("items") or []
    checks.append(CheckResult("erp_orders.items", len(orders) >= 1, f"orders={len(orders)}"))

    feedback_path = _resolve_path(package_root, manifest["domains"]["crm_feedback"]["path"])
    feedback_payload = _load_json(feedback_path)
    feedback_items = feedback_payload.get("items") or []
    checks.append(CheckResult("crm_feedback.items", len(feedback_items) >= 1, f"feedback={len(feedback_items)}"))

    report_request_path = _resolve_path(package_root, manifest["domains"]["report_request"]["path"])
    report_request = _load_json(report_request_path)
    checks.append(
        CheckResult(
            "report_request.formats",
            isinstance(report_request.get("formats"), list) and len(report_request["formats"]) >= 2,
            f"formats={report_request.get('formats')}",
        )
    )

    seed_state_path = _resolve_path(package_root, manifest["domains"]["report_seed_state"]["path"])
    seed_state = _load_json(seed_state_path)
    checks.append(
        CheckResult(
            "report_seed_state.reports",
            bool(seed_state.get("reports")),
            f"reports={len(seed_state.get('reports') or {})}",
        )
    )

    return {
        "status": _status_from_checks(checks),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "checks": [item.to_dict() for item in checks],
    }


def run_runtime_baseline() -> dict[str, Any]:
    settings = _load_settings()
    payload = _collect_runtime_report(settings, include_probes=False)
    validation_failures = [item for item in payload["validation_checks"] if item["status"] == "fail"]
    return {
        "status": "passed" if not validation_failures else "failed",
        "validation_failures": validation_failures,
        **payload,
    }


def run_scenario_catalog_smoke(package_root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    manifest = _load_json(package_root / "manifest.json")
    expectation_path = _resolve_path(package_root, manifest["domains"]["external_mock_expectations"]["path"])
    expectations = _load_json(expectation_path)
    catalog = BusinessScenarioCatalogService()
    checks: list[CheckResult] = []
    resolved_cases: list[dict[str, Any]] = []

    for item in expectations:
        source = str(item["source"])
        query = str(item["query"])
        expected = str(item["expected_scenario_id"])
        resolved = catalog.resolve_external_scenario(source, query)
        actual = ((resolved or {}).get("scenario_id")) or ((resolved or {}).get("scenario") or {}).get("scenario_id")
        passed = actual == expected
        checks.append(
            CheckResult(
                f"scenario.{source}.{expected}",
                passed,
                f"query={query}",
                {"expected_scenario_id": expected, "actual_scenario_id": actual},
            )
        )
        resolved_cases.append(
            {
                "source": source,
                "query": query,
                "expected_scenario_id": expected,
                "actual_scenario_id": actual,
                "matched": passed,
            }
        )

    return {
        "status": _status_from_checks(checks),
        "cases": resolved_cases,
        "checks": [item.to_dict() for item in checks],
    }


async def run_feedback_loop_smoke(run_dir: Path, package_root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    manifest = _load_json(package_root / "manifest.json")
    source_root = PROJECT_ROOT / "artifacts" / "erp_local"
    target_root = run_dir / "erp_local"
    shutil.copytree(source_root, target_root, dirs_exist_ok=True)

    with _pushd(run_dir):
        service = LocalFeedbackLoopService()
        result = await service.run_local_loop(
            task_id=str(manifest["feedback_task_id"]),
            artifact_root=target_root.resolve().as_posix(),
        )

    checks = [
        CheckResult("feedback_loop.closed_loop_ready", bool(result.get("closed_loop_ready")), f"closed_loop_ready={result.get('closed_loop_ready')}"),
        CheckResult("feedback_loop.events", int(result.get("event_count") or 0) >= 2, f"event_count={result.get('event_count')}"),
        CheckResult("feedback_loop.bi_rows", bool((result.get("bi_kpi") or {}).get("rows")), "bi_kpi rows generated"),
        CheckResult("feedback_loop.accuracy_points", bool((result.get("accuracy_trend") or {}).get("points")), "accuracy trend points generated"),
    ]

    outbound_dataset = target_root / "bi" / "outbound-datasets.json"
    checks.append(CheckResult("feedback_loop.outbound_dataset", outbound_dataset.exists(), str(outbound_dataset)))

    local_feature_db = run_dir / "data" / "local_feature_store.db"
    local_knowledge_db = run_dir / "data" / "local_knowledge.db"
    checks.append(CheckResult("feedback_loop.feature_store", local_feature_db.exists(), str(local_feature_db)))
    checks.append(CheckResult("feedback_loop.knowledge_store", local_knowledge_db.exists(), str(local_knowledge_db)))
    warnings: list[str] = []
    knowledge_update = result.get("knowledge_update") or {}
    vector_updates = knowledge_update.get("vector_updates") or []
    if not vector_updates:
        warnings.append("Review cases were ingested, but vector sync updates are missing; local lexical fallback remains active.")
    elif any(not bool(item.get("qdrant_indexed")) for item in vector_updates):
        warnings.append("Review cases were ingested, but Qdrant vector sync failed; local lexical fallback remains active.")

    return {
        "status": _status_from_checks(checks),
        "artifact_root": str(target_root),
        "result": result,
        "checks": [item.to_dict() for item in checks],
        "warnings": warnings,
    }


async def run_report_smoke(run_dir: Path, package_root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    manifest = _load_json(package_root / "manifest.json")
    request_path = _resolve_path(package_root, manifest["domains"]["report_request"]["path"])
    request_payload = _load_json(request_path)

    state_path = run_dir / "report_center" / "state.json"
    service = ReportCenterService(state_path=state_path)
    downloads_dir = run_dir / "report_center" / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    generated_formats: list[dict[str, Any]] = []
    checks: list[CheckResult] = []

    for report_format in request_payload["formats"]:
        report = await service.generate_custom_report(
            report_type=request_payload["report_type"],
            format=report_format,
            task_id="local-pilot-report-task",
            template_name=request_payload.get("template_name"),
            title=request_payload.get("title"),
            summary=request_payload.get("summary"),
            sections=request_payload.get("sections"),
            metrics_filter=request_payload.get("metrics_filter"),
            chart_keys=request_payload.get("chart_keys"),
            params=request_payload.get("params"),
        )
        downloaded = await service.build_download(report["report_id"])
        if downloaded is None:
            checks.append(CheckResult(f"report.{report_format}.download", False, "download payload is missing"))
            continue
        content, media_type, filename = downloaded
        output_path = downloads_dir / filename
        output_path.write_bytes(content)
        generated_formats.append(
            {
                "format": report_format,
                "report_id": report["report_id"],
                "media_type": media_type,
                "output_path": str(output_path),
                "size_bytes": len(content),
            }
        )
        checks.append(CheckResult(f"report.{report_format}.download", output_path.exists() and output_path.stat().st_size > 0, str(output_path)))

    return {
        "status": _status_from_checks(checks),
        "state_path": str(state_path),
        "downloads": generated_formats,
        "checks": [item.to_dict() for item in checks],
    }


async def run_acceptance(*, package_root: Path, output_root: Path) -> dict[str, Any]:
    run_dir = _build_run_dir(output_root)

    runtime_report = run_runtime_baseline()
    package_report = validate_local_pilot_package(package_root)
    scenario_report = run_scenario_catalog_smoke(package_root)
    feedback_report = await run_feedback_loop_smoke(run_dir, package_root)
    report_smoke = await run_report_smoke(run_dir, package_root)

    _write_json(run_dir / "runtime" / "runtime_report.json", runtime_report)
    _write_json(run_dir / "package" / "package_validation.json", package_report)
    _write_json(run_dir / "scenarios" / "scenario_checks.json", scenario_report)
    _write_json(run_dir / "feedback_loop" / "feedback_loop_result.json", feedback_report)
    _write_json(run_dir / "report_center" / "report_generation.json", report_smoke)

    steps = {
        "runtime": runtime_report["status"],
        "package": package_report["status"],
        "scenarios": scenario_report["status"],
        "feedback_loop": feedback_report["status"],
        "report_center": report_smoke["status"],
    }
    overall_status = "passed" if all(status == "passed" for status in steps.values()) else "failed"
    warnings = [item["detail"] for item in runtime_report.get("validation_checks", []) if item.get("status") == "warn"]
    warnings.extend(feedback_report.get("warnings") or [])
    summary = {
        "status": overall_status,
        "accepted": overall_status == "passed",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_dir": str(run_dir),
        "package_root": str(package_root),
        "steps": steps,
        "warnings": warnings,
        "artifacts": {
            "runtime_report": str(run_dir / "runtime" / "runtime_report.json"),
            "package_validation": str(run_dir / "package" / "package_validation.json"),
            "scenario_checks": str(run_dir / "scenarios" / "scenario_checks.json"),
            "feedback_loop_result": str(run_dir / "feedback_loop" / "feedback_loop_result.json"),
            "report_generation": str(run_dir / "report_center" / "report_generation.json"),
        },
    }
    _write_json(run_dir / "summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local pilot acceptance baseline.")
    parser.add_argument("--package-root", default=str(PACKAGE_ROOT), help="Path to the local pilot package root")
    parser.add_argument("--output-root", default=str(ARTIFACT_ROOT), help="Path to the local acceptance artifact root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = asyncio.run(
        run_acceptance(
            package_root=Path(args.package_root).resolve(),
            output_root=Path(args.output_root).resolve(),
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
