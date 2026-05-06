from __future__ import annotations

import argparse
import os
import pathlib
import sys

import local_runtime_manager


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start local dependency services for PMS with Docker Compose, without starting the backend."
    )
    parser.add_argument(
        "--with-ollama",
        action="store_true",
        help="Also start the optional Ollama local LLM stack from docker-compose.local-llm.yml.",
    )
    parser.add_argument(
        "--with-platform",
        action="store_true",
        help="Also start the optional platform stack from docker-compose.wsl-platform.yml.",
    )
    parser.add_argument("--with-postgres-ha", action="store_true", help="Also start the optional PostgreSQL HA stack.")
    parser.add_argument("--with-qdrant-cluster", action="store_true", help="Also start the optional Qdrant HA stack.")
    parser.add_argument(
        "--with-kafka",
        action="store_true",
        help="Also start the canonical local Kafka/Zookeeper/Kafka Connect/Debezium init stack from docker-compose.local-kafka.yml.",
    )
    parser.add_argument("--print-plan", action="store_true", help="Only print the Compose dependency startup sequence.")
    return parser


def main(argv: list[str] | None = None) -> int:
    venv_python = pathlib.Path(local_runtime_manager._resolve_venv_python_path())
    venv_ready_marker = local_runtime_manager._venv_ready_marker_path()
    current_python = pathlib.Path(sys.executable).resolve()
    if venv_ready_marker.exists() and venv_python.exists() and current_python != venv_python.resolve():
        os.execv(str(venv_python), [str(venv_python), __file__, *(argv or sys.argv[1:])])

    args = _build_parser().parse_args(argv)
    settings = local_runtime_manager._load_settings()
    python_cmd = local_runtime_manager._resolve_python_command()
    steps = local_runtime_manager._build_dependency_startup_steps(
        settings,
        workspace_root=local_runtime_manager.ROOT,
        os_name=os.name,
        python_executable=python_cmd,
        include_ollama=args.with_ollama,
        include_platform=args.with_platform,
        include_postgres_ha=args.with_postgres_ha,
        include_qdrant_cluster=args.with_qdrant_cluster,
        include_kafka=args.with_kafka,
    )

    if not steps:
        print("No dependency startup steps are defined for the current local runtime scenario.")
        return 0

    if args.print_plan:
        for index, step in enumerate(steps, start=1):
            print(f"[{index}] {step['name']}: {local_runtime_manager._format_command(step['command'], os_name=os.name)}")
            print(f"    {step['description']}")
        return 0

    for step in steps:
        print(f"Starting {step['name']}: {local_runtime_manager._format_command(step['command'], os_name=os.name)}")
        if local_runtime_manager._run_command(step["command"]) != 0:
            return 1

    print("Local dependency services are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
