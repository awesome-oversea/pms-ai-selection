from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Any
from urllib.error import HTTPError, URLError

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.services.kafka_cluster_status_service import _inspect_kafka_connect_runtime, _inspect_local_kafka_runtime

_COMPOSE_FILE = _PROJECT_ROOT / "docker-compose.local-kafka.yml"
_ARTIFACT_PATH = _PROJECT_ROOT / "artifacts" / "ops" / "local_kafka_debezium_acceptance.json"
_EXPECTED_TOPICS = (
    "pms-data-collection",
    "pms-agent-event",
    "raw_amazon",
    "raw_tiktok",
    "raw_trends",
    "raw_1688",
    "raw_news",
    "cdc.oms",
    "cdc.crm",
)
_SQL_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS public.orders (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.orders REPLICA IDENTITY FULL;

CREATE TABLE IF NOT EXISTS public.order_items (
    item_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.order_items REPLICA IDENTITY FULL;

CREATE TABLE IF NOT EXISTS public.refunds (
    refund_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    refund_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.refunds REPLICA IDENTITY FULL;

CREATE TABLE IF NOT EXISTS public.reviews (
    review_id TEXT PRIMARY KEY,
    rating NUMERIC(4, 2) NOT NULL DEFAULT 0,
    content TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.reviews REPLICA IDENTITY FULL;

CREATE TABLE IF NOT EXISTS public.complaints (
    complaint_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'low',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.complaints REPLICA IDENTITY FULL;

CREATE TABLE IF NOT EXISTS public.customer_feedbacks (
    feedback_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    sentiment NUMERIC(4, 2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.customer_feedbacks REPLICA IDENTITY FULL;
"""

_DOCKER_CANDIDATES = (
    which("docker"),
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
)
_BASE_COMPOSE_FILE = _PROJECT_ROOT / "docker-compose.yml"
_REQUIRED_EXTERNAL_NETWORKS = ("fms_default", "pms-network")


def _resolve_docker_cli() -> str:
    for candidate in _DOCKER_CANDIDATES:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise RuntimeError("docker cli not found")


_DOCKER_CLI = _resolve_docker_cli()


def _docker_args(*args: str) -> list[str]:
    return [_DOCKER_CLI, *args]


def _step(message: str) -> None:
    print(f"[bootstrap] {message}", flush=True)


def _run(
    args: list[str],
    *,
    timeout_seconds: float = 120.0,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        input=stdin,
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


def _docker_network_exists(name: str) -> bool:
    result = subprocess.run(
        _docker_args("network", "inspect", name),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=30.0,
        check=False,
    )
    return result.returncode == 0


def _ensure_external_networks() -> None:
    for network_name in _REQUIRED_EXTERNAL_NETWORKS:
        if _docker_network_exists(network_name):
            continue
        _step(f"creating missing docker network: {network_name}")
        _run(_docker_args("network", "create", network_name), timeout_seconds=30.0)


def _ensure_base_postgres() -> None:
    _step("ensuring base postgres runtime for debezium source tables")
    _run(
        _docker_args("compose", "-f", str(_BASE_COMPOSE_FILE), "up", "-d", "postgres"),
        timeout_seconds=180.0,
    )


def _wait_for_runtime(timeout_seconds: float = 180.0) -> dict[str, Any]:
    return _wait_for_services({"zookeeper", "kafka", "kafka-init", "kafka-connect"}, timeout_seconds=timeout_seconds)


def _wait_for_services(required_services: set[str], *, timeout_seconds: float = 180.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_runtime = _inspect_local_kafka_runtime()
    while time.time() < deadline:
        last_runtime = _inspect_local_kafka_runtime()
        containers = last_runtime.get("containers") or {}
        if all(bool((containers.get(service_name) or {}).get("ready")) for service_name in required_services):
            return last_runtime
        time.sleep(5)
    raise RuntimeError(
        f"local kafka runtime not ready for {sorted(required_services)}: {json.dumps(last_runtime, ensure_ascii=False)}"
    )


def _wait_for_connectors(timeout_seconds: float = 180.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_runtime = _inspect_kafka_connect_runtime()
    while time.time() < deadline:
        last_runtime = _inspect_kafka_connect_runtime()
        if bool(last_runtime.get("all_expected_running")):
            return last_runtime
        time.sleep(5)
    raise RuntimeError(f"debezium connectors not ready: {json.dumps(last_runtime, ensure_ascii=False)}")


def _ensure_local_stack() -> None:
    _step("ensuring local kafka stack")
    _ensure_external_networks()
    _ensure_base_postgres()
    compose_prefix = _docker_args("compose", "-f", str(_COMPOSE_FILE))
    _run([*compose_prefix, "up", "-d", "--force-recreate", "zookeeper", "kafka"])
    _wait_for_services({"zookeeper", "kafka"})
    _run([*compose_prefix, "up", "-d", "--force-recreate", "kafka-init"])
    _wait_for_services({"zookeeper", "kafka", "kafka-init"})
    _run([*compose_prefix, "up", "-d", "--force-recreate", "kafka-connect"])


def _ensure_source_tables() -> None:
    _step("ensuring source tables in pms-postgres")
    _run(
        _docker_args("exec", "-i", "pms-postgres", "psql", "-U", "pms", "-d", "pms_db", "-v", "ON_ERROR_STOP=1"),
        stdin=_SQL_BOOTSTRAP,
    )


def _run_debezium_init() -> dict[str, Any]:
    _step("running debezium-init service")
    compose_prefix = _docker_args("compose", "-f", str(_COMPOSE_FILE))
    _run([*compose_prefix, "up", "-d", "--force-recreate", "debezium-init"])
    return _wait_for_services({"zookeeper", "kafka", "kafka-init", "kafka-connect", "debezium-init"})


def _list_topics() -> list[str]:
    result = _run(
        _docker_args("exec", "pms-local-kafka", "kafka-topics", "--bootstrap-server", "localhost:9092", "--list"),
        timeout_seconds=30.0,
    )
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def _emit_sample_changes(run_id: str) -> dict[str, str]:
    _step("emitting sample source changes")
    order_id = f"ord-{run_id}"
    review_id = f"review-{run_id}"
    sql = f"""
INSERT INTO public.orders (order_id, status, total_amount)
VALUES ('{order_id}', 'created', 99.90)
ON CONFLICT (order_id) DO UPDATE SET status = EXCLUDED.status, total_amount = EXCLUDED.total_amount, updated_at = NOW();
UPDATE public.orders SET status = 'paid', total_amount = 109.90, updated_at = NOW() WHERE order_id = '{order_id}';

INSERT INTO public.reviews (review_id, rating, content)
VALUES ('{review_id}', 4.10, 'local debezium bootstrap sample')
ON CONFLICT (review_id) DO UPDATE SET rating = EXCLUDED.rating, content = EXCLUDED.content, updated_at = NOW();
UPDATE public.reviews SET rating = 4.80, content = 'local debezium bootstrap sample updated', updated_at = NOW() WHERE review_id = '{review_id}';
"""
    _run(
        _docker_args("exec", "-i", "pms-postgres", "psql", "-U", "pms", "-d", "pms_db", "-v", "ON_ERROR_STOP=1"),
        stdin=sql,
    )
    return {"order_id": order_id, "review_id": review_id}


def _consume_cdc_messages(sample_ids: dict[str, str]) -> dict[str, Any]:
    _step("consuming cdc messages from pms-agent-event")
    result = _run(
        _docker_args(
            "exec",
            "pms-local-kafka",
            "kafka-console-consumer",
            "--bootstrap-server",
            "localhost:9092",
            "--topic",
            "pms-agent-event",
            "--from-beginning",
            "--timeout-ms",
            "15000",
            "--max-messages",
            "50",
        ),
        timeout_seconds=30.0,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    matched = [line for line in lines if sample_ids["order_id"] in line or sample_ids["review_id"] in line]
    envelope_ready = any('"before"' in line and '"after"' in line and '"op"' in line and '"source"' in line for line in matched)
    return {
        "message_count": len(lines),
        "matched_count": len(matched),
        "matched_messages": matched,
        "envelope_ready": envelope_ready,
    }


def _write_artifact(payload: dict[str, Any]) -> None:
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap the canonical local Kafka/Zookeeper/Kafka Connect/Debezium stack.")
    parser.add_argument(
        "--startup-only",
        action="store_true",
        help="Only ensure networks, startup, source tables, and Debezium init. Skip sample CDC emission and acceptance verification.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    started_at = datetime.now(timezone.utc).isoformat()
    artifact: dict[str, Any] = {
        "started_at": started_at,
        "compose_file": str(_COMPOSE_FILE),
        "connect_url": "http://localhost:8083",
        "mode": "startup-only" if args.startup_only else "acceptance",
    }
    try:
        _step("waiting for runtime")
        _ensure_local_stack()
        _wait_for_runtime()
        _ensure_source_tables()
        local_runtime = _run_debezium_init()
        _step("waiting for connectors to run")
        connector_runtime = _wait_for_connectors()
        topics = _list_topics()
        missing_topics = [topic for topic in _EXPECTED_TOPICS if topic not in topics]
        artifact.update(
            {
                "local_runtime": local_runtime,
                "connector_registration": {
                    "mode": "compose-service",
                    "service": "debezium-init",
                    "completed_successfully": bool(
                        ((local_runtime.get("containers") or {}).get("debezium-init") or {}).get("completed_successfully")
                    ),
                },
                "connector_runtime": connector_runtime,
                "topics": topics,
                "missing_topics": missing_topics,
            }
        )
        if args.startup_only:
            artifact["accepted"] = (
                bool(local_runtime.get("runtime_ready"))
                and not missing_topics
                and bool(connector_runtime.get("all_expected_running"))
            )
        else:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            sample_ids = _emit_sample_changes(run_id)
            time.sleep(8)
            cdc_messages = _consume_cdc_messages(sample_ids)
            artifact.update(
                {
                    "sample_ids": sample_ids,
                    "cdc_messages": cdc_messages,
                    "accepted": bool(local_runtime.get("runtime_ready"))
                    and not missing_topics
                    and bool(connector_runtime.get("all_expected_running"))
                    and bool(cdc_messages.get("envelope_ready"))
                    and int(cdc_messages.get("matched_count") or 0) >= 2,
                }
            )
    except (HTTPError, URLError, RuntimeError, OSError, TimeoutError, ValueError) as exc:
        artifact["accepted"] = False
        artifact["error"] = str(exc)
    finally:
        artifact["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_artifact(artifact)

    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0 if bool(artifact.get("accepted")) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
