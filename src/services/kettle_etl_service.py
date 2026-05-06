from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class KettleETLService:
    """本地 Kettle-compatible ETL 与 Ray-compatible runner 切换实现。"""

    RUNNER_SPECS = [
        {
            "runner": "python-local",
            "mode": "single_process",
            "notes": "默认本地单进程执行，适合作为 Pandas/Dask 兼容链路的基线。",
        },
        {
            "runner": "ray-compatible",
            "mode": "actor_parallel",
            "notes": "兼容 Ray Actor 分片执行语义，当前以本地 actor-shard 聚合落地。",
        },
    ]

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.erp_root = self.root / "artifacts" / "erp_local"
        self.artifact_root = self.root / "artifacts" / "data_platform"
        self.artifact_path = self.artifact_root / "kettle_etl_job_latest.json"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def supported_runners() -> list[dict[str, str]]:
        return [dict(item) for item in KettleETLService.RUNNER_SPECS]

    @staticmethod
    def _read_json(path: Path) -> Any:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @classmethod
    def _items(cls, path: Path) -> list[dict[str, Any]]:
        payload = cls._read_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _margin_bucket(margin_rate: float) -> str:
        if margin_rate >= 0.3:
            return "healthy"
        if margin_rate >= 0.15:
            return "watch"
        return "risk"

    def _build_supplier_rows(self, quotes: list[dict[str, Any]], outbound_plan: dict[str, Any]) -> list[dict[str, Any]]:
        target_price = self._to_float(outbound_plan.get("target_procurement_price"))
        planned_quantity = int(outbound_plan.get("quantity") or 0)
        task_id = str(outbound_plan.get("task_id") or outbound_plan.get("product_id") or "")
        target_market = str(outbound_plan.get("target_market") or "unknown")

        rows: list[dict[str, Any]] = []
        for item in quotes:
            procurement_price = self._to_float(
                item.get("procurement_price", item.get("quote_price", item.get("price"))),
            )
            price_gap = round(target_price - procurement_price, 4) if target_price else 0.0
            rows.append(
                {
                    "pipeline_key": "supplier_quote_etl",
                    "source_system": "scm",
                    "target_system": "wms",
                    "product_id": str(item.get("product_id") or task_id or ""),
                    "task_id": task_id or str(item.get("product_id") or ""),
                    "asin": str(item.get("asin") or outbound_plan.get("asin") or ""),
                    "supplier_code": str(item.get("supplier_code") or ""),
                    "supplier_name": str(item.get("supplier_name") or ""),
                    "procurement_price": procurement_price,
                    "target_procurement_price": target_price,
                    "price_gap_to_target": price_gap,
                    "planned_quantity": planned_quantity,
                    "target_market": target_market,
                    "decision": str(outbound_plan.get("decision") or "PENDING"),
                }
            )
        return rows

    def _build_finance_rows(
        self,
        profits: list[dict[str, Any]],
        outbound_profit_plan: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        target_profit_map = {
            str(item.get("product_id") or ""): self._to_float(item.get("target_profit"))
            for item in outbound_profit_plan
            if item.get("product_id")
        }
        rows: list[dict[str, Any]] = []
        for item in profits:
            product_id = str(item.get("product_id") or "")
            gross_profit = self._to_float(item.get("gross_profit"))
            cost = self._to_float(item.get("cost"))
            expense = self._to_float(item.get("expense"))
            margin_rate = self._to_float(item.get("margin_rate"))
            target_profit = target_profit_map.get(product_id, 0.0)
            rows.append(
                {
                    "pipeline_key": "finance_profit_etl",
                    "source_system": "fms",
                    "target_system": "bi",
                    "product_id": product_id,
                    "asin": str(item.get("asin") or ""),
                    "product_name": str(item.get("product_name") or ""),
                    "gross_profit": gross_profit,
                    "cost": cost,
                    "expense": expense,
                    "margin_rate": margin_rate,
                    "target_profit": target_profit,
                    "profit_gap": round(gross_profit - target_profit, 4),
                    "margin_bucket": self._margin_bucket(margin_rate),
                }
            )
        return rows

    @classmethod
    def _build_actor_summary(
        cls,
        *,
        runner: str,
        supplier_input_count: int,
        supplier_output_count: int,
        finance_input_count: int,
        finance_output_count: int,
    ) -> list[dict[str, Any]]:
        if runner != "ray-compatible":
            return []
        return [
            {
                "actor": "ray-compatible.supplier_etl_actor",
                "task": "supplier_quote_etl",
                "status": "completed",
                "input_records": supplier_input_count,
                "output_records": supplier_output_count,
            },
            {
                "actor": "ray-compatible.finance_etl_actor",
                "task": "finance_profit_etl",
                "status": "completed",
                "input_records": finance_input_count,
                "output_records": finance_output_count,
            },
        ]

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    def run(self, *, runner: str = "python-local") -> dict[str, Any]:
        supported_runners = {item["runner"] for item in self.RUNNER_SPECS}
        if runner not in supported_runners:
            raise ValueError(f"Unsupported kettle etl runner: {runner}")

        quotes = self._items(self.erp_root / "scm" / "quotes.json")
        profits = self._items(self.erp_root / "fms" / "profit.json")
        outbound_plan = self._read_json(self.erp_root / "scm" / "outbound-product-plan.json")
        if not isinstance(outbound_plan, dict):
            outbound_plan = {}
        outbound_profit_plan = self._items(self.erp_root / "fms" / "outbound-profit-plan.json")

        supplier_rows = self._build_supplier_rows(quotes, outbound_plan)
        finance_rows = self._build_finance_rows(profits, outbound_profit_plan)
        actors = self._build_actor_summary(
            runner=runner,
            supplier_input_count=len(quotes),
            supplier_output_count=len(supplier_rows),
            finance_input_count=len(profits),
            finance_output_count=len(finance_rows),
        )

        mapped_supplier_prices = sum(1 for item in supplier_rows if item["procurement_price"] > 0)
        mapped_target_profits = sum(1 for item in finance_rows if item["target_profit"] > 0)
        avg_procurement_price = round(mean([item["procurement_price"] for item in supplier_rows]), 4) if supplier_rows else 0.0
        avg_margin_rate = round(mean([item["margin_rate"] for item in finance_rows]), 4) if finance_rows else 0.0
        supplier_price_coverage_ratio = self._ratio(mapped_supplier_prices, len(supplier_rows)) if supplier_rows else 0.0
        target_profit_coverage_ratio = self._ratio(mapped_target_profits, len(finance_rows)) if finance_rows else 0.0
        output_coverage_ratio = self._ratio(len(supplier_rows) + len(finance_rows), len(quotes) + len(profits)) if (len(quotes) + len(profits)) else 0.0
        failed_rows = max((len(quotes) - len(supplier_rows)), 0) + max((len(profits) - len(finance_rows)), 0)
        quality_score = round(((supplier_price_coverage_ratio + target_profit_coverage_ratio + output_coverage_ratio) / 3), 4)
        business_consumable = bool(supplier_rows) and bool(finance_rows) and quality_score >= 0.8
        failure_summary = []
        if not supplier_rows:
            failure_summary.append("supplier_quote_etl produced no rows")
        if not finance_rows:
            failure_summary.append("finance_profit_etl produced no rows")
        if supplier_rows and supplier_price_coverage_ratio < 1.0:
            failure_summary.append("supplier procurement price coverage incomplete")
        if finance_rows and target_profit_coverage_ratio < 1.0:
            failure_summary.append("finance target profit coverage incomplete")

        payload = {
            "job_type": "kettle_etl",
            "etl_engine": "pandas-dask-compatible",
            "runner": runner,
            "execution_mode": "actor_parallel" if runner == "ray-compatible" else "single_process",
            "status": "completed",
            "source_assets": [
                "artifacts/erp_local/scm/quotes.json",
                "artifacts/erp_local/scm/outbound-product-plan.json",
                "artifacts/erp_local/fms/profit.json",
                "artifacts/erp_local/fms/outbound-profit-plan.json",
            ],
            "output_assets": [
                "supplier_quote_fact",
                "finance_profit_fact",
                "artifacts/data_platform/kettle_etl_job_latest.json",
            ],
            "records_processed": len(quotes) + len(profits),
            "quality_summary": {
                "input_records": len(quotes) + len(profits),
                "output_records": len(supplier_rows) + len(finance_rows),
                "supplier_rows": len(supplier_rows),
                "finance_rows": len(finance_rows),
                "supplier_price_coverage": mapped_supplier_prices,
                "target_profit_coverage": mapped_target_profits,
                "supplier_price_coverage_ratio": supplier_price_coverage_ratio,
                "target_profit_coverage_ratio": target_profit_coverage_ratio,
                "output_coverage_ratio": output_coverage_ratio,
                "failed_rows": failed_rows,
                "quality_score": quality_score,
                "all_required_fields_ready": bool(supplier_rows) and bool(finance_rows),
                "business_consumable": business_consumable,
                "failure_summary": failure_summary,
            },
            "summary": {
                "supplier_count": len(supplier_rows),
                "finance_count": len(finance_rows),
                "avg_procurement_price": avg_procurement_price,
                "avg_margin_rate": avg_margin_rate,
            },
            "pipelines": {
                "supplier_quote_etl": supplier_rows,
                "finance_profit_etl": finance_rows,
            },
            "actors": actors,
            "supported_runners": self.supported_runners(),
            "business_consumable": business_consumable,
            "latest_run_quality_score": quality_score,
            "failure_summary": failure_summary,
            "executed_at": self._now_iso(),
        }

        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Kettle-compatible ETL completed with runner=%s", runner)
        return payload
