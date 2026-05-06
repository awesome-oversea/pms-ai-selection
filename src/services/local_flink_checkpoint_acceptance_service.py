from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiokafka import AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic


@dataclass(frozen=True)
class DependencySpec:
    group: str
    artifact: str
    version: str

    @property
    def filename(self) -> str:
        return f"{self.artifact}-{self.version}.jar"

    @property
    def url(self) -> str:
        group_path = self.group.replace(".", "/")
        return f"https://repo1.maven.org/maven2/{group_path}/{self.artifact}/{self.version}/{self.filename}"


class LocalFlinkCheckpointAcceptanceService:
    DEFAULT_RUNTIME_MODE = "windows-host"
    WINDOWS_HOST_RUNTIME = "windows-host"
    DOCKER_WSL_RUNTIME = "docker-wsl"
    FLINK_REST_URL = "http://127.0.0.1:18081"
    KAFKA_CONNECT_URL = "http://127.0.0.1:8083/connectors"
    KAFKA_ADMIN_BOOTSTRAP = "localhost:9092"
    WINDOWS_FLINK_JOB_BOOTSTRAP = "localhost:9092"
    DOCKER_FLINK_JOB_BOOTSTRAP = "pms-local-kafka:29092"
    REMOTE_BUILD_ROOT = "/tmp/pms-flink-checkpoint-acceptance-build"
    REMOTE_RUN_ROOT = "/tmp/pms-flink-checkpoint-acceptance"
    JAVA_MAIN_CLASS = "com.pms.acceptance.flink.LocalKafkaCheckpointAcceptanceJob"
    DEPENDENCIES: tuple[DependencySpec, ...] = (
        DependencySpec("org.eclipse.jdt", "ecj", "3.38.0"),
        DependencySpec("org.apache.flink", "flink-connector-kafka", "4.0.0-2.0"),
        DependencySpec("org.apache.kafka", "kafka-clients", "3.9.0"),
        DependencySpec("org.apache.commons", "commons-lang3", "3.3.2"),
        DependencySpec("com.fasterxml.jackson.core", "jackson-annotations", "2.16.2"),
        DependencySpec("com.fasterxml.jackson.core", "jackson-core", "2.16.2"),
        DependencySpec("com.fasterxml.jackson.core", "jackson-databind", "2.16.2"),
        DependencySpec("com.fasterxml.jackson.datatype", "jackson-datatype-jdk8", "2.16.2"),
        DependencySpec("com.fasterxml.jackson.datatype", "jackson-datatype-jsr310", "2.16.2"),
    )

    def __init__(self, root: Path | None = None, runtime_mode: str | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.runtime_mode = (runtime_mode or self.DEFAULT_RUNTIME_MODE).strip().lower()
        self.artifact_root = self.root / "artifacts" / "local_flink_checkpoint"
        self.data_platform_root = self.root / "artifacts" / "data_platform"
        self.dependency_root = self.artifact_root / "_deps"
        self.build_root = self.artifact_root / "_build"
        self.java_source_root = (
            self.root
            / "jobs"
            / "local_flink_checkpoint_acceptance"
            / "src"
            / "main"
            / "java"
        )
        if self.runtime_mode == self.WINDOWS_HOST_RUNTIME:
            self.JOBMANAGER_CONTAINER = None
            self.TASKMANAGER_CONTAINER = None
            self.KAFKA_CONTAINER = None
            self.FLINK_JOB_BOOTSTRAP = self.WINDOWS_FLINK_JOB_BOOTSTRAP
        elif self.runtime_mode == self.DOCKER_WSL_RUNTIME:
            self.JOBMANAGER_CONTAINER = "pms-flink-jobmanager-wsl"
            self.TASKMANAGER_CONTAINER = "pms-flink-taskmanager-wsl"
            self.KAFKA_CONTAINER = "pms-local-kafka"
            self.FLINK_JOB_BOOTSTRAP = self.DOCKER_FLINK_JOB_BOOTSTRAP
        else:
            raise ValueError(f"unsupported runtime mode: {self.runtime_mode}")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _run_id() -> str:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _status_from_checks(checks: list[dict[str, Any]]) -> str:
        return "passed" if all(bool(item.get("passed")) for item in checks) else "failed"

    @staticmethod
    def build_scenario_events(product_id: str) -> dict[str, Any]:
        initial_events = [
            {
                "event_id": f"{product_id}-inventory-001",
                "product_id": product_id,
                "event_type": "inventory.updated",
                "payload": {
                    "product_id": product_id,
                    "inventory_units": 20,
                },
            },
            {
                "event_id": f"{product_id}-order-001",
                "product_id": product_id,
                "event_type": "order.updated",
                "payload": {
                    "product_id": product_id,
                    "units": 5,
                    "unit_price": 89.9,
                },
            },
            {
                "event_id": f"{product_id}-review-001",
                "product_id": product_id,
                "event_type": "review.updated",
                "payload": {
                    "product_id": product_id,
                    "rating": 4.8,
                    "feedback": "首批用户对音质和续航评价较好",
                },
            },
        ]
        fail_event = {
            "event_id": f"{product_id}-control-fail-once",
            "product_id": product_id,
            "event_type": "control.fail_once",
            "payload": {
                "product_id": product_id,
            },
        }
        post_recovery_events = [
            {
                "event_id": f"{product_id}-order-002",
                "product_id": product_id,
                "event_type": "order.updated",
                "payload": {
                    "product_id": product_id,
                    "units": 3,
                    "unit_price": 92.5,
                },
            },
            {
                "event_id": f"{product_id}-review-002",
                "product_id": product_id,
                "event_type": "review.updated",
                "payload": {
                    "product_id": product_id,
                    "rating": 4.4,
                    "feedback": "恢复后持续有好评回流，包装投诉下降",
                },
            },
        ]
        return {
            "initial_events": initial_events,
            "fail_event": fail_event,
            "post_recovery_events": post_recovery_events,
        }

    @staticmethod
    def expected_projection(product_id: str) -> dict[str, Any]:
        return {
            "product_id": product_id,
            "processed_event_count": 5,
            "sales_units": 8,
            "inventory_units": 20,
            "demand_supply_ratio": 0.4,
            "review_count": 2,
            "review_sentiment_score": 0.8,
        }

    @staticmethod
    def parse_projection_rows(raw_text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in raw_text.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    @staticmethod
    def latest_projection(
        rows: list[dict[str, Any]],
        *,
        product_id: str | None = None,
    ) -> dict[str, Any] | None:
        candidates = [row for row in rows if isinstance(row, dict)]
        if product_id is not None:
            candidates = [row for row in candidates if str(row.get("product_id") or "") == product_id]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda row: (
                int(row.get("processed_event_count") or 0),
                str(row.get("updated_at") or ""),
            ),
        )

    @staticmethod
    def projection_check(expected: dict[str, Any], actual: dict[str, Any] | None) -> dict[str, Any]:
        if actual is None:
            return {
                "passed": False,
                "detail": "projection missing",
                "evidence": {
                    "expected": expected,
                    "actual": actual,
                },
            }

        def _close(name: str, tolerance: float = 0.0001) -> bool:
            return abs(float(actual.get(name) or 0.0) - float(expected.get(name) or 0.0)) <= tolerance

        passed = (
            str(actual.get("product_id") or "") == str(expected["product_id"])
            and int(actual.get("processed_event_count") or 0) == int(expected["processed_event_count"])
            and int(actual.get("sales_units") or 0) == int(expected["sales_units"])
            and int(actual.get("inventory_units") or 0) == int(expected["inventory_units"])
            and int(actual.get("review_count") or 0) == int(expected["review_count"])
            and _close("demand_supply_ratio")
            and _close("review_sentiment_score")
        )
        return {
            "passed": passed,
            "detail": (
                f"processed={actual.get('processed_event_count')}, "
                f"sales={actual.get('sales_units')}, "
                f"ratio={actual.get('demand_supply_ratio')}, "
                f"sentiment={actual.get('review_sentiment_score')}"
            ),
            "evidence": {
                "expected": expected,
                "actual": actual,
            },
        }

    @staticmethod
    def parse_consumer_group(raw_text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in raw_text.splitlines():
            text = line.strip()
            if not text or text.startswith("GROUP") or text.startswith("Error:"):
                continue
            parts = re.split(r"\s+", text)
            if len(parts) < 6:
                continue
            try:
                current_offset = int(parts[3]) if parts[3] != "-" else None
                log_end_offset = int(parts[4]) if parts[4] != "-" else None
                lag = int(parts[5]) if parts[5] != "-" else None
            except ValueError:
                continue
            rows.append(
                {
                    "group": parts[0],
                    "topic": parts[1],
                    "partition": int(parts[2]),
                    "current_offset": current_offset,
                    "log_end_offset": log_end_offset,
                    "lag": lag,
                }
            )
        return rows

    def _build_run_dir(self, output_root: Path | None) -> Path:
        root = output_root or self.artifact_root
        run_dir = root / self._run_id()
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _run(
        self,
        args: list[str],
        *,
        timeout_seconds: float = 120.0,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            args,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout_seconds,
            check=False,
        )
        if check and completed.returncode != 0:
            raise RuntimeError(
                "command failed\n"
                f"cmd={' '.join(args)}\n"
                f"stdout={completed.stdout[-4000:]}\n"
                f"stderr={completed.stderr[-4000:]}"
            )
        return completed

    def _docker_exec(self, container: str, script: str, *, timeout_seconds: float = 120.0, check: bool = True) -> str:
        completed = self._run(
            ["docker", "exec", container, "bash", "-lc", script],
            timeout_seconds=timeout_seconds,
            check=check,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return output.strip()

    def _docker_cp_to(self, local_path: Path, container: str, remote_path: str) -> None:
        self._run(["docker", "cp", str(local_path), f"{container}:{remote_path}"], timeout_seconds=120.0)

    def _docker_cp_from(self, container: str, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if local_path.exists():
            if local_path.is_dir():
                shutil.rmtree(local_path)
            else:
                local_path.unlink()
        self._run(["docker", "cp", f"{container}:{remote_path}", str(local_path)], timeout_seconds=120.0)

    def _request_json(self, url: str) -> dict[str, Any]:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise RuntimeError(f"unexpected json payload from {url}")
        return payload

    def _env_path(self, name: str) -> Path:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            raise RuntimeError(f"{name} is required for runtime mode {self.runtime_mode}")
        return Path(raw)

    def _flink_cli_path(self) -> Path:
        flink_home = self._env_path("FLINK_HOME")
        command = flink_home / "bin" / ("flink.bat" if os.name == "nt" else "flink")
        return command

    def _kafka_consumer_groups_cli_path(self) -> Path:
        kafka_home = self._env_path("KAFKA_HOME")
        command = kafka_home / "bin" / ("kafka-consumer-groups.bat" if os.name == "nt" else "kafka-consumer-groups")
        return command

    def _java_home(self) -> Path:
        java_home = (os.environ.get("JAVA_HOME") or "").strip()
        if java_home:
            return Path(java_home)
        for candidate in (Path(r"D:\aitools\software\jdk-17.0.2"), Path(r"D:\aitools\software\jdk17")):
            if candidate.exists():
                return candidate
        raise RuntimeError("JAVA_HOME is required for runtime mode windows-host")

    def _javac_path(self) -> Path:
        java_home = self._java_home()
        command = java_home / "bin" / ("javac.exe" if os.name == "nt" else "javac")
        if not command.exists() and os.name == "nt":
            fallback = java_home / "javac.exe"
            if fallback.exists():
                return fallback
        return command

    def _host_javac_args(self, *, classes_dir: Path, dependency_jars: list[Path], java_sources: list[Path]) -> list[str]:
        classpath_entries = dependency_jars[:]
        classpath = os.pathsep.join(str(path) for path in classpath_entries)
        return [
            str(self._javac_path()),
            "-encoding",
            "UTF-8",
            "-d",
            str(classes_dir),
            "-cp",
            classpath,
            *[str(path) for path in java_sources],
        ]

    def _host_flink_submit_args(
        self,
        *,
        job_jar: Path,
        topic: str,
        group_id: str,
        output_dir: Path,
        fail_marker_path: Path,
    ) -> list[str]:
        return [
            str(self._flink_cli_path()),
            "run",
            "-d",
            "-Drestart-strategy.type=fixed-delay",
            "-Drestart-strategy.fixed-delay.attempts=2",
            "-Drestart-strategy.fixed-delay.delay=2s",
            "-c",
            self.JAVA_MAIN_CLASS,
            str(job_jar),
            "--brokers",
            self.FLINK_JOB_BOOTSTRAP,
            "--input-topic",
            topic,
            "--output-path",
            f"file://{output_dir.as_posix()}",
            "--group-id",
            group_id,
            "--fail-marker-path",
            str(fail_marker_path),
        ]

    def _host_consumer_group_describe_args(self, group_id: str) -> list[str]:
        return [
            str(self._kafka_consumer_groups_cli_path()),
            "--bootstrap-server",
            self.KAFKA_ADMIN_BOOTSTRAP,
            "--describe",
            "--group",
            group_id,
        ]

    def _host_flink_cancel_args(self, job_id: str) -> list[str]:
        return [str(self._flink_cli_path()), "cancel", job_id]

    def flink_rest_endpoint(self) -> str:
        return self.FLINK_REST_URL.rstrip("/")

    def _flink_rest_json(self, path: str) -> dict[str, Any]:
        if self.runtime_mode == self.DOCKER_WSL_RUNTIME:
            payload_raw = self._docker_exec(
                self.JOBMANAGER_CONTAINER,
                f"curl -fsS 'http://127.0.0.1:8081{path}'",
                timeout_seconds=20.0,
            )
            payload = json.loads(payload_raw)
        else:
            payload = self._request_json(f"{self.flink_rest_endpoint()}{path}")
        if not isinstance(payload, dict):
            raise RuntimeError(f"unexpected flink json payload from {path}")
        return payload

    def _download(self, spec: DependencySpec) -> Path:
        self.dependency_root.mkdir(parents=True, exist_ok=True)
        target = self.dependency_root / spec.filename
        if target.exists():
            return target
        with urllib.request.urlopen(spec.url, timeout=30) as response:
            target.write_bytes(response.read())
        return target

    def _inspect_environment(self) -> dict[str, Any]:
        flink_overview = self._flink_rest_json("/jobs/overview")
        with urllib.request.urlopen(self.KAFKA_CONNECT_URL, timeout=10) as response:
            connectors = json.loads(response.read().decode("utf-8"))

        if self.runtime_mode == self.WINDOWS_HOST_RUNTIME:
            kafka_bootstrap_reachable = True
            return {
                "generated_at": self._now_iso(),
                "runtime_mode": self.runtime_mode,
                "containers": {},
                "flink_rest_ready": isinstance(flink_overview.get("jobs"), list),
                "kafka_connectors": connectors,
                "kafka_bootstrap": {
                    "bootstrap_servers": self.FLINK_JOB_BOOTSTRAP,
                    "reachable_from_jobmanager": kafka_bootstrap_reachable,
                    "shared_stream_networks": [],
                },
                "ready": isinstance(flink_overview.get("jobs"), list) and isinstance(connectors, list),
                "stream_runtime_ready": kafka_bootstrap_reachable,
            }

        containers: dict[str, Any] = {}
        network_membership: dict[str, set[str]] = {}
        for name in (self.JOBMANAGER_CONTAINER, self.TASKMANAGER_CONTAINER, self.KAFKA_CONTAINER):
            inspect = self._run(["docker", "inspect", name], timeout_seconds=20.0)
            payload = json.loads(inspect.stdout)
            state = payload[0].get("State") or {}
            networks = payload[0].get("NetworkSettings", {}).get("Networks", {})
            network_membership[name] = set(networks.keys())
            containers[name] = {
                "present": True,
                "status": state.get("Status"),
                "running": bool(state.get("Running")),
                "networks": sorted(networks.keys()),
            }
        jobmanager_networks = network_membership[self.JOBMANAGER_CONTAINER]
        taskmanager_networks = network_membership[self.TASKMANAGER_CONTAINER]
        kafka_networks = network_membership[self.KAFKA_CONTAINER]
        shared_stream_networks = sorted((jobmanager_networks & taskmanager_networks) & kafka_networks)
        kafka_bootstrap_reachable = "fms_default" in shared_stream_networks
        return {
            "generated_at": self._now_iso(),
            "runtime_mode": self.runtime_mode,
            "containers": containers,
            "flink_rest_ready": isinstance(flink_overview.get("jobs"), list),
            "kafka_connectors": connectors,
            "kafka_bootstrap": {
                "bootstrap_servers": self.FLINK_JOB_BOOTSTRAP,
                "reachable_from_jobmanager": kafka_bootstrap_reachable,
                "shared_stream_networks": shared_stream_networks,
            },
            "ready": all(item["running"] for item in containers.values())
            and isinstance(flink_overview.get("jobs"), list)
            and isinstance(connectors, list),
            "stream_runtime_ready": kafka_bootstrap_reachable,
        }

    def _build_job(self, run_dir: Path) -> dict[str, Any]:
        local_build_dir = self.build_root / "current"
        local_build_dir.mkdir(parents=True, exist_ok=True)
        local_dep_dir = local_build_dir / "deps"
        local_classes_dir = local_build_dir / "classes"
        local_staging_dir = local_build_dir / "staging"
        jar_path = local_build_dir / "local-flink-kafka-checkpoint-acceptance-job.jar"
        remote_build_root = f"{self.REMOTE_BUILD_ROOT}/{run_dir.name.lower()}"
        java_sources = [path for path in self.java_source_root.rglob("*.java") if path.is_file()]
        latest_source_mtime = max((path.stat().st_mtime for path in java_sources), default=0.0)
        if jar_path.exists() and jar_path.stat().st_mtime >= latest_source_mtime:
            build_manifest = {
                "generated_at": self._now_iso(),
                "source_root": str(self.java_source_root),
                "classes_dir": str(local_classes_dir),
                "jar_path": str(jar_path),
                "remote_build_root": remote_build_root,
                "compile_output": "reused cached jar",
                "dependencies": [str(path) for path in local_dep_dir.glob("*.jar")],
                "reused_cached_jar": True,
            }
            self._write_json(run_dir / "job_build_manifest.json", build_manifest)
            return build_manifest
        if local_classes_dir.exists():
            shutil.rmtree(local_classes_dir)
        if local_staging_dir.exists():
            shutil.rmtree(local_staging_dir)
        local_dep_dir.mkdir(parents=True, exist_ok=True)

        dependency_paths: dict[str, Path] = {}
        for spec in self.DEPENDENCIES:
            downloaded = self._download(spec)
            copied = local_dep_dir / downloaded.name
            if copied != downloaded:
                shutil.copy2(downloaded, copied)
            dependency_paths[spec.artifact] = copied

        dependency_jars = [
            dependency_paths["flink-connector-kafka"],
            dependency_paths["kafka-clients"],
            dependency_paths["commons-lang3"],
            dependency_paths["jackson-annotations"],
            dependency_paths["jackson-core"],
            dependency_paths["jackson-databind"],
            dependency_paths["jackson-datatype-jdk8"],
            dependency_paths["jackson-datatype-jsr310"],
        ]

        if self.runtime_mode == self.WINDOWS_HOST_RUNTIME:
            local_classes_dir.mkdir(parents=True, exist_ok=True)
            completed = self._run(
                self._host_javac_args(
                    classes_dir=local_classes_dir,
                    dependency_jars=dependency_jars,
                    java_sources=java_sources,
                ),
                timeout_seconds=180.0,
                check=True,
            )
            compile_output = ((completed.stdout or "") + (completed.stderr or "")).strip()
            self._build_uber_jar(
                classes_dir=local_classes_dir,
                dependency_jars=dependency_jars,
                jar_path=jar_path,
            )
            build_manifest = {
                "generated_at": self._now_iso(),
                "source_root": str(self.java_source_root),
                "classes_dir": str(local_classes_dir),
                "jar_path": str(jar_path),
                "compile_output": compile_output[-4000:],
                "dependencies": [str(path) for path in local_dep_dir.glob("*.jar")],
                "reused_cached_jar": False,
                "runtime_mode": self.runtime_mode,
            }
            self._write_json(run_dir / "job_build_manifest.json", build_manifest)
            return build_manifest

        self._docker_exec(
            self.JOBMANAGER_CONTAINER,
            f"mkdir -p '{remote_build_root}/src' '{remote_build_root}/classes' '{remote_build_root}/lib'",
        )
        for jar_path in local_dep_dir.glob("*.jar"):
            self._docker_cp_to(jar_path, self.JOBMANAGER_CONTAINER, f"{remote_build_root}/lib/{jar_path.name}")
        self._docker_cp_to(self.java_source_root, self.JOBMANAGER_CONTAINER, f"{remote_build_root}/src")

        compile_output = self._docker_exec(
            self.JOBMANAGER_CONTAINER,
            (
                "set -euo pipefail; "
                f"mkdir -p '{remote_build_root}/classes'; "
                f"CLASSPATH=$(printf '%s:' /opt/flink/lib/*.jar {remote_build_root}/lib/*.jar); "
                f"java -jar {remote_build_root}/lib/ecj-3.38.0.jar "
                "-17 -encoding UTF-8 "
                f"-cp \"$CLASSPATH\" "
                f"-d {remote_build_root}/classes "
                "$(find "
                f"{remote_build_root}/src -name '*.java' -print)"
            ),
            timeout_seconds=180.0,
        )
        self._docker_cp_from(
            self.JOBMANAGER_CONTAINER,
            f"{remote_build_root}/classes",
            local_classes_dir,
        )

        self._build_uber_jar(
            classes_dir=local_classes_dir,
            dependency_jars=dependency_jars,
            jar_path=jar_path,
        )
        build_manifest = {
            "generated_at": self._now_iso(),
            "source_root": str(self.java_source_root),
            "classes_dir": str(local_classes_dir),
            "jar_path": str(jar_path),
            "remote_build_root": remote_build_root,
            "compile_output": compile_output[-4000:],
            "dependencies": [str(path) for path in local_dep_dir.glob("*.jar")],
            "reused_cached_jar": False,
        }
        self._write_json(run_dir / "job_build_manifest.json", build_manifest)
        return build_manifest

    def _build_uber_jar(self, *, classes_dir: Path, dependency_jars: list[Path], jar_path: Path) -> None:
        jar_path.parent.mkdir(parents=True, exist_ok=True)
        service_entries: dict[str, set[str]] = {}
        written_entries: set[str] = set()

        def _should_skip(name: str) -> bool:
            upper = name.upper()
            return (
                name.endswith("/")
                or name == "META-INF/MANIFEST.MF"
                or upper.endswith(".SF")
                or upper.endswith(".DSA")
                or upper.endswith(".RSA")
                or name.startswith("META-INF/INDEX.LIST")
            )

        with zipfile.ZipFile(jar_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest = (
                "Manifest-Version: 1.0\r\n"
                f"Main-Class: {self.JAVA_MAIN_CLASS}\r\n"
                "\r\n"
            )
            zf.writestr("META-INF/MANIFEST.MF", manifest)
            written_entries.add("META-INF/MANIFEST.MF")

            for class_file in classes_dir.rglob("*"):
                if not class_file.is_file():
                    continue
                arcname = class_file.relative_to(classes_dir).as_posix()
                zf.write(class_file, arcname)
                written_entries.add(arcname)

            for dependency_jar in dependency_jars:
                with zipfile.ZipFile(dependency_jar) as dep_zip:
                    for info in dep_zip.infolist():
                        name = info.filename
                        if _should_skip(name):
                            continue
                        if name.startswith("META-INF/services/"):
                            lines = dep_zip.read(info).decode("utf-8", errors="ignore").splitlines()
                            service_entries.setdefault(name, set()).update(line.strip() for line in lines if line.strip())
                            continue
                        if name in written_entries:
                            continue
                        zf.writestr(name, dep_zip.read(info))
                        written_entries.add(name)

            for name, lines in sorted(service_entries.items()):
                zf.writestr(name, "\n".join(sorted(lines)) + "\n")

    def _ensure_topic(self, topic: str) -> None:
        async def _ensure() -> None:
            client = AIOKafkaAdminClient(bootstrap_servers=self.KAFKA_ADMIN_BOOTSTRAP)
            await client.start()
            try:
                topics = await client.list_topics()
                if topic not in topics:
                    await client.create_topics(
                        [
                            NewTopic(
                                name=topic,
                                num_partitions=1,
                                replication_factor=1,
                            )
                        ]
                    )
                for _ in range(15):
                    topics = await client.list_topics()
                    if topic in topics:
                        return
                    await asyncio.sleep(1)
            finally:
                await client.close()
            raise RuntimeError(f"unable to verify kafka topic creation: {topic}")

        asyncio.run(_ensure())

    def _produce_events(self, topic: str, events: list[dict[str, Any]], artifact_path: Path) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
            encoding="utf-8",
        )
        async def _produce() -> None:
            producer = AIOKafkaProducer(
                bootstrap_servers=self.KAFKA_ADMIN_BOOTSTRAP,
                value_serializer=lambda item: json.dumps(item, ensure_ascii=False).encode("utf-8"),
            )
            await producer.start()
            try:
                for item in events:
                    await producer.send_and_wait(topic, item)
            finally:
                await producer.stop()

        asyncio.run(_produce())

    def _submit_job(
        self,
        *,
        job_jar: Path,
        topic: str,
        group_id: str,
        run_dir_name: str,
    ) -> dict[str, Any]:
        if self.runtime_mode == self.WINDOWS_HOST_RUNTIME:
            run_dir = self.artifact_root / run_dir_name
            output_dir = run_dir / "output"
            fail_marker_path = run_dir / "fail-once.marker"
            output_dir.mkdir(parents=True, exist_ok=True)
            completed = self._run(
                self._host_flink_submit_args(
                    job_jar=job_jar,
                    topic=topic,
                    group_id=group_id,
                    output_dir=output_dir,
                    fail_marker_path=fail_marker_path,
                ),
                timeout_seconds=120.0,
                check=True,
            )
            submit_output = ((completed.stdout or "") + (completed.stderr or "")).strip()
            match = re.search(r"JobID\s+([0-9A-Za-z_-]+)", submit_output, flags=re.IGNORECASE)
            if not match:
                raise RuntimeError(f"unable to parse flink job id from output: {submit_output}")
            return {
                "job_id": match.group(1),
                "output_dir": str(output_dir),
                "fail_marker_path": str(fail_marker_path),
                "submit_output": submit_output,
            }

        remote_dir = f"{self.REMOTE_RUN_ROOT}/{run_dir_name}"
        remote_jar = f"{remote_dir}/{job_jar.name}"
        output_dir = f"{remote_dir}/output"
        fail_marker_path = f"{remote_dir}/fail-once.marker"
        self._docker_exec(
            self.JOBMANAGER_CONTAINER,
            f"rm -rf '{remote_dir}' && mkdir -p '{remote_dir}'",
        )
        self._docker_exec(
            self.TASKMANAGER_CONTAINER,
            f"rm -rf '{remote_dir}' && mkdir -p '{output_dir}'",
        )
        self._docker_cp_to(job_jar, self.JOBMANAGER_CONTAINER, remote_jar)
        submit_output = self._docker_exec(
            self.JOBMANAGER_CONTAINER,
            (
                "flink run -d "
                "-Drestart-strategy.type=fixed-delay "
                "-Drestart-strategy.fixed-delay.attempts=2 "
                "-Drestart-strategy.fixed-delay.delay=2s "
                f"-c {self.JAVA_MAIN_CLASS} '{remote_jar}' "
                f"--brokers {self.FLINK_JOB_BOOTSTRAP} "
                f"--input-topic {topic} "
                f"--output-path file://{output_dir} "
                f"--group-id {group_id} "
                f"--fail-marker-path {fail_marker_path}"
            ),
            timeout_seconds=120.0,
        )
        match = re.search(r"JobID\s+([0-9a-f]+)", submit_output, flags=re.IGNORECASE)
        if not match:
            raise RuntimeError(f"unable to parse flink job id from output: {submit_output}")
        return {
            "job_id": match.group(1),
            "remote_dir": remote_dir,
            "remote_jar": remote_jar,
            "output_dir": output_dir,
            "fail_marker_path": fail_marker_path,
            "submit_output": submit_output,
        }

    def _job_payload(self, job_id: str) -> dict[str, Any]:
        return self._flink_rest_json(f"/jobs/{job_id}")

    def _checkpoint_payload(self, job_id: str) -> dict[str, Any]:
        return self._flink_rest_json(f"/jobs/{job_id}/checkpoints")

    def _exceptions_payload(self, job_id: str) -> dict[str, Any]:
        try:
            return self._flink_rest_json(f"/jobs/{job_id}/exceptions")
        except Exception:
            return {}

    def _wait_for_running(self, job_id: str, *, timeout_seconds: float = 90.0) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        history: list[dict[str, Any]] = []
        while time.time() < deadline:
            payload = self._job_payload(job_id)
            state = str(payload.get("state") or "UNKNOWN")
            history.append({"observed_at": self._now_iso(), "state": state})
            if state == "RUNNING":
                return {"state": state, "history": history, "payload": payload}
            time.sleep(2)
        raise RuntimeError(f"job {job_id} did not reach RUNNING")

    def _wait_for_checkpoint(self, job_id: str, *, timeout_seconds: float = 120.0) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        history: list[dict[str, Any]] = []
        while time.time() < deadline:
            payload = self._checkpoint_payload(job_id)
            counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
            completed = int(counts.get("completed") or 0)
            history.append(
                {
                    "observed_at": self._now_iso(),
                    "completed": completed,
                    "restored": counts.get("restored"),
                }
            )
            if completed >= 1 and isinstance((payload.get("latest") or {}).get("completed"), dict):
                return {
                    "history": history,
                    "payload": payload,
                    "completed": completed,
                }
            time.sleep(2)
        raise RuntimeError(f"job {job_id} did not complete a checkpoint")

    def _wait_for_recovery(self, job_id: str, *, timeout_seconds: float = 120.0) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        history: list[dict[str, Any]] = []
        saw_restart = False
        while time.time() < deadline:
            payload = self._job_payload(job_id)
            state = str(payload.get("state") or "UNKNOWN")
            history.append({"observed_at": self._now_iso(), "state": state})
            if state in {"FAILING", "FAILED", "RESTARTING", "RECONCILING"}:
                saw_restart = True
            if saw_restart and state == "RUNNING":
                return {
                    "history": history,
                    "payload": payload,
                    "recovered": True,
                }
            time.sleep(2)
        raise RuntimeError(f"job {job_id} did not recover after failover")

    def _read_output_rows(self, output_dir: str) -> list[dict[str, Any]]:
        if self.runtime_mode == self.WINDOWS_HOST_RUNTIME:
            output_path = Path(output_dir)
            if not output_path.exists():
                return []
            raw_chunks: list[str] = []
            for path in sorted(output_path.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                raw_chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            return self.parse_projection_rows("\n".join(raw_chunks))

        raw_output = self._docker_exec(
            self.TASKMANAGER_CONTAINER,
            (
                f"if [ -d '{output_dir}' ]; then "
                f"find '{output_dir}' -type f ! -name '.*' | sort | while read -r f; do cat \"$f\"; echo; done; "
                "fi"
            ),
            timeout_seconds=30.0,
            check=False,
        )
        return self.parse_projection_rows(raw_output)

    def _wait_for_projection(
        self,
        *,
        output_dir: str,
        product_id: str,
        expected_event_count: int,
        timeout_seconds: float = 120.0,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            rows = self._read_output_rows(output_dir)
            latest = self.latest_projection(rows, product_id=product_id)
            if latest is not None and int(latest.get("processed_event_count") or 0) >= expected_event_count:
                return {
                    "rows": rows,
                    "latest": latest,
                }
            time.sleep(2)
        raise RuntimeError("projection output did not reach expected event count")

    def _describe_consumer_group(self, group_id: str) -> dict[str, Any]:
        if self.runtime_mode == self.WINDOWS_HOST_RUNTIME:
            try:
                completed = self._run(
                    self._host_consumer_group_describe_args(group_id),
                    timeout_seconds=30.0,
                    check=False,
                )
                raw = ((completed.stdout or "") + (completed.stderr or "")).strip()
            except Exception as exc:
                return {
                    "raw": "",
                    "rows": [],
                    "error": str(exc),
                }
            return {"raw": raw, "rows": self.parse_consumer_group(raw)}

        try:
            raw = self._docker_exec(
                self.KAFKA_CONTAINER,
                f"timeout 15 kafka-consumer-groups --bootstrap-server {self.KAFKA_ADMIN_BOOTSTRAP} --describe --group {group_id}",
                timeout_seconds=30.0,
                check=False,
            )
        except Exception as exc:
            return {
                "raw": "",
                "rows": [],
                "error": str(exc),
            }
        return {"raw": raw, "rows": self.parse_consumer_group(raw)}

    def _cancel_job(self, job_id: str) -> str:
        if self.runtime_mode == self.WINDOWS_HOST_RUNTIME:
            completed = self._run(
                self._host_flink_cancel_args(job_id),
                timeout_seconds=60.0,
                check=False,
            )
            return ((completed.stdout or "") + (completed.stderr or "")).strip()
        return self._docker_exec(
            self.JOBMANAGER_CONTAINER,
            f"flink cancel {job_id}",
            timeout_seconds=60.0,
            check=False,
        )

    def run(self, *, output_root: Path | None = None) -> dict[str, Any]:
        run_dir = self._build_run_dir(output_root)
        summary_path = run_dir / "summary.json"
        partial_artifacts: dict[str, Any] = {"summary": str(summary_path)}
        job_id: str | None = None
        environment: dict[str, Any] = {}
        try:
            product_id = "selection-task-flink-checkpoint-us-001"
            topic = f"pms-flink-checkpoint-{run_dir.name.lower()}"
            group_id = f"pms-flink-checkpoint-group-{run_dir.name.lower()}"
            scenario = self.build_scenario_events(product_id)
            expected = self.expected_projection(product_id)

            environment = self._inspect_environment()
            self._write_json(run_dir / "environment.json", environment)
            partial_artifacts["environment"] = str(run_dir / "environment.json")
            if not environment.get("ready"):
                raise RuntimeError("local flink/kafka environment is not ready")
            if not environment.get("stream_runtime_ready"):
                raise RuntimeError(
                    "jobmanager cannot reach kafka bootstrap pms-local-kafka:29092; "
                    "ensure Kafka joins the fms_default network before running acceptance"
                )

            build_manifest = self._build_job(run_dir)
            partial_artifacts["job_build_manifest"] = str(run_dir / "job_build_manifest.json")
            job_jar = Path(build_manifest["jar_path"])

            self._ensure_topic(topic)
            submit_payload = self._submit_job(
                job_jar=job_jar,
                topic=topic,
                group_id=group_id,
                run_dir_name=run_dir.name.lower(),
            )
            job_id = submit_payload["job_id"]
            self._write_json(run_dir / "job_submit.json", submit_payload)
            partial_artifacts["job_submit"] = str(run_dir / "job_submit.json")

            running_status = self._wait_for_running(job_id)
            self._write_json(run_dir / "job_running.json", running_status)
            partial_artifacts["job_running"] = str(run_dir / "job_running.json")

            self._produce_events(topic, scenario["initial_events"], run_dir / "input_events_initial.jsonl")
            self._write_json(run_dir / "scenario_events.json", scenario)
            partial_artifacts["scenario_events"] = str(run_dir / "scenario_events.json")

            checkpoint_result = self._wait_for_checkpoint(job_id)
            self._write_json(run_dir / "checkpoint_status.json", checkpoint_result)
            partial_artifacts["checkpoint_status"] = str(run_dir / "checkpoint_status.json")

            consumer_group_after_checkpoint = self._describe_consumer_group(group_id)
            self._write_json(run_dir / "consumer_group_after_checkpoint.json", consumer_group_after_checkpoint)
            partial_artifacts["consumer_group_after_checkpoint"] = str(
                run_dir / "consumer_group_after_checkpoint.json"
            )

            self._produce_events(topic, [scenario["fail_event"]], run_dir / "input_event_fail_once.jsonl")
            recovery_result = self._wait_for_recovery(job_id)
            self._write_json(run_dir / "recovery_status.json", recovery_result)
            partial_artifacts["recovery_status"] = str(run_dir / "recovery_status.json")

            self._produce_events(topic, scenario["post_recovery_events"], run_dir / "input_events_post_recovery.jsonl")
            projection_result = self._wait_for_projection(
                output_dir=submit_payload["output_dir"],
                product_id=product_id,
                expected_event_count=expected["processed_event_count"],
            )
            self._write_json(run_dir / "projection_rows.json", projection_result["rows"])
            partial_artifacts["projection_rows"] = str(run_dir / "projection_rows.json")

            checkpoints_payload = self._checkpoint_payload(job_id)
            self._write_json(run_dir / "checkpoint_payload.json", checkpoints_payload)
            partial_artifacts["checkpoint_payload"] = str(run_dir / "checkpoint_payload.json")

            exceptions_payload = self._exceptions_payload(job_id)
            self._write_json(run_dir / "exceptions_payload.json", exceptions_payload)
            partial_artifacts["exceptions_payload"] = str(run_dir / "exceptions_payload.json")

            consumer_group_final = self._describe_consumer_group(group_id)
            self._write_json(run_dir / "consumer_group_final.json", consumer_group_final)
            partial_artifacts["consumer_group_final"] = str(run_dir / "consumer_group_final.json")

            projection_check = self.projection_check(expected, projection_result["latest"])
            checkpoint_completed = int((checkpoints_payload.get("counts") or {}).get("completed") or 0)
            latest_completed = (checkpoints_payload.get("latest") or {}).get("completed") or {}
            restart_states = {
                item["state"] for item in recovery_result["history"] if item["state"] in {"FAILING", "FAILED", "RESTARTING", "RECONCILING"}
            }
            checks = [
                {
                    "name": "kafka_real_topic_events_written",
                    "passed": True,
                    "detail": f"initial={len(scenario['initial_events'])}, post_recovery={len(scenario['post_recovery_events'])}",
                    "evidence": {
                        "input_topic": topic,
                        "initial_events": scenario["initial_events"],
                        "fail_event": scenario["fail_event"],
                        "post_recovery_events": scenario["post_recovery_events"],
                    },
                },
                {
                    "name": "flink_job_has_completed_checkpoint",
                    "passed": checkpoint_completed >= 1 and bool(latest_completed),
                    "detail": f"completed_checkpoints={checkpoint_completed}",
                    "evidence": checkpoints_payload,
                },
                {
                    "name": "flink_job_recovers_after_controlled_failure",
                    "passed": bool(restart_states) and bool(recovery_result.get("recovered")),
                    "detail": f"restart_states={sorted(restart_states)}",
                    "evidence": {
                        "recovery_status": recovery_result,
                        "exceptions": exceptions_payload,
                    },
                },
                {
                    "name": "feature_projection_matches_expected_business_metrics",
                    **projection_check,
                },
                {
                    "name": "runtime_summary_synced_to_data_platform_artifact",
                    "passed": True,
                    "detail": "latest summary written",
                    "evidence": {
                        "data_platform_artifact": str(self.data_platform_root / "flink_checkpoint_acceptance_latest.json"),
                    },
                },
            ]

            summary = {
                "status": self._status_from_checks(checks),
                "accepted": all(bool(item.get("passed")) for item in checks),
                "generated_at": self._now_iso(),
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "job_id": job_id,
                "input_topic": topic,
                "consumer_group": group_id,
                "business_context": {
                    "scenario": "本地蓝牙耳机试点实时特征投影",
                    "product_id": product_id,
                    "projection_fields": [
                        "sales_units",
                        "inventory_units",
                        "demand_supply_ratio",
                        "review_sentiment_score",
                    ],
                },
                "environment": {
                    "runtime_mode": self.runtime_mode,
                    "jobmanager": environment.get("containers", {}).get(self.JOBMANAGER_CONTAINER)
                    if self.JOBMANAGER_CONTAINER
                    else None,
                    "taskmanager": environment.get("containers", {}).get(self.TASKMANAGER_CONTAINER)
                    if self.TASKMANAGER_CONTAINER
                    else None,
                    "kafka": environment.get("containers", {}).get(self.KAFKA_CONTAINER)
                    if self.KAFKA_CONTAINER
                    else None,
                    "kafka_connectors": environment.get("kafka_connectors"),
                },
                "projection_expected": expected,
                "projection_actual": projection_result["latest"],
                "checkpoint_summary": {
                    "completed": checkpoint_completed,
                    "latest_completed": latest_completed,
                },
                "recovery_summary": {
                    "recovered": bool(recovery_result.get("recovered")),
                    "restart_states": sorted(restart_states),
                },
                "checks": checks,
                "artifacts": {
                    **partial_artifacts,
                    "summary": str(summary_path),
                },
            }
            self._write_json(summary_path, summary)
            self.data_platform_root.mkdir(parents=True, exist_ok=True)
            self._write_json(self.data_platform_root / "flink_checkpoint_acceptance_latest.json", summary)
            return summary
        except Exception as exc:
            summary = {
                "status": "failed",
                "accepted": False,
                "generated_at": self._now_iso(),
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "job_id": job_id,
                "error": str(exc),
                "environment": environment,
                "artifacts": partial_artifacts,
            }
            self._write_json(summary_path, summary)
            self.data_platform_root.mkdir(parents=True, exist_ok=True)
            self._write_json(self.data_platform_root / "flink_checkpoint_acceptance_latest.json", summary)
            return summary
        finally:
            if job_id is not None:
                cancel_output = self._cancel_job(job_id)
                with suppress(Exception):
                    self._write_json(run_dir / "job_cancel.json", {"job_id": job_id, "output": cancel_output})
