#!/usr/bin/env python3
"""
模拟Triton Inference Server和其他特殊软件的轻量级服务
用于在WSL2环境未完全就绪时，让项目可以继续开发
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

SCENARIO_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "mock_scenarios"


def _load_scenario(kind: str, scenario_id: str | None) -> dict[str, Any] | None:
    if not scenario_id:
        return None
    path = SCENARIO_ROOT / kind / f"{scenario_id}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _resolve_scenario_id(handler: BaseHTTPRequestHandler) -> str | None:
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    header_value = handler.headers.get("X-Scenario-ID")
    query_value = (params.get("scenario") or [None])[0]
    return header_value or query_value


def _apply_scenario_defaults(handler: BaseHTTPRequestHandler, kind: str) -> tuple[int | None, dict[str, Any] | None]:
    scenario_id = _resolve_scenario_id(handler)
    scenario = _load_scenario(kind, scenario_id)
    if not scenario:
        return None, None
    behavior = scenario.get("behavior") if isinstance(scenario.get("behavior"), dict) else {}
    delay_ms = int(behavior.get("delay_ms") or 0)
    if delay_ms > 0:
        time.sleep(delay_ms / 1000)
    error = behavior.get("error")
    if error == "timeout":
        time.sleep(5)
    status_code = int(behavior.get("status_code") or 200)
    response = scenario.get("response") if isinstance(scenario.get("response"), dict) else {}
    if error == "auth_failed":
        status_code = 401
        response = {"error": "auth_failed", "scenario_id": scenario_id}
    elif error == "rate_limited":
        status_code = 429
        response = {"error": "rate_limited", "scenario_id": scenario_id}
    elif error == "server_error":
        status_code = 500
        response = {"error": "server_error", "scenario_id": scenario_id}
    elif error == "partial_data":
        response = {**response, "degraded": True, "scenario_id": scenario_id}
    return status_code, response


def _normalize_internal_erp_path(path: str) -> str:
    parsed_path = urlparse(path).path
    internal_prefix = "/api/internal/v1/"
    if not parsed_path.startswith(internal_prefix):
        return parsed_path
    remainder = parsed_path[len(internal_prefix) :]
    _, _, resource = remainder.partition("/")
    return f"/{resource}" if resource else "/"


class MockTritonHandler(BaseHTTPRequestHandler):
    """模拟Triton Inference Server的HTTP处理器"""

    def do_GET(self) -> None:
        """处理GET请求"""
        if self.path == "/v2/health/ready":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ready": True,
                "status": "ok",
                "mode": "local-compatible",
                "service": "mock-triton",
                "capabilities": ["rerank", "embedding", "multimodal"],
            }).encode("utf-8"))
            logger.info("Triton health check passed")
        elif self.path == "/v2/health/live":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"live": True}).encode("utf-8"))
        elif self.path == "/v2/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"models": ["embedding", "rerank", "multimodal"]}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        """处理POST请求"""
        if self.path == "/v1/rerank":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            
            logger.info(f"Received rerank request: {data}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            response = {
                "mode": "local-compatible",
                "results": [
                    {
                        "index": i,
                        "score": 1.0 - (i * 0.1),
                        "relevance_score": 1.0 - (i * 0.1),
                        "document": data.get("documents", [])[i],
                    }
                    for i in range(len(data.get("documents", [])))
                ]
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
            logger.info("Rerank response sent")
        elif self.path == "/v1/embedding":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            
            logger.info(f"Received embedding request: {data}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # 生成随机向量
            vectors = []
            for text in data.get("texts", []):
                vector = [random.random() for _ in range(768)]  # 768维向量
                vectors.append(vector)
            
            response = {
                "embeddings": vectors
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
            logger.info("Embedding response sent")
        elif self.path == "/v1/multimodal":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            
            logger.info(f"Received multimodal request: {data}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            response = {
                "analysis": {
                    "objects": ["product", "packaging"],
                    "sentiment": "positive",
                    "confidence": 0.95
                }
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
            logger.info("Multimodal response sent")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """自定义日志"""
        logger.info(f"[Triton] [{self.address_string()}] {format % args}")


class MockKongHandler(BaseHTTPRequestHandler):
    """模拟Kong Gateway的HTTP处理器"""

    def do_GET(self) -> None:
        """处理GET请求"""
        scenario_status, scenario_response = _apply_scenario_defaults(self, "gateway")
        parsed_path = urlparse(self.path).path
        if scenario_status is not None and scenario_response is not None:
            self.send_response(scenario_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(scenario_response).encode("utf-8"))
            return
        if parsed_path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "kong": {"version": "3.4.0"},
                "database": {"reachable": True},
                "server": {"connections": {"accepted": 0, "handled": 0}}
            }).encode("utf-8"))
        elif self.path.startswith("/services"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": []}).encode("utf-8"))
        elif self.path == "/routes":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": []}).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"message": "Hello from mock Kong"}).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        logger.info(f"[Kong] [{self.address_string()}] {format % args}")


class MockOpenSearchHandler(BaseHTTPRequestHandler):
    """模拟OpenSearch的HTTP处理器"""

    def do_GET(self) -> None:
        """处理GET请求"""
        scenario_status, scenario_response = _apply_scenario_defaults(self, "search")
        parsed_path = urlparse(self.path).path
        if scenario_status is not None and scenario_response is not None:
            self.send_response(scenario_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(scenario_response).encode("utf-8"))
            return
        if parsed_path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "name": "opensearch-node",
                "cluster_name": "opensearch-cluster",
                "version": {"number": "2.11.0"}
            }).encode("utf-8"))
        elif self.path == "/_cluster/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "cluster_name": "opensearch-cluster",
                "status": "green",
                "number_of_nodes": 1,
                "number_of_data_nodes": 1
            }).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # 模拟搜索结果
            hits = []
            for i in range(3):
                hits.append({
                    "_id": f"doc_{i}",
                    "_score": 1.0 - (i * 0.1),
                    "_source": {
                        "title": f"Product {i}",
                        "description": f"Description for product {i}",
                        "price": 100 + (i * 10)
                    }
                })
            self.wfile.write(json.dumps({"hits": {"hits": hits}}).encode("utf-8"))

    def do_POST(self) -> None:
        """处理POST请求"""
        scenario_status, scenario_response = _apply_scenario_defaults(self, "search")
        parsed_path = urlparse(self.path).path
        if scenario_status is not None and scenario_response is not None:
            self.send_response(scenario_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(scenario_response).encode("utf-8"))
            return
        if parsed_path.endswith("/_search"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            
            logger.info(f"Received search request: {data}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # 模拟搜索结果
            hits = []
            for i in range(5):
                hits.append({
                    "_id": f"doc_{i}",
                    "_score": 1.0 - (i * 0.1),
                    "_source": {
                        "title": f"Product {i}",
                        "description": f"Description for product {i}",
                        "price": 100 + (i * 10),
                        "category": "electronics"
                    }
                })
            
            response = {
                "hits": {
                    "total": {"value": 100, "relation": "eq"},
                    "hits": hits
                }
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
            logger.info("Search response sent")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"acknowledged": True}).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        logger.info(f"[OpenSearch] [{self.address_string()}] {format % args}")


class MockExternalAPIHandler(BaseHTTPRequestHandler):
    """模拟外部API的HTTP处理器"""

    def do_GET(self) -> None:
        """处理GET请求"""
        scenario_status, scenario_response = _apply_scenario_defaults(self, "external_api")
        parsed_path = urlparse(self.path).path
        if scenario_status is not None and scenario_response is not None:
            self.send_response(scenario_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(scenario_response).encode("utf-8"))
            return
        normalized_path = _normalize_internal_erp_path(self.path)
        if parsed_path.startswith("/amazon"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "products": [
                    {"id": "B08X5G8Q2Y", "title": "Wireless Earbuds", "price": 49.99, "rating": 4.5},
                    {"id": "B07K14XKZH", "title": "Bluetooth Speaker", "price": 79.99, "rating": 4.3}
                ]
            }).encode("utf-8"))
        elif self.path.startswith("/tiktok"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "trends": [
                    {"hashtag": "#wirelessearbuds", "views": 123456789},
                    {"hashtag": "#bluetoothspeaker", "views": 987654321}
                ]
            }).encode("utf-8"))
        elif self.path.startswith("/google-trends"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "interest_over_time": [
                    {"date": "2026-04-01", "value": 80},
                    {"date": "2026-04-02", "value": 85},
                    {"date": "2026-04-03", "value": 90}
                ]
            }).encode("utf-8"))
        elif self.path.startswith("/1688"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "suppliers": [
                    {"id": "12345", "name": "Shenzhen Electronics Co.", "min_order": 10, "price": 25.00},
                    {"id": "67890", "name": "Guangzhou Audio Tech", "min_order": 5, "price": 28.00}
                ]
            }).encode("utf-8"))
        # ERP系统需要的端点
        elif normalized_path == "/products":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "items": [
                    {"id": "1", "name": "Wireless Earbuds", "price": 49.99, "stock": 100},
                    {"id": "2", "name": "Bluetooth Speaker", "price": 79.99, "stock": 50}
                ]
            }).encode("utf-8"))
        elif normalized_path == "/supplier-products":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "items": [
                    {"id": "SP1", "supplier_id": "12345", "product_name": "Wireless Earbuds", "cost": 25.00, "min_order": 10},
                    {"id": "SP2", "supplier_id": "67890", "product_name": "Bluetooth Speaker", "cost": 40.00, "min_order": 5}
                ]
            }).encode("utf-8"))
        elif normalized_path == "/inventory-snapshots":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "items": [
                    {"id": "INV1", "sku": "SKU-001", "warehouse_id": "WH-01", "available_quantity": 18, "safety_stock": 10}
                ]
            }).encode("utf-8"))
        elif normalized_path == "/customer-feedbacks":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "items": [
                    {"id": "FB1", "product_id": "1", "rating": 4.5, "comment": "Great product!", "date": "2026-04-01"},
                    {"id": "FB2", "product_id": "2", "rating": 4.0, "comment": "Good quality", "date": "2026-04-02"}
                ]
            }).encode("utf-8"))
        elif normalized_path in {"/listings", "/recommendations"}:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"items": []}).encode("utf-8"))
        elif normalized_path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"message": "Hello from mock External API"}).encode("utf-8"))

    def do_POST(self) -> None:
        """处理POST请求"""
        scenario_status, scenario_response = _apply_scenario_defaults(self, "external_api")
        normalized_path = _normalize_internal_erp_path(self.path)
        if scenario_status is not None and scenario_response is not None:
            self.send_response(scenario_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(scenario_response).encode("utf-8"))
            return
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
        payload = json.loads(post_data or b"{}")

        response: dict[str, Any]
        if normalized_path == "/recommendations":
            response = {
                "recommendation_id": payload.get("recommendation_id") or f"REC-{payload.get('task_id', 'HTTP')}",
                "status": payload.get("status") or "submitted",
                "owner_domain": payload.get("owner_domain") or "pdm",
                "write_object": payload.get("write_object") or "recommendation",
                "accepted": True,
            }
        elif normalized_path == "/product-plans/bulk-upsert":
            response = {
                "purchase_order_id": payload.get("purchase_order_id") or f"PO-{payload.get('task_id', 'HTTP')}",
                "status": payload.get("status") or "pending_review",
                "supplier_code": payload.get("supplier_code"),
                "owner_domain": payload.get("owner_domain") or "scm",
                "write_object": payload.get("write_object") or "recommendation",
                "accepted": True,
            }
        elif normalized_path == "/replenishment-plans/bulk-upsert":
            response = {
                "reservation_id": payload.get("reservation_id") or f"RSV-{payload.get('task_id', 'HTTP')}",
                "status": payload.get("status") or "reserved",
                "location_code": payload.get("location_code") or "WH-A-01",
                "owner_domain": payload.get("owner_domain") or "wms",
                "write_object": payload.get("write_object") or "recommendation",
                "accepted": True,
            }
        elif normalized_path in {"/products/bulk-upsert", "/listing-drafts"}:
            response = {
                "listing_draft_id": payload.get("listing_draft_id") or f"LST-{payload.get('task_id', 'HTTP')}",
                "status": payload.get("status") or "pending_approval",
                "owner_domain": "som",
                "write_object": "draft",
                "accepted": True,
            }
        else:
            response = {"status": "success", "accepted": True}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        logger.info(f"[ExternalAPI] [{self.address_string()}] {format % args}")


def run_server(server_class: type[HTTPServer], handler_class: type[BaseHTTPRequestHandler], port: int, name: str) -> None:
    """运行HTTP服务器"""
    server_address = ("", port)
    server_class.allow_reuse_address = True
    server_class.allow_reuse_port = True
    httpd = server_class(server_address, handler_class)
    logger.info(f"Starting {name} mock server on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info(f"Stopping {name} mock server...")
        httpd.shutdown()


def main() -> int:
    """主函数"""
    parser = argparse.ArgumentParser(description="模拟特殊软件运行")
    parser.add_argument("--triton", action="store_true", help="启动Triton模拟服务器")
    parser.add_argument("--kong", action="store_true", help="启动Kong模拟服务器")
    parser.add_argument("--opensearch", action="store_true", help="启动OpenSearch模拟服务器")
    parser.add_argument("--external-api", action="store_true", help="启动外部API模拟服务器")
    parser.add_argument("--all", action="store_true", help="启动所有模拟服务器")
    parser.add_argument("--triton-port", type=int, default=8000, help="Triton端口 (默认: 8000)")
    parser.add_argument("--kong-port", type=int, default=8001, help="Kong端口 (默认: 8001)")
    parser.add_argument("--opensearch-port", type=int, default=9200, help="OpenSearch端口 (默认: 9200)")
    parser.add_argument("--external-api-port", type=int, default=8080, help="外部API端口 (默认: 8080)")
    
    args = parser.parse_args()
    
    threads: list[Thread] = []
    
    if args.all or args.triton:
        triton_thread = Thread(
            target=run_server,
            args=(HTTPServer, MockTritonHandler, args.triton_port, "Triton"),
            daemon=True
        )
        triton_thread.start()
        threads.append(triton_thread)
        time.sleep(0.5)
    
    if args.all or args.kong:
        kong_thread = Thread(
            target=run_server,
            args=(HTTPServer, MockKongHandler, args.kong_port, "Kong"),
            daemon=True
        )
        kong_thread.start()
        threads.append(kong_thread)
        time.sleep(0.5)
    
    if args.all or args.opensearch:
        opensearch_thread = Thread(
            target=run_server,
            args=(HTTPServer, MockOpenSearchHandler, args.opensearch_port, "OpenSearch"),
            daemon=True
        )
        opensearch_thread.start()
        threads.append(opensearch_thread)
        time.sleep(0.5)
    
    if args.all or args.external_api:
        external_api_thread = Thread(
            target=run_server,
            args=(HTTPServer, MockExternalAPIHandler, args.external_api_port, "ExternalAPI"),
            daemon=True
        )
        external_api_thread.start()
        threads.append(external_api_thread)
        time.sleep(0.5)
    
    if not threads:
        print("请指定至少一个模拟服务器: --triton, --kong, --opensearch, --external-api, 或 --all")
        return 1
    
    logger.info("所有模拟服务器已启动")
    logger.info("服务地址:")
    if args.all or args.triton:
        logger.info(f"  Triton: http://localhost:{args.triton_port}")
    if args.all or args.kong:
        logger.info(f"  Kong: http://localhost:{args.kong_port}")
    if args.all or args.opensearch:
        logger.info(f"  OpenSearch: http://localhost:{args.opensearch_port}")
    if args.all or args.external_api:
        logger.info(f"  External API: http://localhost:{args.external_api_port}")
    logger.info("按 Ctrl+C 停止所有服务器")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("正在停止所有服务器...")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
