from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx


class OllamaClient:
    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        timeout_seconds: float = 10.0,
        model_name: str = "qwen2.5:1.5b-instruct",
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.model_name = model_name

    async def list_models(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
            try:
                response = await client.get(f"{self.endpoint}/api/tags")
                response.raise_for_status()
                payload = response.json()
                models = payload.get("models", []) if isinstance(payload, dict) else []
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                response = await client.get(f"{self.endpoint}/v1/models")
                response.raise_for_status()
                payload = response.json()
                raw_models = payload.get("data", []) if isinstance(payload, dict) else []
                models = [
                    {"name": item.get("id") or item.get("name") or ""}
                    for item in raw_models
                    if isinstance(item, dict)
                ]
        return {"endpoint": self.endpoint, "models": models, "count": len(models)}

    async def generate(
        self,
        prompt: str,
        model_name: str | None = None,
        images: list[str] | None = None,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        target_model = model_name or self.model_name
        resolved_model = target_model
        payload: dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
        }
        if images:
            payload["images"] = images
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
            try:
                response = await client.post(
                    f"{self.endpoint}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                raw_payload = response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                try:
                    available_models = await self._list_model_names_via_native_api(client)
                except httpx.HTTPStatusError:
                    available_models = []
                fallback_model = self._select_compatible_model(target_model, available_models)
                if available_models and fallback_model:
                    resolved_model = fallback_model
                    payload["model"] = fallback_model
                    response = await client.post(
                        f"{self.endpoint}/api/generate",
                        json=payload,
                    )
                    response.raise_for_status()
                    raw_payload = response.json()
                else:
                    response = await client.post(
                        f"{self.endpoint}/v1/chat/completions",
                        json=self._build_chat_completions_payload(
                            prompt=prompt,
                            model_name=target_model,
                            images=images,
                            system=system,
                            options=options,
                        ),
                    )
                    response.raise_for_status()
                    raw_payload = self._normalize_chat_completions_payload(
                        payload=response.json(),
                        model_name=target_model,
                    )
        result = raw_payload if isinstance(raw_payload, dict) else {"response": str(raw_payload)}
        result.setdefault("latency_ms", round((perf_counter() - started) * 1000, 3))
        result.setdefault("model", resolved_model)
        return result

    async def healthcheck(self) -> dict[str, Any]:
        try:
            models = await self.list_models()
            return {
                "reachable": True,
                "endpoint": self.endpoint,
                "model_count": models["count"],
                "models": [item.get("name") for item in models.get("models", [])[:10]],
            }
        except Exception as exc:
            return {
                "reachable": False,
                "endpoint": self.endpoint,
                "model_count": 0,
                "models": [],
                "error": str(exc),
            }

    def _build_chat_completions_payload(
        self,
        *,
        prompt: str,
        model_name: str,
        images: list[str] | None,
        system: str | None,
        options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})

        content: Any = prompt
        if images:
            content = [{"type": "text", "text": prompt or "Analyze the supplied media."}]
            for image in images:
                data_url = image if image.startswith("data:") else f"data:image/png;base64,{image}"
                content.append({"type": "image_url", "image_url": {"url": data_url}})

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages + [{"role": "user", "content": content}],
            "stream": False,
        }
        if options:
            if options.get("temperature") is not None:
                payload["temperature"] = options["temperature"]
            if options.get("top_p") is not None:
                payload["top_p"] = options["top_p"]
            if options.get("num_predict") is not None:
                payload["max_tokens"] = options["num_predict"]
        return payload

    def _normalize_chat_completions_payload(
        self,
        *,
        payload: dict[str, Any],
        model_name: str,
    ) -> dict[str, Any]:
        choices = payload.get("choices", []) if isinstance(payload, dict) else []
        message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, list):
            text_parts = [
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            response_text = "\n".join(part for part in text_parts if part).strip()
        else:
            response_text = str(content or "").strip()
        return {
            "response": response_text,
            "done": True,
            "model": str(payload.get("model") or model_name),
        }

    async def _list_model_names_via_native_api(self, client: httpx.AsyncClient) -> list[str]:
        response = await client.get(f"{self.endpoint}/api/tags")
        response.raise_for_status()
        payload = response.json()
        raw_models = payload.get("models", []) if isinstance(payload, dict) else []
        names: list[str] = []
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("model") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def _select_compatible_model(self, target_model: str, available_models: list[str]) -> str | None:
        if not available_models:
            return None
        if target_model in available_models:
            return target_model

        normalized_target = target_model.replace("-instruct", "")
        if normalized_target in available_models:
            return normalized_target

        target_family = target_model.split(":", 1)[0]
        family_matches = [model for model in available_models if model.split(":", 1)[0] == target_family]
        if family_matches:
            return family_matches[0]

        return available_models[0]
