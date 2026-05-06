from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from src.config.settings import CollectionAPISettings
from src.services.proxy_provider_service import ProxyProviderService


class _ProxyAwareFixtureHandler(BaseHTTPRequestHandler):
    server_version = "ProxyAwareFixture/1.0"

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(
            {
                "origin": "127.0.0.1",
                "path": self.path,
                "proxy_node": self.headers.get("X-Proxy-Node"),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class _ForwardProxyHandler(BaseHTTPRequestHandler):
    server_version = "LocalForwardProxy/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if not parsed.scheme or not parsed.hostname:
            self.send_error(400, "proxy requires absolute URL")
            return

        request_path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=5.0)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"proxy-connection", "connection", "host"}
        }
        headers["Host"] = parsed.netloc
        headers["X-Proxy-Node"] = getattr(self.server, "proxy_node", "local-proxy")

        try:
            connection.request("GET", request_path, headers=headers)
            response = connection.getresponse()
            body = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() in {"transfer-encoding", "connection", "server", "date", "content-length"}:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        finally:
            connection.close()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class LocalProxyRuntimeService:
    """本地自建代理池运行时，用于 P1-07 本地可验收基线。"""

    DEFAULT_ARTIFACT_PATH = Path("artifacts/ops/local_proxy_provider_acceptance.json")

    def __init__(self, artifact_path: Path | None = None) -> None:
        self.artifact_path = artifact_path or self.DEFAULT_ARTIFACT_PATH

    @contextmanager
    def _serve(self, handler_cls: type[BaseHTTPRequestHandler], *, proxy_node: str | None = None) -> Iterator[ThreadingHTTPServer]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        server.proxy_node = proxy_node
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def run_acceptance(self) -> dict[str, Any]:
        with ExitStack() as stack:
            fixture = stack.enter_context(self._serve(_ProxyAwareFixtureHandler))
            proxy_a = stack.enter_context(self._serve(_ForwardProxyHandler, proxy_node="proxy-node-a"))
            proxy_b = stack.enter_context(self._serve(_ForwardProxyHandler, proxy_node="proxy-node-b"))

            probe_url = f"http://127.0.0.1:{fixture.server_port}/ip"
            proxy_urls = [
                f"http://127.0.0.1:{proxy_a.server_port}",
                f"http://127.0.0.1:{proxy_b.server_port}",
            ]
            settings = CollectionAPISettings(
                proxy_provider="self_hosted",
                proxy_list=",".join(proxy_urls),
                proxy_probe_url=probe_url,
                proxy_probe_timeout_seconds=5.0,
            )
            provider_runtime = ProxyProviderService(settings=settings).build_status(include_probe=True)

        payload = {
            "accepted": bool(provider_runtime.get("probe", {}).get("ready")),
            "provider_runtime": provider_runtime,
            "runtime": {
                "fixture_url": probe_url,
                "proxy_nodes": [
                    {"name": "proxy-node-a", "proxy_url": proxy_urls[0]},
                    {"name": "proxy-node-b", "proxy_url": proxy_urls[1]},
                ],
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
