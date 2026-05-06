from __future__ import annotations

from src.infrastructure.ws_gateway import ERPGateway, WebSocketManager

_ws_manager = WebSocketManager()
_erp_gateway = ERPGateway()


def get_websocket_manager() -> WebSocketManager:
    return _ws_manager


def get_erp_gateway() -> ERPGateway:
    return _erp_gateway


def get_realtime_gateway_status() -> dict:
    return {
        "websocket": _ws_manager.get_status(),
        "erp_gateway": {
            "supported_systems": sorted(list(_erp_gateway.SUPPORTED_SYSTEMS)),
            "registered_adapters": sorted(list(_erp_gateway._adapters.keys())),
            "queue_size": len(_erp_gateway._event_queue),
            "dead_letter_size": len(_erp_gateway._dead_letter_queue),
            "sync_log_size": len(_erp_gateway._sync_log),
        },
        "transport": {
            "sse_ready": True,
            "websocket_manager_ready": True,
            "client_reconnect_strategy": "client_reconnect",
        },
    }
