from __future__ import annotations

import os

import httpx


def main() -> int:
    endpoint = os.environ.get("LLM_OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
    model = os.environ.get("LLM_PRIMARY_MODEL", "qwen2.5:1.5b-instruct")
    payload = {
        "model": model,
        "prompt": "你好",
        "stream": False,
        "options": {
            "num_predict": 8,
            "temperature": 0,
        },
    }

    response = httpx.post(f"{endpoint}/api/generate", json=payload, timeout=180)
    print(response.status_code)
    print(response.text[:1000])
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
