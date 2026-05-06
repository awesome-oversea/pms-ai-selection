from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from src.services.local_dify_runtime_manager import LocalDifyRuntimeManager


def test_local_dify_runtime_manager_prepares_runtime_from_upstream_fixture(tmp_path: Path) -> None:
    root = tmp_path
    upstream_docker_root = root / "docker" / "dify-self-host" / "upstream" / "1.13.3" / "docker"
    upstream_docker_root.mkdir(parents=True, exist_ok=True)
    (upstream_docker_root / ".env.example").write_text(
        "\n".join(
            [
                "CONSOLE_API_URL=",
                "CONSOLE_WEB_URL=",
                "SERVICE_API_URL=",
                "TRIGGER_URL=http://localhost",
                "APP_API_URL=",
                "APP_WEB_URL=",
                "FILES_URL=",
                "INTERNAL_FILES_URL=",
                "NEXT_PUBLIC_SOCKET_URL=ws://localhost",
                "WEB_API_CORS_ALLOW_ORIGINS=*",
                "CONSOLE_CORS_ALLOW_ORIGINS=*",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (upstream_docker_root / "docker-compose.yaml").write_text(
        yaml.safe_dump(
            {
                "services": {
                    "nginx": {"ports": ["80:80", "443:443"]},
                    "plugin_daemon": {"ports": ["5003:5003"]},
                }
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    manager = LocalDifyRuntimeManager(root, version="1.13.3")
    manifest = manager.prepare_runtime()

    compose_payload = yaml.safe_load(manager.runtime_compose_path.read_text(encoding="utf-8"))
    env_text = manager.runtime_env_path.read_text(encoding="utf-8")

    assert manifest["base_url"] == "http://localhost:58080"
    assert compose_payload["services"]["nginx"]["ports"] == ["58080:80", "58443:443"]
    assert compose_payload["services"]["plugin_daemon"]["ports"] == ["58083:5003"]
    assert "COMPOSE_PROJECT_NAME=pms-local-dify" in env_text
    assert "CONSOLE_API_URL=http://localhost:58080" in env_text
    assert "NEXT_PUBLIC_SOCKET_URL=ws://localhost:58080" in env_text


def test_up_refuses_when_required_images_are_missing(tmp_path: Path, monkeypatch) -> None:
    manager = LocalDifyRuntimeManager(tmp_path, version="1.13.3")
    manager.runtime_root.mkdir(parents=True, exist_ok=True)
    manager.runtime_env_path.write_text("", encoding="utf-8")
    manager.runtime_compose_path.write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(manager, "missing_local_images", lambda: ["langgenius/dify-api:1.13.3", "postgres:15-alpine"])

    result = manager.up()

    assert result["returncode"] == 1
    assert result["pull_policy"] == "never"
    assert result["missing_images"] == ["langgenius/dify-api:1.13.3", "postgres:15-alpine"]
    assert "--pull" in result["command"]
    assert "never" in result["command"]
    assert "bootstrap_local_dify_runtime.py up --pull" in result["stderr"]


def test_up_uses_pull_never_when_images_are_present(tmp_path: Path, monkeypatch) -> None:
    manager = LocalDifyRuntimeManager(tmp_path, version="1.13.3")
    manager.runtime_root.mkdir(parents=True, exist_ok=True)
    manager.runtime_env_path.write_text("", encoding="utf-8")
    manager.runtime_compose_path.write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(manager, "missing_local_images", lambda: [])
    monkeypatch.setattr(
        manager,
        "_run_compose",
        lambda *args, check=False: subprocess.CompletedProcess(
            args=manager.compose_command(*args),
            returncode=0,
            stdout="started",
            stderr="",
        ),
    )

    result = manager.up()

    assert result["returncode"] == 0
    assert result["pull_policy"] == "never"
    assert result["missing_images"] == []
    assert result["command"][-4:] == ["up", "-d", "--pull", "never"]


def test_pull_only_fetches_missing_images(tmp_path: Path, monkeypatch) -> None:
    manager = LocalDifyRuntimeManager(tmp_path, version="1.13.3")
    manager.runtime_root.mkdir(parents=True, exist_ok=True)
    manager.runtime_env_path.write_text("", encoding="utf-8")
    manager.runtime_compose_path.write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(manager, "configured_images", lambda: ["langgenius/dify-api:1.13.3", "postgres:15-alpine"])
    monkeypatch.setattr(manager, "image_exists_locally", lambda image: image == "postgres:15-alpine")
    monkeypatch.setattr(
        manager,
        "_run_docker",
        lambda *args, check=False: subprocess.CompletedProcess(
            args=["docker", *args],
            returncode=0,
            stdout="pulled",
            stderr="",
        ),
    )

    result = manager.pull()

    assert result["mode"] == "missing_only"
    assert result["missing_images_before_pull"] == ["langgenius/dify-api:1.13.3"]
    assert result["pulled_images"] == ["langgenius/dify-api:1.13.3"]
    assert result["skipped_existing_images"] == ["postgres:15-alpine"]
    assert result["steps"][0]["image"] == "langgenius/dify-api:1.13.3"
