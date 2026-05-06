from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover - real bootstrap environment should install neo4j-driver
    GraphDatabase = None

from src.config.settings import get_settings
from src.services.graph_rag_service import GraphRAGService

COMPOSE_FILE = PROJECT_ROOT / "docker-compose.wsl-local.yml"
ARTIFACT_PATH = PROJECT_ROOT / "artifacts" / "ops" / "local_graph_rag_neo4j_acceptance.json"
CONTAINER_NAME = "pms-neo4j-local"
NEO4J_URI = "bolt://127.0.0.1:17687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "pms_graph_dev"
NEO4J_DATABASE = "neo4j"
SAMPLE_TEXT = "EcoFlowDELTA 是一款便携电源，品牌 EcoFlow，供应商 1688供应商华东仓，与 Jackery 是竞争对手。"
DOCKER_CANDIDATES = (
    which("docker"),
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
)


def _step(message: str) -> None:
    print(f"[graph-rag-bootstrap] {message}", flush=True)


def _resolve_docker_cli() -> str:
    for candidate in DOCKER_CANDIDATES:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise RuntimeError("docker cli not found")


DOCKER_CLI = _resolve_docker_cli()


def _docker_args(*args: str) -> list[str]:
    return [DOCKER_CLI, *args]


def _run(args: list[str], *, timeout_seconds: float = 180.0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _ensure_local_neo4j() -> None:
    _step("ensuring local neo4j runtime")
    _run(_docker_args("compose", "-f", str(COMPOSE_FILE), "up", "-d", "neo4j"))


def _inspect_container_health() -> str:
    result = _run(
        _docker_args(
            "inspect",
            CONTAINER_NAME,
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        ),
        timeout_seconds=30.0,
    )
    return result.stdout.strip()


def _wait_for_neo4j(timeout_seconds: float = 180.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_status = "unknown"
    while time.time() < deadline:
        last_status = _inspect_container_health()
        if last_status == "healthy" or _probe_bolt_driver_ready():
            return {
                "container_name": CONTAINER_NAME,
                "compose_file": str(COMPOSE_FILE),
                "health_status": last_status,
                "ready": True,
                "bolt_uri": NEO4J_URI,
                "ready_check": "docker-health" if last_status == "healthy" else "bolt-driver",
            }
        time.sleep(5)
    raise RuntimeError(f"neo4j runtime not ready: health_status={last_status}")


def _run_cypher_via_driver(query: str) -> list[dict[str, Any]]:
    if GraphDatabase is None:
        raise RuntimeError("neo4j-driver not installed")
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
        connection_timeout=5.0,
    )
    try:
        driver.verify_connectivity()
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query)
            return [dict(record) for record in result]
    finally:
        driver.close()


def _probe_bolt_driver_ready() -> bool:
    try:
        records = _run_cypher_via_driver("RETURN 1 AS ok")
    except Exception:
        return False
    return bool(records and records[0].get("ok") == 1)


def _reset_graph() -> None:
    _step("resetting graph store")
    _run_cypher_via_driver("MATCH (n) DETACH DELETE n")


def _with_env(overrides: dict[str, str]) -> dict[str, str | None]:
    previous: dict[str, str | None] = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = value
    return previous


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


async def _run_graph_acceptance() -> dict[str, Any]:
    previous = _with_env(
        {
            "NEO4J_ENABLED": "true",
            "NEO4J_URI": NEO4J_URI,
            "NEO4J_USERNAME": NEO4J_USERNAME,
            "NEO4J_PASSWORD": NEO4J_PASSWORD,
            "NEO4J_DATABASE": NEO4J_DATABASE,
            "NEO4J_PREFER_LOCAL_FALLBACK": "true",
        }
    )
    get_settings.cache_clear()
    try:
        service = GraphRAGService()
        build_result = await service.build_graph_from_text(text=SAMPLE_TEXT, doc_id="local-neo4j-acceptance")
        query_result = await service.query_graph(query="EcoFlow的竞品有哪些", max_hops=2, top_k=10)
        competitor_result = await service.get_competitor_graph(brand_name="EcoFlow")
        product_result = await service.get_product_graph(product_name="EcoFlowDELTA", max_hops=2)
        status = service.get_status()
        return {
            "build_result": build_result,
            "query_result": query_result,
            "competitor_result": competitor_result,
            "product_result": product_result,
            "status": status,
        }
    finally:
        get_settings.cache_clear()
        _restore_env(previous)


def _build_acceptance_payload(runtime: dict[str, Any], graph_result: dict[str, Any]) -> dict[str, Any]:
    status = graph_result["status"]
    query_result = graph_result["query_result"]
    competitor_result = graph_result["competitor_result"]
    product_result = graph_result["product_result"]
    neo4j_status = status.get("neo4j") or {}
    accepted = (
        status.get("storage_backend") == "Neo4jGraphStore"
        and bool(neo4j_status.get("connection_verified"))
        and not neo4j_status.get("fallback_reason")
        and int((neo4j_status or {}).get("node_count") or 0) >= 4
        and int((neo4j_status or {}).get("edge_count") or 0) >= 3
        and int(query_result.get("total") or 0) >= 1
        and bool(competitor_result.get("found"))
        and bool(product_result.get("found"))
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "compose_file": str(COMPOSE_FILE),
        "runtime": runtime,
        "neo4j_target": {
            "uri": NEO4J_URI,
            "username": NEO4J_USERNAME,
            "database": NEO4J_DATABASE,
        },
        "sample_text": SAMPLE_TEXT,
        "build_result": graph_result["build_result"],
        "query_result": query_result,
        "competitor_result": competitor_result,
        "product_result": product_result,
        "status": status,
        "accepted": accepted,
    }


def main() -> int:
    artifact: dict[str, Any]
    try:
        _ensure_local_neo4j()
        runtime = _wait_for_neo4j(timeout_seconds=420.0)
        _reset_graph()
        graph_result = asyncio.run(_run_graph_acceptance())
        artifact = _build_acceptance_payload(runtime, graph_result)
    except (RuntimeError, OSError, TimeoutError, ValueError) as exc:
        artifact = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "compose_file": str(COMPOSE_FILE),
            "accepted": False,
            "error": str(exc),
        }

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0 if artifact.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
