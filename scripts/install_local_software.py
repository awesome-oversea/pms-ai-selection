from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SOFTWARE_ROOT = Path(r"D:\aitools\software")

DEFAULT_LOCAL_TOOL_ROOT = Path(r"D:\aitools")
DEFAULT_SHARED_ROOT = Path(r"D:\aitools\shared")
DEFAULT_FMS_TOOL_ROOT = DEFAULT_LOCAL_TOOL_ROOT / "fms"
DEFAULT_OLLAMA_DATA_DIR = DEFAULT_SHARED_ROOT / "ollama"
DEFAULT_MODEL_CACHE_DIR = DEFAULT_FMS_TOOL_ROOT / "model-cache"
DEFAULT_FMS_LOG_DIR = DEFAULT_FMS_TOOL_ROOT / "logs"
DEFAULT_FMS_TEMP_DIR = DEFAULT_FMS_TOOL_ROOT / "temp"
DEFAULT_FMS_ARTIFACT_DIR = DEFAULT_FMS_TOOL_ROOT / "artifacts"
SHARED_SERVICE_DIRS = (
    "mysql",
    "postgresql",
    "redis",
    "kafka",
    "elasticsearch",
    "opensearch",
    "minio",
    "mongodb",
    "neo4j",
    "qdrant",
    "milvus",
    "clickhouse",
    "nacos",
    "kong",
    "jaeger",
    "prometheus",
    "grafana",
    "ollama",
)


@dataclass(frozen=True)
class SoftwareItem:
    key: str
    name: str
    required: bool
    install_windows: tuple[str, ...] | None
    note: str
    probe: Callable[[], tuple[bool, str]]
    remediation: str | None = None


def _run_capture(command: list[str], *, timeout: float = 10.0) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, f"{command[0]} not found"
    except Exception as exc:
        return False, str(exc)

    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
    if completed.returncode == 0:
        return True, output or "ok"
    return False, output or f"exit={completed.returncode}"


def _docker_candidates() -> tuple[Path, ...]:
    return (
        Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"),
        Path(r"C:\Program Files\Docker\Docker\resources\bin\com.docker.cli.exe"),
    )


def _software_candidate(*relative_parts: str) -> str | None:
    candidate = SOFTWARE_ROOT.joinpath(*relative_parts)
    if candidate.exists():
        return str(candidate)
    return None


def _glob_software_candidate(pattern: str) -> str | None:
    matches = sorted(SOFTWARE_ROOT.glob(pattern))
    for match in matches:
        if match.exists():
            return str(match)
    return None


def _probe_existing_path(*candidates: str) -> tuple[bool, str]:
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return True, candidate
    return False, "not found"


def _probe_existing_command(*candidates: str) -> tuple[bool, str]:
    available, resolved = _probe_existing_path(*candidates)
    if available:
        return True, resolved
    return False, "command not found"


def _resolve_command_path(*commands: str, fallbacks: tuple[Path, ...] = ()) -> str | None:
    for command in commands:
        resolved = shutil.which(command)
        if resolved:
            return resolved
    for candidate in fallbacks:
        if candidate.exists():
            return str(candidate)
    return None


