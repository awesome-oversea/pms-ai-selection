from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import httpx
import yaml


class LocalDifyRuntimeManager:
    DEFAULT_RELEASE_VERSION = "1.13.3"
    DEFAULT_PROJECT_NAME = "pms-local-dify"
    DEFAULT_HTTP_PORT = 58080
    DEFAULT_HTTPS_PORT = 58443
    DEFAULT_PLUGIN_DAEMON_PORT = 58083

    def __init__(
        self,
        root: Path | None = None,
        *,
        version: str | None = None,
        http_port: int = DEFAULT_HTTP_PORT,
        https_port: int = DEFAULT_HTTPS_PORT,
        plugin_daemon_port: int = DEFAULT_PLUGIN_DAEMON_PORT,
    ) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.version = version or self.DEFAULT_RELEASE_VERSION
        self.http_port = http_port
        self.https_port = https_port
        self.plugin_daemon_port = plugin_daemon_port
        self.assets_root = self.root / "docker" / "dify-self-host"
        self.upstream_root = self.assets_root / "upstream" / self.version
        self.upstream_docker_root = self.upstream_root / "docker"
        self.runtime_root = self.assets_root / "runtime" / self.version
        self.runtime_compose_path = self.runtime_root / "docker-compose.yaml"
        self.runtime_env_path = self.runtime_root / ".env"
        self.workflow_dsl_path = self.assets_root / "pms_selection_brief_workflow.dify.yml"
        self._configured_images_cache: list[str] | None = None

    @property
    def release_zip_url(self) -> str:
        return f"https://github.com/langgenius/dify/archive/refs/tags/{self.version}.zip"

    @property
    def release_tag_url(self) -> str:
        return f"https://github.com/langgenius/dify/releases/tag/{self.version}"

    @property
    def docs_url(self) -> str:
        return "https://docs.dify.ai/en/self-host/quick-start/docker-compose"

    @property
    def base_url(self) -> str:
        return f"http://localhost:{self.http_port}"

    def _download_release_archive(self, destination: Path) -> None:
        request = urllib.request.Request(
            self.release_zip_url,
            headers={"User-Agent": "pms-local-dify-runtime-bootstrap"},
        )
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as file:
            shutil.copyfileobj(response, file)

    def _extract_docker_directory(self, archive_path: Path, destination: Path) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="pms-dify-extract-"))
        try:
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(temp_dir)
            extracted_roots = [item for item in temp_dir.iterdir() if item.is_dir()]
            if not extracted_roots:
                raise RuntimeError("Failed to locate extracted Dify source directory")
            docker_root = extracted_roots[0] / "docker"
            if not docker_root.exists():
                raise RuntimeError("Official Dify release archive does not contain docker directory")
            shutil.copytree(docker_root, destination)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def ensure_upstream_docker_directory(self, *, force_refresh: bool = False) -> Path:
        if force_refresh and self.upstream_root.exists():
            shutil.rmtree(self.upstream_root)
        if self.upstream_docker_root.exists():
            return self.upstream_docker_root

        self.upstream_root.mkdir(parents=True, exist_ok=True)
        archive_path = self.upstream_root / f"dify-{self.version}.zip"
        self._download_release_archive(archive_path)
        self._extract_docker_directory(archive_path, self.upstream_docker_root)
        archive_path.unlink(missing_ok=True)
        return self.upstream_docker_root

    @staticmethod
    def _read_env_file(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        if not path.exists():
            return values
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = raw_line.partition("=")
            values[key.strip()] = value.strip()
        return values

    def _local_env_overrides(self) -> dict[str, str]:
        return {
            "COMPOSE_PROJECT_NAME": self.DEFAULT_PROJECT_NAME,
            "CONSOLE_API_URL": self.base_url,
            "CONSOLE_WEB_URL": self.base_url,
            "SERVICE_API_URL": self.base_url,
            "TRIGGER_URL": self.base_url,
            "APP_API_URL": self.base_url,
            "APP_WEB_URL": self.base_url,
            "FILES_URL": self.base_url,
            "INTERNAL_FILES_URL": "http://api:5001",
            "NEXT_PUBLIC_SOCKET_URL": f"ws://localhost:{self.http_port}",
            "WEB_API_CORS_ALLOW_ORIGINS": "*",
            "CONSOLE_CORS_ALLOW_ORIGINS": "*",
        }

    def _write_runtime_env(self) -> None:
        template_path = self.upstream_docker_root / ".env.example"
        values = self._read_env_file(template_path)
        current_values = self._read_env_file(self.runtime_env_path)
        values.update(current_values)
        values.update(self._local_env_overrides())
        lines = [
            "# Auto-generated by scripts/bootstrap_local_dify_runtime.py",
            f"# Official release: {self.version}",
            "",
        ]
        for key in sorted(values):
            lines.append(f"{key}={values[key]}")
        self.runtime_env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _patch_runtime_compose(self) -> None:
        if not self.runtime_compose_path.exists():
            raise RuntimeError("Runtime docker-compose.yaml is missing")
        compose_text = self.runtime_compose_path.read_text(encoding="utf-8")
        compose_payload = yaml.safe_load(compose_text)
        if not isinstance(compose_payload, dict):
            raise RuntimeError("Runtime compose file is invalid")
        services = compose_payload.get("services")
        if not isinstance(services, dict):
            raise RuntimeError("Runtime compose file does not define services")

        nginx_service = services.get("nginx")
        if isinstance(nginx_service, dict):
            nginx_service["ports"] = [f"{self.http_port}:80", f"{self.https_port}:443"]

        plugin_service = services.get("plugin_daemon")
        if isinstance(plugin_service, dict):
            plugin_service["ports"] = [f"{self.plugin_daemon_port}:5003"]

        self.runtime_compose_path.write_text(
            yaml.safe_dump(compose_payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def prepare_runtime(self, *, force_refresh: bool = False) -> dict[str, Any]:
        self.ensure_upstream_docker_directory(force_refresh=force_refresh)
        if force_refresh and self.runtime_root.exists():
            shutil.rmtree(self.runtime_root)
        if not self.runtime_root.exists():
            shutil.copytree(self.upstream_docker_root, self.runtime_root)
        self._patch_runtime_compose()
        self._write_runtime_env()
        self._configured_images_cache = None
        return self.build_manifest()

    def compose_command(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--env-file",
            str(self.runtime_env_path),
            "--profile",
            "postgresql",
            "-f",
            str(self.runtime_compose_path),
            *args,
        ]

    def _run_compose(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.compose_command(*args),
            cwd=self.runtime_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=check,
        )

    def _run_docker(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", *args],
            cwd=self.runtime_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=check,
        )

    @staticmethod
    def _dedupe_lines(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    def _configured_images_from_yaml(self) -> list[str]:
        compose_payload = yaml.safe_load(self.runtime_compose_path.read_text(encoding="utf-8"))
        services = compose_payload.get("services") if isinstance(compose_payload, dict) else {}
        if not isinstance(services, dict):
            return []
        images = [str(service.get("image") or "").strip() for service in services.values() if isinstance(service, dict)]
        return self._dedupe_lines(images)

    def configured_images(self) -> list[str]:
        if self._configured_images_cache is not None:
            return list(self._configured_images_cache)
        result = self._run_compose("config", "--images")
        if result.returncode == 0:
            images = self._dedupe_lines([line.strip() for line in result.stdout.splitlines()])
        else:
            images = self._configured_images_from_yaml()
        self._configured_images_cache = images
        return list(images)

    def image_exists_locally(self, image: str) -> bool:
        result = self._run_docker("image", "inspect", image)
        return result.returncode == 0

    def missing_local_images(self) -> list[str]:
        return [image for image in self.configured_images() if not self.image_exists_locally(image)]

    def pull(self, *, only_missing: bool = True) -> dict[str, Any]:
        configured_images = self.configured_images()
        missing_images = [image for image in configured_images if not self.image_exists_locally(image)]
        images_to_pull = list(missing_images if only_missing else configured_images)
        steps: list[dict[str, Any]] = []
        pulled_images: list[str] = []
        returncode = 0

        for image in images_to_pull:
            result = self._run_docker("pull", image)
            payload = self._completed_process_payload(result)
            payload["image"] = image
            steps.append(payload)
            if result.returncode == 0:
                pulled_images.append(image)
            elif returncode == 0:
                returncode = result.returncode

        skipped_existing_images = [image for image in configured_images if image not in images_to_pull]
        stdout = "\n".join(step["stdout"] for step in steps if step.get("stdout")).strip()
        stderr = "\n".join(step["stderr"] for step in steps if step.get("stderr")).strip()
        if not images_to_pull:
            stdout = "all required images already exist locally"

        return {
            "command": ["docker", "pull", "<missing-images>"] if only_missing else ["docker", "pull", "<all-configured-images>"],
            "mode": "missing_only" if only_missing else "all_configured",
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "configured_images": configured_images,
            "missing_images_before_pull": missing_images,
            "pulled_images": pulled_images,
            "skipped_existing_images": skipped_existing_images,
            "steps": steps,
        }

    def up(self) -> dict[str, Any]:
        missing_images = self.missing_local_images()
        command = self.compose_command("up", "-d", "--pull", "never")
        if missing_images:
            return {
                "command": command,
                "returncode": 1,
                "stdout": "",
                "stderr": (
                    "Refusing to start local Dify runtime because required images are missing locally. "
                    "Run `python scripts/bootstrap_local_dify_runtime.py up --pull` first. "
                    f"Missing images: {', '.join(missing_images)}"
                ),
                "pull_policy": "never",
                "missing_images": missing_images,
            }
        result = self._run_compose("up", "-d", "--pull", "never")
        payload = self._completed_process_payload(result)
        payload["pull_policy"] = "never"
        payload["missing_images"] = []
        return payload

    def down(self, *, remove_volumes: bool = False) -> dict[str, Any]:
        args = ["down"]
        if remove_volumes:
            args.append("-v")
        result = self._run_compose(*args)
        return self._completed_process_payload(result)

    def ps(self) -> dict[str, Any]:
        result = self._run_compose("ps", check=False)
        return self._completed_process_payload(result)

    @staticmethod
    def _completed_process_payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        return {
            "command": result.args,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    def wait_until_ready(self, *, timeout_seconds: float = 600.0) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        last_error: str | None = None
        url = f"{self.base_url}/console/api/setup"
        while time.time() < deadline:
            try:
                response = httpx.get(url, timeout=10.0, follow_redirects=True)
                if response.status_code == 200:
                    payload = response.json()
                    if isinstance(payload, dict) and payload.get("step") in {"not_started", "finished"}:
                        return {
                            "ready": True,
                            "status_code": response.status_code,
                            "payload": payload,
                            "url": url,
                        }
                last_error = f"unexpected status: {response.status_code}"
            except Exception as exc:  # pragma: no cover - exercised in real runtime
                last_error = str(exc)
            time.sleep(5)
        return {
            "ready": False,
            "status_code": None,
            "payload": None,
            "url": url,
            "error": last_error or "timeout waiting for local dify runtime",
        }

    def build_manifest(self) -> dict[str, Any]:
        return {
            "release_version": self.version,
            "release_zip_url": self.release_zip_url,
            "release_tag_url": self.release_tag_url,
            "docs_url": self.docs_url,
            "base_url": self.base_url,
            "http_port": self.http_port,
            "https_port": self.https_port,
            "plugin_daemon_port": self.plugin_daemon_port,
            "upstream_docker_root": str(self.upstream_docker_root),
            "runtime_root": str(self.runtime_root),
            "runtime_compose_path": str(self.runtime_compose_path),
            "runtime_env_path": str(self.runtime_env_path),
            "workflow_dsl_path": str(self.workflow_dsl_path),
            "compose_pull_command": "python scripts/bootstrap_local_dify_runtime.py up --pull",
            "compose_up_command": " ".join(self.compose_command("up", "-d", "--pull", "never")),
            "compose_down_command": " ".join(self.compose_command("down")),
        }

    def build_summary(self) -> str:
        return json.dumps(self.build_manifest(), ensure_ascii=False, indent=2)
