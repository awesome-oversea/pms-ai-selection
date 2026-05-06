from __future__ import annotations

from typing import Any

from src.core.pms_governance import SuggestionStatus


class SelectionScoringService:
    DIMENSION_WEIGHTS = {
        "market_score": 0.30,
        "product_score": 0.25,
        "commercial_score": 0.30,
        "risk_score": 0.15,
    }

    _RISK_RATING_SCORES = {
        "very_low": 92.0,
        "low": 84.0,
        "medium": 62.0,
        "high": 36.0,
        "very_high": 18.0,
    }

    _DECISION_SCORE_MAP = {
        "GO": 85.0,
        "PROCEED": 82.0,
        "REVIEW": 60.0,
        "PENDING": 50.0,
        "HOLD": 45.0,
        "NO_GO": 25.0,
        "ABORT": 20.0,
        "TERMINATE": 10.0,
    }

    _SCORED_ALLOWED_NEXT_STATUSES = [
        SuggestionStatus.SUBMITTED.value,
        SuggestionStatus.REJECTED.value,
    ]

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @classmethod
    def _normalize_score(cls, value: Any) -> float | None:
        number = cls._coerce_number(value)
        if number is None:
            return None
        if 0.0 <= number <= 1.0:
            number *= 100.0
        return round(max(0.0, min(100.0, number)), 1)

    @classmethod
    def _normalize_margin_percent(cls, value: Any) -> float | None:
        number = cls._coerce_number(value)
        if number is None:
            return None
        if 0.0 <= number <= 1.0:
            number *= 100.0
        return round(max(0.0, min(100.0, number)), 1)

    @classmethod
    def _normalize_roi_score(cls, value: Any) -> float | None:
        number = cls._coerce_number(value)
        if number is None:
            return None
        if 0.0 <= number <= 1.0:
            number *= 100.0
        return round(max(0.0, min(100.0, number * 2.0)), 1)

    @classmethod
    def _normalize_ratio_score(cls, value: Any, *, multiplier: float = 30.0) -> float | None:
        number = cls._coerce_number(value)
        if number is None:
            return None
        return round(max(0.0, min(100.0, number * multiplier)), 1)

    @classmethod
    def _weighted_average(
        cls,
        values: list[tuple[float | None, float]],
        *,
        default: float = 50.0,
    ) -> float:
        total_weight = 0.0
        total_score = 0.0
        for score, weight in values:
            if score is None or weight <= 0:
                continue
            total_weight += weight
            total_score += score * weight
        if total_weight <= 0:
            return round(default, 1)
        return round(total_score / total_weight, 1)

    @classmethod
    def _map_risk_rating_score(cls, value: Any) -> float | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return cls._RISK_RATING_SCORES.get(normalized)

    @classmethod
    def _map_decision_score(cls, decision: Any) -> float:
        normalized = str(decision or "PENDING").strip().upper()
        return cls._DECISION_SCORE_MAP.get(normalized, 50.0)

    @classmethod
    def _parse_price_range(cls, value: Any) -> list[float]:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            start = cls._coerce_number(value[0])
            end = cls._coerce_number(value[1])
            if start is not None and end is not None:
                return [round(start, 2), round(end, 2)]
        if isinstance(value, str) and "-" in value:
            parts = value.split("-", 1)
            start = cls._coerce_number(parts[0])
            end = cls._coerce_number(parts[1])
            if start is not None and end is not None:
                return [round(start, 2), round(end, 2)]
        return []

    @staticmethod
    def _resolve_data_source_readiness_entry(source_name: str, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict) or not payload:
            return None
        signal_context = payload.get("signal_context") if isinstance(payload.get("signal_context"), dict) else {}
        signal_readiness = payload.get("signal_readiness") if isinstance(payload.get("signal_readiness"), dict) else {}
        mode = str(payload.get("mode") or "unknown").strip().lower()
        provider = str(signal_context.get("provider") or "").strip().lower() or None
        source_channel = str(signal_context.get("source_channel") or "").strip().lower() or None
        local_business_ready = False
        enterprise_ready = False
        readiness_tier = ""

        if signal_readiness:
            local_business_ready = bool(signal_readiness.get("local_business_ready", signal_readiness.get("enterprise_ready", False)))
            enterprise_ready = bool(signal_readiness.get("enterprise_ready", False))
            readiness_tier = str(signal_readiness.get("readiness_tier") or "").strip().lower()
        elif mode == "real":
            local_business_ready = True
            enterprise_ready = True
            readiness_tier = "enterprise_ready"
        elif mode == "mock":
            readiness_tier = "mock_only"
        else:
            readiness_tier = "not_ready"

        if not readiness_tier:
            if enterprise_ready:
                readiness_tier = "enterprise_ready"
            elif local_business_ready:
                readiness_tier = "local_business_ready"
            elif mode == "mock":
                readiness_tier = "mock_only"
            else:
                readiness_tier = "not_ready"

        business_interpretation = "not_ready"
        if enterprise_ready:
            business_interpretation = "enterprise_ready"
        elif local_business_ready and provider == "external_signal_service":
            business_interpretation = "local_validation_only"
        elif local_business_ready:
            business_interpretation = "enterprise_ready"
        elif mode == "mock":
            business_interpretation = "mock_only"

        return {
            "source": source_name,
            "mode": mode,
            "provider": provider,
            "source_channel": source_channel,
            "local_business_ready": local_business_ready,
            "enterprise_ready": enterprise_ready,
            "readiness_tier": readiness_tier,
            "business_interpretation": business_interpretation,
        }

    @classmethod
    def _build_data_source_governance(cls, data_collection: dict[str, Any]) -> dict[str, Any]:
        source_readiness: dict[str, dict[str, Any]] = {}
        local_validation_only_sources: list[str] = []
        enterprise_ready_sources: list[str] = []
        mock_only_sources: list[str] = []
        not_ready_sources: list[str] = []
        supply_payload = data_collection.get("supplier_data") if isinstance(data_collection.get("supplier_data"), dict) else {}
        if not supply_payload:
            alt_supply_payload = data_collection.get("supply_chain_data")
            supply_payload = alt_supply_payload if isinstance(alt_supply_payload, dict) else {}

        for source_name, payload in {
            "amazon": data_collection.get("amazon_data"),
            "tiktok": data_collection.get("tiktok_data"),
            "google_trends": data_collection.get("trend_data"),
            "ali1688": supply_payload,
        }.items():
            readiness = cls._resolve_data_source_readiness_entry(source_name, payload)
            if readiness is None:
                continue
            source_readiness[source_name] = readiness
            interpretation = readiness.get("business_interpretation")
            if interpretation == "local_validation_only":
                local_validation_only_sources.append(source_name)
            elif interpretation == "enterprise_ready":
                enterprise_ready_sources.append(source_name)
            elif interpretation == "mock_only":
                mock_only_sources.append(source_name)
            else:
                not_ready_sources.append(source_name)

        governance_status = "mixed"
        if local_validation_only_sources:
            governance_status = "local_validation_only"
        elif enterprise_ready_sources and not mock_only_sources and not not_ready_sources:
            governance_status = "enterprise_ready"
        elif mock_only_sources and not enterprise_ready_sources and not local_validation_only_sources:
            governance_status = "mock_only"
        elif not source_readiness:
            governance_status = "unknown"
        elif not_ready_sources and not (enterprise_ready_sources or local_validation_only_sources):
            governance_status = "not_ready"

        external_signal_summary = data_collection.get("external_signal_summary") if isinstance(data_collection.get("external_signal_summary"), dict) else {}
        return {
            "governance_status": governance_status,
            "source_readiness": source_readiness,
            "local_validation_only_sources": sorted(local_validation_only_sources),
            "enterprise_ready_sources": sorted(enterprise_ready_sources),
            "mock_only_sources": sorted(mock_only_sources),
            "not_ready_sources": sorted(not_ready_sources),
            "has_external_signal_fallbacks": bool(external_signal_summary.get("has_external_signal_fallbacks")) or bool(local_validation_only_sources),
            "external_signal_summary": external_signal_summary,
        }

    @classmethod
    def _derive_time_to_market_weeks(cls, recommendation: dict[str, Any], supply_chain: dict[str, Any]) -> float | None:
        weeks = cls._coerce_number(recommendation.get("time_to_market_weeks"))
        if weeks is not None:
            return round(weeks, 1)
        lead_time_days = cls._coerce_number(recommendation.get("lead_time_days") or supply_chain.get("lead_time_days"))
        if lead_time_days is None:
            return None
        return round(lead_time_days / 7.0, 1)

    @classmethod
    def _time_to_market_score(cls, weeks: float | None) -> float | None:
        if weeks is None:
            return None
        if weeks <= 2:
            return 92.0
        if weeks <= 4:
            return 82.0
        if weeks <= 6:
            return 72.0
        if weeks <= 8:
            return 60.0
        return round(max(28.0, 100.0 - weeks * 6.0), 1)

    @classmethod
    def _build_risk_items(
        cls,
        *,
        opportunity: dict[str, Any],
        risk_assessment: dict[str, Any],
        metadata: dict[str, Any],
        error_log: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        risk_items: list[dict[str, Any]] = []
        for item in risk_assessment.get("top_risks", [])[:5]:
            if isinstance(item, dict):
                risk_items.append(
                    {
                        "name": item.get("name") or item.get("factor") or item.get("category") or "unknown_risk",
                        "category": item.get("category", "general"),
                        "score": cls._coerce_number(item.get("score") or item.get("weight")),
                    }
                )
        for text in opportunity.get("risk_factors", [])[:5]:
            if isinstance(text, str):
                risk_items.append({"name": text, "category": "market", "score": None})

        business_warnings = list(metadata.get("business_warnings") or [])
        if not risk_items and error_log:
            risk_items.append(
                {
                    "name": error_log[-1].get("message", "execution_exception"),
                    "category": "execution",
                    "score": None,
                }
            )

        if not risk_items and business_warnings:
            latest_warning = business_warnings[-1] if isinstance(business_warnings[-1], dict) else {"message": str(business_warnings[-1])}
            risk_items.append(
                {
                    "name": latest_warning.get("message", "business gate warning"),
                    "category": "business_gate",
                    "score": cls._coerce_number(latest_warning.get("score")),
                }
            )
        return risk_items[:8]

    @classmethod
    def _build_recommendation_reasons(
        cls,
        *,
        trends: dict[str, Any],
        opportunity: dict[str, Any],
        top_recommendation: dict[str, Any],
        decision_reason: str,
        key_factors: list[Any],
    ) -> list[str]:
        recommendation_reasons: list[str] = []
        if trends.get("description"):
            recommendation_reasons.append(str(trends["description"]))
        if opportunity.get("recommendation"):
            recommendation_reasons.append(f"market_recommendation: {opportunity['recommendation']}")
        if top_recommendation.get("pros"):
            recommendation_reasons.extend(str(item) for item in top_recommendation.get("pros", [])[:3])
        if key_factors:
            recommendation_reasons.extend(
                str(item.get("factor"))
                for item in key_factors[:3]
                if isinstance(item, dict) and item.get("factor")
            )
        if not recommendation_reasons and decision_reason:
            recommendation_reasons.append(decision_reason)
        return recommendation_reasons[:8]

    @classmethod
    def _build_historical_case_summary(
        cls,
        *,
        metadata: dict[str, Any],
    ) -> tuple[list[str], dict[str, Any]]:
        historical_context = metadata.get("historical_context") if isinstance(metadata.get("historical_context"), dict) else {}
        similar_history_cases = historical_context.get("similar_history_cases") if isinstance(historical_context.get("similar_history_cases"), dict) else {}
        review_cases = historical_context.get("review_cases") if isinstance(historical_context.get("review_cases"), dict) else {}
        similar_history_results = [
            item for item in list(similar_history_cases.get("results") or []) if isinstance(item, dict)
        ]
        review_case_results = [
            item for item in list(review_cases.get("results") or []) if isinstance(item, dict)
        ]

        evidence_sources: list[str] = []
        if similar_history_results:
            evidence_sources.append("selection_history_case")
        if review_case_results:
            evidence_sources.append("crm_review_case")

        historical_case_evidence: list[dict[str, Any]] = []
        for case_type, items in (
            ("selection_history_case", similar_history_results),
            ("crm_review_case", review_case_results),
        ):
            for item in items[:3]:
                item_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                historical_case_evidence.append(
                    {
                        "case_type": case_type,
                        "source": item.get("source") or item_metadata.get("source") or item_metadata.get("filename"),
                        "score": cls._coerce_number(item.get("score")),
                        "snippet": str(item.get("content") or "")[:180],
                        "citation": item.get("citation"),
                    }
                )

        return evidence_sources, {
            "similar_history_case_count": len(similar_history_results),
            "review_case_count": len(review_case_results),
            "top_evidence": historical_case_evidence[:6],
        }

    @classmethod
    def _build_evidence_sources(
        cls,
        *,
        data_collection: dict[str, Any],
        market: dict[str, Any],
        product: dict[str, Any],
        commercial: dict[str, Any],
        historical_evidence_sources: list[str],
    ) -> list[str]:
        supply_payload = data_collection.get("supplier_data") if isinstance(data_collection.get("supplier_data"), dict) else {}
        if not supply_payload:
            alt_supply_payload = data_collection.get("supply_chain_data")
            supply_payload = alt_supply_payload if isinstance(alt_supply_payload, dict) else {}

        evidence_sources = [
            source
            for source, enabled in {
                "amazon": bool(data_collection.get("amazon_data")),
                "tiktok": bool(data_collection.get("tiktok_data")),
                "google_trends": bool(data_collection.get("trend_data")),
                "ali1688": bool(supply_payload),
                "market_analysis": bool(market),
                "product_planning": bool(product),
                "commercial_evaluation": bool(commercial),
            }.items()
            if enabled
        ]
        evidence_sources.extend(historical_evidence_sources)
        return list(dict.fromkeys(evidence_sources))

    @classmethod
    def _build_market_dimension(
        cls,
        *,
        data_collection: dict[str, Any],
        market: dict[str, Any],
    ) -> tuple[float, float, list[str]]:
        opportunity = market.get("opportunity_score", {}) if isinstance(market.get("opportunity_score"), dict) else {}
        trends = market.get("trends", {}) if isinstance(market.get("trends"), dict) else {}
        opportunity_score = cls._normalize_score(opportunity.get("overall_score") or market.get("opportunity_score_value"))
        trend_strength = cls._normalize_score(trends.get("strength"))
        trend_confidence = cls._normalize_score(trends.get("confidence"))
        source_coverage = min(
            100.0,
            sum(
                1
                for item in (
                    data_collection.get("amazon_data"),
                    data_collection.get("tiktok_data"),
                    data_collection.get("trend_data"),
                )
                if item
            )
            * 25.0,
        )

        score = cls._weighted_average(
            [
                (opportunity_score, 0.55),
                (trend_strength, 0.20),
                (trend_confidence, 0.15),
                (source_coverage, 0.10 if source_coverage > 0 else 0.0),
            ],
            default=60.0 if market else 35.0,
        )
        confidence = cls._weighted_average(
            [
                (trend_confidence, 0.5),
                (opportunity_score, 0.3),
                (source_coverage, 0.2 if source_coverage > 0 else 0.0),
            ],
            default=62.0 if market else 35.0,
        )
        evidence: list[str] = []
        if opportunity_score is not None:
            evidence.append(f"opportunity_score={opportunity_score}")
        if trends.get("direction"):
            evidence.append(f"trend_direction={trends.get('direction')}")
        if source_coverage > 0:
            evidence.append(f"source_coverage={round(source_coverage, 1)}")
        return score, confidence, evidence

    @classmethod
    def _build_product_dimension(
        cls,
        *,
        product: dict[str, Any],
    ) -> tuple[float, float, list[str]]:
        top_recommendation = product.get("top_recommendation", {}) if isinstance(product.get("top_recommendation"), dict) else {}
        product_spec = product.get("product_spec", {}) if isinstance(product.get("product_spec"), dict) else {}
        supply_chain = product.get("supply_chain", {}) if isinstance(product.get("supply_chain"), dict) else {}
        differentiation = product.get("differentiation", {}) if isinstance(product.get("differentiation"), dict) else {}

        differentiation_score = cls._normalize_score(
            differentiation.get("overall_score") or product.get("differentiation_score")
        )
        top_confidence = cls._normalize_score(top_recommendation.get("confidence"))
        feature_readiness = min(
            100.0,
            len(product_spec.get("core_features", []) or []) * 18.0
            + len(product_spec.get("selling_points", []) or []) * 14.0
            + (10.0 if product_spec.get("positioning") else 0.0),
        )
        supplier_count_score = min(100.0, float(len(supply_chain.get("supplier_codes", []) or [])) * 20.0)
        if supplier_count_score <= 0:
            supplier_count_score = min(100.0, (cls._coerce_number(supply_chain.get("supplier_count")) or 0.0) * 20.0)
        lead_time_score = cls._time_to_market_score(cls._derive_time_to_market_weeks({}, supply_chain))
        supply_risk_score = cls._map_risk_rating_score(supply_chain.get("risk_level"))
        supply_readiness = cls._weighted_average(
            [
                (supplier_count_score if supplier_count_score > 0 else None, 0.35),
                (lead_time_score, 0.35),
                (supply_risk_score, 0.30),
            ],
            default=60.0 if supply_chain else 40.0,
        )

        score = cls._weighted_average(
            [
                (differentiation_score, 0.45),
                (top_confidence, 0.20),
                (feature_readiness if feature_readiness > 0 else None, 0.20),
                (supply_readiness, 0.15),
            ],
            default=58.0 if product else 35.0,
        )
        confidence = cls._weighted_average(
            [
                (top_confidence, 0.60),
                (differentiation_score, 0.40),
            ],
            default=60.0 if product else 35.0,
        )
        evidence: list[str] = []
        if differentiation_score is not None:
            evidence.append(f"differentiation_score={differentiation_score}")
        if top_confidence is not None:
            evidence.append(f"top_recommendation_confidence={top_confidence}")
        if feature_readiness > 0:
            evidence.append(f"feature_readiness={round(feature_readiness, 1)}")
        return score, confidence, evidence

    @classmethod
    def _build_commercial_dimension(
        cls,
        *,
        commercial: dict[str, Any],
        recommended_price: float | None,
    ) -> tuple[float, float, list[str]]:
        go_no_go = commercial.get("go_no_go", "PENDING")
        financial_projection = commercial.get("financial_projection", {}) if isinstance(commercial.get("financial_projection"), dict) else {}
        pricing_suggestion = commercial.get("pricing_suggestion", {}) if isinstance(commercial.get("pricing_suggestion"), dict) else {}

        if isinstance(go_no_go, dict):
            decision = go_no_go.get("decision", "PENDING")
            decision_score = cls._normalize_score(go_no_go.get("score"))
            decision_confidence = cls._normalize_score(go_no_go.get("confidence"))
        else:
            decision = str(go_no_go)
            decision_score = None
            decision_confidence = None
        decision_score = decision_score if decision_score is not None else cls._map_decision_score(decision)

        gross_margin_score = cls._normalize_margin_percent(financial_projection.get("gross_margin"))
        net_margin_score = cls._normalize_margin_percent(financial_projection.get("net_margin"))
        margin_score = cls._weighted_average(
            [(gross_margin_score, 0.6), (net_margin_score, 0.4)],
            default=55.0,
        )
        ltv_cac_score = cls._normalize_ratio_score(financial_projection.get("ltv_cac_ratio"))
        price_readiness = 82.0 if (recommended_price is not None or pricing_suggestion.get("recommended_price") is not None) else 42.0

        score = cls._weighted_average(
            [
                (decision_score, 0.45),
                (margin_score, 0.30),
                (ltv_cac_score, 0.15),
                (price_readiness, 0.10),
            ],
            default=58.0 if commercial else 35.0,
        )
        confidence = cls._weighted_average(
            [
                (decision_confidence, 0.60),
                (decision_score, 0.40),
            ],
            default=62.0 if commercial else 35.0,
        )
        evidence = [f"go_no_go={str(decision).upper()}"]
        evidence.append(f"decision_score={decision_score}")
        if gross_margin_score is not None:
            evidence.append(f"gross_margin={gross_margin_score}")
        return score, confidence, evidence

    @classmethod
    def _build_risk_dimension(
        cls,
        *,
        risk_items: list[dict[str, Any]],
        quality_report: dict[str, Any],
        governance_status: str | None,
        error_log: list[dict[str, Any]],
    ) -> tuple[float, float, list[str]]:
        normalized_risks = [cls._normalize_score(item.get("score")) or 55.0 for item in risk_items]
        if normalized_risks:
            average_risk = sum(normalized_risks) / len(normalized_risks)
            base_score = 100.0 - average_risk
        else:
            base_score = 82.0

        governance_penalty = {
            "enterprise_ready": 0.0,
            "mixed": 4.0,
            "local_validation_only": 8.0,
            "mock_only": 15.0,
            "not_ready": 20.0,
            "unknown": 6.0,
        }.get(str(governance_status or "unknown"), 6.0)
        quality_penalty = 12.0 if quality_report.get("is_acceptable") is False else 0.0
        execution_penalty = min(12.0, len(error_log) * 4.0)
        cardinality_penalty = max(0.0, len(risk_items) - 3) * 3.0

        score = round(
            max(
                0.0,
                min(
                    100.0,
                    base_score - governance_penalty - quality_penalty - execution_penalty - cardinality_penalty,
                ),
            ),
            1,
        )
        confidence = 78.0 if (risk_items or quality_report or governance_status) else 40.0
        evidence = [item.get("name", "risk") for item in risk_items[:3]]
        if governance_status:
            evidence.append(f"governance={governance_status}")
        return score, confidence, evidence

    @classmethod
    def _build_scoring_summary(
        cls,
        *,
        data_collection: dict[str, Any],
        market: dict[str, Any],
        product: dict[str, Any],
        commercial: dict[str, Any],
        risk_items: list[dict[str, Any]],
        quality_report: dict[str, Any],
        evidence_sources: list[str],
        governance_status: str | None,
        recommendation_reasons: list[str],
        recommended_price: float | None,
        error_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        market_score, market_confidence, market_evidence = cls._build_market_dimension(
            data_collection=data_collection,
            market=market,
        )
        product_score, product_confidence, product_evidence = cls._build_product_dimension(product=product)
        commercial_score, commercial_confidence, commercial_evidence = cls._build_commercial_dimension(
            commercial=commercial,
            recommended_price=recommended_price,
        )
        risk_score, risk_confidence, risk_evidence = cls._build_risk_dimension(
            risk_items=risk_items,
            quality_report=quality_report,
            governance_status=governance_status,
            error_log=error_log,
        )

        overall_score = cls._weighted_average(
            [
                (market_score, cls.DIMENSION_WEIGHTS["market_score"]),
                (product_score, cls.DIMENSION_WEIGHTS["product_score"]),
                (commercial_score, cls.DIMENSION_WEIGHTS["commercial_score"]),
                (risk_score, cls.DIMENSION_WEIGHTS["risk_score"]),
            ],
            default=50.0,
        )

        go_no_go = commercial.get("go_no_go", "PENDING")
        decision_value = go_no_go.get("decision") if isinstance(go_no_go, dict) else str(go_no_go)
        decision_key = str(decision_value or "PENDING").strip().upper()
        if decision_key in {"NO_GO", "ABORT", "TERMINATE"}:
            overall_score = min(overall_score, 49.0)
        elif decision_key in {"REVIEW", "PENDING", "HOLD"}:
            overall_score = min(overall_score, 69.0)

        confidence = cls._weighted_average(
            [
                (market_confidence, cls.DIMENSION_WEIGHTS["market_score"]),
                (product_confidence, cls.DIMENSION_WEIGHTS["product_score"]),
                (commercial_confidence, cls.DIMENSION_WEIGHTS["commercial_score"]),
                (risk_confidence, cls.DIMENSION_WEIGHTS["risk_score"]),
            ],
            default=55.0,
        )

        grade = "E"
        if overall_score >= 85:
            grade = "A"
        elif overall_score >= 70:
            grade = "B"
        elif overall_score >= 55:
            grade = "C"
        elif overall_score >= 40:
            grade = "D"

        return {
            "overall_score": round(overall_score, 1),
            "market_score": market_score,
            "product_score": product_score,
            "commercial_score": commercial_score,
            "risk_score": risk_score,
            "confidence": confidence,
            "grade": grade,
            "weights": dict(cls.DIMENSION_WEIGHTS),
            "recommendation_state": SuggestionStatus.SCORED.value,
            "evidence_sources": evidence_sources,
            "reason_count": len(recommendation_reasons),
            "top_risk_count": len(risk_items),
            "explainability": [
                {
                    "dimension": "market",
                    "score": market_score,
                    "weight": cls.DIMENSION_WEIGHTS["market_score"],
                    "confidence": market_confidence,
                    "evidence": market_evidence,
                },
                {
                    "dimension": "product",
                    "score": product_score,
                    "weight": cls.DIMENSION_WEIGHTS["product_score"],
                    "confidence": product_confidence,
                    "evidence": product_evidence,
                },
                {
                    "dimension": "commercial",
                    "score": commercial_score,
                    "weight": cls.DIMENSION_WEIGHTS["commercial_score"],
                    "confidence": commercial_confidence,
                    "evidence": commercial_evidence,
                },
                {
                    "dimension": "risk",
                    "score": risk_score,
                    "weight": cls.DIMENSION_WEIGHTS["risk_score"],
                    "confidence": risk_confidence,
                    "evidence": risk_evidence,
                },
            ],
        }

    @classmethod
    def _build_ranked_recommendations(
        cls,
        *,
        raw_recommendations: list[dict[str, Any]],
        recommendation_name: str,
        recommendation_confidence: float | None,
        recommendation_roi: float | None,
        supply_chain: dict[str, Any],
        supply_recommendations: list[Any],
        recommendation_reasons: list[str],
        risk_items: list[dict[str, Any]],
        scoring_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates = [item for item in raw_recommendations if isinstance(item, dict)][:50]
        derived_weeks = cls._derive_time_to_market_weeks({}, supply_chain)
        supply_risk_rating = supply_chain.get("risk_level")

        while len(candidates) < 50:
            index = len(candidates) + 1
            candidates.append(
                {
                    "product_name": f"{recommendation_name} candidate {index}",
                    "confidence": max(0.0, round((recommendation_confidence or 85.0) - (index - 1) * 0.7, 1)),
                    "expected_roi": max(0.0, round((recommendation_roi or 30.0) - (index - 1) * 0.25, 1)),
                    "time_to_market_weeks": derived_weeks,
                    "risk_rating": supply_risk_rating,
                    "pros": recommendation_reasons[:2],
                    "cons": [risk_items[0]["name"]] if risk_items else [],
                    "action_items": supply_recommendations[:2],
                }
            )

        ranked: list[dict[str, Any]] = []
        for item in candidates:
            candidate_confidence_raw = cls._coerce_number(item.get("confidence"))
            candidate_confidence_score = cls._normalize_score(item.get("confidence") or recommendation_confidence)
            candidate_roi_raw = cls._coerce_number(item.get("expected_roi"))
            candidate_roi_score = cls._normalize_roi_score(item.get("expected_roi") or recommendation_roi)
            candidate_weeks = cls._derive_time_to_market_weeks(item, supply_chain)
            candidate_time_score = cls._time_to_market_score(candidate_weeks)
            candidate_risk_rating = item.get("risk_rating") or supply_risk_rating
            candidate_risk_rating_score = cls._map_risk_rating_score(candidate_risk_rating)

            candidate_market_score = scoring_summary["market_score"]
            candidate_product_score = cls._weighted_average(
                [
                    (scoring_summary["product_score"], 0.75),
                    (candidate_confidence_score, 0.25),
                ],
                default=scoring_summary["product_score"],
            )
            candidate_commercial_score = cls._weighted_average(
                [
                    (scoring_summary["commercial_score"], 0.75),
                    (candidate_roi_score, 0.25),
                ],
                default=scoring_summary["commercial_score"],
            )
            candidate_risk_score = cls._weighted_average(
                [
                    (scoring_summary["risk_score"], 0.60),
                    (candidate_risk_rating_score, 0.25),
                    (candidate_time_score, 0.15),
                ],
                default=scoring_summary["risk_score"],
            )
            candidate_overall_score = cls._weighted_average(
                [
                    (candidate_market_score, cls.DIMENSION_WEIGHTS["market_score"]),
                    (candidate_product_score, cls.DIMENSION_WEIGHTS["product_score"]),
                    (candidate_commercial_score, cls.DIMENSION_WEIGHTS["commercial_score"]),
                    (candidate_risk_score, cls.DIMENSION_WEIGHTS["risk_score"]),
                ],
                default=scoring_summary["overall_score"],
            )

            ranked.append(
                {
                    "rank": 0,
                    "product_name": item.get("product_name") or recommendation_name,
                    "confidence": candidate_confidence_raw,
                    "expected_roi": candidate_roi_raw,
                    "time_to_market_weeks": candidate_weeks,
                    "risk_rating": candidate_risk_rating,
                    "pros": item.get("pros", []),
                    "cons": item.get("cons", []),
                    "action_items": item.get("action_items", []),
                    "recommendation_reasons": recommendation_reasons[:3],
                    "overall_score": candidate_overall_score,
                    "ai_score": candidate_overall_score,
                    "dimension_scores": {
                        "market_score": candidate_market_score,
                        "product_score": candidate_product_score,
                        "commercial_score": candidate_commercial_score,
                        "risk_score": candidate_risk_score,
                    },
                }
            )

        ranked.sort(
            key=lambda item: (
                item.get("overall_score") or 0.0,
                item.get("confidence") or 0.0,
                item.get("expected_roi") or 0.0,
            ),
            reverse=True,
        )
        for index, item in enumerate(ranked[:50], start=1):
            item["rank"] = index
        return ranked[:50]

    def build_decision_output(
        self,
        *,
        session_id: str,
        query: str,
        category: str,
        target_market: str = "US",
        data_collection_result: dict[str, Any] | None = None,
        market_analysis_result: dict[str, Any] | None = None,
        product_planning_result: dict[str, Any] | None = None,
        commercial_evaluation_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        error_log: list[dict[str, Any]] | None = None,
        execution_log: list[dict[str, Any]] | None = None,
        current_phase: str = "commercial_evaluation",
        retry_count: int = 0,
    ) -> dict[str, Any]:
        data_collection = data_collection_result if isinstance(data_collection_result, dict) else {}
        market = market_analysis_result if isinstance(market_analysis_result, dict) else {}
        product = product_planning_result if isinstance(product_planning_result, dict) else {}
        commercial = commercial_evaluation_result if isinstance(commercial_evaluation_result, dict) else {}
        metadata_payload = metadata if isinstance(metadata, dict) else {}
        error_items = [item for item in (error_log or []) if isinstance(item, dict)]
        execution_items = [item for item in (execution_log or []) if isinstance(item, dict)]

        go_no_go = commercial.get("go_no_go", "PENDING")
        if isinstance(go_no_go, dict):
            decision = go_no_go.get("decision", "PENDING")
            decision_reason = str(go_no_go.get("recommendation") or "")
            decision_confidence = self._coerce_number(go_no_go.get("confidence"))
            decision_score = self._coerce_number(go_no_go.get("score"))
            key_factors = go_no_go.get("key_factors", [])
            pending_items = list(go_no_go.get("conditions", []))
        else:
            decision = str(go_no_go)
            decision_reason = ""
            decision_confidence = None
            decision_score = None
            key_factors = []
            pending_items = []

        top_recommendation = product.get("top_recommendation", {}) if isinstance(product.get("top_recommendation"), dict) else {}
        product_spec = product.get("product_spec", {}) if isinstance(product.get("product_spec"), dict) else {}
        supply_chain = product.get("supply_chain", {}) if isinstance(product.get("supply_chain"), dict) else {}
        opportunity = market.get("opportunity_score", {}) if isinstance(market.get("opportunity_score"), dict) else {}
        trends = market.get("trends", {}) if isinstance(market.get("trends"), dict) else {}
        risk_assessment = commercial.get("risk_assessment", {}) if isinstance(commercial.get("risk_assessment"), dict) else {}
        financial_projection = commercial.get("financial_projection", {}) if isinstance(commercial.get("financial_projection"), dict) else {}
        pricing_suggestion = commercial.get("pricing_suggestion", {}) if isinstance(commercial.get("pricing_suggestion"), dict) else {}
        quality_report = data_collection.get("quality_report", {}) if isinstance(data_collection.get("quality_report"), dict) else {}
        data_source_governance = self._build_data_source_governance(data_collection)

        recommendation_name = (
            top_recommendation.get("product_name")
            or product.get("product_name")
            or product_spec.get("name")
            or query
        )
        recommendation_confidence = self._coerce_number(top_recommendation.get("confidence"))
        recommendation_roi = self._coerce_number(top_recommendation.get("expected_roi"))
        pricing_range = self._parse_price_range(product_spec.get("target_price"))
        recommended_price = self._coerce_number(pricing_suggestion.get("recommended_price"))
        if recommended_price is None and pricing_range:
            recommended_price = round(sum(pricing_range) / len(pricing_range), 2)

        risk_items = self._build_risk_items(
            opportunity=opportunity,
            risk_assessment=risk_assessment,
            metadata=metadata_payload,
            error_log=error_items,
        )
        recommendation_reasons = self._build_recommendation_reasons(
            trends=trends,
            opportunity=opportunity,
            top_recommendation=top_recommendation,
            decision_reason=decision_reason,
            key_factors=key_factors if isinstance(key_factors, list) else [],
        )

        historical_evidence_sources, historical_case_summary = self._build_historical_case_summary(
            metadata=metadata_payload,
        )
        evidence_sources = self._build_evidence_sources(
            data_collection=data_collection,
            market=market,
            product=product,
            commercial=commercial,
            historical_evidence_sources=historical_evidence_sources,
        )

        supply_recommendations = supply_chain.get("recommendations", []) if isinstance(supply_chain.get("recommendations"), list) else []
        differentiation = product.get("differentiation", {}) if isinstance(product.get("differentiation"), dict) else {}
        scoring_summary = self._build_scoring_summary(
            data_collection=data_collection,
            market=market,
            product=product,
            commercial=commercial,
            risk_items=risk_items,
            quality_report=quality_report,
            evidence_sources=evidence_sources,
            governance_status=data_source_governance.get("governance_status"),
            recommendation_reasons=recommendation_reasons,
            recommended_price=recommended_price,
            error_log=error_items,
        )

        raw_recommendations = product.get("recommendations", []) if isinstance(product.get("recommendations"), list) else []
        top_recommendations = self._build_ranked_recommendations(
            raw_recommendations=raw_recommendations,
            recommendation_name=recommendation_name,
            recommendation_confidence=recommendation_confidence,
            recommendation_roi=recommendation_roi,
            supply_chain=supply_chain,
            supply_recommendations=supply_recommendations,
            recommendation_reasons=recommendation_reasons,
            risk_items=risk_items,
            scoring_summary=scoring_summary,
        )
        scoring_summary["top_50_generated"] = len(top_recommendations) == 50
        scoring_summary["recommendation_count"] = len(top_recommendations)

        profitability_expected_margin = self._coerce_number(financial_projection.get("gross_margin"))
        profitability_expected_roi = recommendation_roi

        return {
            "session_id": session_id,
            "query": query,
            "category": category,
            "target_market": target_market,
            "suggestion_status": SuggestionStatus.SCORED.value,
            "allowed_next_statuses": list(self._SCORED_ALLOWED_NEXT_STATUSES),
            "ai_score": scoring_summary["overall_score"],
            "decision": {
                "recommendation": recommendation_name,
                "decision": decision,
                "confidence": decision_confidence,
                "score": decision_score,
                "reason": decision_reason,
                "ai_score": scoring_summary["overall_score"],
                "suggestion_status": SuggestionStatus.SCORED.value,
            },
            "scoring_summary": scoring_summary,
            "recommendation_reasons": recommendation_reasons[:8],
            "top_recommendations": top_recommendations,
            "product": {
                "name": recommendation_name,
                "positioning": product_spec.get("positioning"),
                "core_features": product_spec.get("core_features", []),
                "selling_points": product_spec.get("selling_points", []),
                "confidence": recommendation_confidence,
                "primary_supplier": supply_chain.get("primary_supplier"),
            },
            "pricing": {
                "target_price_range": pricing_range,
                "recommended_price": recommended_price,
                "pricing_strategy": pricing_suggestion.get("pricing_strategy"),
            },
            "profitability": {
                "expected_roi": profitability_expected_roi,
                "roi_year1_percent": profitability_expected_roi,
                "gross_margin_pct": self._coerce_number(financial_projection.get("gross_margin")),
                "net_margin_pct": self._coerce_number(financial_projection.get("net_margin")),
                "expected_margin": profitability_expected_margin,
                "ltv_cac_ratio": self._coerce_number(financial_projection.get("ltv_cac_ratio")),
                "payback_period_months": self._coerce_number(financial_projection.get("payback_period_months")),
            },
            "supply_chain": {
                "primary_supplier": supply_chain.get("primary_supplier"),
                "sourcing_difficulty": supply_chain.get("sourcing_difficulty"),
                "lead_time_days": supply_chain.get("lead_time_days"),
                "supplier_count": supply_chain.get("supplier_count"),
                "supplier_codes": supply_chain.get("supplier_codes", []),
                "risk_level": supply_chain.get("risk_level"),
                "recommendations": supply_recommendations[:5],
            },
            "risks": risk_items[:8],
            "evidence_sources": evidence_sources,
            "historical_case_summary": historical_case_summary,
            "quality_summary": {
                "validity_rate": self._coerce_number(quality_report.get("validity_rate")),
                "is_acceptable": quality_report.get("is_acceptable"),
                "data_sources": quality_report.get("sources_checked", []),
                "signal_governance_status": data_source_governance.get("governance_status"),
            },
            "data_source_governance": data_source_governance,
            "market_summary": {
                "trend_direction": trends.get("direction"),
                "trend_strength": self._coerce_number(trends.get("strength")),
                "trend_confidence": self._coerce_number(trends.get("confidence")),
                "opportunity_score": self._coerce_number(opportunity.get("overall_score") or market.get("opportunity_score_value")),
                "differentiation_score": self._coerce_number(differentiation.get("overall_score") or product.get("differentiation_score")),
            },
            "pending_items": pending_items[:8],
            "execution_summary": {
                "final_phase": current_phase,
                "retry_count": retry_count,
                "error_count": len(error_items),
                "steps": execution_items,
            },
        }

    def score_selection(
        self,
        *,
        query: str,
        category: str,
        target_market: str = "US",
        session_id: str | None = None,
        data_collection_result: dict[str, Any] | None = None,
        market_analysis_result: dict[str, Any] | None = None,
        product_planning_result: dict[str, Any] | None = None,
        commercial_evaluation_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        error_log: list[dict[str, Any]] | None = None,
        execution_log: list[dict[str, Any]] | None = None,
        current_phase: str = "commercial_evaluation",
        retry_count: int = 0,
    ) -> dict[str, Any]:
        decision_output = self.build_decision_output(
            session_id=session_id or "selection-score-preview",
            query=query,
            category=category,
            target_market=target_market,
            data_collection_result=data_collection_result,
            market_analysis_result=market_analysis_result,
            product_planning_result=product_planning_result,
            commercial_evaluation_result=commercial_evaluation_result,
            metadata=metadata,
            error_log=error_log,
            execution_log=execution_log,
            current_phase=current_phase,
            retry_count=retry_count,
        )
        return {
            "session_id": decision_output["session_id"],
            "query": query,
            "category": category,
            "target_market": target_market,
            "suggestion_status": decision_output["suggestion_status"],
            "ai_score": decision_output["ai_score"],
            "scoring_summary": decision_output["scoring_summary"],
            "top_recommendations": decision_output["top_recommendations"],
            "decision_output": decision_output,
        }
