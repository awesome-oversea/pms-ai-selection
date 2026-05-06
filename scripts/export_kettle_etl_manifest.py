from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "artifacts" / "data_platform" / "kettle_etl_manifest.json"

from src.services.kettle_etl_service import KettleETLService


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "etl_engine": "kettle-compatible",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "supported_runners": KettleETLService.supported_runners(),
        "latest_run_artifact": "artifacts/data_platform/kettle_etl_job_latest.json",
        "pipelines": [
            {
                "pipeline_key": "scm_to_wms_replenishment",
                "source_system": "scm",
                "target_system": "wms",
                "source_entity": "product_plan",
                "target_entity": "replenishment_plan",
                "mapping": {"supplier_code": "supplier_code", "planned_quantity": "replenishment_quantity", "expected_delivery_date": "expected_arrival_date"},
            },
            {
                "pipeline_key": "wms_to_oms_inventory",
                "source_system": "wms",
                "target_system": "oms",
                "source_entity": "inventory_snapshot",
                "target_entity": "listing_inventory",
                "mapping": {"sku": "sku", "available_quantity": "available_quantity", "location_code": "warehouse_location"},
            },
            {
                "pipeline_key": "oms_to_fms_orders",
                "source_system": "oms",
                "target_system": "fms",
                "source_entity": "order",
                "target_entity": "finance_metric",
                "mapping": {"order_id": "order_id", "sales_amount": "gross_revenue", "refund_amount": "refund_total"},
            },
            {
                "pipeline_key": "crm_to_bi_review_metrics",
                "source_system": "crm",
                "target_system": "bi",
                "source_entity": "review",
                "target_entity": "selection_daily_kpis",
                "mapping": {"rating": "avg_rating", "review_count": "review_count", "complaint_count": "complaint_count"},
            },
        ],
    }
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
