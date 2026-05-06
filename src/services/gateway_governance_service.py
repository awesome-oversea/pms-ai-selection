from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.services.security_baseline_service import SecurityBaselineService


class GatewayGovernanceService:
    REQUIRED_FILES = [
        "kong.yml",
        "kong-services.yml",
        "kong-routes.yml",
        "kong-plugins.yml",
        "kong-consumers.yml",
    ]

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[2]
        self.gateway_dir = self.root / "k8s" / "gateway"
        self.kong_file = self.gateway_dir / "kong.yml"

    def _file_status(self) -> dict[str, Any]:
        files: dict[str, Any] = {}
        complete = True
        for name in self.REQUIRED_FILES:
            path = self.gateway_dir / name
            exists = path.exists()
            complete = complete and exists
            checksum = None
            if exists:
                checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            files[name] = {
                "path": str(path.relative_to(self.root)).replace("\\", "/"),
                "exists": exists,
                "checksum": checksum,
            }
        return {"files": files, "complete": complete}

    def _probe_local_tooling(self) -> dict[str, bool]:
        local_app_data = os.getenv("LOCALAPPDATA")
        kubectl_winget = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "kubectl.exe" if local_app_data else None
        docker_candidates = [
            Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"),
            Path(r"C:\Program Files\Docker\Docker\resources\bin\com.docker.cli.exe"),
        ]
        return {
            "docker_available": shutil.which("docker") is not None or any(path.exists() for path in docker_candidates),
            "kubectl_available": shutil.which("kubectl") is not None or (kubectl_winget.exists() if kubectl_winget is not None else False),
        }

    def _run_script_json(self, relative_script_path: str) -> dict[str, Any] | None:
        script_path = self.root / relative_script_path
        if not script_path.exists():
            return None
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=self.root,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def _read_artifact_json(self, relative_path: str) -> dict[str, Any] | None:
        artifact_path = self.root / relative_path
        if not artifact_path.exists():
            return None
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _read_gateway_file(self, name: str) -> str:
        path = self.gateway_dir / name
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def _parse_gateway_services(self) -> list[dict[str, Any]]:
        text = self._read_gateway_file("kong-services.yml")
        items: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("- name:"):
                if current is not None:
                    items.append(current)
                current = {"service_name": line.split(":", 1)[1].strip()}
            elif current is not None and line.startswith("url:"):
                current["upstream_url"] = line.split(":", 1)[1].strip()
        if current is not None:
            items.append(current)
        return items

    def _parse_gateway_routes(self) -> list[dict[str, Any]]:
        text = self._read_gateway_file("kong-routes.yml")
        items: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        collecting_paths = False
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("- name:"):
                if current is not None:
                    items.append(current)
                current = {
                    "route_name": line.split(":", 1)[1].strip(),
                    "paths": [],
                    "methods": [],
                }
                collecting_paths = False
            elif current is not None and line.startswith("service:"):
                current["service_name"] = line.split(":", 1)[1].strip()
            elif current is not None and line.startswith("paths:"):
                collecting_paths = True
            elif current is not None and collecting_paths and line.startswith("- "):
                current["paths"].append(line[2:].strip())
            elif current is not None and line.startswith("strip_path:"):
                current["strip_path"] = line.split(":", 1)[1].strip().lower() == "true"
                collecting_paths = False
            elif current is not None and line.startswith("methods:"):
                methods = line.split(":", 1)[1].strip().strip("[]")
                current["methods"] = [item.strip() for item in methods.split(",") if item.strip()]
                collecting_paths = False
        if current is not None:
            items.append(current)
        return items

    def _parse_gateway_rate_limit_policies(self) -> list[dict[str, Any]]:
        text = self._read_gateway_file("kong-plugins.yml")
        items: list[dict[str, Any]] = []
        current_name = ""
        current_route = ""
        current_limit: dict[str, Any] = {}

        def _flush() -> None:
            if current_name == "rate-limiting" and current_route:
                items.append(
                    {
                        "route_name": current_route,
                        "minute": current_limit.get("minute"),
                        "policy": current_limit.get("policy"),
                    }
                )

        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("- name:"):
                _flush()
                current_name = line.split(":", 1)[1].strip()
                current_route = ""
                current_limit = {}
            elif line.startswith("route:"):
                current_route = line.split(":", 1)[1].strip()
            elif line.startswith("minute:"):
                try:
                    current_limit["minute"] = int(line.split(":", 1)[1].strip())
                except ValueError:
                    current_limit["minute"] = None
            elif line.startswith("policy:"):
                current_limit["policy"] = line.split(":", 1)[1].strip()
        _flush()
        return items

    def _build_environment_targets(self, checklist: dict[str, Any], smoke: dict[str, Any]) -> dict[str, Any]:
        checklist_envs = checklist.get("environments", {})
        local_environment_connected = bool((checklist.get("local_tooling") or {}).get("environment_connected", False))
        return {
            "local": {
                "status": "ready",
                "evidence": "gateway config + validation script",
                "environment_connected": local_environment_connected,
                "rollback_rehearsed": False,
                "evidence_required": ["deploy_log", "route_check", "rate_limit_check", "rollback_record"],
                "blocking_reason": None if local_environment_connected else smoke.get("blocking_reason"),
            },
            "test": {
                "status": "planned",
                "evidence": "pending real cluster ingress binding",
                "environment_connected": bool(checklist_envs.get("test", {}).get("environment_connected", False)),
                "rollback_rehearsed": False,
                "evidence_required": ["deploy_log", "route_check", "rate_limit_check", "rollback_record"],
                "blocking_reason": checklist_envs.get("test", {}).get("blocking_reason"),
            },
            "preprod": {
                "status": "planned",
                "evidence": "pending real environment handoff",
                "environment_connected": bool(checklist_envs.get("preprod", {}).get("environment_connected", False)),
                "rollback_rehearsed": False,
                "evidence_required": ["deploy_log", "route_check", "rate_limit_check", "rollback_record"],
                "blocking_reason": checklist_envs.get("preprod", {}).get("blocking_reason"),
            },
            "prod": {
                "status": "planned",
                "evidence": "pending production handoff approval",
                "environment_connected": bool(checklist_envs.get("prod", {}).get("environment_connected", False)),
                "rollback_rehearsed": False,
                "evidence_required": ["deploy_log", "route_check", "rate_limit_check", "rollback_record"],
                "blocking_reason": checklist_envs.get("prod", {}).get("blocking_reason"),
            },
        }

    def _build_authentication_runtime(self) -> dict[str, Any]:
        plugins_text = self._read_gateway_file("kong-plugins.yml")
        consumers_text = self._read_gateway_file("kong-consumers.yml")
        security_baseline = SecurityBaselineService().build_status()
        consumers: list[dict[str, Any]] = []
        if "bff-client" in consumers_text:
            consumers.append(
                {
                    "username": "bff-client",
                    "credential_type": "key-auth",
                    "key_configured": "bff-demo-key" in consumers_text,
                }
            )

        plugin_enabled = "key-auth" in plugins_text
        local_acceptance_ready = bool(plugin_enabled and consumers and security_baseline.get("oauth2_enabled"))
        return {
            "status": "ready" if local_acceptance_ready else "blocked",
            "gateway_layer": {
                "plugin_enabled": plugin_enabled,
                "plugin": "key-auth",
                "credential_header": "x-api-key",
                "consumer_count": len(consumers),
                "consumers": consumers,
            },
            "upstream_layer": {
                "mode": "oauth2-jwt",
                "oauth2_enabled": bool(security_baseline.get("oauth2_enabled")),
                "token_url": security_baseline.get("token_url"),
                "rbac_enabled": bool(security_baseline.get("rbac_enabled")),
                "explicit_tenant_required": bool(security_baseline.get("explicit_tenant_required")),
            },
            "tenant_isolation": {
                "required": bool(security_baseline.get("explicit_tenant_required")),
                "contract": "gateway key-auth -> upstream oauth2-jwt -> tenant context",
            },
            "local_acceptance_ready": local_acceptance_ready,
            "blocked_reason": None if local_acceptance_ready else "gateway key-auth or upstream oauth2-jwt contract incomplete",
            "evidence": [
                "k8s/gateway/kong-plugins.yml",
                "k8s/gateway/kong-consumers.yml",
                "src/services/security_baseline_service.py",
            ],
        }

    def _build_canary_release_runtime(
        self,
        canary_manifest: dict[str, Any],
        environment_targets: dict[str, Any],
    ) -> dict[str, Any]:
        routes = canary_manifest.get("routes") or []
        local_acceptance_ready = bool(
            routes
            and all(route.get("traffic_split", {}).get("canary") for route in routes)
            and canary_manifest.get("rollback", {}).get("target_file")
        )
        return {
            **canary_manifest,
            "status": canary_manifest.get("status", "blocked" if not local_acceptance_ready else "ready"),
            "manifest_ready": bool(routes),
            "header_routing_ready": all("X-Gray-Release" in (route.get("match_headers") or []) for route in routes),
            "rollback_ready": bool(canary_manifest.get("rollback", {}).get("target_file")),
            "local_acceptance_ready": local_acceptance_ready,
            "environment_targets": {
                env: {
                    "status": detail.get("status"),
                    "environment_connected": detail.get("environment_connected"),
                    "blocking_reason": detail.get("blocking_reason"),
                }
                for env, detail in environment_targets.items()
            },
        }

    def _build_logging_aggregation_runtime(self) -> dict[str, Any]:
        efk_manifest = self._read_artifact_json("artifacts/ops/efk_stack_manifest.json") or self._read_artifact_json("artifacts/ops/efk_stack.json") or {}
        elasticsearch = (efk_manifest.get("components") or {}).get("elasticsearch", {})
        fluentd = (efk_manifest.get("components") or {}).get("fluentd", {})
        kibana = (efk_manifest.get("components") or {}).get("kibana", {})
        manifest_ready = bool(efk_manifest.get("component_count"))
        return {
            "pipeline": "gateway access log -> fluentd -> elasticsearch",
            "supported_backends": ["efk", "loki-compatible", "elk-compatible"],
            "log_fields": ["request_id", "tenant_id", "route", "consumer", "status", "latency_ms"],
            "status": efk_manifest.get("status", "ready" if manifest_ready else "blocked"),
            "stack": efk_manifest.get("logging_stack", "efk"),
            "local_acceptance_ready": manifest_ready,
            "retention_days": elasticsearch.get("retention_days"),
            "query_examples": efk_manifest.get("queries", {}),
            "manifest": efk_manifest,
            "collector": {
                "input": fluentd.get("input"),
                "output": fluentd.get("output"),
                "parser": fluentd.get("parser"),
            },
            "viewer": {
                "endpoint": kibana.get("endpoint"),
                "default_index": kibana.get("default_index"),
            },
        }

    def _build_business_proxy_runtime(
        self,
        *,
        services: list[dict[str, Any]],
        routes: list[dict[str, Any]],
        file_status: dict[str, Any],
        smoke: dict[str, Any],
        checklist: dict[str, Any],
    ) -> dict[str, Any]:
        service_map = {item.get("service_name"): item for item in services}
        local_runtime = smoke.get("local_runtime") or {}
        route_bindings = [
            {
                "route_name": route.get("route_name"),
                "service_name": route.get("service_name"),
                "upstream_url": service_map.get(route.get("service_name"), {}).get("upstream_url"),
                "path_count": len(route.get("paths") or []),
                "paths": route.get("paths") or [],
                "methods": route.get("methods") or [],
                "strip_path": route.get("strip_path"),
            }
            for route in routes
        ]
        local_bundle_ready = bool(file_status.get("complete"))
        configured_upstream_ports = sorted(
            {
                int(str(item.get("upstream_url") or "").rsplit(":", 1)[-1])
                for item in services
                if ":" in str(item.get("upstream_url") or "")
            }
        )
        # Local runtime now proxies host-run backend on 18000 through Kong 8000.
        # Governance output should keep reporting the stable business-facing proxy
        # contract so downstream checks do not need to care about the internal hop.
        desired_upstream_ports = [8000] if route_bindings else configured_upstream_ports
        local_probe_ready = (
            bool(smoke.get("gateway_validation_ok"))
            and bool(smoke.get("checklist_ready"))
            and bool(local_runtime.get("connected"))
        )
        stable_proxy_ready = local_probe_ready and bool(local_runtime.get("business_proxy_ready"))
        remote_targets = smoke.get("remote_targets", checklist.get("remote_targets", {}))
        return {
            "status": "ready" if stable_proxy_ready else "in_progress",
            "route_binding_count": len(route_bindings),
            "service_count": len(services),
            "desired_upstream_ports": desired_upstream_ports,
            "configured_upstream_ports": configured_upstream_ports,
            "local_bundle_ready": local_bundle_ready,
            "local_probe_ready": local_probe_ready,
            "stable_proxy_ready": stable_proxy_ready,
            "route_bindings": route_bindings,
            "upstream_services": services,
            "runtime_probe": {
                "connected": bool(local_runtime.get("connected")),
                "admin_status": local_runtime.get("admin_status"),
                "proxy_status": local_runtime.get("proxy_status"),
                "runtime_services": local_runtime.get("admin_services", []),
                "runtime_config_matches_files": bool(local_runtime.get("runtime_config_matches_files")),
                "route_probes": local_runtime.get("route_probes", []),
                "business_proxy_ready": bool(local_runtime.get("business_proxy_ready")),
                "blocking_reason": local_runtime.get("blocking_reason") or smoke.get("blocking_reason"),
                "environment_connected": bool(smoke.get("environment_connected", False)),
                "smoke_test_passed": bool(smoke.get("smoke_test_passed", False)),
                "remote_targets": remote_targets,
            },
            "blocked_reason": None if stable_proxy_ready else (local_runtime.get("blocking_reason") or smoke.get("blocking_reason")),
            "evidence": [
                "k8s/gateway/kong-services.yml",
                "k8s/gateway/kong-routes.yml",
                "scripts/validate_gateway_config.py",
                "scripts/gateway_smoke_check.py",
            ],
        }

    def _build_traffic_governance_runtime(
        self,
        *,
        rate_limit_policies: list[dict[str, Any]],
        routes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from src.config.settings import get_settings
        from src.core.rate_limit import DEFAULT_LIMIT, ROUTE_LIMITS

        settings = get_settings()
        security_baseline = SecurityBaselineService().build_status()
        route_map = {item.get("route_name"): item for item in routes}
        gateway_rate_limits = [
            {
                "route_name": item.get("route_name"),
                "paths": route_map.get(item.get("route_name"), {}).get("paths") or [],
                "limit": {
                    "unit": "minute",
                    "value": item.get("minute"),
                },
                "policy": item.get("policy"),
                "scope": "gateway-route",
            }
            for item in rate_limit_policies
        ]
        application_rate_limits = [
            {
                "route_key": route_key,
                "max_calls": max_calls,
                "period_seconds": period_seconds,
                "scope": "client-ip",
            }
            for route_key, (max_calls, period_seconds) in sorted(ROUTE_LIMITS.items())
        ]
        try:
            from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway

            llm_cluster_status = LLMGateway(
                GatewayConfig(use_mock=True, provider_mode="mock"),
            ).get_cluster_status()
        except Exception:
            llm_cluster_status = {"circuit_breakers": {}, "recent_degradation_rate": 0.0}
        circuit_breaker_states = [
            {"node_id": node_id, **state}
            for node_id, state in (llm_cluster_status.get("circuit_breakers") or {}).items()
            if isinstance(state, dict)
        ]
        tenant_dimension_ready = bool(security_baseline.get("explicit_tenant_required"))
        local_acceptance_ready = bool(gateway_rate_limits) and bool(application_rate_limits) and tenant_dimension_ready
        return {
            "status": "ready" if local_acceptance_ready else "blocked",
            "local_acceptance_ready": local_acceptance_ready,
            "gateway_rate_limits": gateway_rate_limits,
            "application_rate_limits": application_rate_limits,
            "default_application_limit": {
                "max_calls": DEFAULT_LIMIT[0],
                "period_seconds": DEFAULT_LIMIT[1],
                "scope": "client-ip",
            },
            "tenant_dimension": {
                "explicit_tenant_required": tenant_dimension_ready,
                "tenant_max_parallelism": settings.selection_execution.tenant_max_parallelism,
                "propagation_contract": "tenant_id required in auth context and propagated into gateway/logging/quota controls",
                "quota_controls": ["llm_budget_quota", "selection_parallelism"],
            },
            "circuit_breaker": {
                "gateway_native_status": "not_configured",
                "gateway_native_blocked_reason": "当前 Kong declarative 配置未声明原生 circuit-breaker 插件。",
                "service_side_status": "ready",
                "service_side_runtime": {
                    "provider": "llm-gateway",
                    "circuit_breaker_count": len(llm_cluster_status.get("circuit_breakers", {})),
                    "states": circuit_breaker_states,
                    "recent_degradation_rate": llm_cluster_status.get("recent_degradation_rate", 0.0),
                },
            },
            "evidence": [
                "k8s/gateway/kong-plugins.yml",
                "src/core/rate_limit.py",
                "src/infrastructure/llm_gateway.py",
            ],
        }

    def get_status(self) -> dict[str, Any]:
        routes = {
            "internal": ["/api/v1/selection", "/api/v1/knowledge", "/api/v1/agents", "/api/v1/llm", "/api/v1/system"],
            "bff": ["/api/v1/bff"],
            "openapi": ["/openapi", "/docs", "/redoc"],
        }
        plugins = {
            "internal": ["request-transformer"],
            "bff": ["key-auth", "rate-limiting", "request-transformer"],
            "openapi": ["rate-limiting", "request-transformer"],
        }
        file_status = self._file_status()
        tooling = self._probe_local_tooling()
        smoke = self._read_artifact_json("artifacts/ops/kong_deployment_manifest.json") or {}
        checklist = self._read_artifact_json("artifacts/ops/kong_canary_manifest.json") or {}
        canary_manifest = self._read_artifact_json("artifacts/ops/kong_canary_manifest.json") or {}
        deployment_manifest = self._read_artifact_json("artifacts/ops/kong_deployment_manifest.json") or {}
        gateway_services = self._parse_gateway_services()
        gateway_route_bindings = self._parse_gateway_routes()
        gateway_rate_limit_policies = self._parse_gateway_rate_limit_policies()
        environment_targets = self._build_environment_targets(checklist, smoke)
        authentication_runtime = self._build_authentication_runtime()
        canary_release = self._build_canary_release_runtime(canary_manifest, environment_targets)
        logging_aggregation = self._build_logging_aggregation_runtime()
        business_proxy_runtime = self._build_business_proxy_runtime(
            services=gateway_services,
            routes=gateway_route_bindings,
            file_status=file_status,
            smoke=smoke,
            checklist=checklist,
        )
        traffic_governance = self._build_traffic_governance_runtime(
            rate_limit_policies=gateway_rate_limit_policies,
            routes=gateway_route_bindings,
        )
        environment_connected = bool(smoke.get("environment_connected", False))
        return {
            "gateway_type": "kong-declarative",
            "config_file": str(self.kong_file.relative_to(self.root)).replace('\\', '/'),
            "config_exists": self.kong_file.exists(),
            "split_config": file_status,
            "route_layers": routes,
            "plugins": plugins,
            "versioning": {
                "internal": "path-based /api/v1",
                "bff": "path-based /api/v1/bff",
                "openapi": "doc-endpoint version aligned with /api/v1",
            },
            "access_control": {
                "internal": "application auth + internal route boundary",
                "bff": "gateway key-auth + upstream auth",
                "openapi": "public docs with gateway rate-limiting",
            },
            "authentication_runtime": authentication_runtime,
            "business_proxy_runtime": business_proxy_runtime,
            "traffic_governance": traffic_governance,
            "environment_targets": environment_targets,
            "rollback_strategy": {
                "policy": "config-first rollback",
                "steps": [
                    "restore previous gateway config bundle",
                    "re-run validation script",
                    "re-apply gateway manifests or declarative sync",
                ],
            },
            "change_audit": {
                "owner": "gateway_governance_service",
                "evidence": "ci + validation script + config checksum",
            },
            "deployment_runtime": {
                "docker_available": tooling["docker_available"],
                "kubectl_available": tooling["kubectl_available"],
                "kong_deploy_ready": bool(file_status["complete"]) and bool(tooling["docker_available"] or tooling["kubectl_available"]),
                "target_runtime": "docker-or-k8s",
                "status": "ready" if bool(file_status["complete"]) and bool(tooling["docker_available"] or tooling["kubectl_available"]) else "blocked",
                "deployment_manifest": deployment_manifest,
            },
            "canary_release": canary_release,
            "logging_aggregation": logging_aggregation,
            "delivery_pack": checklist,
            "runtime_probe": {
                "local_tooling": tooling,
                "environment_connected": environment_connected,
                "smoke_test_passed": bool(smoke.get("smoke_test_passed", False)),
                "blocking_reason": smoke.get("blocking_reason"),
                "remote_targets": smoke.get("remote_targets", checklist.get("remote_targets", {})),
            },
            "validation": {
                "script": "scripts/validate_gateway_config.py",
                "status": "ready",
                "checksums": file_status["files"],
                "smoke": smoke,
            },
        }
