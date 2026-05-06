"""
API端点模块初始化。
"""

from src.api.v1.endpoints.health import router as health_router
from src.api.v1.endpoints.system import router as system_router

__all__ = ["health_router", "system_router"]
