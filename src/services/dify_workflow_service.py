from __future__ import annotations

from typing import Any

import httpx

from src.agents.framework_adapter import AgentFrameworkAdapterRegistry
from src.config.settings import DifySettings, get_settings


class DifyWorkflowError(RuntimeError):
    """Raised when the real Dify HTTP workflow runtime is unavailable."""


class DifyWorkflowService:
    def __init__(
        self,
        settings: DifySettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings().dify
        self._transport = transport
        self._last_error: str | None = None

    @staticmethod
    def _normalize_path(path: str) -> str:
        cleaned = str(path or "").strip()
        if not cleaned:
            return "/v1/workflows/run"
        return cleaned if cleaned.startswith("/") else f"/{cleaned}"

    @staticmethod
    def _template_key_for_category(category: str) -> str:
        if category in {"electronics", "consumer_electronics"}:
            return "selection-electronics-brief"
        return "selection-market-brief"

    @staticmethod
    def _extract_answer(outputs: dict[str, Any]) -> str | None:
        for key in ("answer", "text", "result", "summary", "content"):
            value = outputs.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def build_runtime_status(self) -> dict[str, Any]:
        base_url = str(self.settings.base_url or "").strip().rstrip("/")
        workflow_run_path = self._normalize_path(self.settings.workflow_run_path)
        api_key_configured = bool(str(self.settings.api_key or "").strip())
        enabled = bool(self.settings.enabled)
        configuration_ready = enabled and bool(base_url) and api_key_configured
        blocked_reason: str | None = None
        runtime_status = "compatible-only"

        if enabled and not base_url:
            blocked_reason = "Dify enabled but DIFY_BASE_URL is empty"
            runtime_status = "fallback" if self.settings.prefer_compatible_fallback else "blocked"
        elif enabled and not api_key_configured:
            blocked_reason = "Dify enabled but DIFY_API_KEY is not configured"
            runtime_status = "fallback" if self.settings.prefer_compatible_fallback else "blocked"
        elif enabled and self._last_error:
            blocked_reason = self._last_error
            runtime_status = "fallback" if self.settings.prefer_compatible_fallback else "blocked"
        elif configuration_ready:
            runtime_status = "active"

        return {
            "enabled": enabled,
            "base_url": base_url,
            "workflow_run_path": workflow_run_path,
            "workflow_endpoint": f"{base_url}{workflow_run_path}" if base_url else workflow_run_path,
            "api_key_configured": api_key_configured,
            "configuration_ready": configuration_ready,
            "real_runtime_ready": configuration_ready,
            "timeout_seconds": self.settings.timeout_seconds,
            "response_mode": self.settings.response_mode,
            "user_prefix": self.settings.user_prefix,
            "prefer_compatible_fallback": self.settings.prefer_compatible_fallback,
            "runtime_status": runtime_status,
            "blocked_reason": blocked_reason,
            "last_error": self._last_error,
        }

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = str(self.settings.api_key or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _build_request_payload(self, input_data: dict[str, Any]) -> dict[str, Any]:
        request_user = str(
            input_data.get("request_user")
            or input_data.get("user")
            or input_data.get("tenant_id")
            or "local"
        ).strip() or "local"
        return {
            "inputs": dict(input_data),
            "response_mode": self.settings.response_mode,
            "user": f"{self.settings.user_prefix}:{request_user}",
        }

    async def invoke_workflow(self, *, input_data: dict[str, Any]) -> dict[str, Any]:
        runtime = self.build_runtime_status()
        if not runtime["configuration_ready"]:
            raise DifyWorkflowError(str(runtime["blocked_reason"] or "Dify HTTP runtime is not configured"))

        query = str(input_data.get("query") or "").strip()
        if not query:
            raise ValueError("query不能为空")
        category = str(input_data.get("category") or "general")
        target_market = str(input_data.get("target_market") or "global")
        template_key = str(input_data.get("template_key") or self._template_key_for_category(category))
        request_payload = self._build_request_payload(input_data)

        try:
            async with httpx.AsyncClient(
                base_url=str(runtime["base_url"]),
                headers=self._build_headers(),
                timeout=httpx.Timeout(self.settings.timeout_seconds),
                transport=self._transport,
                follow_redirects=True,
            ) as client:
                response = await client.post(str(runtime["workflow_run_path"]), json=request_payload)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._last_error = str(exc)
            raise DifyWorkflowError(f"Dify workflow invocation failed: {exc}") from exc

        self._last_error = None
        runtime = self.build_runtime_status()
        data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}
        outputs = data.get("outputs") if isinstance(data.get("outputs"), dict) else {}
        answer = self._extract_answer(outputs)
        normalized_status = str(data.get("status") or payload.get("status") or "completed")

        return {
            "framework": "dify-compatible",
            "provider": "dify",
            "status": normalized_status,
            "execution_mode": "prompt_orchestration",
            "runtime_channel": "dify-http",
            "template_key": template_key,
            "variables": dict(input_data),
            "rendered_prompt": answer,
            "routing": {
                "template_key": template_key,
                "channel": "dify-http",
                "strategy": "workflow-api",
            },
            "provider_request": {
                "endpoint": runtime["workflow_endpoint"],
                "response_mode": self.settings.response_mode,
                "user": request_payload["user"],
            },
            "provider_response": {
                "workflow_run_id": data.get("workflow_run_id") or payload.get("workflow_run_id"),
                "task_id": data.get("task_id") or payload.get("task_id"),
                "status": normalized_status,
                "elapsed_time": data.get("elapsed_time"),
                "total_tokens": data.get("total_tokens"),
            },
            "outputs": outputs,
            "dify_runtime": runtime,
            "business_summary": AgentFrameworkAdapterRegistry._build_business_summary(
                framework_key="dify-compatible",
                query=query,
                category=category,
                target_market=target_market,
                source_count=1,
                recommended_next_action="继续结合 Dify 输出补齐市场机会、竞争风险和供应链关注点，再进入人工复核。",
            ),
        }
