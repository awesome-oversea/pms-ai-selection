"""
接口分层治理服务
================

为 T8.3 提供最小 Gateway / BFF / OpenAPI 分层治理定义。
"""

from __future__ import annotations

from typing import Any


class InterfaceGovernanceService:
    def build_governance(self) -> dict[str, Any]:
        return {
            "gateway": {
                "audience": "internal-platform",
                "prefixes": ["/api/v1"],
                "capabilities": ["auth", "rate_limit", "audit", "api_contract"],
                "versioning": {"strategy": "path_prefix", "current": "v1"},
                "rate_limit_policy": {"mode": "middleware", "applies_to": ["/api/v1/*"]},
            },
            "bff": {
                "audience": "web-frontend",
                "prefixes": ["/dashboard", "/selection", "/approval", "/results", "/agents/monitor"],
                "capabilities": ["html_rendering", "view_aggregation"],
                "versioning": {"strategy": "server-side-rendered", "current": "web-v1"},
                "rate_limit_policy": {"mode": "gateway_inherited", "applies_to": ["web views"]},
            },
            "openapi": {
                "audience": "integrators",
                "docs_url": "/docs",
                "openapi_url": "/openapi.json",
                "capabilities": ["schema_export", "sdk_generation_baseline"],
                "versioning": {"strategy": "openapi_v1", "current": "v1"},
                "deprecation_policy": {"required_fields": ["deprecated", "sunset_note"]},
            },
            "rules": {
                "public_interface_boundary": "Only /api/v1 and OpenAPI docs are supported for integration.",
                "bff_boundary": "Web routes are for first-party UI only and not integration contracts.",
                "change_policy": "Breaking changes require version bump or compatibility window.",
            },
        }
