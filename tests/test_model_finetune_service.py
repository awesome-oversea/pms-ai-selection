from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

from src.services.model_finetune_service import ModelFinetuneService
from src.workers.model_finetune_worker import WeeklyModelFinetuneWorker


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_feedback_root(tmp_path: Path) -> Path:
    feedback_root = tmp_path / "erp_local"
    _write_json(
        feedback_root / "crm" / "feedback.json",
        {
            "items": [
                {
                    "id": "crm-positive",
                    "product_id": "sku-positive",
                    "product_name": "蓝牙耳机高分样本",
                    "feedback": "客户好评明显增加，复购稳定，包装满意。",
                    "customer_score": 4.9,
                    "review_count": 32,
                },
                {
                    "id": "crm-negative",
                    "product_id": "sku-negative",
                    "product_name": "家居收纳盒风险样本",
                    "feedback": "差评增多，出现退货投诉和破损反馈。",
                    "customer_score": 3.2,
                    "review_count": 18,
                },
            ]
        },
    )
    _write_json(
        feedback_root / "oms" / "orders.json",
        {
            "items": [
                {
                    "order_id": "ord-positive-1",
                    "product_id": "sku-positive",
                    "quantity": 9,
                    "revenue": 899.1,
                },
                {
                    "order_id": "ord-positive-2",
                    "product_id": "sku-positive",
                    "quantity": 6,
                    "sales_7d": 599.4,
                },
                {
                    "order_id": "ord-negative-1",
                    "product_id": "sku-negative",
                    "quantity": 2,
                    "revenue": 79.8,
                },
            ]
        },
    )
    return feedback_root


def _build_single_class_feedback_root(tmp_path: Path) -> Path:
    feedback_root = tmp_path / "erp_local_single_class"
    _write_json(
        feedback_root / "crm" / "feedback.json",
        {
            "items": [
                {
                    "id": "crm-only-negative",
                    "product_id": "sku-only-negative",
                    "product_name": "家居收纳盒风险样本",
                    "feedback": "差评增多，出现退货投诉和破损反馈。",
                    "customer_score": 3.1,
                    "review_count": 11,
                }
            ]
        },
    )
    _write_json(
        feedback_root / "oms" / "orders.json",
        {
            "items": [
                {
                    "order_id": "ord-only-negative",
                    "product_id": "sku-only-negative",
                    "quantity": 1,
                    "revenue": 39.9,
                }
            ]
        },
    )
    return feedback_root


def _build_scenario_root(tmp_path: Path) -> Path:
    scenario_root = tmp_path / "mock_scenarios"
    _write_json(
        scenario_root / "external_api" / "amazon_hot_selling.json",
        {"response": {"products": [{"title": "耳机", "sales_growth": 0.34, "refund_rate": 0.02, "risk_flag": "growth"}]}},
    )
    _write_json(
        scenario_root / "external_api" / "amazon_high_refund.json",
        {"response": {"products": [{"title": "收纳盒", "sales_growth": 0.06, "refund_rate": 0.18, "risk_flag": "high_refund"}]}},
    )
    _write_json(
        scenario_root / "external_api" / "google_trends_growth.json",
        {"response": {"keyword": "wireless earbuds", "trend": "up", "risk_flag": "growth"}},
    )
    _write_json(
        scenario_root / "external_api" / "google_trends_spike_then_drop.json",
        {"response": {"keyword": "storage box", "trend": "drop", "risk_flag": "spike_then_drop"}},
    )
    _write_json(
        scenario_root / "erp" / "listing_draft_created.json",
        {"response": {"status": "draft_created", "accepted": True, "channel": "amazon"}},
    )
    _write_json(
        scenario_root / "erp" / "profit_trace_decline.json",
        {"response": {"risk_flag": "profit_decline", "margin_rate": 0.12, "complaints": 4}},
    )
    return scenario_root


@pytest.mark.asyncio
async def test_model_finetune_service_writes_local_artifact_and_registry(tmp_path: Path):
    feedback_root = _build_feedback_root(tmp_path)
    scenario_root = _build_scenario_root(tmp_path)
    artifact_root = tmp_path / "llm_artifacts"

    service = ModelFinetuneService(
        session=None,
        tenant_id="00000000-0000-0000-0000-000000000001",
        feedback_root=feedback_root,
        scenario_root=scenario_root,
        artifact_root=artifact_root,
    )
    result = await service.run_weekly_finetune(registry_key="tenant-a", train_days=7)

    artifact_path = Path(result["artifact_path"])
    latest_path = Path(result["latest_artifact_path"])
    assert result["status"] == "completed"
    assert result["training_mode"] == "local-real"
    assert result["training_backend"] == "cpu-feedback-adapter"
    assert artifact_path.exists()
    assert latest_path.exists()
    assert result["training_snapshot"]["source_breakdown"]["erp_feedback"] == 2
    assert result["training_snapshot"]["source_breakdown"]["scenario_seed"] == 6
    assert result["evaluation"]["not_regressed"] is True
    assert result["model_registry"]["active_model_version"] == result["new_model_version"]

    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_payload["new_model_version"] == result["new_model_version"]
    assert artifact_payload["adapter_summary"]["vocabulary_size"] > 0


@pytest.mark.asyncio
async def test_model_finetune_service_uses_builtin_seeds_when_scenarios_missing(tmp_path: Path):
    feedback_root = _build_single_class_feedback_root(tmp_path)
    scenario_root = tmp_path / "empty_scenarios"
    artifact_root = tmp_path / "llm_artifacts"

    service = ModelFinetuneService(
        session=None,
        tenant_id="00000000-0000-0000-0000-000000000001",
        feedback_root=feedback_root,
        scenario_root=scenario_root,
        artifact_root=artifact_root,
    )
    result = await service.run_weekly_finetune(registry_key="tenant-b", train_days=14)

    assert result["status"] == "completed"
    assert result["training_snapshot"]["source_breakdown"]["builtin_seed"] == 4
    assert result["evaluation"]["validation_examples"] >= 1
    assert Path(result["artifact_path"]).exists()


@pytest.mark.asyncio
async def test_model_finetune_worker_run_once_updates_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_root = _build_feedback_root(tmp_path)
    scenario_root = _build_scenario_root(tmp_path)
    artifact_root = tmp_path / "worker_artifacts"

    class _ConfiguredModelFinetuneService(ModelFinetuneService):
        def __init__(self, session, tenant_id: str):
            super().__init__(
                session,
                tenant_id,
                feedback_root=feedback_root,
                scenario_root=scenario_root,
                artifact_root=artifact_root,
            )

    monkeypatch.setattr("src.workers.model_finetune_worker.ModelFinetuneService", _ConfiguredModelFinetuneService)

    worker = WeeklyModelFinetuneWorker(interval_seconds=1.0)
    result = await worker.run_once(registry_key="tenant-worker", train_days=7)

    assert result["status"] == "completed"
    assert result["training_backend"] == "cpu-feedback-adapter"
    assert Path(result["artifact_path"]).exists()
