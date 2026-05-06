"""
AI选品系统 (FMS - AI Product Selection System)
=============================================

跨境电商AI智能产品选择平台 - 企业级终极设计方案实现

项目结构:
    src/
    ├── config/          # 配置管理 (Pydantic Settings)
    ├── core/            # 核心工具 (日志/异常/依赖注入)
    ├── models/           # 数据模型 (SQLAlchemy ORM / Pydantic)
    ├── api/              # API路由层 (FastAPI Router)
    ├── services/         # 业务逻辑层
    ├── infrastructure/   # 基础设施配置 (K8s/Docker/网络)
    └── agents/           # AI Agent层

版本: v0.1.0
作者: PMS Team
"""

__version__ = "0.1.0"
__author__ = "PMS Team"
