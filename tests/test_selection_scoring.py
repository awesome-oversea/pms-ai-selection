from __future__ import annotations

from src.agents.selection_master import SelectionMaster, SelectionState
from src.services.selection_scoring_service import SelectionScoringService


def _build_scoring_payload() -> dict:
    return {
        "query": "bluetooth headset",
        "category": "electronics",
        "target_market": "US",
        "data_collection_result": {
            "amazon_data": {
                "mode": "real",
                "signal_context": {"provider": "amazon"},
            },
            "tiktok_data": {
                "mode": "real",
                "signal_context": {"provider": "tiktok"},
            },
            "trend_data": {
                "mode": "real",
                "signal_context": {"provider": "google_trends"},
            },
            "supplier_data": {
                "mode": "real",
                "signal_context": {"provider": "ali1688"},
            },
            "quality_report": {
                "validity_rate": 0.86,
                "is_acceptable": True,
                "sources_checked": ["amazon", "tiktok", "google_trends", "ali1688"],
            },
        },
        "market_analysis_result": {
            "opportunity_score": {
                "overall_score": 78.0,
                "recommendation": "enter selected niche",
                "risk_factors": ["price competition"],
            },
            "trends": {
                "direction": "up",
                "strength": 0.82,
                "confidence": 0.91,
                "description": "search trend is rising",
            },
        },
        "product_planning_result": {
            "differentiation_score": 74.0,
            "product_spec": {
                "name": "bluetooth headset pro",
                "target_price": "$29.99 - $39.99",
                "positioning": "mid-range",
                "core_features": ["anc", "long_battery"],
                "selling_points": ["portable", "comfortable"],
            },
            "top_recommendation": {
                "product_name": "bluetooth headset pro",
                "confidence": 91.0,
                "expected_roi": "43%",
                "pros": ["clear value proposition", "healthy margin"],
            },
            "supply_chain": {
                "primary_supplier": "SUP-001",
                "supplier_count": 4,
                "lead_time_days": 21,
                "risk_level": "low",
                "recommendations": ["validate sample", "lock initial supplier"],
            },
            "recommendations": [
                {
                    "product_name": "bluetooth headset lite",
                    "confidence": 72.0,
                    "expected_roi": 26.0,
                    "time_to_market_weeks": 6,
                    "risk_rating": "high",
                    "pros": ["low entry cost"],
                    "cons": ["weak moat"],
                    "action_items": ["re-check differentiation"],
                },
                {
                    "product_name": "bluetooth headset pro",
                    "confidence": 94.0,
                    "expected_roi": 44.0,
                    "time_to_market_weeks": 4,
                    "risk_rating": "low",
                    "pros": ["best feature balance"],
                    "cons": [],
                    "action_items": ["start supplier validation"],
                },
                {
                    "product_name": "bluetooth headset max",
                    "confidence": 88.0,
                    "expected_roi": 35.0,
                    "time_to_market_weeks": 5,
                    "risk_rating": "medium",
                    "pros": ["good positioning"],
                    "cons": ["slightly higher cost"],
                    "action_items": ["review pricing"],
                },
            ],
        },
        "commercial_evaluation_result": {
            "go_no_go": {
                "decision": "GO",
                "confidence": 88.0,
                "score": 81.0,
                "recommendation": "launch pilot",
            },
            "financial_projection": {
                "gross_margin": "35%",
                "net_margin": "18%",
                "ltv_cac_ratio": 2.4,
                "payback_period_months": 9.5,
            },
            "risk_assessment": {
                "top_risks": [
                    {"name": "price competition", "category": "market", "score": 42},
                ]
            },
            "pricing_suggestion": {
                "recommended_price": 34.99,
                "pricing_strategy": "competitive",
            },
        },
        "metadata": {
            "historical_context": {
                "similar_history_cases": {
                    "results": [
                        {"source": "history-001", "score": 0.82, "content": "historical similar product"}
                    ]
                }
            }
        },
        "error_log": [],
        "execution_log": [{"phase": "commercial_evaluation", "status": "completed"}],
        "current_phase": "commercial_evaluation",
        "retry_count": 0,
    }


def test_selection_scoring_service_outputs_scored_state_and_sorted_top50() -> None:
    payload = _build_scoring_payload()

    result = SelectionScoringService().score_selection(**payload)

    assert result["suggestion_status"] == "scored"
    assert result["scoring_summary"]["overall_score"] >= 70
    assert result["scoring_summary"]["market_score"] > 0
    assert result["scoring_summary"]["product_score"] > 0
    assert result["scoring_summary"]["commercial_score"] > 0
    assert result["scoring_summary"]["risk_score"] > 0
    assert len(result["scoring_summary"]["explainability"]) == 4
    assert len(result["top_recommendations"]) == 50
    assert result["top_recommendations"][0]["product_name"] == "bluetooth headset pro"
    assert result["top_recommendations"][0]["rank"] == 1
    assert result["top_recommendations"][0]["overall_score"] >= result["top_recommendations"][1]["overall_score"]
    assert result["decision_output"]["allowed_next_statuses"] == ["submitted", "rejected"]
    assert result["decision_output"]["decision"]["ai_score"] == result["scoring_summary"]["overall_score"]


def test_selection_scoring_service_keeps_no_go_result_below_pass_threshold() -> None:
    payload = _build_scoring_payload()
    payload["commercial_evaluation_result"] = {
        "go_no_go": {
            "decision": "NO_GO",
            "confidence": 64.0,
            "score": 28.0,
            "recommendation": "do not proceed",
        },
        "financial_projection": {
            "gross_margin": "12%",
            "net_margin": "4%",
            "ltv_cac_ratio": 1.1,
        },
        "risk_assessment": {
            "top_risks": [
                {"name": "thin margin", "category": "commercial", "score": 82},
                {"name": "weak reviews", "category": "quality", "score": 76},
            ]
        },
        "pricing_suggestion": {"recommended_price": 19.99, "pricing_strategy": "discount"},
    }

    result = SelectionScoringService().score_selection(**payload)

    assert result["decision_output"]["decision"]["decision"] == "NO_GO"
    assert result["scoring_summary"]["overall_score"] < 50
    assert result["suggestion_status"] == "scored"


def test_selection_master_decision_output_includes_scoring_summary_and_scored_state() -> None:
    payload = _build_scoring_payload()
    state = SelectionState(
        session_id="sess-score-001",
        query=payload["query"],
        category=payload["category"],
        target_market=payload["target_market"],
    )
    state.data_collection_result = payload["data_collection_result"]
    state.market_analysis_result = payload["market_analysis_result"]
    state.product_planning_result = payload["product_planning_result"]
    state.commercial_evaluation_result = payload["commercial_evaluation_result"]
    state.metadata = payload["metadata"]

    output = SelectionMaster._build_decision_output(state, execution_log=payload["execution_log"])

    assert output["suggestion_status"] == "scored"
    assert output["ai_score"] == output["scoring_summary"]["overall_score"]
    assert output["top_recommendations"][0]["rank"] == 1
    assert len(output["top_recommendations"]) == 50
