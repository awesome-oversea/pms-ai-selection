from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "ops" / "local_flink_demo_job_acceptance.json"
JOBMANAGER_CONTAINER = "pms-flink-jobmanager-wsl"
TASKMANAGER_CONTAINER = "pms-flink-taskmanager-wsl"
FILE_CONTAINERS = (JOBMANAGER_CONTAINER, TASKMANAGER_CONTAINER)
REMOTE_ROOT = "/tmp/pms-flink"


@dataclass(frozen=True)
class JobSpec:
    name: str
    sql_file: Path
    sample_file: Path
    remote_dir: str
    remote_input_name: str


SPECS = {
    "feature": JobSpec(
        name="feature",
        sql_file=ROOT / "sql" / "flink_feature_processing.sql",
        sample_file=ROOT / "sql" / "samples" / "flink_feature_processing.csv",
        remote_dir="feature",
        remote_input_name="feature_input.csv",
    ),
    "trendwide": JobSpec(
        name="trendwide",
        sql_file=ROOT / "sql" / "flink_trend_wide_table.sql",
        sample_file=ROOT / "sql" / "samples" / "flink_trend_wide_table.csv",
        remote_dir="trendwide",
        remote_input_name="trendwide_input.csv",
    ),
    "forum-topic": JobSpec(
        name="forum-topic",
        sql_file=ROOT / "sql" / "flink_forum_topic_modeling.sql",
        sample_file=ROOT / "sql" / "samples" / "flink_forum_topic_modeling.csv",
        remote_dir="forum-topic",
        remote_input_name="forum_topic_input.csv",
    ),
}


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def _docker_exec(container: str, script: str) -> str:
    return _run(["docker", "exec", container, "bash", "-lc", script]).stdout


def _docker_cp(container: str, local_file: Path, remote_file: str) -> None:
    _run(["docker", "cp", str(local_file), f"{container}:{remote_file}"])


def _fetch_jobs_overview() -> dict:
    with urllib.request.urlopen("http://127.0.0.1:18081/jobs/overview", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_job_id(submit_output: str) -> str | None:
    match = re.search(r"Job ID:\s*([0-9a-f]+)", submit_output)
    return match.group(1) if match else None


def _collect_output(container: str, remote_dir: str) -> str:
    script = (
        f"if [ -d '{remote_dir}/output' ]; then "
        f"for f in $(find '{remote_dir}/output' -type f | sort); do "
        'echo "FILE:${f}"; cat "${f}"; '
        "done; fi"
    )
    return _docker_exec(container, script).strip()


def _submit(spec: JobSpec, *, keep_running: bool) -> dict:
    remote_dir = f"{REMOTE_ROOT}/{spec.remote_dir}"
    remote_sql = f"{remote_dir}/{spec.sql_file.name}"
    remote_input = f"{remote_dir}/{spec.remote_input_name}"

    for container in FILE_CONTAINERS:
        _docker_exec(container, f"rm -rf '{remote_dir}' && mkdir -p '{remote_dir}/output'")
        _docker_cp(container, spec.sample_file, remote_input)
    _docker_cp(JOBMANAGER_CONTAINER, spec.sql_file, remote_sql)

    submit_output = _docker_exec(JOBMANAGER_CONTAINER, f"sql-client.sh -f '{remote_sql}'")
    job_id = _parse_job_id(submit_output)
    time.sleep(2)
    jobs_overview = _fetch_jobs_overview()
    job_state = None
    for job in jobs_overview.get("jobs", []):
        if job.get("jid") == job_id:
            job_state = job.get("state")
            break

    cancel_output = ""
    if job_id and not keep_running and job_state == "RUNNING":
        completed = _run(
            ["docker", "exec", JOBMANAGER_CONTAINER, "bash", "-lc", f"flink cancel '{job_id}'"],
            check=False,
        )
        cancel_output = (completed.stdout or completed.stderr)[-2000:]
        time.sleep(1)

    output_preview = _collect_output(TASKMANAGER_CONTAINER, remote_dir) or _collect_output(JOBMANAGER_CONTAINER, remote_dir)

    return {
        "job": spec.name,
        "sql_file": str(spec.sql_file.relative_to(ROOT)),
        "sample_file": str(spec.sample_file.relative_to(ROOT)),
        "remote_dir": remote_dir,
        "job_id": job_id,
        "job_state_before_cancel": job_state,
        "submit_output": submit_output[-4000:],
        "cancel_output": cancel_output[-2000:],
        "output_preview": output_preview[:4000],
        "jobs_overview": jobs_overview,
        "status": "completed" if job_id and job_state in {"RUNNING", "FINISHED"} else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit local Flink SQL demo jobs to the WSL jobmanager container.")
    parser.add_argument("job", choices=[*SPECS.keys(), "all"], nargs="?", default="feature")
    parser.add_argument("--keep-running", action="store_true")
    args = parser.parse_args()

    selected = list(SPECS.values()) if args.job == "all" else [SPECS[args.job]]
    results = [_submit(spec, keep_running=args.keep_running) for spec in selected]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "container": JOBMANAGER_CONTAINER,
        "file_containers": list(FILE_CONTAINERS),
        "accepted": all(result["status"] == "completed" and result["job_id"] for result in results),
        "results": results,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
