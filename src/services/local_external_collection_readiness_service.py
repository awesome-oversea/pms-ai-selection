from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agents.data_collection import DataCollectionAgent
from src.config.settings import get_settings
from src.infrastructure.kafka import close_kafka
from src.services.external_signal_service import ExternalSignalService


class LocalExternalCollectionReadinessService:
    BUSINESS_QUERY = "bluetooth earbuds noise cancelling"
    GOOGLE_KEYWORDS = ["bluetooth earbuds", "noise cancelling earbuds"]
    GDELT_QUERY = "bluetooth earbuds"
    COLLECTION_PROBE_TIMEOUT_SECONDS = 75.0
    MOCK_PROBE_TIMEOUT_SECONDS = 10.0
    GDELT_PROBE_TIMEOUT_SECONDS = 20.0

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.artifact_root = self.root / "artifacts" / "local_external_collection_readiness"
        self.ops_root = self.root / "artifacts" / "ops"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _run_id() -> str:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _status_from_checks(checks: list[dict[str, Any]]) -> str:
        return "passed" if all(bool(item.get("passed")) for item in checks) else "failed"

    @staticmethod
    def _mask_secret(value: str | None) -> str | None:
        if not value:
            return None
        if len(value) <= 6:
            return "*" * len(value)
        return f"{value[:3]}***{value[-2:]}"

    @staticmethod
    def _resolve_record_count(payload: dict[str, Any]) -> int:
        for key in ("total_results", "total_suppliers", "total_creators", "total_analyzed", "total_count"):
            value = payload.get(key)
            if isinstance(value, int):
                return value
        for key in ("products", "suppliers", "creators", "sample_reviews", "top_articles"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        return 0

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        message = str(exc).strip()
        return message or repr(exc)

    @staticmethod
    def _timeout_message(label: str, timeout_seconds: float) -> str:
        return f"{label} timed out after {timeout_seconds:.1f}s"

    @staticmethod
    def _build_source_config() -> dict[str, dict[str, Any]]:
        settings = get_settings().collection_api
        return {
            "amazon": {
                "preferred_channel": "amazon_sp_api",
                "endpoint": settings.amazon_endpoint,
                "credential_ready": bool(settings.amazon_api_key),
                "credential_masked": LocalExternalCollectionReadinessService._mask_secret(settings.amazon_api_key),
                "timeout_seconds": settings.amazon_timeout_seconds,
            },
            "tiktok": {
                "preferred_channel": "tiktok_business_api",
                "endpoint": settings.tiktok_endpoint,
                "credential_ready": bool(settings.tiktok_api_key),
                "credential_masked": LocalExternalCollectionReadinessService._mask_secret(settings.tiktok_api_key),
                "timeout_seconds": settings.tiktok_timeout_seconds,
            },
            "google_trends": {
                "preferred_channel": "google_trends_endpoint",
                "endpoint": settings.google_trends_endpoint,
                "credential_ready": True,
                "optional_api_key_present": bool(settings.google_trends_api_key),
                "credential_masked": LocalExternalCollectionReadinessService._mask_secret(settings.google_trends_api_key),
                "timeout_seconds": settings.google_trends_timeout_seconds,
            },
            "ali1688": {
                "preferred_channel": "ali1688_open_api",
                "endpoint": settings.ali1688_endpoint,
                "credential_ready": bool(settings.ali1688_api_key and settings.ali1688_secret_key),
                "credential_masked": {
                    "api_key": LocalExternalCollectionReadinessService._mask_secret(settings.ali1688_api_key),
                    "secret_key": LocalExternalCollectionReadinessService._mask_secret(settings.ali1688_secret_key),
                },
                "timeout_seconds": settings.ali1688_timeout_seconds,
            },
            "gdelt": {
                "preferred_channel": "gdelt_http",
                "endpoint": "https://api.gdeltproject.org/api/v2/doc/doc",
                "credential_ready": True,
                "timeout_seconds": 15.0,
            },
            "http_retry": {
                "max_attempts": settings.http_max_attempts,
                "base_backoff_seconds": settings.http_base_backoff_seconds,
                "max_backoff_seconds": settings.http_max_backoff_seconds,
                "proxy_provider": settings.proxy_provider,
            },
        }

    @staticmethod
    def _classify_probe(source: str, payload: dict[str, Any], *, credential_ready: bool) -> str:
        mode = str(payload.get("mode") or "unknown")
        signal_context = payload.get("signal_context") if isinstance(payload.get("signal_context"), dict) else {}
        source_channel = str(signal_context.get("source_channel") or "").strip().lower()
        if mode == "mock":
            return "mock"
        if mode == "error":
            return "error"
        if signal_context.get("provider") == "external_signal_service":
            if source_channel in {"public_web_signal", "open_api_signal"}:
                return "web_signal_fallback"
            if source_channel == "enterprise_api" and mode == "real" and not payload.get("degraded"):
                return "preferred_api_real"
        if source == "google_trends":
            if payload.get("real_signal"):
                return "web_signal_fallback"
            if mode == "real":
                return "configured_endpoint_real"
        if source in {"amazon", "tiktok", "ali1688"}:
            if mode == "real" and credential_ready and not payload.get("degraded"):
                return "preferred_api_real"
            if mode == "real":
                return "web_signal_fallback"
        return mode

    @staticmethod
    def _resolve_business_interpretation(payload: dict[str, Any]) -> str:
        signal_readiness = payload.get("signal_readiness") if isinstance(payload.get("signal_readiness"), dict) else {}
        signal_context = payload.get("signal_context") if isinstance(payload.get("signal_context"), dict) else {}
        if signal_readiness:
            if bool(signal_readiness.get("enterprise_ready")):
                return "enterprise_ready"
            if bool(signal_readiness.get("local_business_ready")):
                return "local_validation_only"
            return "not_ready"
        if signal_context.get("provider") == "external_signal_service":
            return "local_validation_only"
        if payload.get("real_signal"):
            return "local_validation_only"
        if payload.get("mode") == "real":
            return "formal_channel_ready"
        if payload.get("mode") == "mock":
            return "mock_only"
        return "error"

    @staticmethod
    def _build_business_readiness_overview(source_probes: dict[str, Any]) -> dict[str, Any]:
        classification_breakdown: dict[str, int] = {}
        local_validation_only_sources: list[str] = []
        formal_ready_sources: list[str] = []
        blocked_sources: list[str] = []
        next_actions: list[str] = []

        for source, probe in source_probes.items():
            classification = str(probe.get("channel_classification") or "unknown")
            classification_breakdown[classification] = classification_breakdown.get(classification, 0) + 1
            interpretation = str(probe.get("business_interpretation") or "unknown")
            if interpretation == "local_validation_only":
                local_validation_only_sources.append(source)
            elif interpretation in {"enterprise_ready", "formal_channel_ready"}:
                formal_ready_sources.append(source)
            elif interpretation in {"not_ready", "mock_only", "error"}:
                blocked_sources.append(source)

        if local_validation_only_sources:
            next_actions.append(
                "keep treating these sources as local business validation only until formal APIs are connected: "
                + ", ".join(sorted(local_validation_only_sources))
            )
        if blocked_sources:
            next_actions.append(
                "prioritize credential, throttling, or endpoint recovery for: " + ", ".join(sorted(blocked_sources))
            )
        if not next_actions:
            next_actions.append("continue replacing fallback-only channels with formal source integrations where available")

        return {
            "classification_breakdown": classification_breakdown,
            "local_validation_only_sources": sorted(local_validation_only_sources),
            "formal_ready_sources": sorted(formal_ready_sources),
            "blocked_sources": sorted(blocked_sources),
            "formal_api_ready_count": len(formal_ready_sources),
            "local_validation_only_count": len(local_validation_only_sources),
            "blocked_source_count": len(blocked_sources),
            "next_actions": next_actions,
        }

    def _build_run_dir(self, output_root: Path | None) -> Path:
        root = output_root or self.artifact_root
        run_dir = root / self._run_id()
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _await_with_timeout(self, awaitable: Any, *, timeout_seconds: float, label: str) -> Any:
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(self._timeout_message(label, timeout_seconds)) from exc

    async def _probe_collection_source(
        self,
        *,
        source: str,
        tool_name: str,
        kwargs: dict[str, Any],
        credential_ready: bool,
    ) -> tuple[str, dict[str, Any]]:
        agent = DataCollectionAgent(config={"quality_threshold": 0.1})
        try:
            payload = await self._await_with_timeout(
                agent.call_tool(tool_name, **kwargs),
                timeout_seconds=self.COLLECTION_PROBE_TIMEOUT_SECONDS,
                label=f"{source} runtime probe",
            )
            signal_context = payload.get("signal_context") if isinstance(payload.get("signal_context"), dict) else {}
            signal_readiness = payload.get("signal_readiness") if isinstance(payload.get("signal_readiness"), dict) else {}
            upstream_error = payload.get("upstream_error") if isinstance(payload.get("upstream_error"), dict) else None
            channel_classification = self._classify_probe(
                source,
                payload,
                credential_ready=credential_ready,
            )
            return source, {
                "tool_name": tool_name,
                "request": kwargs,
                "status": "success",
                "mode": payload.get("mode"),
                "degraded": bool(payload.get("degraded")),
                "degradation_reason": payload.get("degradation_reason"),
                "fallback_reason": payload.get("degradation_reason") or signal_context.get("source_channel"),
                "upstream_error": upstream_error,
                "last_success_at": payload.get("collected_at") or self._now_iso(),
                "recent_error": upstream_error.get("message") if upstream_error else None,
                "record_count": self._resolve_record_count(payload),
                "channel_classification": channel_classification,
                "business_interpretation": self._resolve_business_interpretation(payload),
                "formal_api_ready": channel_classification in {"preferred_api_real", "configured_endpoint_real"},
                "signal_context": signal_context or None,
                "signal_readiness": signal_readiness or None,
                "payload_excerpt": {
                    "source": payload.get("source"),
                    "mode": payload.get("mode"),
                    "degraded": payload.get("degraded"),
                    "record_count": self._resolve_record_count(payload),
                    "source_channel": signal_context.get("source_channel"),
                    "local_business_ready": signal_readiness.get("local_business_ready"),
                    "enterprise_ready": signal_readiness.get("enterprise_ready"),
                    "readiness_tier": signal_readiness.get("readiness_tier"),
                },
            }
        except Exception as exc:
            error = self._format_exception(exc)
            return source, {
                "tool_name": tool_name,
                "request": kwargs,
                "status": "error",
                "error": error,
                "recent_error": error,
                "fallback_reason": "probe_error",
                "last_success_at": None,
                "channel_classification": "error",
                "business_interpretation": "error",
                "formal_api_ready": False,
            }

    async def _probe_collection_sources(self) -> dict[str, Any]:
        configs = self._build_source_config()
        source_requests = {
            "amazon": ("amazon_bsr", {"category": self.BUSINESS_QUERY, "top_n": 5, "marketplace": "US", "mode": "real"}),
            "tiktok": ("tiktok_products", {"query": self.BUSINESS_QUERY, "top_n": 5, "region": "US", "mode": "real"}),
            "google_trends": (
                "google_trends",
                {"keywords": list(self.GOOGLE_KEYWORDS), "time_range": "12m", "geo": "US", "mode": "real"},
            ),
            "ali1688": ("ali1688_supply", {"product_keyword": self.BUSINESS_QUERY, "max_suppliers": 5, "mode": "real"}),
        }
        results = await asyncio.gather(
            *(
                self._probe_collection_source(
                    source=source,
                    tool_name=tool_name,
                    kwargs=kwargs,
                    credential_ready=bool(configs[source].get("credential_ready")),
                )
                for source, (tool_name, kwargs) in source_requests.items()
            )
        )
        return dict(results)

    async def _probe_mock_contract(
        self,
        *,
        name: str,
        tool_name: str,
        kwargs: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        agent = DataCollectionAgent(config={"quality_threshold": 0.1})
        payload = await self._await_with_timeout(
            agent.call_tool(tool_name, **kwargs),
            timeout_seconds=self.MOCK_PROBE_TIMEOUT_SECONDS,
            label=f"{name} mock contract probe",
        )
        return name, {
            "tool_name": tool_name,
            "request": kwargs,
            "mode": payload.get("mode"),
            "degraded": bool(payload.get("degraded")),
            "degradation_reason": payload.get("degradation_reason"),
            "upstream_error": payload.get("upstream_error"),
        }

    async def _probe_mock_contracts(self) -> dict[str, Any]:
        scenarios = {
            "amazon_rate_limited": ("amazon_bsr", {"category": "Amazon 429 limit", "mode": "mock"}),
            "tiktok_auth_failed": ("tiktok_products", {"query": "auth token failed", "mode": "mock"}),
            "ali1688_supplier_unstable": ("ali1688_supply", {"product_keyword": "supplier unstable", "mode": "mock"}),
        }
        results = await asyncio.gather(
            *(
                self._probe_mock_contract(name=name, tool_name=tool_name, kwargs=kwargs)
                for name, (tool_name, kwargs) in scenarios.items()
            )
        )
        return dict(results)

    async def _probe_gdelt_mode(self, *, service: ExternalSignalService, mode: str) -> dict[str, Any]:
        try:
            return await self._await_with_timeout(
                service.collect_gdelt_event_signals(query=self.GDELT_QUERY, mode=mode),
                timeout_seconds=self.GDELT_PROBE_TIMEOUT_SECONDS,
                label=f"gdelt {mode} probe",
            )
        except Exception as exc:
            error = self._format_exception(exc)
            return {
                "source": "media_news",
                "mode": "error",
                "ready": False,
                "query": self.GDELT_QUERY,
                "error": error,
                "degradation": {
                    "degraded": True,
                    "reason": error,
                    "http_status": None,
                    "retry_after_seconds": None,
                    "fallback_mode": None,
                    "live_endpoint_ready": False,
                    "businessization_ready": False,
                },
            }

    async def _probe_gdelt(self) -> dict[str, Any]:
        service = ExternalSignalService(timeout_seconds=15.0)
        real_result, auto_result = await asyncio.gather(
            self._probe_gdelt_mode(service=service, mode="real"),
            self._probe_gdelt_mode(service=service, mode="auto"),
        )
        return {
            "query": self.GDELT_QUERY,
            "real_result": real_result,
            "auto_result": auto_result,
        }

    @staticmethod
    def _is_gdelt_real_ready(result: dict[str, Any]) -> bool:
        degradation = result.get("degradation") or {}
        businessization_ready = degradation.get("businessization_ready")
        live_endpoint_ready = degradation.get("live_endpoint_ready")
        total_count = result.get("total_count")
        records_ready = int(total_count or 0) > 0 if total_count is not None else True
        business_ready = (
            bool(businessization_ready)
            if businessization_ready is not None
            else bool(live_endpoint_ready)
        )
        return (
            result.get("mode") == "real"
            and bool(result.get("ready"))
            and not bool(degradation.get("degraded"))
            and business_ready
            and records_ready
        )

    def _select_gdelt_real_result(self, gdelt_probe: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
        real_result = gdelt_probe.get("real_result") or {}
        auto_result = gdelt_probe.get("auto_result") or {}
        if self._is_gdelt_real_ready(real_result):
            return "real", real_result
        if self._is_gdelt_real_ready(auto_result):
            return "auto", auto_result
        return None, None

    async def run_async(self, output_root: Path | None = None) -> dict[str, Any]:
        run_dir = self._build_run_dir(output_root)
        summary_path = run_dir / "summary.json"
        latest_path = self.ops_root / "local_external_collection_readiness_latest.json"
        partial_artifacts: dict[str, Any] = {"summary": str(summary_path)}
        runtime_warnings: list[dict[str, str]] = []

        try:
            config_matrix = self._build_source_config()
            self._write_json(run_dir / "config_matrix.json", config_matrix)
            partial_artifacts["config_matrix"] = str(run_dir / "config_matrix.json")

            source_probes = await self._probe_collection_sources()
            self._write_json(run_dir / "source_probes.json", source_probes)
            partial_artifacts["source_probes"] = str(run_dir / "source_probes.json")
            business_readiness_overview = self._build_business_readiness_overview(source_probes)
            self._write_json(run_dir / "business_readiness_overview.json", business_readiness_overview)
            partial_artifacts["business_readiness_overview"] = str(run_dir / "business_readiness_overview.json")

            mock_contracts = await self._probe_mock_contracts()
            self._write_json(run_dir / "mock_degradation_contracts.json", mock_contracts)
            partial_artifacts["mock_degradation_contracts"] = str(run_dir / "mock_degradation_contracts.json")

            gdelt_probe = await self._probe_gdelt()
            self._write_json(run_dir / "gdelt_probe.json", gdelt_probe)
            partial_artifacts["gdelt_probe"] = str(run_dir / "gdelt_probe.json")
            gdelt_real_source, gdelt_real_result = self._select_gdelt_real_result(gdelt_probe)

            checks = [
                {
                    "name": "config_matrix_written",
                    "passed": True,
                    "detail": "collection api endpoints / credentials / retry policy recorded",
                    "evidence": config_matrix,
                },
                {
                    "name": "credential_gaps_are_explicit",
                    "passed": all(
                        "credential_ready" in config_matrix[source]
                        for source in ("amazon", "tiktok", "google_trends", "ali1688")
                    ),
                    "detail": "credential readiness is explicit for all collection sources",
                    "evidence": {
                        source: config_matrix[source]["credential_ready"]
                        for source in ("amazon", "tiktok", "google_trends", "ali1688")
                    },
                },
                {
                    "name": "runtime_probe_completed_for_all_sources",
                    "passed": all(
                        source_probes[source].get("channel_classification") in {
                            "preferred_api_real",
                            "configured_endpoint_real",
                            "web_signal_fallback",
                            "error",
                            "mock",
                        }
                        for source in ("amazon", "tiktok", "google_trends", "ali1688")
                    ),
                    "detail": "all sources produced a structured runtime classification",
                    "evidence": {
                        source: {
                            "status": source_probes[source].get("status"),
                            "classification": source_probes[source].get("channel_classification"),
                        }
                        for source in ("amazon", "tiktok", "google_trends", "ali1688")
                    },
                },
                {
                    "name": "fallback_business_semantics_are_explicit",
                    "passed": all(
                        source_probes[source].get("business_interpretation") != "local_validation_only"
                        or bool(source_probes[source].get("signal_context"))
                        or source == "google_trends"
                        for source in ("amazon", "tiktok", "google_trends", "ali1688")
                    ),
                    "detail": "fallback probes expose explicit business semantics instead of only mode=real",
                    "evidence": {
                        source: {
                            "classification": source_probes[source].get("channel_classification"),
                            "business_interpretation": source_probes[source].get("business_interpretation"),
                            "signal_context": source_probes[source].get("signal_context"),
                            "signal_readiness": source_probes[source].get("signal_readiness"),
                        }
                        for source in ("amazon", "tiktok", "google_trends", "ali1688")
                    },
                },
                {
                    "name": "mock_degradation_contracts_intact",
                    "passed": all(
                        bool(mock_contracts[name].get("degraded"))
                        and bool(mock_contracts[name].get("degradation_reason"))
                        for name in mock_contracts
                    ),
                    "detail": "amazon/tiktok/1688 mock degraded scenarios still expose degradation fields",
                    "evidence": mock_contracts,
                },
                {
                    "name": "gdelt_live_probe_ready",
                    "passed": gdelt_real_result is not None,
                    "detail": "gdelt real data is reachable through real or auto mode and not degraded",
                    "evidence": {
                        "real_result_source": gdelt_real_source,
                        "ready": gdelt_real_result.get("ready") if gdelt_real_result else False,
                        "total_count": gdelt_real_result.get("total_count") if gdelt_real_result else 0,
                        "degradation": gdelt_real_result.get("degradation") if gdelt_real_result else None,
                    },
                },
                {
                    "name": "latest_summary_synced",
                    "passed": True,
                    "detail": "latest readiness summary written to artifacts/ops",
                    "evidence": {"latest_summary_path": str(latest_path)},
                },
            ]

            summary = {
                "task_scope": ["N2-01", "N2-02"],
                "task_name": "外部采集真实联调准备与限流治理本地验收",
                "status": self._status_from_checks(checks),
                "accepted": all(bool(item.get("passed")) for item in checks),
                "generated_at": self._now_iso(),
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "business_context": {
                    "selection_query": self.BUSINESS_QUERY,
                    "goal": "明确官方 API readiness、网页信号 fallback readiness 与 GDELT 实时状态，避免把网页 real 信号误判为官方联通。",
                },
                "config_matrix": config_matrix,
                "source_probes": source_probes,
                "business_readiness_overview": business_readiness_overview,
                "readiness_snapshot": {
                    "formal_api_ready_count": business_readiness_overview.get("formal_api_ready_count", 0),
                    "local_validation_only_count": business_readiness_overview.get("local_validation_only_count", 0),
                    "blocked_source_count": business_readiness_overview.get("blocked_source_count", 0),
                    "next_actions": business_readiness_overview.get("next_actions", []),
                },
                "mock_degradation_contracts": mock_contracts,
                "gdelt_probe": {
                    "query": gdelt_probe["query"],
                    "real_ready": gdelt_real_result is not None,
                    "real_result_source": gdelt_real_source,
                    "real_article_count": int(gdelt_real_result.get("total_count") or 0) if gdelt_real_result else 0,
                    "real_degraded": ((gdelt_real_result or {}).get("degradation") or {}).get("degraded"),
                    "auto_mode": (gdelt_probe.get("auto_result") or {}).get("mode"),
                },
                "checks": checks,
                "artifacts": partial_artifacts,
            }
        except Exception as exc:
            summary = {
                "task_scope": ["N2-01", "N2-02"],
                "task_name": "外部采集真实联调准备与限流治理本地验收",
                "status": "failed",
                "accepted": False,
                "generated_at": self._now_iso(),
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "error": self._format_exception(exc),
                "artifacts": partial_artifacts,
            }
        finally:
            try:
                await close_kafka()
            except Exception as exc:
                runtime_warnings.append(
                    {
                        "component": "kafka_producer",
                        "warning": f"close_failed: {self._format_exception(exc)}",
                    }
                )

        if runtime_warnings:
            summary["runtime_warnings"] = runtime_warnings

        self._write_json(summary_path, summary)
        self._write_json(latest_path, summary)
        return summary

    def run(self, output_root: Path | None = None) -> dict[str, Any]:
        return asyncio.run(self.run_async(output_root=output_root))
