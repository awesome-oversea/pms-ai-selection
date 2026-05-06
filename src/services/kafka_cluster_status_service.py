from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from src.config.settings import get_settings
from src.infrastructure.kafka import build_dlq_topic, check_kafka_health

_LOCAL_KAFKA_COMPOSE_PATH = Path("docker-compose.local-kafka.yml")
_LOCAL_KAFKA_REQUIRED_SERVICES = ("zookeeper", "kafka", "kafka-init", "kafka-connect", "debezium-init")
_LOCAL_KAFKA_CONTAINER_NAMES = {
    "zookeeper": "pms-local-zookeeper",
    "kafka": "pms-local-kafka",
    "kafka-init": "pms-local-kafka-init",
    "kafka-connect": "pms-local-kafka-connect",
    "debezium-init": "pms-local-debezium-init",
}
_KAFKA_CONNECT_REST_URL = "http://localhost:8083"
_EXPECTED_DEBEZIUM_CONNECTORS = ("oms-debezium-connector", "crm-debezium-connector")


def _inspect_local_kafka_compose(path: Path = _LOCAL_KAFKA_COMPOSE_PATH) -> dict[str, Any]:
    service_markers = {service: f"{service}:" for service in _LOCAL_KAFKA_REQUIRED_SERVICES}
    connect_internal_topics = ("pms-connect-configs", "pms-connect-offsets", "pms-connect-status")
    if not path.exists():
        return {
            "compose_file": str(path),
            "compose_services": [],
            "missing_services": list(_LOCAL_KAFKA_REQUIRED_SERVICES),
            "service_count": 0,
            "port_mappings": [],
            "connect_internal_topics_compacted": False,
            "ready": False,
        }

    text = path.read_text(encoding="utf-8")
    present_services = [service for service, marker in service_markers.items() if marker in text]
    missing_services = [service for service in _LOCAL_KAFKA_REQUIRED_SERVICES if service not in present_services]
    port_mappings = [mapping for mapping in ("2181:2181", "9092:9092", "8083:8083") if mapping in text]
    topic_bootstrap_ready = "pms-data-collection" in text and "pms-agent-event" in text
    connector_ready = "debezium/connect" in text and "debezium-connector-postgres" in text
    connect_internal_topics_compacted = (
        all(topic in text for topic in connect_internal_topics)
        and "cleanup.policy=compact" in text
        and "--partitions 1 --replication-factor 1 --config cleanup.policy=compact" in text
        and "kafka-topics --bootstrap-server pms-local-kafka:29092 --delete --if-exists --topic" in text
        and "kafka-configs --bootstrap-server pms-local-kafka:29092 --alter --entity-type topics" in text
    )

    return {
        "compose_file": str(path),
        "compose_services": present_services,
        "missing_services": missing_services,
        "service_count": len(present_services),
        "port_mappings": port_mappings,
        "topic_bootstrap_ready": topic_bootstrap_ready,
        "connector_ready": connector_ready,
        "connect_internal_topics_compacted": connect_internal_topics_compacted,
        "ready": not missing_services
        and len(port_mappings) == 3
        and topic_bootstrap_ready
        and connector_ready
        and connect_internal_topics_compacted,
    }


