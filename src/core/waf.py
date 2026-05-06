from __future__ import annotations

import ipaddress
import json
from urllib.parse import unquote_plus

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.api_contract import build_error_envelope
from src.core.exceptions import IPAllowlistDeniedError, RequestBlockedByWAFError

_SQLI_PATTERNS = [
    " union select ",
    " union all select ",
    " or 1=1",
    " and 1=1",
    " drop table ",
    " delete from ",
    " insert into ",
    " update set ",
    " sleep(",
    " benchmark(",
    "information_schema",
    "xp_cmdshell",
    "waitfor delay",
    "--",
    "/*",
    "*/",
]

_XSS_PATTERNS = [
    "<script",
    "javascript:",
    "vbscript:",
    "data:text/html",
    "onerror=",
    "onload=",
    "onclick=",
    "onfocus=",
    "<img",
    "<iframe",
    "<svg",
    "<object",
]

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _build_blocked_response(request: Request, exc: IPAllowlistDeniedError | RequestBlockedByWAFError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=build_error_envelope(
            request=request,
            message=exc.message,
            error_code=exc.error_code,
            detail=exc.detail,
        ),
    )


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """IP白名单中间件"""

    def __init__(self, app, whitelist: list[str] | None = None):
        super().__init__(app)
        self.whitelist = whitelist or []
        self._whitelist_set: set[str] = set()
        self._whitelist_networks: list[ipaddress.IPv4Network] = []
        self._load_whitelist()

    def _load_whitelist(self) -> None:
        for item in self.whitelist:
            try:
                ip = ipaddress.IPv4Address(item)
                self._whitelist_set.add(str(ip))
            except ipaddress.AddressValueError:
                try:
                    network = ipaddress.IPv4Network(item)
                    self._whitelist_networks.append(network)
                except ipaddress.AddressValueError:
                    pass

    def _is_ip_allowed(self, ip: str) -> bool:
        if ip in self._whitelist_set:
            return True
        try:
            ip_obj = ipaddress.IPv4Address(ip)
            for network in self._whitelist_networks:
                if ip_obj in network:
                    return True
        except ipaddress.AddressValueError:
            pass
        return False

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        if self.whitelist and not self._is_ip_allowed(client_ip):
            return _build_blocked_response(request, IPAllowlistDeniedError(client_ip=client_ip, target=request.url.path))
        return await call_next(request)


class RequestWAFMiddleware(BaseHTTPMiddleware):
    """轻量级请求 WAF。"""

    def _scan_text(self, raw_text: str) -> tuple[str, str] | None:
        normalized = f" {unquote_plus(raw_text).lower()} "
        for pattern in _SQLI_PATTERNS:
            if pattern in normalized:
                return "sql_injection", pattern.strip()
        for pattern in _XSS_PATTERNS:
            if pattern in normalized:
                return "xss", pattern
        return None

    async def _read_body_text(self, request: Request) -> str:
        body = await request.body()
        if not body:
            return ""

        async def receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        request._body = body  # type: ignore[attr-defined]
        request._receive = receive  # type: ignore[attr-defined]
        return body.decode("utf-8", errors="ignore")

    @staticmethod
    def _should_scan_raw_body(request: Request) -> bool:
        content_type = (request.headers.get("content-type") or "").lower()
        # Multipart boundaries contain "--" by design, so scanning the raw
        # multipart payload would false-positive on normal file uploads.
        return not content_type.startswith("multipart/form-data")

    def _check_csrf(self, request: Request) -> tuple[str, str] | None:
        if request.method.upper() not in _WRITE_METHODS:
            return None
        cookie_header = request.headers.get("cookie", "")
        auth_header = request.headers.get("authorization", "")
        if not cookie_header or auth_header.lower().startswith("bearer "):
            return None
        csrf_header = request.headers.get("x-csrf-token", "")
        if not csrf_header:
            return "csrf", "missing_csrf_token"
        origin = request.headers.get("origin") or request.headers.get("referer")
        host = request.headers.get("host", "")
        if not origin:
            return "csrf", "missing_origin"
        if host and host not in origin:
            return "csrf", "cross_site_origin"
        return None

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        csrf_hit = self._check_csrf(request)
        if csrf_hit:
            reason, keyword = csrf_hit
            return _build_blocked_response(
                request,
                RequestBlockedByWAFError(reason=reason, matched_keyword=keyword, location="headers"),
            )

        query_text = str(request.url.query or "")
        query_hit = self._scan_text(query_text)
        if query_hit:
            reason, keyword = query_hit
            return _build_blocked_response(
                request,
                RequestBlockedByWAFError(reason=reason, matched_keyword=keyword, location="query"),
            )

        header_text = json.dumps(
            {
                "user-agent": request.headers.get("user-agent", ""),
                "referer": request.headers.get("referer", ""),
                "origin": request.headers.get("origin", ""),
            },
            ensure_ascii=False,
        )
        header_hit = self._scan_text(header_text)
        if header_hit:
            reason, keyword = header_hit
            return _build_blocked_response(
                request,
                RequestBlockedByWAFError(reason=reason, matched_keyword=keyword, location="headers"),
            )

        if request.method.upper() in _WRITE_METHODS and self._should_scan_raw_body(request):
            body_text = await self._read_body_text(request)
            body_hit = self._scan_text(body_text)
            if body_hit:
                reason, keyword = body_hit
                return _build_blocked_response(
                    request,
                    RequestBlockedByWAFError(reason=reason, matched_keyword=keyword, location="body"),
                )

        return await call_next(request)


def get_ip_whitelist() -> list[str]:
    from src.config.settings import get_settings

    settings = get_settings()
    return settings.security.llm_ip_allowlist


def is_ip_allowed(ip: str) -> bool:
    whitelist = get_ip_whitelist()
    if not whitelist:
        return True
    middleware = IPWhitelistMiddleware(None, whitelist)
    return middleware._is_ip_allowed(ip)
