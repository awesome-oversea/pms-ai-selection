from __future__ import annotations

import httpx
import pytest
from src.infrastructure.ollama_client import OllamaClient


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        self.calls.append(("GET", url, None))
        if url.endswith("/api/tags"):
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "qwen2.5:0.5b"},
                        {"name": "qwen3.5:2b"},
                    ]
                },
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected GET {url}")

    async def post(self, url: str, json: dict | None = None):
        self.calls.append(("POST", url, json))
        request = httpx.Request("POST", url, json=json)
        if url.endswith("/api/generate") and json and json.get("model") == "qwen2.5:1.5b-instruct":
            return httpx.Response(404, json={"error": "model not found"}, request=request)
        if url.endswith("/api/generate") and json and json.get("model") == "qwen2.5:0.5b":
            return httpx.Response(
                200,
                json={"model": "qwen2.5:0.5b", "response": "4", "done": True, "eval_count": 2},
                request=request,
            )
        raise AssertionError(f"unexpected POST {url} {json}")


class _OpenAICompatOnlyClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        request = httpx.Request("GET", url)
        return httpx.Response(404, json={"error": "not found"}, request=request)

    async def post(self, url: str, json: dict | None = None):
        request = httpx.Request("POST", url, json=json)
        if url.endswith("/api/generate"):
            return httpx.Response(404, json={"error": "not found"}, request=request)
        if url.endswith("/v1/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "model": "qwen2.5:1.5b-instruct",
                    "choices": [{"message": {"content": "兼容接口返回"}}],
                },
                request=request,
            )
        raise AssertionError(f"unexpected POST {url}")


@pytest.mark.asyncio
async def test_ollama_client_falls_back_to_available_native_model(monkeypatch):
    monkeypatch.setattr("src.infrastructure.ollama_client.httpx.AsyncClient", _FakeAsyncClient)
    client = OllamaClient(model_name="qwen2.5:1.5b-instruct")

    result = await client.generate("2+2等于几？")

    assert result["model"] == "qwen2.5:0.5b"
    assert result["response"] == "4"


@pytest.mark.asyncio
async def test_ollama_client_uses_openai_compatible_endpoint_when_native_api_missing(monkeypatch):
    monkeypatch.setattr("src.infrastructure.ollama_client.httpx.AsyncClient", _OpenAICompatOnlyClient)
    client = OllamaClient(model_name="qwen2.5:1.5b-instruct")

    result = await client.generate("给我一个摘要")

    assert result["model"] == "qwen2.5:1.5b-instruct"
    assert result["response"] == "兼容接口返回"
