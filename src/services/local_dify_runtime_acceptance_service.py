from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from src.config.settings import DifySettings
from src.services.dify_workflow_service import DifyWorkflowService
from src.services.local_dify_runtime_manager import LocalDifyRuntimeManager


class LocalDifyRuntimeAcceptanceService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.manager = LocalDifyRuntimeManager(self.root)
        self.artifact_root = self.root / "artifacts" / "local_dify_runtime"
        self.ops_root = self.root / "artifacts" / "ops"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _run_id() -> str:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _status_from_checks(checks: list[dict[str, Any]]) -> str:
        return "passed" if all(bool(item.get("passed")) for item in checks) else "failed"

    def _build_run_dir(self, output_root: Path | None) -> Path:
        root = output_root or self.artifact_root
        run_dir = root / self._run_id()
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _mask_secret(value: str) -> str:
        if len(value) <= 10:
            return "*" * len(value)
        return f"{value[:6]}...{value[-4:]}"

    @staticmethod
    def _encode_password(value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _json_or_text(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _csrf_headers(client: httpx.Client) -> dict[str, str]:
        for key, value in client.cookies.items():
            if str(key).endswith("csrf_token"):
                return {"X-CSRF-Token": str(value)}
        return {}

    def _run_pytest(self, *args: str) -> dict[str, Any]:
        command = [sys.executable, "-m", "pytest", *args]
        result = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "passed": result.returncode == 0,
        }

    def _ensure_runtime_ready(self) -> dict[str, Any]:
        prepare = self.manager.prepare_runtime()
        up = self.manager.up()
        if int(up.get("returncode") or 0) == 0:
            readiness = self.manager.wait_until_ready()
        else:
            readiness = {
                "ready": False,
                "status_code": None,
                "payload": None,
                "url": f"{self.manager.base_url}/console/api/setup",
                "error": str(up.get("stderr") or up.get("stdout") or "docker compose up failed"),
            }
        return {"prepare": prepare, "up": up, "readiness": readiness}

    def _setup_admin(
        self,
        client: httpx.Client,
        *,
        admin_email: str,
        admin_name: str,
        admin_password: str,
    ) -> dict[str, Any]:
        status_response = client.get("/console/api/setup")
        status_response.raise_for_status()
        payload = self._json_or_text(status_response)
        if isinstance(payload, dict) and payload.get("step") == "finished":
            return {
                "status": "already_configured",
                "status_code": status_response.status_code,
                "payload": payload,
            }

        response = client.post(
            "/console/api/setup",
            json={
                "email": admin_email,
                "name": admin_name,
                "password": admin_password,
                "language": "zh-Hans",
            },
        )
        response.raise_for_status()
        return {
            "status": "created",
            "status_code": response.status_code,
            "payload": self._json_or_text(response),
        }

    def _login(self, client: httpx.Client, *, admin_email: str, admin_password: str) -> dict[str, Any]:
        response = client.post(
            "/console/api/login",
            json={
                "email": admin_email,
                "password": self._encode_password(admin_password),
                "remember_me": True,
            },
        )
        response.raise_for_status()
        headers = self._csrf_headers(client)
        if not headers:
            raise RuntimeError("Dify console login did not return csrf_token cookie")
        return {
            "status_code": response.status_code,
            "payload": self._json_or_text(response),
            "csrf_header": headers,
        }

    def _import_workflow(self, client: httpx.Client, *, headers: dict[str, str], run_name: str) -> dict[str, Any]:
        dsl_text = self.manager.workflow_dsl_path.read_text(encoding="utf-8")
        response = client.post(
            "/console/api/apps/imports",
            headers=headers,
            json={
                "mode": "create",
                "yaml_content": dsl_text,
                "name": f"PMS 本地 Dify 验收 {run_name}",
                "description": "PMS local Dify runtime acceptance workflow",
            },
        )
        response.raise_for_status()
        payload = self._json_or_text(response)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected workflow import response")
        if str(payload.get("status") or "").lower() == "pending":
            import_id = str(payload.get("id") or "").strip()
            if not import_id:
                raise RuntimeError("Import returned pending status without import id")
            confirm = client.post(f"/console/api/apps/imports/{import_id}/confirm", headers=headers)
            confirm.raise_for_status()
            payload = self._json_or_text(confirm)
            if not isinstance(payload, dict):
                raise RuntimeError("Unexpected workflow import confirm response")
        return payload

    def _publish_workflow(self, client: httpx.Client, *, headers: dict[str, str], app_id: str) -> dict[str, Any]:
        response = client.post(
            f"/console/api/apps/{app_id}/workflows/publish",
            headers=headers,
            json={
                "marked_name": "PMS 本地验收",
                "marked_comment": "Published by local_dify_runtime_acceptance_service",
            },
        )
        response.raise_for_status()
        return {
            "status_code": response.status_code,
            "payload": self._json_or_text(response),
        }

    def _create_api_key(self, client: httpx.Client, *, headers: dict[str, str], app_id: str) -> dict[str, Any]:
        response = client.post(f"/console/api/apps/{app_id}/api-keys", headers=headers)
        response.raise_for_status()
        payload = self._json_or_text(response)
        if not isinstance(payload, dict) or not str(payload.get("token") or "").strip():
            raise RuntimeError("Dify did not return app api key token")
        return payload

    def _verify_ui(self, client: httpx.Client) -> dict[str, Any]:
        response = client.get("/")
        return {
            "status_code": response.status_code,
            "ok": response.status_code < 400,
            "final_url": str(response.url),
        }

    def _invoke_real_runtime(self, *, api_key: str, workflow_input: dict[str, Any]) -> dict[str, Any]:
        settings = DifySettings(
            enabled=True,
            base_url=self.manager.base_url,
            api_key=api_key,
            workflow_run_path="/v1/workflows/run",
            timeout_seconds=30.0,
            response_mode="blocking",
            user_prefix="pms",
            prefer_compatible_fallback=True,
        )
        service = DifyWorkflowService(settings=settings)
        return asyncio.run(service.invoke_workflow(input_data=workflow_input))

    def run(
        self,
        *,
        output_root: Path | None = None,
        admin_email: str = "admin@pms.local",
        admin_name: str = "PMS Admin",
        admin_password: str = "PmsDify!2026",
    ) -> dict[str, Any]:
        run_dir = self._build_run_dir(output_root)
        summary_path = run_dir / "summary.json"
        partial_artifacts: dict[str, Any] = {"summary": str(summary_path)}

        environment: dict[str, Any] = {}
        try:
            environment = self._ensure_runtime_ready()
            self._write_json(run_dir / "environment.json", environment)
            partial_artifacts["environment"] = str(run_dir / "environment.json")
            readiness = environment.get("readiness") or {}
            if not readiness.get("ready"):
                raise RuntimeError(str(readiness.get("error") or "Local Dify runtime is not ready"))

            regression_results = {
                "test_dify_workflow_service": self._run_pytest("tests/test_dify_workflow_service.py", "-q"),
                "test_agent_platform_service_dify_subset": self._run_pytest(
                    "tests/test_agent_platform_service.py",
                    "-k",
                    "test_agent_platform_service_uses_real_dify_runtime_when_available or "
                    "test_agent_platform_service_falls_back_when_dify_runtime_errors",
                    "-q",
                ),
                "test_agent_service_dify_status": self._run_pytest("tests/test_agent_service_dify_status.py", "-q"),
            }
            self._write_json(run_dir / "regression_results.json", regression_results)
            partial_artifacts["regression_results"] = str(run_dir / "regression_results.json")

            workflow_input = {
                "query": "输出蓝牙耳机北美试点选品摘要",
                "category": "electronics",
                "target_market": "US",
                "request_user": "local-acceptance",
            }

            with httpx.Client(base_url=self.manager.base_url, timeout=30.0, follow_redirects=True) as client:
                ui_status = self._verify_ui(client)
                self._write_json(run_dir / "ui_status.json", ui_status)
                partial_artifacts["ui_status"] = str(run_dir / "ui_status.json")

                setup_result = self._setup_admin(
                    client,
                    admin_email=admin_email,
                    admin_name=admin_name,
                    admin_password=admin_password,
                )
                self._write_json(run_dir / "setup_result.json", setup_result)
                partial_artifacts["setup_result"] = str(run_dir / "setup_result.json")

                login_result = self._login(client, admin_email=admin_email, admin_password=admin_password)
                self._write_json(
                    run_dir / "login_result.json",
                    {
                        "status_code": login_result["status_code"],
                        "payload": login_result["payload"],
                    },
                )
                partial_artifacts["login_result"] = str(run_dir / "login_result.json")

                headers = dict(login_result["csrf_header"])
                import_result = self._import_workflow(client, headers=headers, run_name=run_dir.name)
                self._write_json(run_dir / "import_result.json", import_result)
                partial_artifacts["import_result"] = str(run_dir / "import_result.json")
                app_id = str(import_result.get("app_id") or "").strip()
                if not app_id:
                    raise RuntimeError("Workflow import did not return app_id")

                publish_result = self._publish_workflow(client, headers=headers, app_id=app_id)
                self._write_json(run_dir / "publish_result.json", publish_result)
                partial_artifacts["publish_result"] = str(run_dir / "publish_result.json")

                api_key_result = self._create_api_key(client, headers=headers, app_id=app_id)
                self._write_json(
                    run_dir / "api_key_result.json",
                    {
                        "id": api_key_result.get("id"),
                        "type": api_key_result.get("type"),
                        "token_masked": self._mask_secret(str(api_key_result.get("token") or "")),
                    },
                )
                partial_artifacts["api_key_result"] = str(run_dir / "api_key_result.json")

            real_runtime_result = self._invoke_real_runtime(
                api_key=str(api_key_result["token"]),
                workflow_input=workflow_input,
            )
            self._write_json(run_dir / "real_runtime_result.json", real_runtime_result)
            partial_artifacts["real_runtime_result"] = str(run_dir / "real_runtime_result.json")

            runtime_scope = {
                "real_http_runtime": True,
                "compatible_fallback": bool(
                    regression_results["test_agent_platform_service_dify_subset"]["passed"]
                ),
                "agent_status_runtime_exposed": bool(regression_results["test_agent_service_dify_status"]["passed"]),
                "real_dify_container_ui_verified": bool(ui_status.get("ok")),
                "builtin_rag_pipeline_verified": False,
            }

            checks = [
                {
                    "name": "dify_runtime_http_ready",
                    "passed": bool(readiness.get("ready")),
                    "detail": f"url={readiness.get('url')}",
                    "evidence": readiness,
                },
                {
                    "name": "dify_console_ui_reachable",
                    "passed": bool(ui_status.get("ok")),
                    "detail": f"status_code={ui_status.get('status_code')}",
                    "evidence": ui_status,
                },
                {
                    "name": "dify_console_setup_completed",
                    "passed": setup_result.get("status") in {"already_configured", "created"},
                    "detail": str(setup_result.get("status")),
                    "evidence": setup_result,
                },
                {
                    "name": "dify_console_login_succeeds",
                    "passed": int(login_result.get("status_code") or 0) == 200,
                    "detail": f"status_code={login_result.get('status_code')}",
                    "evidence": {"status_code": login_result.get("status_code")},
                },
                {
                    "name": "workflow_dsl_imported_to_real_dify",
                    "passed": bool(app_id),
                    "detail": f"app_id={app_id}",
                    "evidence": import_result,
                },
                {
                    "name": "workflow_published_to_runtime_api",
                    "passed": int(publish_result.get("status_code") or 0) < 400,
                    "detail": f"status_code={publish_result.get('status_code')}",
                    "evidence": publish_result,
                },
                {
                    "name": "real_dify_app_api_key_created",
                    "passed": bool(str(api_key_result.get("token") or "").strip()),
                    "detail": f"api_key_id={api_key_result.get('id')}",
                    "evidence": {
                        "id": api_key_result.get("id"),
                        "type": api_key_result.get("type"),
                        "token_masked": self._mask_secret(str(api_key_result.get("token") or "")),
                    },
                },
                {
                    "name": "pms_real_dify_http_runtime_invocation_succeeds",
                    "passed": str(real_runtime_result.get("runtime_channel") or "") == "dify-http"
                    and bool((real_runtime_result.get("outputs") or {}).get("result")),
                    "detail": f"workflow_run_id={((real_runtime_result.get('provider_response') or {}).get('workflow_run_id'))}",
                    "evidence": {
                        "runtime_channel": real_runtime_result.get("runtime_channel"),
                        "provider_response": real_runtime_result.get("provider_response"),
                        "outputs": real_runtime_result.get("outputs"),
                    },
                },
                {
                    "name": "compatible_fallback_regression_preserved",
                    "passed": runtime_scope["compatible_fallback"],
                    "detail": f"returncode={regression_results['test_agent_platform_service_dify_subset']['returncode']}",
                    "evidence": regression_results["test_agent_platform_service_dify_subset"],
                },
                {
                    "name": "agent_status_runtime_exposure_regression_preserved",
                    "passed": runtime_scope["agent_status_runtime_exposed"],
                    "detail": f"returncode={regression_results['test_agent_service_dify_status']['returncode']}",
                    "evidence": regression_results["test_agent_service_dify_status"],
                },
            ]

            summary = {
                "task_id": "N2-04",
                "reference_task_id": "P6-04",
                "task_name": "Dify 真实编排环境联通",
                "status": self._status_from_checks(checks),
                "accepted": all(bool(item.get("passed")) for item in checks),
                "generated_at": self._now_iso(),
                "acceptance_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "base_url": self.manager.base_url,
                "runtime_scope": runtime_scope,
                "workflow": {
                    "dsl_path": str(self.manager.workflow_dsl_path),
                    "app_id": app_id,
                    "api_key_masked": self._mask_secret(str(api_key_result.get("token") or "")),
                    "workflow_input": workflow_input,
                    "workflow_run_id": (real_runtime_result.get("provider_response") or {}).get("workflow_run_id"),
                    "task_id": (real_runtime_result.get("provider_response") or {}).get("task_id"),
                },
                "real_runtime_result": {
                    "runtime_channel": real_runtime_result.get("runtime_channel"),
                    "outputs": real_runtime_result.get("outputs"),
                    "provider_response": real_runtime_result.get("provider_response"),
                    "dify_runtime": real_runtime_result.get("dify_runtime"),
                },
                "regression_results": regression_results,
                "checks": checks,
                "artifacts": {
                    **partial_artifacts,
                    "summary": str(summary_path),
                },
            }
            self._write_json(summary_path, summary)
            self.ops_root.mkdir(parents=True, exist_ok=True)
            self._write_json(self.ops_root / "local_dify_runtime_acceptance.json", summary)
            return summary
        except Exception as exc:
            summary = {
                "task_id": "N2-04",
                "reference_task_id": "P6-04",
                "task_name": "Dify 真实编排环境联通",
                "status": "failed",
                "accepted": False,
                "generated_at": self._now_iso(),
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "base_url": self.manager.base_url,
                "error": str(exc),
                "environment": environment,
                "artifacts": partial_artifacts,
            }
            self._write_json(summary_path, summary)
            self.ops_root.mkdir(parents=True, exist_ok=True)
            self._write_json(self.ops_root / "local_dify_runtime_acceptance.json", summary)
            return summary
