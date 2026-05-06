from __future__ import annotations

from pathlib import Path

from src.services.kafka_cluster_status_service import _inspect_local_kafka_compose


def test_local_kafka_compose_is_no_longer_placeholder():
    compose_text = Path("docker-compose.local-kafka.yml").read_text(encoding="utf-8")

    assert "zookeeper:" in compose_text
    assert "kafka:" in compose_text
    assert "kafka-init:" in compose_text
    assert "kafka-connect:" in compose_text
    assert "debezium-init:" in compose_text
    assert "echo srvr | nc localhost 2181 | grep Mode" in compose_text
    assert "bash -lc 'echo > /dev/tcp/127.0.0.1/9092'" in compose_text
    assert "9092:9092" in compose_text
    assert "8083:8083" in compose_text
    assert "pms-data-collection" in compose_text
    assert "pms-connect-offsets" in compose_text
    assert "cleanup.policy=compact" in compose_text
    assert "--partitions 1 --replication-factor 1 --config cleanup.policy=compact" in compose_text
    assert "kafka-topics --bootstrap-server pms-local-kafka:29092 --delete --if-exists --topic" in compose_text
    assert "kafka-configs --bootstrap-server pms-local-kafka:29092 --alter --entity-type topics" in compose_text
    assert "debezium/connect" in compose_text
    assert "host.docker.internal:host-gateway" in compose_text
    assert "local_zookeeper_data:/var/lib/zookeeper/data" in compose_text
    assert "local_zookeeper_log:/var/lib/zookeeper/log" in compose_text
    assert "local_kafka_data:/var/lib/kafka/data" in compose_text
    assert "name: pms-network" in compose_text
    assert "pms-local-kafka-connect" in compose_text
    assert "kafka-connect" in compose_text


def test_inspect_local_kafka_compose_marks_compose_ready():
    payload = _inspect_local_kafka_compose()

    assert payload["compose_services"] == ["zookeeper", "kafka", "kafka-init", "kafka-connect", "debezium-init"]
    assert payload["missing_services"] == []
    assert payload["topic_bootstrap_ready"] is True
    assert payload["connector_ready"] is True
    assert payload["connect_internal_topics_compacted"] is True
    assert payload["ready"] is True
