"""
核心工具模块
===========

提供全局日志配置、自定义异常类、依赖注入等基础能力。
所有其他模块依赖此模块提供的通用基础设施。
"""

from src.core.exceptions import (
    ConfigurationError,
    PMSBaseException,
    ResourceNotFoundError,
    ValidationError,
)
from src.core.logging import get_logger, setup_logger

__all__ = [
    "setup_logger",
    "get_logger",
    "PMSBaseException",
    "ConfigurationError",
    "ResourceNotFoundError",
    "ValidationError",
]