def _probe_python() -> tuple[bool, str]:
    preferred_python = Path(r"D:\aitools\software\python\python.exe")
    candidates: list[str] = []
    if preferred_python.exists():
        candidates.append(str(preferred_python))

    resolved_python = _resolve_command_path("python", "py")
    if resolved_python and resolved_python not in candidates:
        candidates.append(resolved_python)

    if not candidates:
        return False, "python not found on PATH"

    for python_cmd in candidates:
        command = [python_cmd, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')"]
        ok, detail = _run_capture(command)
        if not ok:
            continue
        version_text = detail.splitlines()[-1].strip()
        try:
            major, minor, *_ = [int(part) for part in version_text.split(".")]
        except ValueError:
            return False, f"unexpected python version output: {version_text}"
        if (major, minor) < (3, 11):
            continue
        return True, f"python {version_text}"

    return False, f"python {version_text} is below 3.11"


def _local_tool_storage_paths() -> tuple[Path, Path, Path, Path, Path, Path]:
    root = Path(os.environ.get("LOCAL_TOOL_ROOT", str(DEFAULT_LOCAL_TOOL_ROOT)))
    ollama_dir = Path(os.environ.get("LOCAL_OLLAMA_DATA_DIR", str(DEFAULT_OLLAMA_DATA_DIR)))
    model_cache_dir = Path(os.environ.get("LOCAL_MODEL_CACHE_DIR", str(DEFAULT_MODEL_CACHE_DIR)))
    fms_log_dir = Path(os.environ.get("FMS_LOG_DIR", str(DEFAULT_FMS_LOG_DIR)))
    fms_temp_dir = Path(os.environ.get("FMS_TEMP_DIR", str(DEFAULT_FMS_TEMP_DIR)))
    fms_artifact_dir = Path(os.environ.get("FMS_ARTIFACT_DIR", str(DEFAULT_FMS_ARTIFACT_DIR)))
    return root, ollama_dir, model_cache_dir, fms_log_dir, fms_temp_dir, fms_artifact_dir


def _probe_local_tool_root() -> tuple[bool, str]:
    if os.name != "nt":
        return True, "not applicable on non-Windows hosts"

    root, ollama_dir, model_cache_dir, fms_log_dir, fms_temp_dir, fms_artifact_dir = _local_tool_storage_paths()
    shared_root = root / "shared"
    required_paths = (root, shared_root, ollama_dir, model_cache_dir, fms_log_dir, fms_temp_dir, fms_artifact_dir)
    invalid_drives = [str(path) for path in required_paths if path.drive.upper() != "D:"]
    if invalid_drives:
        return False, f"all heavy local assets must stay on D: drive, current={', '.join(invalid_drives)}"

    missing = [str(path) for path in required_paths if not path.exists()]
    for service_name in SHARED_SERVICE_DIRS:
        service_dir = shared_root / service_name
        if not service_dir.exists():
            missing.append(str(service_dir))
    if missing:
        return False, f"missing local storage directories: {', '.join(missing)}"

    return True, (
        f"root={root}; shared={shared_root}; ollama={ollama_dir}; model_cache={model_cache_dir}; "
        f"fms_logs={fms_log_dir}; fms_temp={fms_temp_dir}; fms_artifacts={fms_artifact_dir}"
    )


def _local_tool_root_install_command() -> tuple[str, ...]:
    return (
        sys.executable,
        "-c",
        (
            "from pathlib import Path; import os; "
            "root=Path(os.environ.get('LOCAL_TOOL_ROOT', r'D:\\aitools')); "
            "shared=root / 'shared'; "
            "ollama=Path(os.environ.get('LOCAL_OLLAMA_DATA_DIR', str(shared / 'ollama'))); "
            "model_cache=Path(os.environ.get('LOCAL_MODEL_CACHE_DIR', str(root / 'fms' / 'model-cache'))); "
            "fms_logs=Path(os.environ.get('FMS_LOG_DIR', str(root / 'fms' / 'logs'))); "
            "fms_temp=Path(os.environ.get('FMS_TEMP_DIR', str(root / 'fms' / 'temp'))); "
            "fms_artifacts=Path(os.environ.get('FMS_ARTIFACT_DIR', str(root / 'fms' / 'artifacts'))); "
            "service_names=('mysql','postgresql','redis','kafka','elasticsearch','opensearch','minio','mongodb','neo4j','qdrant','milvus','clickhouse','nacos','kong','jaeger','prometheus','grafana','ollama'); "
            "paths=[root, shared, ollama, model_cache, fms_logs, fms_temp, fms_artifacts, *[shared / name for name in service_names]]; "
            "invalid=[str(path) for path in paths if path.drive.upper() != 'D:']; "
            "assert not invalid, f'expected D: paths, got {invalid}'; "
            "[path.mkdir(parents=True, exist_ok=True) for path in paths]; "
            "print('\\n'.join(str(path) for path in paths))"
        ),
    )


def _probe_docker_cli() -> tuple[bool, str]:
    docker_cmd = _resolve_command_path("docker", fallbacks=_docker_candidates())
    if not docker_cmd:
        return False, "docker executable not found"
    ok, detail = _run_capture([docker_cmd, "version", "--format", "{{.Client.Version}}"])
    return (ok, detail if ok else f"docker CLI unavailable: {detail}")


def _probe_docker_daemon() -> tuple[bool, str]:
    docker_cmd = _resolve_command_path("docker", fallbacks=_docker_candidates())
    if not docker_cmd:
        return False, "docker executable not found"
    ok, detail = _run_capture([docker_cmd, "info", "--format", "{{.ServerVersion}}"])
    return (ok, detail if ok else f"docker daemon unavailable: {detail}")


def _probe_compose_plugin() -> tuple[bool, str]:
    docker_cmd = _resolve_command_path("docker", fallbacks=_docker_candidates())
    if not docker_cmd:
        return False, "docker executable not found"
    ok, detail = _run_capture([docker_cmd, "compose", "version"])
    return (ok, detail.splitlines()[0] if ok else f"docker compose unavailable: {detail}")


def _resolve_wsl_command() -> str | None:
    return _resolve_command_path("wsl.exe", "wsl")


def _list_wsl_distros() -> list[str]:
    wsl_cmd = _resolve_wsl_command()
    if not wsl_cmd:
        return []
    ok, detail = _run_capture([wsl_cmd, "-l", "-q"])
    if not ok:
        return []
    return [line.strip() for line in detail.splitlines() if line.strip()]


def _preferred_ubuntu_distro() -> str | None:
    distros = _list_wsl_distros()
    if not distros:
        return None
    for distro in distros:
        if distro.lower() == "ubuntu-22.04":
            return distro
    for distro in distros:
        if distro.lower().startswith("ubuntu"):
            return distro
    return distros[0]


def _probe_wsl_distribution() -> tuple[bool, str]:
    wsl_cmd = _resolve_wsl_command()
    if not wsl_cmd:
        return False, "wsl executable not found"
    distro = _preferred_ubuntu_distro()
    if not distro:
        return False, "no Ubuntu distro detected"
    return True, f"detected {distro}"


def _probe_wsl_integration() -> tuple[bool, str]:
    if os.name != "nt":
        return True, "not applicable on non-Windows hosts"
    wsl_cmd = _resolve_wsl_command()
    if not wsl_cmd:
        return False, "wsl executable not found"
    distro = _preferred_ubuntu_distro()
    if not distro:
        return False, "no Ubuntu distro detected"
    ok, detail = _run_capture(
        [
            wsl_cmd,
            "-d",
            distro,
            "sh",
            "-lc",
            "docker info --format '{{.OSType}}'",
        ]
    )
    if not ok:
        return False, f"docker not reachable inside WSL distro {distro}: {detail}"
    if "linux" not in detail.lower():
        return False, f"unexpected docker OSType from WSL distro {distro}: {detail}"
    return True, f"docker desktop integration ready in {distro}"


def _probe_node() -> tuple[bool, str]:
    node_cmd = _resolve_command_path("node")
    if not node_cmd:
        return False, "node not found on PATH"
    ok, detail = _run_capture([node_cmd, "--version"])
    return (ok, detail if ok else f"node unavailable: {detail}")


def _probe_postgresql() -> tuple[bool, str]:
    return _probe_existing_command(
        shutil.which("psql") or "",
        shutil.which("psql.exe") or "",
        _software_candidate("postgresql", "bin", "psql.exe") or "",
        _glob_software_candidate("postgres*/bin/psql.exe") or "",
    )


def _probe_redis() -> tuple[bool, str]:
    return _probe_existing_command(
        shutil.which("redis-cli") or "",
        shutil.which("redis-cli.exe") or "",
        _software_candidate("redis", "Redis-7.2.9-Windows-x64-msys2", "redis-cli.exe") or "",
        _software_candidate("redis", "redis-cli.exe") or "",
    )


def _probe_opensearch() -> tuple[bool, str]:
    ok, detail = _run_capture(["curl", "-fsS", "http://127.0.0.1:9201"])
    if ok:
        return True, detail
    return _probe_existing_command(
        _software_candidate("opensearch-2.15.0", "bin", "opensearch.bat") or "",
        _glob_software_candidate("opensearch*/*/opensearch.bat") or "",
        _glob_software_candidate("opensearch*/bin/opensearch.bat") or "",
    )


def _probe_qdrant() -> tuple[bool, str]:
    ok, detail = _run_capture(["curl", "-fsS", "http://127.0.0.1:6333/collections"])
    if ok:
        return True, detail
    return _probe_existing_command(
        _software_candidate("qdrant", "qdrant.exe") or "",
        _glob_software_candidate("qdrant*/qdrant.exe") or "",
    )


def _probe_neo4j() -> tuple[bool, str]:
    return _probe_existing_command(
        shutil.which("cypher-shell") or "",
        shutil.which("cypher-shell.bat") or "",
        _software_candidate("neo4j-community-5.23.0", "bin", "neo4j.bat") or "",
        _glob_software_candidate("neo4j*/bin/neo4j.bat") or "",
    )


def _probe_ollama() -> tuple[bool, str]:
    ollama_cmd = _resolve_command_path(
        "ollama",
        fallbacks=(Path(r"D:\aitools\software\ollama-new\ollama.exe"), Path(r"D:\aitools\software\ollama\ollama.exe")),
    )
    if not ollama_cmd:
        return False, "ollama not found"
    ok, detail = _run_capture([ollama_cmd, "--version"])
    return (ok, detail if ok else f"ollama unavailable: {detail}")


def _probe_flink() -> tuple[bool, str]:
    flink_home = (os.environ.get("FLINK_HOME") or "").strip()
    if flink_home:
        return True, flink_home
    return _probe_existing_command(
        shutil.which("flink") or "",
        shutil.which("flink.bat") or "",
        _software_candidate("flink", "bin", "flink.bat") or "",
        _glob_software_candidate("flink*/bin/flink.bat") or "",
    )


def _probe_mongodb() -> tuple[bool, str]:
    return _probe_existing_command(
        shutil.which("mongod") or "",
        shutil.which("mongod.exe") or "",
        _software_candidate("mongodb", "bin", "mongod.exe") or "",
        _software_candidate("mongodb-win32-x86_64-windows-7.0.11", "bin", "mongod.exe") or "",
        _glob_software_candidate("mongodb*/bin/mongod.exe") or "",
    )


def _probe_mysql() -> tuple[bool, str]:
    return _probe_existing_command(
        shutil.which("mysql") or "",
        shutil.which("mysql.exe") or "",
        _software_candidate("mysql", "bin", "mysql.exe") or "",
        _glob_software_candidate("mysql*/bin/mysql.exe") or "",
    )


def _probe_minio() -> tuple[bool, str]:
    ok, detail = _run_capture(["curl", "-fsS", "http://127.0.0.1:9000/minio/health/live"])
    if ok:
        return True, detail
    return _probe_existing_command(
        shutil.which("minio") or "",
        shutil.which("minio.exe") or "",
        _software_candidate("minio", "minio.exe") or "",
        _glob_software_candidate("minio*/minio.exe") or "",
    )


def _probe_elasticsearch() -> tuple[bool, str]:
    ok, detail = _run_capture(["curl", "-fsS", "http://127.0.0.1:9200"])
    if ok:
        return True, detail
    return _probe_existing_command(
        _software_candidate("elasticsearch", "elasticsearch-8.18.8", "bin", "elasticsearch.bat") or "",
        _glob_software_candidate("elasticsearch*/bin/elasticsearch.bat") or "",
        _glob_software_candidate("elasticsearch/elasticsearch*/bin/elasticsearch.bat") or "",
    )


SOFTWARE_ITEMS: tuple[SoftwareItem, ...] = (
    SoftwareItem(
        key="local-tool-root",
        name=r"Local Tool Root (D:\aitools)",
        required=True,
        install_windows=_local_tool_root_install_command(),
        note="Heavy local downloads, model caches, and tool payloads must stay off C: and live under D:\\aitools, with shared services under D:\\aitools\\shared.",
        probe=_probe_local_tool_root,
        remediation=(
            "Create D:\\aitools plus the Ollama/model-cache subdirectories, keep LOCAL_TOOL_ROOT on D:, "
            "and move Docker Desktop / WSL disk images to D: manually if you need image-layer storage off C: as well."
        ),
    ),
    SoftwareItem(
        key="python",
        name="Python 3.11+",
        required=True,
        install_windows=("winget", "install", "-e", "--id", "Python.Python.3.12"),
        note="Required to run the repo scripts and backend tooling.",
        probe=_probe_python,
    ),
    SoftwareItem(
        key="postgresql",
        name="PostgreSQL 16",
        required=False,
        install_windows=("winget", "install", "-e", "--id", "PostgreSQL.PostgreSQL.16"),
        note="Shared PostgreSQL instance for the first environment; FMS uses localhost:5432 with a dedicated database/user.",
        probe=_probe_postgresql,
    ),
    SoftwareItem(
        key="mysql",
        name="MariaDB",
        required=False,
        install_windows=None,
        note="Shared MySQL-compatible instance for AIMS and Shop local development on localhost:3306.",
        probe=_probe_mysql,
        remediation="Install MariaDB under D:\\aitools\\software\\mysql and initialize the shared data directory.",
    ),
    SoftwareItem(
        key="redis",
        name="Redis 7",
        required=False,
        install_windows=("winget", "install", "-e", "--id", "Memurai.MemuraiDeveloper"),
        note="Shared Redis instance for the first environment; FMS uses DB 4 with project-specific key prefixes.",
        probe=_probe_redis,
    ),
    SoftwareItem(
        key="minio",
        name="MinIO",
        required=False,
        install_windows=None,
        note="Shared object storage endpoint for local development on localhost:9000 with console on localhost:9001.",
        probe=_probe_minio,
        remediation="Install MinIO under D:\\aitools\\software\\minio and point it at D:\\aitools\\shared\\minio\\data.",
    ),
    SoftwareItem(
        key="kafka",
        name="Kafka 3.6",
        required=False,
        install_windows=None,
        note="Optional shared Kafka for ERP/erpPython/FMS on localhost:9092 in the first environment.",
        probe=lambda: _probe_existing_path(
            shutil.which("kafka-topics") or "",
            shutil.which("kafka-topics.bat") or "",
            _software_candidate("kafka", "bin", "windows", "kafka-topics.bat") or "",
            _software_candidate("kafka_2.13-3.6.1", "bin", "windows", "kafka-topics.bat") or "",
        ),
        remediation="Install Apache Kafka under D:\\aitools\\shared\\kafka and expose CLI tools on PATH or via KAFKA_HOME.",
    ),
    SoftwareItem(
        key="elasticsearch",
        name="Elasticsearch 8",
        required=False,
        install_windows=None,
        note="Optional shared Elasticsearch instance for ERP Python and Shop local development on localhost:9200.",
        probe=_probe_elasticsearch,
        remediation="Install Elasticsearch under D:\\aitools\\software\\elasticsearch and bind it to port 9200.",
    ),
    SoftwareItem(
        key="opensearch",
        name="OpenSearch 2",
        required=False,
        install_windows=None,
        note="Shared OpenSearch instance for FMS local development on localhost:9201.",
        probe=_probe_opensearch,
        remediation="Install OpenSearch under D:\\aitools\\shared\\opensearch and bind it to port 9201 for FMS local development.",
    ),
    SoftwareItem(
        key="qdrant",
        name="Qdrant 1.9+",
        required=False,
        install_windows=None,
        note="Shared Qdrant instance for AIMS/FMS local development on localhost:6333.",
        probe=_probe_qdrant,
        remediation="Install Qdrant under D:\\aitools\\shared\\qdrant and bind it to port 6333.",
    ),
    SoftwareItem(
        key="mongodb",
        name="MongoDB 7",
        required=False,
        install_windows=("winget", "install", "-e", "--id", "MongoDB.Server"),
        note="Shared MongoDB instance for Shop local development on localhost:27017.",
        probe=_probe_mongodb,
        remediation="Install MongoDB under D:\\aitools\\software\\mongodb and bind it to port 27017.",
    ),
    SoftwareItem(
        key="neo4j",
        name="Neo4j 5",
        required=False,
        install_windows=None,
        note="Shared Neo4j instance for FMS/Shop local development on localhost:7687.",
        probe=_probe_neo4j,
        remediation="Install Neo4j under D:\\aitools\\shared\\neo4j and enable the bolt port 7687.",
    ),
    SoftwareItem(
        key="ollama",
        name="Ollama",
        required=False,
        install_windows=("winget", "install", "-e", "--id", "Ollama.Ollama"),
        note="Shared Ollama endpoint for AIMS/FMS/Shop local development on localhost:11434.",
        probe=_probe_ollama,
    ),
    SoftwareItem(
        key="flink",
        name="Apache Flink",
        required=False,
        install_windows=None,
        note="Needed when running FMS local Flink checkpoint acceptance on the first environment with FLINK_HOME configured.",
        probe=_probe_flink,
        remediation="Install Apache Flink under D:\\aitools\\shared\\flink and set FLINK_HOME to that location.",
    ),
    SoftwareItem(
        key="docker",
        name="Docker Desktop",
        required=False,
        install_windows=("winget", "install", "-e", "--id", "Docker.DockerDesktop"),
        note="Second-environment dependency for WSL/Docker local integration, not required for first-environment Windows-native development.",
        probe=_probe_docker_cli,
    ),
    SoftwareItem(
        key="docker-daemon",
        name="Docker Daemon",
        required=False,
        install_windows=None,
        note="Second-environment dependency for Docker Compose based local integration.",
        probe=_probe_docker_daemon,
        remediation="Start Docker Desktop and confirm the Linux engine is running.",
    ),
    SoftwareItem(
        key="compose-plugin",
        name="Docker Compose Plugin",
        required=False,
        install_windows=None,
        note="Second-environment dependency for the shared WSL/Docker runtime.",
        probe=_probe_compose_plugin,
        remediation="Upgrade or reinstall Docker Desktop so the compose plugin is available.",
    ),
    SoftwareItem(
        key="wsl-distro",
        name="WSL + Ubuntu",
        required=False,
        install_windows=("wsl", "--install", "-d", "Ubuntu-22.04"),
        note="Second-environment dependency for the local integration/test runtime.",
        probe=_probe_wsl_distribution,
    ),
    SoftwareItem(
        key="wsl-integration",
        name="WSL Integration",
        required=False,
        install_windows=None,
        note="Second-environment dependency when Docker Desktop is used from Ubuntu WSL.",
        probe=_probe_wsl_integration,
        remediation="Enable Docker Desktop WSL integration for your Ubuntu distro, then restart Docker Desktop.",
    ),
    SoftwareItem(
        key="node",
        name="Node.js LTS",
        required=False,
        install_windows=("winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS"),
        note="Needed only when running the frontend locally.",
        probe=_probe_node,
    ),
)


def _run_command(command: tuple[str, ...]) -> int:
    try:
        completed = subprocess.run(list(command), check=False)
        return completed.returncode
    except FileNotFoundError as exc:
        print(f"Command not found: {command[0]} ({exc})")
        return 127


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check or install local software prerequisites for PMS.")
    parser.add_argument("--apply", action="store_true", help="Run installer commands for missing software when supported.")
    parser.add_argument("--include-node", action="store_true", help="Also manage the optional Node.js prerequisite.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    is_windows = os.name == "nt"

    selected_items = []
    for item in SOFTWARE_ITEMS:
        if item.key == "node" and not args.include_node:
            continue
        selected_items.append(item)

    missing_required = False
    for item in selected_items:
        available, detail = item.probe()
        status = "PASS" if available else ("FAIL" if item.required else "WARN")
        print(f"[{status}] {item.name}: {item.note}")
        print(f"  Probe: {detail}")
        if available:
            continue

        if item.required:
            missing_required = True

        if not is_windows:
            print("  Install command is only automated for Windows hosts. Please install manually on this platform.")
            continue

        if item.install_windows:
            print(f"  Suggested command: {' '.join(item.install_windows)}")
            if args.apply:
                print(f"  Running installer for {item.name}")
                if _run_command(item.install_windows) != 0 and item.required:
                    return 1
        elif item.remediation:
            print(f"  Manual action: {item.remediation}")
            if args.apply and item.required:
                return 1

    if args.apply and is_windows:
        print("Software prerequisite installation flow completed.")
    elif not args.apply:
        print("Dry run only. Re-run with --apply to attempt missing installs on Windows.")

    return 1 if missing_required and not args.apply else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
