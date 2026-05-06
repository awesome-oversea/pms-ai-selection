from __future__ import annotations

from src.services.batch_ads_service import BatchAdsService, LocalBatchAdsStore
from src.services.local_feature_job_service import LocalFeatureJobService


def test_local_feature_job_service_persists_ads_rows(tmp_path):
    root = tmp_path / "workspace"
    (root / "artifacts" / "erp_local" / "oms").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "erp_local" / "crm").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "erp_local" / "wms").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "erp_local" / "scm").mkdir(parents=True, exist_ok=True)
    (root / "data" / "lake" / "selection_tasks" / "snapshots" / "20260416").mkdir(parents=True, exist_ok=True)

    (root / "artifacts" / "erp_local" / "oms" / "orders.json").write_text('{"items":[{"order_id":"o-1","task_id":"task-ads-001","quantity":10,"revenue":399.0}]}', encoding='utf-8')
    (root / "artifacts" / "erp_local" / "crm" / "feedback.json").write_text('{"items":[{"id":"r-1","task_id":"task-ads-001","customer_score":4.5,"review_count":2,"feedback":"good quality"}]}', encoding='utf-8')
    (root / "artifacts" / "erp_local" / "wms" / "inventory.json").write_text('{"items":[{"task_id":"task-ads-001","available_quantity":18,"safety_stock":6}]}', encoding='utf-8')
    (root / "artifacts" / "erp_local" / "scm" / "quotes.json").write_text('{"items":[{"task_id":"task-ads-001","quote_price":21.5},{"task_id":"task-ads-001","quote_price":22.0}]}', encoding='utf-8')
    (root / "data" / "lake" / "selection_tasks" / "snapshots" / "20260416" / "selection_tasks.jsonl").write_text('{"task_id":"task-ads-001"}\n', encoding='utf-8')

    store = LocalBatchAdsStore(root / "data" / "local_batch_ads.db")
    service = LocalFeatureJobService(root=root, ads_store=store)
    payload = service.run_batch_feature_job()

    assert payload["status"] == "completed"
    batch_service = BatchAdsService(store=store)
    latest = batch_service.get_latest_features(limit=10)
    assert latest["total"] == 1
    assert latest["items"][0]["product_id"] == "task-ads-001"
    overview = batch_service.get_selection_overview_ads()
    assert overview is not None
    assert overview["product_id"] == "task-ads-001"
    assert overview["total_units"] == 10
