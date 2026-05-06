from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


GATE_ARTIFACT = Path("artifacts/release/latest_gate_check.json")
MAX_GATE_AGE_HOURS = 24


def _read_gate_record() -> dict | None:
    if not GATE_ARTIFACT.exists():
        return None
    try:
        return json.loads(GATE_ARTIFACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _required_gate_mode(target: str) -> str:
    return "all" if target in {"preprod", "prod"} else "smoke"


def _gate_is_fresh(gate_record: dict | None) -> bool:
    if not gate_record:
        return False
    checked_at = gate_record.get("checked_at")
    if not checked_at:
        return False
    try:
        checked_time = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - checked_time <= timedelta(hours=MAX_GATE_AGE_HOURS)


def _gate_blocking_reason(gate_record: dict | None, required_gate_mode: str) -> str:
    if gate_record is None:
        return "release_gate_record_missing"
    if gate_record.get("status") != "passed":
        return "release_quality_gates_not_passed"
    if gate_record.get("mode") not in {required_gate_mode, "all"}:
        return f"release_gate_mode_mismatch_required_{required_gate_mode}"
    if not _gate_is_fresh(gate_record):
        return "release_gate_record_stale"
    return "release_quality_gates_not_passed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["test", "staging", "preprod", "prod"], required=True)
    parser.add_argument("--version", default="local-dev")
    parser.add_argument("--skip-gate-check", action="store_true")
    args = parser.parse_args()

    gate_record = _read_gate_record()
    required_gate_mode = _required_gate_mode(args.target)
    gate_ok = bool(
        gate_record
        and gate_record.get("status") == "passed"
        and gate_record.get("mode") in {required_gate_mode, "all"}
        and _gate_is_fresh(gate_record)
    )

    artifact_dir = Path("artifacts/release")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_gate_check and not gate_ok:
        record = {
            "target": args.target,
            "version": args.version,
            "status": "blocked",
            "blocked_at": datetime.now(timezone.utc).isoformat(),
            "required_gate_mode": required_gate_mode,
            "gate_check": gate_record,
            "blocking_reason": _gate_blocking_reason(gate_record, required_gate_mode),
        }
        (artifact_dir / "latest_release.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False))
        return 1

    record = {
        "target": args.target,
        "version": args.version,
        "status": "deployed",
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "required_gates": ["smoke", "migration-smoke"] if args.target in {"test", "staging"} else ["all"],
        "gate_check": gate_record,
    }
    (artifact_dir / "latest_release.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
