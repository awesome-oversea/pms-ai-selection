"""
配置管理模块
============

基于 pydantic-settings 实现分层配置管理:
- 基础配置: 应用名/版本/日志级别
- 数据库配置: PostgreSQL连接参数
- Redis配置: 缓存集群连接
- Kafka配置: 消息队列连接
- K8s配置: 集群拓扑/节点规格/网络方案
- LLM配置: 模型路由/Ollama/兼容vLLM-Triton
- 安全配置: JWT/RBAC/CORS

配置加载优先级: 环境变量 > .env文件 > 默认值

使用方式:
    from src.config.settings import get_settings

    settings = get_settings()
    print(settings.app_name)
    print(settings.k8s.cluster_name)
"""

from src.config.k8s_config import (
    K8sClusterConfig,
    K8sNetworkConfig,
    K8sNodeSpec,
    K8sSecurityConfig,
    K8sStorageConfig,
    K8sTopologyConfig,
)
from src.config.settings import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
    "K8sTopologyConfig",
    "K8sClusterConfig",
    "K8sNodeSpec",
    "K8sNetworkConfig",
    "K8sStorageConfig",
    "K8sSecurityConfig",
]