def _run_command(args: list[str], *, timeout_seconds: float = 5.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def _inspect_docker_container(container_name: str) -> dict[str, Any]:
    return_code, stdout, stderr = _run_command(["docker", "inspect", container_name])
    if return_code != 0:
        return {
            "container_name": container_name,
            "present": False,
            "running": False,
            "status": "missing",
            "healthy": False,
            "health_status": "missing",
            "error": (stderr or stdout or "docker inspect failed").strip(),
        }

    payload = json.loads(stdout)
    if not payload:
        return {
            "container_name": container_name,
            "present": False,
            "running": False,
            "status": "missing",
            "healthy": False,
            "health_status": "missing",
            "error": "docker inspect returned empty payload",
        }

    item = payload[0]
    state = item.get("State") or {}
    health = state.get("Health") or {}
    health_status = str(health.get("Status") or "none")
    status = str(state.get("Status") or "unknown")
    ports = sorted((item.get("NetworkSettings") or {}).get("Ports", {}).keys())
    return {
        "container_name": container_name,
        "present": True,
        "running": bool(state.get("Running")),
        "status": status,
        "healthy": health_status == "healthy",
        "health_status": health_status,
        "exit_code": state.get("ExitCode"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "ports": ports,
        "image": str(item.get("Config", {}).get("Image") or ""),
    }


def _inspect_local_kafka_runtime() -> dict[str, Any]:
    containers: dict[str, Any] = {}
    ready_services: list[str] = []
    present_services: list[str] = []

    for service_name in _LOCAL_KAFKA_REQUIRED_SERVICES:
        runtime = _inspect_docker_container(_LOCAL_KAFKA_CONTAINER_NAMES[service_name])
        if runtime.get("present"):
            present_services.append(service_name)

        if service_name in {"kafka-init", "debezium-init"}:
            completed_successfully = runtime.get("status") == "exited" and int(runtime.get("exit_code") or 0) == 0
            runtime["completed_successfully"] = completed_successfully
            runtime["ready"] = completed_successfully
        else:
            runtime["ready"] = bool(runtime.get("running")) and str(runtime.get("health_status") or "none") in {"healthy", "none"}

        if runtime.get("ready"):
            ready_services.append(service_name)
        containers[service_name] = runtime

    return {
        "container_names": dict(_LOCAL_KAFKA_CONTAINER_NAMES),
        "containers": containers,
        "present_services": present_services,
        "ready_services": ready_services,
        "present_service_count": len(present_services),
        "ready_service_count": len(ready_services),
        "all_required_present": len(present_services) == len(_LOCAL_KAFKA_REQUIRED_SERVICES),
        "runtime_ready": len(ready_services) == len(_LOCAL_KAFKA_REQUIRED_SERVICES),
    }


def _read_json(url: str, *, timeout_seconds: float = 3.0) -> tuple[int, Any]:
    with urlopen(url, timeout=timeout_seconds) as response:
        status_code = int(getattr(response, "status", response.getcode()))
        body = response.read().decode("utf-8")
    return status_code, json.loads(body)


def _inspect_kafka_connect_runtime(rest_url: str = _KAFKA_CONNECT_REST_URL) -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "rest_url": rest_url,
        "reachable": False,
        "http_status": None,
        "registered_connectors": [],
        "connector_count": 0,
        "connectors": {},
        "plugin_classes": [],
        "plugin_ready": False,
        "missing_expected_connectors": list(_EXPECTED_DEBEZIUM_CONNECTORS),
        "running_expected_connectors": [],
        "all_expected_running": False,
    }

    try:
        http_status, connectors_payload = _read_json(f"{rest_url}/connectors")
    except HTTPError as exc:
        runtime["http_status"] = exc.code
        runtime["error"] = str(exc)
        return runtime
    except URLError as exc:
        runtime["error"] = str(exc.reason)
        return runtime
    except Exception as exc:
        runtime["error"] = str(exc)
        return runtime

    connectors = sorted(str(item) for item in connectors_payload if isinstance(item, str))
    runtime["reachable"] = True
    runtime["http_status"] = http_status
    runtime["registered_connectors"] = connectors
    runtime["connector_count"] = len(connectors)

    try:
        _, plugins_payload = _read_json(f"{rest_url}/connector-plugins")
        plugin_classes = sorted(str(item.get("class")) for item in plugins_payload if isinstance(item, dict) and item.get("class"))
        runtime["plugin_classes"] = plugin_classes
        runtime["plugin_ready"] = "io.debezium.connector.postgresql.PostgresConnector" in plugin_classes
    except Exception as exc:
        runtime["plugin_error"] = str(exc)

    connector_details: dict[str, Any] = {}
    for connector_name in connectors:
        try:
            _, connector_payload = _read_json(f"{rest_url}/connectors/{quote(connector_name)}/status")
        except Exception as exc:
            connector_details[connector_name] = {
                "name": connector_name,
                "running": False,
                "error": str(exc),
            }
            continue

        connector_state = str((connector_payload.get("connector") or {}).get("state") or "UNKNOWN").upper()
        tasks_payload = connector_payload.get("tasks") or []
        task_states = [str(task.get("state") or "UNKNOWN").upper() for task in tasks_payload if isinstance(task, dict)]
        connector_details[connector_name] = {
            "name": connector_name,
            "type": connector_payload.get("type"),
            "connector_state": connector_state,
            "task_states": task_states,
            "task_count": len(task_states),
            "running": connector_state == "RUNNING" and all(state == "RUNNING" for state in task_states),
            "worker_id": (connector_payload.get("connector") or {}).get("worker_id"),
        }

    runtime["connectors"] = connector_details
    missing_expected_connectors = [name for name in _EXPECTED_DEBEZIUM_CONNECTORS if name not in connectors]
    running_expected_connectors = [
        name for name in _EXPECTED_DEBEZIUM_CONNECTORS if bool((connector_details.get(name) or {}).get("running"))
    ]
    runtime["missing_expected_connectors"] = missing_expected_connectors
    runtime["running_expected_connectors"] = running_expected_connectors
    runtime["all_expected_running"] = not missing_expected_connectors and len(running_expected_connectors) == len(_EXPECTED_DEBEZIUM_CONNECTORS)
    return runtime


class KafkaClusterStatusService:
    async def build_status(self) -> dict[str, Any]:
        settings = get_settings().kafka
        bootstrap_servers = [item.strip() for item in settings.bootstrap_servers.split(",") if item.strip()]
        health = await check_kafka_health()
        local_deployment = _inspect_local_kafka_compose()
        local_runtime = _inspect_local_kafka_runtime()
        kafka_connect_runtime = _inspect_kafka_connect_runtime()
        raw_topics = ["raw_amazon", "raw_tiktok", "raw_trends", "raw_1688", "raw_news"]
        topics = [
            settings.topics_data_collection,
            settings.topics_agent_event,
            *raw_topics,
            "cdc.oms",
            "cdc.crm",
            build_dlq_topic(settings.topics_data_collection),
            build_dlq_topic(settings.topics_agent_event),
        ]
        expected_connectors = [
            {"name": "oms-debezium-connector", "topic_prefix": "cdc.oms", "tables": ["public.orders", "public.order_items", "public.refunds"]},
            {"name": "crm-debezium-connector", "topic_prefix": "cdc.crm", "tables": ["public.reviews", "public.complaints", "public.customer_feedbacks"]},
        ]
        missing_connectors_payload = kafka_connect_runtime.get("missing_expected_connectors")
        running_connectors_payload = kafka_connect_runtime.get("running_expected_connectors")
        missing_connectors = list(missing_connectors_payload) if isinstance(missing_connectors_payload, list) else [item["name"] for item in expected_connectors]
        running_connectors = list(running_connectors_payload) if isinstance(running_connectors_payload, list) else []
        kafka_connect_ready = bool(kafka_connect_runtime.get("reachable")) and bool(kafka_connect_runtime.get("plugin_ready"))
        debezium_ready = kafka_connect_ready and not missing_connectors and bool(kafka_connect_runtime.get("all_expected_running"))
        return {
            "bootstrap_servers": bootstrap_servers,
            "cluster_mode": len(bootstrap_servers) >= 3,
            "broker_target_count": len(bootstrap_servers),
            "health": health,
            "topics": topics,
            "raw_topics": raw_topics,
            "topic_count": len(topics),
            "production_ready": len(bootstrap_servers) >= 3,
            "local_deployment": {
                **local_deployment,
                "runtime": local_runtime,
                "runtime_ready": bool(local_runtime.get("runtime_ready")),
                "broker": "pms-local-kafka:29092",
                "shared_network_alias": "kafka:29092",
                "external_bootstrap": "localhost:9092",
                "connect_shared_network_alias": "kafka-connect:8083",
                "topic_bootstrap_command": "kafka-topics --bootstrap-server pms-local-kafka:29092 --create --if-not-exists",
            },
            "kafka_connect": {
                "service": "kafka-connect",
                "rest_url": _KAFKA_CONNECT_REST_URL,
                "plugin": "debezium-connector-postgres",
                "ready": kafka_connect_ready,
                "runtime": kafka_connect_runtime,
            },
            "debezium": {
                "connector_class": "io.debezium.connector.postgresql.PostgresConnector",
                "connectors": expected_connectors,
                "registered_connectors": list(kafka_connect_runtime.get("registered_connectors") or []),
                "running_connectors": running_connectors,
                "missing_connectors": missing_connectors,
                "message_format": "debezium-envelope",
                "required_fields": ["before", "after", "op", "ts_ms", "source"],
                "ready": debezium_ready,
            },
            "zookeeper_mode": True,
        }
