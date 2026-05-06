from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.agents.commercial import CommercialAgent
from src.agents.data_collection import Tool1688
from src.infrastructure.fms_client import FMSClient
from src.infrastructure.oms_client import OMSClient
from src.infrastructure.redis import CacheService, get_redis_connection
from src.infrastructure.scm_client import SCMClient

_QUOTE_CACHE_FALLBACK: dict[str, dict[str, Any]] = {}


class ProfitOptimizationService:
    QUOTE_CACHE_TTL_SECONDS = 3600

    def __init__(self) -> None:
        self.agent = CommercialAgent()
        self.tool_1688 = Tool1688()

    @staticmethod
    def _cache_key(*, product_keyword: str, max_suppliers: int) -> str:
        return f"profit-opt:1688:quotes:{product_keyword.strip().lower()}:{max_suppliers}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    async def _read_quote_cache(self, *, cache_key: str) -> dict[str, Any] | None:
        try:
            redis_client = get_redis_connection()
            cache = CacheService(redis_client)
            cached = await cache.get(cache_key)
            if cached:
                payload = json.loads(cached)
                if isinstance(payload, dict):
                    payload["cache_backend"] = "redis"
                    payload["cache_hit"] = True
                    return payload
        except Exception:
            pass
        fallback = _QUOTE_CACHE_FALLBACK.get(cache_key)
        if fallback is not None:
            return {**fallback, "cache_backend": "memory", "cache_hit": True}
        return None

    async def _write_quote_cache(self, *, cache_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["cached_at"] = self._now_iso()
        normalized["expires_in_seconds"] = self.QUOTE_CACHE_TTL_SECONDS
        try:
            redis_client = get_redis_connection()
            cache = CacheService(redis_client)
            await cache.set(cache_key, json.dumps(normalized, ensure_ascii=False), ttl_seconds=self.QUOTE_CACHE_TTL_SECONDS)
            normalized["cache_backend"] = "redis"
        except Exception:
            _QUOTE_CACHE_FALLBACK[cache_key] = dict(normalized)
            normalized["cache_backend"] = "memory"
        normalized["cache_hit"] = False
        return normalized

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _extract_fms_cost_snapshot(
        cls,
        metrics: list[dict[str, Any]],
        *,
        product_id: str | None,
        exchange_rate: float,
    ) -> dict[str, Any]:
        matched = None
        if product_id:
            for item in metrics:
                if str(item.get("product_id") or item.get("external_product_id") or item.get("id")) == str(product_id):
                    matched = item
                    break
        if matched is None and metrics:
            matched = metrics[0]
        if matched is None:
            return {
                "found": False,
                "product_id": product_id,
                "exchange_rate": exchange_rate,
                "currency": None,
                "procurement_cost_per_unit": 0.0,
                "logistics_cost_per_unit": 0.0,
                "marketing_cost_per_unit": 0.0,
                "tax_cost_per_unit": 0.0,
                "platform_fee_rate": 0.0,
                "platform_fee_amount": 0.0,
                "gross_profit": 0.0,
            }
        return {
            "found": True,
            "product_id": str(matched.get("product_id") or matched.get("external_product_id") or matched.get("id")),
            "exchange_rate": exchange_rate,
            "currency": matched.get("currency") or "USD",
            "procurement_cost_per_unit": cls._safe_float(matched.get("procurement_cost_per_unit") or matched.get("cost") or matched.get("purchase_cost_per_unit")),
            "logistics_cost_per_unit": cls._safe_float(matched.get("logistics_cost_per_unit") or matched.get("logistics_cost")),
            "marketing_cost_per_unit": cls._safe_float(matched.get("marketing_cost_per_unit") or matched.get("advertising_cost_per_unit") or matched.get("ad_cost_per_unit") or matched.get("expense")),
            "tax_cost_per_unit": cls._safe_float(matched.get("tax_cost_per_unit") or matched.get("tax") or matched.get("vat_cost_per_unit")),
            "platform_fee_rate": cls._safe_float(matched.get("platform_fee_rate")),
            "platform_fee_amount": cls._safe_float(matched.get("platform_fee_amount")),
            "gross_profit": cls._safe_float(matched.get("gross_profit")),
        }

    @staticmethod
    def _round(value: float) -> float:
        return round(float(value), 2)

    @classmethod
    def _normalize_supplier_quotes(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        suppliers = payload.get("suppliers") if isinstance(payload.get("suppliers"), list) else []
        normalized: list[dict[str, Any]] = []
        for item in suppliers:
            if not isinstance(item, dict):
                continue
            tiers = item.get("moq_tiers") if isinstance(item.get("moq_tiers"), list) else []
            tier = tiers[0] if tiers else {}
            unit_price = cls._safe_float(item.get("unit_price_usd") or tier.get("unit_price_usd"))
            min_qty = int(tier.get("min_qty") or item.get("moq") or 1)
            reliability = round(
                (cls._safe_float(item.get("rating"), 4.0) / 5.0) * 0.45
                + cls._safe_float(item.get("response_rate"), 0.8) * 0.25
                + (1.0 if item.get("is_verified") else 0.0) * 0.15
                + (1.0 if item.get("trade_assurance") else 0.0) * 0.15,
                4,
            )
            normalized.append(
                {
                    "supplier_code": str(item.get("supplier_id") or item.get("supplier_code") or "supplier-unknown"),
                    "supplier_name": item.get("company_name") or item.get("supplier_name"),
                    "unit_price_usd": cls._round(unit_price),
                    "min_order_qty": max(1, min_qty),
                    "lead_time_days": int(item.get("lead_time_days") or 0),
                    "monthly_capacity": int(item.get("monthly_capacity") or 0),
                    "defect_rate_pct": cls._round(cls._safe_float(item.get("defect_rate_pct"), 0.0)),
                    "reliability_score": reliability,
                    "is_verified": bool(item.get("is_verified", False)),
                    "trade_assurance": bool(item.get("trade_assurance", False)),
                    "response_rate": cls._round(cls._safe_float(item.get("response_rate"), 0.0)),
                    "rating": cls._round(cls._safe_float(item.get("rating"), 0.0)),
                    "tiers": tiers,
                }
            )
        normalized.sort(key=lambda item: (item["unit_price_usd"], -item["reliability_score"]))
        return normalized

    @classmethod
    def _build_quote_cache_summary(cls, product_keyword: str, quotes: list[dict[str, Any]]) -> dict[str, Any]:
        prices = [item["unit_price_usd"] for item in quotes if item.get("unit_price_usd") is not None]
        return {
            "product_keyword": product_keyword,
            "supplier_count": len(quotes),
            "lowest_unit_price_usd": cls._round(min(prices)) if prices else 0.0,
            "highest_unit_price_usd": cls._round(max(prices)) if prices else 0.0,
            "avg_unit_price_usd": cls._round(sum(prices) / len(prices)) if prices else 0.0,
            "verified_supplier_count": sum(1 for item in quotes if item.get("is_verified")),
            "trade_assurance_supplier_count": sum(1 for item in quotes if item.get("trade_assurance")),
        }

    @classmethod
    def _extract_scm_supplier_reliability(
        cls,
        items: list[dict[str, Any]],
        *,
        supplier_code: str | None = None,
        product_keyword: str | None = None,
    ) -> dict[str, Any]:
        matched: dict[str, Any] | None = None
        normalized_keyword = (product_keyword or "").strip().lower()
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate_code = str(item.get("supplier_code") or item.get("supplier_id") or item.get("id") or "")
            if supplier_code and candidate_code == str(supplier_code):
                matched = item
                break
            if matched is None and normalized_keyword:
                haystacks = [
                    str(item.get("product_keyword") or ""),
                    str(item.get("product_name") or ""),
                    str(item.get("product_title") or ""),
                    str(item.get("category") or ""),
                    str(item.get("company_name") or item.get("supplier_name") or ""),
                ]
                if any(normalized_keyword in value.lower() for value in haystacks if value):
                    matched = item
        if matched is None and items:
            first = items[0]
            matched = first if isinstance(first, dict) else None
        if matched is None:
            return {
                "found": False,
                "supplier_code": supplier_code,
                "supplier_name": None,
                "quality_score": 0.0,
                "on_time_delivery_rate": 0.0,
                "price_stability_score": 0.0,
                "response_rate": 0.0,
                "lead_time_days": 0,
                "price_trend": "unknown",
                "reliability_score": 0.0,
                "risk_level": "high",
            }

        quality_score = cls._safe_float(matched.get("quality_score") or matched.get("quality_rating") or matched.get("rating"), 0.0)
        if quality_score > 5:
            quality_score = min(5.0, quality_score / 20)
        on_time_delivery_rate = cls._safe_float(matched.get("on_time_delivery_rate") or matched.get("delivery_rate") or matched.get("ontime_rate"), 0.0)
        if on_time_delivery_rate > 1:
            on_time_delivery_rate = on_time_delivery_rate / 100
        response_rate = cls._safe_float(matched.get("response_rate"), 0.0)
        if response_rate > 1:
            response_rate = response_rate / 100
        price_stability_score = cls._safe_float(matched.get("price_stability_score") or matched.get("price_score") or matched.get("price_stability"), 0.0)
        if price_stability_score > 1:
            price_stability_score = min(1.0, price_stability_score / 100)
        lead_time_days = int(matched.get("lead_time_days") or matched.get("avg_lead_time_days") or 0)
        weighted = (
            (quality_score / 5.0) * 0.4
            + on_time_delivery_rate * 0.25
            + price_stability_score * 0.2
            + response_rate * 0.15
        )
        reliability_score = cls._round(weighted * 100)
        risk_level = "low" if reliability_score >= 80 else "medium" if reliability_score >= 60 else "high"
        return {
            "found": True,
            "supplier_code": str(matched.get("supplier_code") or matched.get("supplier_id") or matched.get("id") or supplier_code or "supplier-unknown"),
            "supplier_name": matched.get("supplier_name") or matched.get("company_name"),
            "quality_score": cls._round(quality_score),
            "on_time_delivery_rate": cls._round(on_time_delivery_rate),
            "price_stability_score": cls._round(price_stability_score),
            "response_rate": cls._round(response_rate),
            "lead_time_days": lead_time_days,
            "price_trend": matched.get("price_trend") or "stable",
            "reliability_score": reliability_score,
            "risk_level": risk_level,
        }

    @classmethod
    def _build_optimal_purchase_batch(
        cls,
        *,
        monthly_demand: int,
        unit_price: float,
        min_order_qty: int,
        lead_time_days: int,
        service_level_days: int = 7,
        ordering_cost: float = 120.0,
        holding_cost_rate: float = 0.24,
    ) -> dict[str, Any]:
        monthly_demand = max(1, int(monthly_demand))
        annual_demand = monthly_demand * 12
        effective_unit_price = max(0.01, unit_price)
        annual_holding_cost = effective_unit_price * max(0.01, holding_cost_rate)
        eoq = ((2 * annual_demand * ordering_cost) / annual_holding_cost) ** 0.5 if annual_holding_cost > 0 else float(monthly_demand)
        recommended_batch = max(int(round(eoq)), int(min_order_qty), int(round(monthly_demand * 0.5)))
        lead_time_demand = int(round(monthly_demand / 30 * max(lead_time_days, 1)))
        safety_stock = int(round(monthly_demand / 30 * max(service_level_days, 1)))
        reorder_point = lead_time_demand + safety_stock
        return {
            "annual_demand": annual_demand,
            "economic_order_quantity": int(round(eoq)),
            "recommended_batch": recommended_batch,
            "min_order_qty": int(min_order_qty),
            "reorder_point_units": reorder_point,
            "safety_stock_units": safety_stock,
            "lead_time_demand_units": lead_time_demand,
            "estimated_ordering_cost": cls._round(ordering_cost),
            "estimated_holding_cost_rate": cls._round(holding_cost_rate),
        }

    @classmethod
    def _build_restock_plan(
        cls,
        *,
        product_keyword: str,
        supplier: dict[str, Any],
        monthly_demand: int,
        current_inventory_units: int,
        target_price: float,
        elasticity_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        batch = cls._build_optimal_purchase_batch(
            monthly_demand=monthly_demand,
            unit_price=cls._safe_float(supplier.get("unit_price_usd"), 0.0),
            min_order_qty=int(supplier.get("min_order_qty") or 1),
            lead_time_days=int(supplier.get("lead_time_days") or 7),
        )
        current_inventory_units = max(0, int(current_inventory_units))
        reorder_needed = current_inventory_units <= batch["reorder_point_units"]
        recommended_units = max(batch["recommended_batch"] - current_inventory_units, batch["min_order_qty"]) if reorder_needed else 0
        projected_revenue = cls._round(recommended_units * max(target_price, 0.0))
        procurement_cost = cls._round(recommended_units * cls._safe_float(supplier.get("unit_price_usd"), 0.0))
        gross_margin = cls._round(projected_revenue - procurement_cost)
        coverage_days = cls._round((current_inventory_units / max(monthly_demand, 1)) * 30)
        return {
            "product_keyword": product_keyword,
            "supplier": supplier,
            "inventory_snapshot": {
                "current_inventory_units": current_inventory_units,
                "inventory_coverage_days": coverage_days,
            },
            "optimal_purchase_batch": batch,
            "restock_recommended": reorder_needed,
            "recommended_restock_units": int(recommended_units),
            "projected_procurement_cost": procurement_cost,
            "projected_revenue": projected_revenue,
            "projected_gross_margin": gross_margin,
            "price_elasticity_snapshot": elasticity_snapshot,
            "generated_at": cls._now_iso(),
        }

    @classmethod
    def _build_oms_price_elasticity_snapshot(cls, orders: list[dict[str, Any]], *, product_id: str | None = None, target_price: float | None = None) -> dict[str, Any]:
        matched = []
        for item in orders:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("product_id") or item.get("external_product_id") or item.get("id") or "")
            if product_id and candidate_id and candidate_id != str(product_id):
                continue
            matched.append(item)
        if not matched:
            return {
                "found": False,
                "data_points": 0,
                "avg_selling_price": None,
                "avg_units": 0,
                "elasticity_signal": "insufficient_data",
                "recommended_price_band": {
                    "lower": target_price,
                    "upper": target_price,
                },
            }
        units = [int(item.get("quantity") or item.get("units") or 0) for item in matched]
        revenues = [cls._safe_float(item.get("revenue") or item.get("sales") or item.get("sales_7d"), 0.0) for item in matched]
        prices = [revenue / unit for revenue, unit in zip(revenues, units, strict=False) if unit > 0]
        avg_price = cls._round(sum(prices) / len(prices)) if prices else cls._round(target_price or 0.0)
        avg_units = cls._round(sum(units) / len(units)) if units else 0.0
        lower = cls._round((target_price or avg_price) * 0.95)
        upper = cls._round((target_price or avg_price) * 1.05)
        return {
            "found": True,
            "data_points": len(matched),
            "avg_selling_price": avg_price,
            "avg_units": avg_units,
            "elasticity_signal": "observed_order_curve",
            "recommended_price_band": {"lower": lower, "upper": upper},
        }

    async def build_quote_cache(self, *, product_keyword: str, max_suppliers: int = 10) -> dict[str, Any]:
        cache_key = self._cache_key(product_keyword=product_keyword, max_suppliers=max_suppliers)
        cached = await self._read_quote_cache(cache_key=cache_key)
        if cached is not None:
            return cached
        raw = await self.tool_1688.execute(product_keyword=product_keyword, max_suppliers=max_suppliers)
        quotes = self._normalize_supplier_quotes(raw if isinstance(raw, dict) else {})
        payload = {
            "product_keyword": product_keyword,
            "quotes": quotes,
            "summary": self._build_quote_cache_summary(product_keyword, quotes),
            "source": "ali1688",
        }
        return await self._write_quote_cache(cache_key=cache_key, payload=payload)

    @classmethod
    def _score_supplier_recommendation(cls, supplier: dict[str, Any], *, lowest_price: float, monthly_demand: int) -> dict[str, Any]:
        unit_price = cls._safe_float(supplier.get("unit_price_usd"), 0.0)
        lead_time_days = int(supplier.get("lead_time_days") or 0)
        defect_rate_pct = cls._safe_float(supplier.get("defect_rate_pct"), 0.0)
        reliability_score = cls._safe_float(supplier.get("reliability_score"), 0.0)
        response_rate = cls._safe_float(supplier.get("response_rate"), 0.0)
        monthly_capacity = int(supplier.get("monthly_capacity") or 0)

        price_score = min(100.0, (lowest_price / max(unit_price, 0.01)) * 100.0) if lowest_price > 0 else 0.0
        delivery_score = max(0.0, min(100.0, 100.0 - max(lead_time_days - 3, 0) * 4.0))
        quality_score = max(0.0, min(100.0, 100.0 - defect_rate_pct * 18.0))
        history_score = max(0.0, min(100.0, reliability_score * 100.0 if reliability_score <= 1 else reliability_score))
        capacity_score = min(100.0, (monthly_capacity / max(monthly_demand, 1)) * 100.0) if monthly_capacity else 60.0
        service_score = min(100.0, response_rate * 100.0 if response_rate <= 1 else response_rate)
        weighted_score = (
            delivery_score * 0.25
            + quality_score * 0.30
            + price_score * 0.25
            + history_score * 0.12
            + capacity_score * 0.05
            + service_score * 0.03
        )
        risk_level = "low" if weighted_score >= 80 else "medium" if weighted_score >= 65 else "high"
        return {
            **supplier,
            "score": cls._round(weighted_score),
            "score_breakdown": {
                "delivery_score": cls._round(delivery_score),
                "quality_score": cls._round(quality_score),
                "price_score": cls._round(price_score),
                "history_score": cls._round(history_score),
                "capacity_score": cls._round(capacity_score),
                "service_score": cls._round(service_score),
            },
            "risk_level": risk_level,
        }

    async def build_supplier_recommendations(
        self,
        *,
        product_keyword: str,
        monthly_demand: int = 300,
        max_suppliers: int = 10,
        target_price: float = 39.9,
    ) -> dict[str, Any]:
        quote_cache = await self.build_quote_cache(product_keyword=product_keyword, max_suppliers=max_suppliers)
        quotes = quote_cache.get("quotes") if isinstance(quote_cache.get("quotes"), list) else []
        if not quotes:
            raise ValueError("未获取到可推荐供应商")
        prices = [self._safe_float(item.get("unit_price_usd"), 0.0) for item in quotes if item.get("unit_price_usd") is not None]
        lowest_price = min(prices) if prices else 0.0
        scored = [self._score_supplier_recommendation(item, lowest_price=lowest_price, monthly_demand=monthly_demand) for item in quotes]
        scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        recommendations = []
        for rank, supplier in enumerate(scored[:5], start=1):
            batch = self._build_optimal_purchase_batch(
                monthly_demand=monthly_demand,
                unit_price=self._safe_float(supplier.get("unit_price_usd"), 0.0),
                min_order_qty=int(supplier.get("min_order_qty") or 1),
                lead_time_days=int(supplier.get("lead_time_days") or 7),
            )
            projected_margin = self._round((target_price - self._safe_float(supplier.get("unit_price_usd"), 0.0)) / max(target_price, 0.01) * 100.0)
            recommendations.append({
                "rank": rank,
                "supplier_code": supplier.get("supplier_code"),
                "supplier_name": supplier.get("supplier_name"),
                "score": supplier.get("score"),
                "risk_level": supplier.get("risk_level"),
                "unit_price_usd": supplier.get("unit_price_usd"),
                "lead_time_days": supplier.get("lead_time_days"),
                "defect_rate_pct": supplier.get("defect_rate_pct"),
                "recommended_batch": batch.get("recommended_batch"),
                "reorder_point_units": batch.get("reorder_point_units"),
                "projected_margin_pct": projected_margin,
                "score_breakdown": supplier.get("score_breakdown", {}),
            })
        return {
            "product_keyword": product_keyword,
            "monthly_demand": monthly_demand,
            "target_price": target_price,
            "source": "supplier_scoring_model",
            "scoring_model": {
                "delivery": 0.25,
                "quality": 0.30,
                "price": 0.25,
                "history": 0.12,
                "capacity": 0.05,
                "service": 0.03,
            },
            "quote_cache": {
                "cache_backend": quote_cache.get("cache_backend"),
                "cache_hit": quote_cache.get("cache_hit"),
                "supplier_count": (quote_cache.get("summary") or {}).get("supplier_count"),
            },
            "recommendations": recommendations,
            "top_supplier": recommendations[0] if recommendations else None,
            "recommendation_ready": bool(recommendations),
            "generated_at": self._now_iso(),
        }

    async def build_restock_plan(
        self,
        *,
        product_keyword: str,
        monthly_demand: int,
        current_inventory_units: int,
        target_price: float,
        max_suppliers: int = 10,
        preferred_supplier_code: str | None = None,
        oms_api_endpoint: str | None = None,
        oms_api_key: str | None = None,
        oms_inbound_path: str = "/orders",
        product_id: str | None = None,
    ) -> dict[str, Any]:
        quote_cache = await self.build_quote_cache(product_keyword=product_keyword, max_suppliers=max_suppliers)
        quotes = quote_cache.get("quotes") if isinstance(quote_cache.get("quotes"), list) else []
        if not quotes:
            raise ValueError("未获取到可用1688供应商报价")
        supplier = next((item for item in quotes if str(item.get("supplier_code")) == str(preferred_supplier_code)), None) if preferred_supplier_code else None
        if supplier is None:
            supplier = max(quotes, key=lambda item: (item.get("reliability_score", 0.0) - item.get("unit_price_usd", 0.0) * 0.01))

        orders: list[dict[str, Any]] = []
        if oms_api_endpoint:
            client = OMSClient(
                api_endpoint=oms_api_endpoint,
                api_key=oms_api_key,
                inbound_path=oms_inbound_path,
                outbound_path="/products/bulk-upsert",
                timeout_seconds=5,
            )
            orders = await client.fetch_orders()
        elasticity_snapshot = self._build_oms_price_elasticity_snapshot(orders, product_id=product_id, target_price=target_price)
        plan = self._build_restock_plan(
            product_keyword=product_keyword,
            supplier=supplier,
            monthly_demand=monthly_demand,
            current_inventory_units=current_inventory_units,
            target_price=target_price,
            elasticity_snapshot=elasticity_snapshot,
        )
        plan["quote_cache"] = {
            "cache_backend": quote_cache.get("cache_backend"),
            "cache_hit": quote_cache.get("cache_hit"),
            "cached_at": quote_cache.get("cached_at"),
            "expires_in_seconds": quote_cache.get("expires_in_seconds"),
        }
        plan["supplier_options"] = quotes[:5]
        return plan

    async def build_supplier_reliability(
        self,
        *,
        product_keyword: str,
        scm_api_endpoint: str,
        scm_api_key: str | None = None,
        scm_inbound_path: str = "/supplier-products",
        preferred_supplier_code: str | None = None,
    ) -> dict[str, Any]:
        client = SCMClient(
            api_endpoint=scm_api_endpoint,
            api_key=scm_api_key,
            inbound_path=scm_inbound_path,
            outbound_path="/purchase-suggestions",
            timeout_seconds=5,
        )
        supplier_items = await client.fetch_supplier_quotes()
        snapshot = self._extract_scm_supplier_reliability(
            supplier_items,
            supplier_code=preferred_supplier_code,
            product_keyword=product_keyword,
        )
        top_suppliers: list[dict[str, Any]] = []
        for item in supplier_items[:20]:
            if not isinstance(item, dict):
                continue
            extracted = self._extract_scm_supplier_reliability([item], product_keyword=product_keyword)
            if extracted.get("found"):
                top_suppliers.append(extracted)
        top_suppliers.sort(key=lambda item: item.get("reliability_score", 0.0), reverse=True)
        return {
            "product_keyword": product_keyword,
            "source": "scm_supplier_reliability",
            "supplier_count": len([item for item in supplier_items if isinstance(item, dict)]),
            "selected_supplier": snapshot,
            "top_suppliers": top_suppliers[:5],
        }

    async def build_fms_cost_snapshot(
        self,
        *,
        product_id: str | None,
        fms_api_endpoint: str,
        fms_api_key: str | None = None,
        fms_inbound_path: str = "/finance-metrics",
        ad_spending_path: str | None = None,
        currency: str = "USD",
        exchange_rate: float = 1.0,
    ) -> dict[str, Any]:
        client = FMSClient(
            api_endpoint=fms_api_endpoint,
            api_key=fms_api_key,
            inbound_path=fms_inbound_path,
            outbound_path="/profit-plans/bulk-upsert",
            timeout_seconds=5,
            ad_spending_path=ad_spending_path or "/ad-spending",
        )
        metrics = await client.fetch_finance_metrics()
        try:
            ad_spending_items = await client.fetch_ad_spending()
        except Exception:
            ad_spending_items = []
        snapshot = self._extract_fms_cost_snapshot(metrics, product_id=product_id, exchange_rate=exchange_rate)
        ad_summary = {
            "found": False,
            "ad_spending_total": 0.0,
            "ad_sales_total": 0.0,
            "acos": 0.0,
        }
        if ad_spending_items:
            filtered = [
                item for item in ad_spending_items
                if product_id is None or str(item.get("product_id") or item.get("external_product_id") or item.get("id")) == str(product_id)
            ]
            target_items = filtered or ad_spending_items
            ad_spending_total = sum(self._safe_float(item.get("ad_spending") or item.get("advertising_spend") or item.get("expense"), 0.0) for item in target_items)
            ad_sales_total = sum(self._safe_float(item.get("ad_sales") or item.get("advertising_sales") or item.get("sales"), 0.0) for item in target_items)
            acos = self._round(ad_spending_total / ad_sales_total) if ad_sales_total > 0 else 0.0
            ad_summary = {
                "found": True,
                "ad_spending_total": self._round(ad_spending_total),
                "ad_sales_total": self._round(ad_sales_total),
                "acos": acos,
            }
            if ad_spending_total > 0 and snapshot.get("marketing_cost_per_unit", 0.0) <= 0:
                snapshot["marketing_cost_per_unit"] = self._round(ad_spending_total)
        snapshot["currency"] = snapshot.get("currency") or currency
        snapshot["source"] = "fms_cost_snapshot"
        snapshot["record_count"] = len(metrics)
        snapshot["ad_spending_summary"] = ad_summary
        return snapshot

    async def build_oms_price_elasticity_snapshot(
        self,
        *,
        oms_api_endpoint: str,
        oms_api_key: str | None = None,
        oms_inbound_path: str = "/orders",
        product_id: str | None = None,
        target_price: float | None = None,
    ) -> dict[str, Any]:
        client = OMSClient(
            api_endpoint=oms_api_endpoint,
            api_key=oms_api_key,
            inbound_path=oms_inbound_path,
            outbound_path="/products/bulk-upsert",
            timeout_seconds=5,
        )
        orders = await client.fetch_orders()
        snapshot = self._build_oms_price_elasticity_snapshot(orders, product_id=product_id, target_price=target_price)
        snapshot["source"] = "oms_price_elasticity_snapshot"
        snapshot["product_id"] = product_id
        snapshot["record_count"] = len([item for item in orders if isinstance(item, dict)])
        return snapshot

    @staticmethod
    def _build_explicit_cost_inputs(*, unit_cost_1688: float, logistics_cost_per_unit: float, platform_fee_rate: float, marketing_cost_per_unit: float, target_price: float) -> dict[str, Any]:
        platform_fee_amount = target_price * platform_fee_rate
        total_explicit_cost = unit_cost_1688 + logistics_cost_per_unit + marketing_cost_per_unit + platform_fee_amount
        margin_pct = ((target_price - total_explicit_cost) / target_price * 100) if target_price > 0 else 0.0
        return {
            "procurement_cost_per_unit": ProfitOptimizationService._round(unit_cost_1688),
            "logistics_cost_per_unit": ProfitOptimizationService._round(logistics_cost_per_unit),
            "platform_fee_rate": ProfitOptimizationService._round(platform_fee_rate),
            "platform_fee_amount": ProfitOptimizationService._round(platform_fee_amount),
            "marketing_cost_per_unit": ProfitOptimizationService._round(marketing_cost_per_unit),
            "total_explicit_cost_per_unit": ProfitOptimizationService._round(total_explicit_cost),
            "explicit_margin_pct": ProfitOptimizationService._round(margin_pct),
        }

    async def _build_scenario_analysis(
        self,
        *,
        category: str,
        target_price: float,
        monthly_volume_est: int,
        base_total_cost_per_unit: float,
        competitor_prices: list[float],
        pricing_strategy: str,
        initial_investment: float,
    ) -> list[dict[str, Any]]:
        scenarios = [
            {"name": "conservative", "price_factor": 0.95, "volume_factor": 0.85, "cost_factor": 1.08},
            {"name": "base", "price_factor": 1.0, "volume_factor": 1.0, "cost_factor": 1.0},
            {"name": "aggressive", "price_factor": 1.05, "volume_factor": 1.15, "cost_factor": 0.95},
        ]
        outputs: list[dict[str, Any]] = []
        for scenario in scenarios:
            scenario_price = self._round(target_price * scenario["price_factor"])
            scenario_cost = self._round(base_total_cost_per_unit * scenario["cost_factor"])
            scenario_volume = max(1, int(monthly_volume_est * scenario["volume_factor"]))
            pricing = await self.agent._recommend_pricing(  # noqa: SLF001
                cost_per_unit=scenario_cost,
                competitor_prices=competitor_prices,
                target_margin=max(18.0, ((scenario_price - scenario_cost) / scenario_price * 100) if scenario_price else 18.0),
                pricing_strategy=pricing_strategy,
            )
            roi = await self.agent._predict_roi(  # noqa: SLF001
                initial_investment=initial_investment,
                monthly_revenue=scenario_price * scenario_volume,
                monthly_cost=scenario_cost * scenario_volume,
                gross_margin_pct=((scenario_price - scenario_cost) / scenario_price * 100) if scenario_price else 0.0,
            )
            outputs.append(
                {
                    "scenario": scenario["name"],
                    "assumptions": {
                        "price_factor": scenario["price_factor"],
                        "volume_factor": scenario["volume_factor"],
                        "cost_factor": scenario["cost_factor"],
                    },
                    "recommended_price": pricing.get("final_recommendation", {}).get("price", scenario_price),
                    "volume_estimate": scenario_volume,
                    "cost_per_unit": scenario_cost,
                    "roi_year1_percent": roi.get("key_metrics", {}).get("roi_year1_percent"),
                    "payback_period_months": roi.get("key_metrics", {}).get("payback_period_months"),
                    "verdict": roi.get("investment_verdict", {}).get("verdict"),
                }
            )
        return outputs

    async def optimize(
        self,
        *,
        category: str,
        target_price: float,
        monthly_volume_est: int,
        unit_cost_1688: float,
        competitor_prices: list[float],
        pricing_strategy: str = "competitive",
        initial_investment: float = 50000,
        logistics_cost_per_unit: float = 0.0,
        platform_fee_rate: float = 0.0,
        marketing_cost_per_unit: float = 0.0,
        product_id: str | None = None,
        fms_api_endpoint: str | None = None,
        fms_api_key: str | None = None,
        fms_inbound_path: str = "/finance-metrics",
        currency: str = "USD",
        exchange_rate: float = 1.0,
        tax_cost_per_unit: float = 0.0,
    ) -> dict[str, Any]:
        fms_cost_snapshot = {
            "found": False,
            "product_id": product_id,
            "exchange_rate": exchange_rate,
            "currency": currency,
            "procurement_cost_per_unit": 0.0,
            "logistics_cost_per_unit": 0.0,
            "marketing_cost_per_unit": 0.0,
            "tax_cost_per_unit": 0.0,
            "platform_fee_rate": 0.0,
            "platform_fee_amount": 0.0,
            "gross_profit": 0.0,
        }
        if fms_api_endpoint:
            client = FMSClient(
                api_endpoint=fms_api_endpoint,
                api_key=fms_api_key,
                inbound_path=fms_inbound_path,
                outbound_path="/profit-plans/bulk-upsert",
                timeout_seconds=5,
                ad_spending_path=fms_inbound_path,
            )
            metrics = await client.fetch_finance_metrics()
            ad_spending_items = await client.fetch_ad_spending()
            fms_cost_snapshot = self._extract_fms_cost_snapshot(metrics, product_id=product_id, exchange_rate=exchange_rate)
            if ad_spending_items:
                filtered = [
                    item for item in ad_spending_items
                    if product_id is None or str(item.get("product_id") or item.get("external_product_id") or item.get("id")) == str(product_id)
                ]
                target_items = filtered or ad_spending_items
                ad_spending_total = sum(self._safe_float(item.get("ad_spending") or item.get("advertising_spend") or item.get("expense"), 0.0) for item in target_items)
                ad_sales_total = sum(self._safe_float(item.get("ad_sales") or item.get("advertising_sales") or item.get("sales"), 0.0) for item in target_items)
                fms_cost_snapshot["ad_spending_summary"] = {
                    "found": True,
                    "ad_spending_total": self._round(ad_spending_total),
                    "ad_sales_total": self._round(ad_sales_total),
                    "acos": self._round(ad_spending_total / ad_sales_total) if ad_sales_total > 0 else 0.0,
                }
            if fms_cost_snapshot.get("found"):
                unit_cost_1688 = max(unit_cost_1688, self._safe_float(fms_cost_snapshot.get("procurement_cost_per_unit"), unit_cost_1688))
                logistics_cost_per_unit = max(logistics_cost_per_unit, self._safe_float(fms_cost_snapshot.get("logistics_cost_per_unit"), logistics_cost_per_unit))
                marketing_cost_per_unit = max(marketing_cost_per_unit, self._safe_float(fms_cost_snapshot.get("marketing_cost_per_unit"), marketing_cost_per_unit))
                tax_cost_per_unit = max(tax_cost_per_unit, self._safe_float(fms_cost_snapshot.get("tax_cost_per_unit"), tax_cost_per_unit))
                platform_fee_rate = max(platform_fee_rate, self._safe_float(fms_cost_snapshot.get("platform_fee_rate"), platform_fee_rate))

        cost_breakdown = await self.agent._calculate_detailed_costs(  # noqa: SLF001
            selling_price=target_price,
            unit_cost_1688=unit_cost_1688,
            category=category,
        )
        explicit_cost_inputs = self._build_explicit_cost_inputs(
            unit_cost_1688=unit_cost_1688,
            logistics_cost_per_unit=logistics_cost_per_unit,
            platform_fee_rate=platform_fee_rate,
            marketing_cost_per_unit=marketing_cost_per_unit,
            target_price=target_price,
        )
        explicit_cost_inputs["tax_cost_per_unit"] = self._round(tax_cost_per_unit)
        explicit_cost_inputs["currency"] = currency
        explicit_cost_inputs["exchange_rate"] = self._round(exchange_rate)
        explicit_cost_inputs["total_explicit_cost_per_unit"] = self._round(explicit_cost_inputs["total_explicit_cost_per_unit"] + tax_cost_per_unit)
        explicit_cost_inputs["explicit_margin_pct"] = self._round(((target_price - explicit_cost_inputs["total_explicit_cost_per_unit"]) / target_price * 100) if target_price > 0 else 0.0)
        base_total_cost_per_unit = max(
            cost_breakdown.get("total_cost_per_unit", unit_cost_1688),
            explicit_cost_inputs["total_explicit_cost_per_unit"],
        )
        pricing = await self.agent._recommend_pricing(  # noqa: SLF001
            cost_per_unit=base_total_cost_per_unit,
            competitor_prices=competitor_prices,
            target_margin=max(20.0, cost_breakdown.get("gross_margin_pct", explicit_cost_inputs["explicit_margin_pct"])),
            pricing_strategy=pricing_strategy,
        )
        roi = await self.agent._predict_roi(  # noqa: SLF001
            initial_investment=initial_investment,
            monthly_revenue=target_price * monthly_volume_est,
            monthly_cost=base_total_cost_per_unit * monthly_volume_est,
            gross_margin_pct=((target_price - base_total_cost_per_unit) / target_price * 100) if target_price else 0.0,
        )
        elasticity = await self.agent._price_elasticity_model(  # noqa: SLF001
            base_price=target_price,
            base_volume=monthly_volume_est,
            category=category,
        )
        scenario_analysis = await self._build_scenario_analysis(
            category=category,
            target_price=target_price,
            monthly_volume_est=monthly_volume_est,
            base_total_cost_per_unit=base_total_cost_per_unit,
            competitor_prices=competitor_prices,
            pricing_strategy=pricing_strategy,
            initial_investment=initial_investment,
        )

        quote_cache = await self.build_quote_cache(product_keyword=category, max_suppliers=10)
        quote_summary = quote_cache.get("summary", {}) if isinstance(quote_cache, dict) else {}
        supplier_quotes = quote_cache.get("quotes", []) if isinstance(quote_cache, dict) else []
        selected_supplier = supplier_quotes[0] if supplier_quotes else None
        elasticity_snapshot = self._build_oms_price_elasticity_snapshot([], product_id=product_id, target_price=target_price)
        restock_plan = self._build_restock_plan(
            product_keyword=category,
            supplier=selected_supplier or {
                "supplier_code": "supplier-unknown",
                "supplier_name": "supplier-unknown",
                "unit_price_usd": unit_cost_1688,
                "min_order_qty": 1,
                "lead_time_days": 7,
            },
            monthly_demand=monthly_volume_est,
            current_inventory_units=0,
            target_price=target_price,
            elasticity_snapshot=elasticity_snapshot,
        )

        final_price = pricing.get("final_recommendation", {}).get("price", target_price)
        final_recommendation = {
            "recommended_price": final_price,
            "pricing_strategy": pricing.get("strategy_selected", pricing_strategy),
            "expected_margin": pricing.get("final_recommendation", {}).get("expected_margin"),
            "roi_year1_percent": roi.get("key_metrics", {}).get("roi_year1_percent"),
            "payback_period_months": roi.get("key_metrics", {}).get("payback_period_months"),
            "verdict": roi.get("investment_verdict", {}).get("verdict"),
        }

        return {
            "category": category,
            "target_price": target_price,
            "monthly_volume_est": monthly_volume_est,
            "explicit_cost_inputs": explicit_cost_inputs,
            "fms_cost_snapshot": fms_cost_snapshot,
            "cost_trace": {
                "procurement_cost_per_unit": "fms" if fms_cost_snapshot.get("found") and fms_cost_snapshot.get("procurement_cost_per_unit") else "request",
                "logistics_cost_per_unit": "fms" if fms_cost_snapshot.get("found") and fms_cost_snapshot.get("logistics_cost_per_unit") else "request",
                "marketing_cost_per_unit": "fms" if fms_cost_snapshot.get("found") and fms_cost_snapshot.get("marketing_cost_per_unit") else "request",
                "tax_cost_per_unit": "fms" if fms_cost_snapshot.get("found") and fms_cost_snapshot.get("tax_cost_per_unit") else "request",
                "platform_fee_rate": "fms" if fms_cost_snapshot.get("found") and fms_cost_snapshot.get("platform_fee_rate") else "request",
                "exchange_rate": "fms" if fms_cost_snapshot.get("found") else "request",
            },
            "cost_breakdown": cost_breakdown,
            "supplier_quote_cache": quote_cache,
            "quote_summary": quote_summary,
            "selected_supplier": selected_supplier,
            "pricing_recommendation": pricing,
            "roi_projection": roi,
            "price_elasticity": elasticity,
            "oms_price_elasticity_snapshot": elasticity_snapshot,
            "restock_plan": restock_plan,
            "scenario_analysis": scenario_analysis,
            "decision_ready_summary": {
                "pricing": {
                    "recommended_price": final_recommendation["recommended_price"],
                    "pricing_strategy": final_recommendation["pricing_strategy"],
                },
                "profitability": {
                    "roi_year1_percent": final_recommendation["roi_year1_percent"],
                    "payback_period_months": final_recommendation["payback_period_months"],
                    "expected_margin": final_recommendation["expected_margin"],
                },
                "best_scenario": max(scenario_analysis, key=lambda item: item.get("roi_year1_percent") or float("-inf")),
            },
            "final_recommendation": final_recommendation,
        }
