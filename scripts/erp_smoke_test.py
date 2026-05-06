from __future__ import annotations

import json

SYSTEMS = ["oms", "wms", "crm", "fms", "bi"]
REQUIRED_PATHS = ["config", "test_connection", "sync_or_metrics", "logs"]


def build_payload() -> dict:
    return {
        "smoke_scope": "erp_minimal_smoke",
        "systems": {
            system: {
                "required_paths": REQUIRED_PATHS,
                "ready_for_manual_smoke": True,
                "environment_connected": False,
                "evidence_required": ["config_record", "connection_result", "sync_or_metrics_result", "log_record"],
            }
            for system in SYSTEMS
        },
        "api_examples": {
            "oms": [
                "/api/v1/integration/oms/config",
                "/api/v1/integration/oms/test-connection",
                "/api/v1/integration/oms/sync/inbound",
                "/api/v1/integration/oms/logs",
            ],
            "wms": [
                "/api/v1/integration/wms/config",
                "/api/v1/integration/wms/test-connection",
                "/api/v1/integration/wms/sync/inbound",
                "/api/v1/integration/wms/logs",
            ],
            "crm": [
                "/api/v1/integration/crm/config",
                "/api/v1/integration/crm/test-connection",
                "/api/v1/integration/crm/sync/inbound",
                "/api/v1/integration/crm/logs",
            ],
            "fms": [
                "/api/v1/integration/fms/config",
                "/api/v1/integration/fms/test-connection",
                "/api/v1/integration/fms/sync/inbound",
                "/api/v1/integration/fms/logs",
            ],
            "bi": [
                "/api/v1/integration/bi/config",
                "/api/v1/integration/bi/test-connection",
                "/api/v1/integration/bi/tasks/{task_id}/metrics",
                "/api/v1/integration/bi/logs",
            ],
        },
    }


def main() -> int:
    print(json.dumps(build_payload(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
