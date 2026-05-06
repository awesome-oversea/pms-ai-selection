from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


OBSOLETE_CONTAINERS: tuple[str, ...] = (
    # Legacy Kafka stack names
    "pms-zookeeper",
    "pms-kafka",
    "pms-kafka-init",
    "pms-kafka-connect",
    "pms-debezium-init",
    # Canonical local Kafka stack containers can be recreated by docker-compose.local-kafka.yml;
    # if they are currently stopped, removing the stale containers is safe.
    "pms-local-zookeeper",
    "pms-local-kafka",
    "pms-local-kafka-init",
    "pms-local-kafka-connect",
    "pms-local-debezium-init",
    # Deprecated WSL/platform/HA stacks
    "pms-keycloak-wsl",
    "pms-keycloak-db-wsl",
    "pms-redis-master-wsl",
    "pms-redis-replica-1-wsl",
    "pms-redis-replica-2-wsl",
    "pms-redis-sentinel-1-wsl",
    "pms-redis-sentinel-2-wsl",
    "pms-redis-sentinel-3-wsl",
    "pms-pgpool-wsl",
    "pms-pg-primary-wsl",
    "pms-pg-standby-1-wsl",
    "pms-pg-standby-2-wsl",
    "pms-flink-jobmanager-wsl",
    "pms-flink-taskmanager-wsl",
    # Deprecated Kong migration container after switching to declarative config
    "pms-kong-migrations-local",
)

OBSOLETE_CONTAINER_DETAILS: dict[str, str] = {
    # Legacy Kafka stack names
    "pms-zookeeper": "obsolete legacy Kafka stack container",
    "pms-kafka": "obsolete legacy Kafka stack container",
    "pms-kafka-init": "obsolete legacy Kafka stack container",
    "pms-kafka-connect": "obsolete legacy Kafka stack container",
    "pms-debezium-init": "obsolete legacy Kafka stack container",
    # Canonical local Kafka stack containers can be recreated by docker-compose.local-kafka.yml
    "pms-local-zookeeper": "stopped canonical local Kafka stack container",
    "pms-local-kafka": "stopped canonical local Kafka stack container",
    "pms-local-kafka-init": "stopped canonical local Kafka stack container",
    "pms-local-kafka-connect": "stopped canonical local Kafka stack container",
    "pms-local-debezium-init": "stopped canonical local Kafka stack container",
    # Deprecated WSL/platform/HA stacks
    "pms-keycloak-wsl": "deprecated WSL Keycloak container",
    "pms-keycloak-db-wsl": "deprecated WSL Keycloak database container",
    "pms-redis-master-wsl": "deprecated WSL HA Redis container",
    "pms-redis-replica-1-wsl": "deprecated WSL HA Redis container",
    "pms-redis-replica-2-wsl": "deprecated WSL HA Redis container",
    "pms-redis-sentinel-1-wsl": "deprecated WSL HA Redis Sentinel container",
    "pms-redis-sentinel-2-wsl": "deprecated WSL HA Redis Sentinel container",
    "pms-redis-sentinel-3-wsl": "deprecated WSL HA Redis Sentinel container",
    "pms-pgpool-wsl": "deprecated WSL HA PostgreSQL Pgpool container",
    "pms-pg-primary-wsl": "deprecated WSL HA PostgreSQL primary container",
    "pms-pg-standby-1-wsl": "deprecated WSL HA PostgreSQL standby container",
    "pms-pg-standby-2-wsl": "deprecated WSL HA PostgreSQL standby container",
    "pms-flink-jobmanager-wsl": "deprecated WSL Flink JobManager container",
    "pms-flink-taskmanager-wsl": "deprecated WSL Flink TaskManager container",
    # Deprecated Kong migration container after switching to declarative config
    "pms-kong-migrations-local": "obsolete Kong migrations container",
}

ORPHAN_CONTAINER_SUFFIXES: tuple[str, ...] = (
    "_pms-kong-local",
)

OBSOLETE_VOLUMES: tuple[str, ...] = (
    "fms_zookeeper_data",
    "fms_zookeeper_log",
    "fms_kafka_data",
)

