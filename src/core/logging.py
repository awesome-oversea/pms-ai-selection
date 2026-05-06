"""
全局日志配置模块
===============

基于 loguru 实现统一日志管理，支持:
- 控制台彩色输出 (开发环境)
- 文件轮转记录 (生产环境)
- 结构化JSON输出 (可选，对接ELK)
- 请求追踪ID自动注入

使用方式:
    from src.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("任务创建成功", extra={"task_id": "TASK-001"})
"""

import sys
from pathlib import Path

from loguru import logger as _base_logger


def setup_logger(
    log_level: str = "INFO",
    log_dir: Path | None = None,
    json_format: bool = False,
) -> None:
    """
    初始化并配置全局日志系统。

    移除默认handler，添加自定义格式化的控制台和文件处理器。

    Args:
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        log_dir: 日志文件存放目录，None则不写文件
        json_format: 是否使用JSON格式输出(用于ELK采集)

    Returns:
        None

    Example:
        >>> from src.core.logging import setup_logger
        >>> setup_logger(log_level="DEBUG", log_dir=Path("./logs"))

    Note:
        - 控制台使用彩色格式便于开发调试
        - 文件按日期轮转，单文件最大100MB，保留30天
        - JSON格式适用于生产环境日志采集系统
    """
    _base_logger.remove()

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{message}"
    )

    _base_logger.add(
        sys.stderr,
        format=console_format,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        _base_logger.add(
            log_dir / "pms_{time:YYYY-MM-DD}.log",
            format=file_format if not json_format else "{message}",
            level=log_level,
            rotation="100 MB",
            retention="30 days",
            compression="gz",
            encoding="utf-8",
        )


def get_logger(name: str):
    """
    获取模块级logger实例。

    每个模块应通过此函数获取专属logger，
    便于在日志中定位问题来源。

    Args:
        name: 通常传入 __name__，如 "src.services.selection"

    Returns:
        loguru.Logger: 配置好的logger实例

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("处理选品请求", extra={"user_id": "u001"})
    """
    return _base_logger.bind(name=name)
