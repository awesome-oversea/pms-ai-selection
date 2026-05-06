"""
统一 API 契约工具
================

为 /api/v1/* 提供：
- 成功响应 envelope
- 错误响应 envelope
- OpenAPI schema 包裹
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "no-request"


def build_success_envelope(*, request: Request, data: Any, code: str = "OK", message: str = "success") -> dict[str, Any]:
    payload = {
        "code": code,
        "message": message,
        "data": data,
        "request_id": _request_id(request),
        "timestamp": _now_iso(),
    }
    if isinstance(data, dict):
        for key, value in data.items():
            if key not in payload:
                payload[key] = value
    return payload


def build_error_envelope(
    *,
    request: Request,
    message: str,
    error_code: str,
    detail: Any = None,
    data: Any = None,
) -> dict[str, Any]:
    payload = {
        "code": error_code,
        "message": message,
        "data": data,
        "request_id": _request_id(request),
        "timestamp": _now_iso(),
        "error_code": error_code,
        "detail": detail if detail is not None else message,
    }
    if isinstance(detail, dict):
        for key, value in detail.items():
            if key not in payload:
                payload[key] = value
    return payload


def _wrap_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "code": {"type": "string", "example": "OK"},
            "message": {"type": "string", "example": "success"},
            "data": deepcopy(schema),
            "request_id": {"type": "string", "example": "req-demo-001"},
            "timestamp": {"type": "string", "format": "date-time"},
        },
        "required": ["code", "message", "data", "request_id", "timestamp"],
    }


def install_openapi_envelope(app: FastAPI, api_prefix: str = "/api/v1") -> None:
    original_openapi = app.openapi

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = original_openapi() if original_openapi is not None else get_openapi(title=app.title, version=app.version, routes=app.routes)
        schema.setdefault("info", {})["x-interface-governance"] = {
            "gateway": {"prefixes": [api_prefix], "audience": "internal-platform"},
            "bff": {"prefixes": ["/dashboard", "/selection", "/approval", "/results", "/agents/monitor"], "audience": "web-frontend"},
            "openapi": {"docs_url": "/docs", "openapi_url": "/openapi.json", "audience": "integrators"},
        }
        for path, path_item in schema.get("paths", {}).items():
            if not path.startswith(api_prefix):
                continue
            for _, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                for _status_code, response in operation.get("responses", {}).items():
                    content = response.get("content", {})
                    media = content.get("application/json")
                    if not media:
                        continue
                    response_schema = media.get("schema", {"type": "object"})
                    media["schema"] = _wrap_schema(response_schema)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


class ApiContractMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_prefix: str = "/api/v1"):
        super().__init__(app)
        self.api_prefix = api_prefix

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith(self.api_prefix):
            return response
        if response.status_code >= 400:
            return response
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        if not body:
            return response

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return Response(content=body, status_code=response.status_code, headers=dict(response.headers), media_type=response.media_type)

        if isinstance(payload, dict) and {"code", "message", "data", "request_id", "timestamp"}.issubset(payload.keys()):
            wrapped = payload
        else:
            wrapped = build_success_envelope(request=request, data=payload)

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return JSONResponse(content=wrapped, status_code=response.status_code, headers=headers, background=response.background)