MANUAL_HOST_HINTS: tuple[str, ...] = (
    "Do not auto-uninstall Python, Docker Desktop, WSL, or Node.js from this repo script.",
    "If you previously installed an unused local Ollama outside the current workflow, remove it manually after confirming no other project still uses it.",
    "Only the canonical Kafka stack from docker-compose.local-kafka.yml is still supported.",
)


@dataclass
class CleanupItem:
    kind: str
    name: str
    exists: bool
    action: str
    ok: bool = True
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.detail is None:
            payload.pop("detail")
        return payload


def _docker_cli() -> str | None:
    for candidate in (
        shutil.which("docker"),
        r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        r"C:\Program Files\Docker\Docker\resources\bin\com.docker.cli.exe",
    ):
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def _run_capture(args: list[str], *, timeout_seconds: float = 20.0) -> tuple[int, str, str]:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout_seconds,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _container_exists(docker: str, name: str) -> bool:
    code, _, _ = _run_capture([docker, "container", "inspect", name])
    return code == 0


def _list_container_names(docker: str) -> list[str]:
    code, stdout, _ = _run_capture([docker, "ps", "-a", "--format", "{{.Names}}"])
    if code != 0:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _volume_exists(docker: str, name: str) -> bool:
    code, _, _ = _run_capture([docker, "volume", "inspect", name])
    return code == 0


def _stop_and_remove_container(docker: str, name: str) -> tuple[bool, str]:
    code, _, stderr = _run_capture([docker, "rm", "-f", name], timeout_seconds=60.0)
    return code == 0, (stderr.strip() or "removed")


def _remove_volume(docker: str, name: str) -> tuple[bool, str]:
    code, _, stderr = _run_capture([docker, "volume", "rm", name], timeout_seconds=60.0)
    return code == 0, (stderr.strip() or "removed")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean obsolete local runtime Docker resources after runtime consolidation.")
    parser.add_argument("--apply", action="store_true", help="Actually remove obsolete Docker containers and volumes.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    docker = _docker_cli()
    if not docker:
        payload = {
            "status": "failed",
            "detail": "docker cli not found",
            "manual_host_hints": list(MANUAL_HOST_HINTS),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "docker cli not found")
        return 1

    items: list[CleanupItem] = []

    for container_name in OBSOLETE_CONTAINERS:
        exists = _container_exists(docker, container_name)
        item = CleanupItem(
            kind="container",
            name=container_name,
            exists=exists,
            action="remove" if args.apply and exists else "report",
            detail=OBSOLETE_CONTAINER_DETAILS.get(container_name, "obsolete local runtime container"),
        )
        if args.apply and exists:
            item.ok, detail = _stop_and_remove_container(docker, container_name)
            item.detail = detail
        items.append(item)

    for container_name in sorted(_list_container_names(docker)):
        if container_name == "pms-kong-local":
            continue
        if not any(container_name.endswith(suffix) for suffix in ORPHAN_CONTAINER_SUFFIXES):
            continue
        item = CleanupItem(
            kind="container",
            name=container_name,
            exists=True,
            action="remove" if args.apply else "report",
            detail="orphan declarative Kong runtime duplicate",
        )
        if args.apply:
            item.ok, detail = _stop_and_remove_container(docker, container_name)
            item.detail = detail
        items.append(item)

    for volume_name in OBSOLETE_VOLUMES:
        exists = _volume_exists(docker, volume_name)
        item = CleanupItem(
            kind="volume",
            name=volume_name,
            exists=exists,
            action="remove" if args.apply and exists else "report",
            detail="obsolete legacy Kafka stack volume",
        )
        if args.apply and exists:
            item.ok, detail = _remove_volume(docker, volume_name)
            item.detail = detail
        items.append(item)

    status = "passed" if all(item.ok for item in items) else "failed"
    payload = {
        "status": status,
        "mode": "apply" if args.apply else "dry-run",
        "managed_targets": [item.to_dict() for item in items],
        "manual_host_hints": list(MANUAL_HOST_HINTS),
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"cleanup status: {status} ({payload['mode']})")
        for item in items:
            state = "present" if item.exists else "missing"
            print(f"- [{item.kind}] {item.name}: {state} -> {item.action}")
            if item.detail:
                print(f"  {item.detail}")
        print("manual host hints:")
        for hint in MANUAL_HOST_HINTS:
            print(f"- {hint}")

    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
