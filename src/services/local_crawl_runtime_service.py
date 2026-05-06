from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote


class LocalCrawlRuntimeService:
    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        fixture_root: Path | None = None,
        runtime_root: Path | None = None,
        acceptance_path: Path | None = None,
    ) -> None:
        self.workspace_root = workspace_root or Path(__file__).resolve().parents[2]
        self.fixture_root = fixture_root or self.workspace_root / "artifacts" / "crawl_platform" / "targets"
        self.runtime_root = runtime_root or self.workspace_root / "artifacts" / "crawl_platform" / "runtime"
        self.acceptance_path = acceptance_path or self.workspace_root / "artifacts" / "crawl_platform" / "runtime_acceptance.json"

    def build_status(self) -> dict[str, Any]:
        return {
            "fixture_root": self.fixture_root.as_posix(),
            "runtime_root": self.runtime_root.as_posix(),
            "acceptance_artifact": self.acceptance_path.as_posix(),
            "scrapy": {
                "project": "src.crawlers.scrapy_local",
                "spider": "local_site",
                "command": "python -m scrapy crawl local_site -a start_url=<fixture_url> -a query=<keyword>",
                "installed": importlib.util.find_spec("scrapy") is not None,
            },
            "playwright": {
                "browser": "chromium",
                "command": "python -m playwright install chromium",
                "package_installed": importlib.util.find_spec("playwright.async_api") is not None,
            },
            "latest_acceptance": self._read_json(self.acceptance_path),
        }

    async def run_scrapy_fixture(self, *, query: str) -> dict[str, Any]:
        with self._serve_fixture_root() as base_url:
            output_path = self.runtime_root / "scrapy_runtime_output.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                output_path.unlink()
            command = [
                sys.executable,
                "-m",
                "scrapy",
                "crawl",
                "local_site",
                "-a",
                f"start_url={base_url}/scrapy_listing.html",
                "-a",
                f"query={query}",
                "-O",
                output_path.as_posix(),
                "-s",
                "LOG_ENABLED=False",
            ]
            completed = await asyncio.to_thread(self._run_subprocess, command)
            items = self._read_json_array(output_path)
            return {
                "engine": "scrapy-compatible",
                "runtime": "scrapy-cli",
                "query": query,
                "ready": completed.returncode == 0 and len(items) >= 3,
                "command": command,
                "output_path": output_path.as_posix(),
                "item_count": len(items),
                "records": items,
                "stdout_tail": completed.stdout[-1000:],
                "stderr_tail": completed.stderr[-1000:],
            }

    async def run_playwright_fixture(self, *, query: str) -> dict[str, Any]:
        with self._serve_fixture_root() as base_url:
            output_path = self.runtime_root / "playwright_runtime_output.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            records = await self._capture_playwright_page(url=f"{base_url}/playwright_dynamic.html?query={quote(query)}")
            output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            return {
                "engine": "playwright-compatible",
                "runtime": "playwright-chromium",
                "query": query,
                "ready": len(records) >= 3,
                "browser": "chromium",
                "output_path": output_path.as_posix(),
                "item_count": len(records),
                "records": records,
            }

    async def run_acceptance(self, *, query: str) -> dict[str, Any]:
        scrapy_result = await self.run_scrapy_fixture(query=query)
        playwright_result = await self.run_playwright_fixture(query=query)
        payload = {
            "accepted": scrapy_result["ready"] and playwright_result["ready"],
            "query": query,
            "scrapy": {
                "ready": scrapy_result["ready"],
                "item_count": scrapy_result["item_count"],
                "output_path": scrapy_result["output_path"],
            },
            "playwright": {
                "ready": playwright_result["ready"],
                "item_count": playwright_result["item_count"],
                "output_path": playwright_result["output_path"],
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }
        self.acceptance_path.parent.mkdir(parents=True, exist_ok=True)
        self.acceptance_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    async def _capture_playwright_page(self, *, url: str) -> list[dict[str, Any]]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url)
                await page.wait_for_selector(".dynamic-card")
                await page.wait_for_timeout(100)
                cards = await page.locator(".dynamic-card").evaluate_all(
                    """elements => elements.map(card => ({
                        title: card.querySelector('.title')?.textContent?.trim() || '',
                        channel: card.querySelector('.channel')?.textContent?.trim() || '',
                        summary: card.querySelector('.summary')?.textContent?.trim() || '',
                        url: card.querySelector('.link')?.getAttribute('href') || '',
                        render_mode: 'dynamic-dom'
                    }))"""
                )
                return [{"source": "playwright_runtime", **card} for card in cards]
            finally:
                await browser.close()

    def _run_subprocess(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.workspace_root)
        return subprocess.run(
            command,
            cwd=self.workspace_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )

    @contextlib.contextmanager
    def _serve_fixture_root(self):
        self.fixture_root.mkdir(parents=True, exist_ok=True)
        handler = partial(SimpleHTTPRequestHandler, directory=str(self.fixture_root))
        server = ThreadingHTTPServer(("127.0.0.1", self._reserve_port()), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    @staticmethod
    def _reserve_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _read_json_array(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
