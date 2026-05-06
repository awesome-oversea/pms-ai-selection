from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse


class LocalObjectStore:
    def __init__(self, root: str = "data/lake") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_text(self, relative_path: str, content: str) -> str:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target).replace("\\", "/")

    def exists(self, relative_path: str) -> bool:
        return (self.root / relative_path).exists()

    def resolve(self, relative_path: str) -> str:
        return str(self.root / relative_path).replace("\\", "/")

    def kind(self) -> Literal["local"]:
        return "local"


def is_local_artifact_endpoint(api_endpoint: str) -> bool:
    return api_endpoint.startswith("file://")


def _normalize_file_uri_path(api_endpoint: str) -> Path:
    parsed = urlparse(api_endpoint)
    raw_path = unquote(parsed.path or "")
    if parsed.netloc:
        raw_path = f"{parsed.netloc}{raw_path}"
    if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return Path(raw_path)


def resolve_local_artifact_path(api_endpoint: str, relative_path: str | None = None) -> Path:
    root = _normalize_file_uri_path(api_endpoint)
    if not relative_path or relative_path in {"/", "."}:
        return root
    return root / relative_path.lstrip("/")


def read_json_artifact(api_endpoint: str, relative_path: str | None = None) -> Any:
    target = resolve_local_artifact_path(api_endpoint, relative_path)
    return json.loads(target.read_text(encoding="utf-8"))


def write_json_artifact(api_endpoint: str, relative_path: str | None, payload: Any) -> str:
    target = resolve_local_artifact_path(api_endpoint, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target).replace("\\", "/")
