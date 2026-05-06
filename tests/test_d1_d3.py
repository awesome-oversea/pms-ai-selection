"""D1-D3 单元测试: 项目启动与架构设计

验证K8s配置模型的行为逻辑:
    - 节点资源计算(total_cpu/total_memory/total_gpu)
    - 资源清单表格行转换
    - 网络配置工厂方法
    - 拓扑配置聚合计算
    - Markdown/YAML导出
    - Settings配置加载
"""

from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")


from src.config.k8s_config import (
    CNIType,
    K8sClusterConfig,
    K8sNetworkConfig,
    K8sNodeSpec,
    K8sSecurityConfig,
    K8sStorageConfig,
    K8sTopologyConfig,
    NodeRole,
    StorageClassType,
)
from src.config.settings import Settings


class TestK8sNodeSpec:
    """节点规格行为测试: 验证资源计算逻辑"""

    def test_total_cpu_cores_multiplies_by_count(self):
        node = K8sNodeSpec(role=NodeRole.WORKER_APP, count=6, cpu_cores=8, memory_gb=16)
        assert node.total_cpu_cores() == 48

    def test_total_memory_gb_multiplies_by_count(self):
        node = K8sNodeSpec(role=NodeRole.WORKER_APP, count=6, cpu_cores=8, memory_gb=16)
        assert node.total_memory_gb() == 96

    def test_total_gpu_count_multiplies_by_count(self):
        node = K8sNodeSpec(
            role=NodeRole.WORKER_GPU, count=4, cpu_cores=16, memory_gb=64,
            gpu_type="A100-80GB", gpu_count=3,
        )
        assert node.total_gpu_count() == 12

    def test_gpu_count_zero_when_no_gpu(self):
        node = K8sNodeSpec(role=NodeRole.MASTER, count=2, cpu_cores=4, memory_gb=8)
        assert node.total_gpu_count() == 0

    def test_to_resource_table_row_includes_computed_totals(self):
        node = K8sNodeSpec(
            role=NodeRole.WORKER_GPU, count=4, cpu_cores=16, memory_gb=64,
            gpu_type="A100-80GB", gpu_count=3, storage_gb=500,
        )
        row = node.to_resource_table_row()
        assert row["role"] == "worker_gpu"
        assert row["count"] == 4
        assert row["total_cpu"] == 64
        assert row["total_mem"] == 256
        assert row["total_gpu"] == 12
        assert "A100-80GB" in row["gpu"]

    def test_to_resource_table_row_shows_no_gpu_when_absent(self):
        node = K8sNodeSpec(role=NodeRole.MASTER, count=2, cpu_cores=4, memory_gb=8)
        row = node.to_resource_table_row()
        assert row["gpu"] == "无"


class TestK8sNetworkConfig:
    """网络配置行为测试: 验证工厂方法产出正确配置"""

    def test_default_calico_sets_cni_and_policy(self):
        net = K8sNetworkConfig.default_calico()
        assert net.cni_type == CNIType.CALICO
        assert net.network_policy_enabled is True

    def test_default_cilium_sets_cni_and_policy(self):
        net = K8sNetworkConfig.default_cilium()
        assert net.cni_type == CNIType.CILIUM
        assert net.network_policy_enabled is True

    def test_default_cidr_ranges_are_valid(self):
        net = K8sNetworkConfig()
        assert net.pod_cidr.startswith("10.")
        assert net.service_cidr.startswith("10.")
        assert "/" in net.pod_cidr
        assert "/" in net.service_cidr


class TestK8sStorageConfig:
    """存储配置行为测试: 验证默认存储类映射"""

    def test_storage_classes_contains_required_keys(self):
        storage = K8sStorageConfig()
        assert "fast-ssd" in storage.storage_classes
        assert "shared-nfs" in storage.storage_classes
        assert "object-storage" in storage.storage_classes

    def test_default_shared_storage_type_is_nfs(self):
        storage = K8sStorageConfig()
        assert storage.shared_storage_type == StorageClassType.NFS


class TestK8sClusterConfig:
    """集群配置行为测试: 验证默认值合理性"""

    def test_defaults_satisfy_ha_requirements(self):
        config = K8sClusterConfig()
        assert config.master_count >= 2, "HA requires at least 2 masters"
        assert config.etcd_count >= 3, "etcd quorum requires odd number >= 3"
        assert config.etcd_count % 2 == 1, "etcd count must be odd for quorum"

    def test_namespaces_include_required_system_ns(self):
        config = K8sClusterConfig()
        assert "kube-system" in config.namespaces
        assert "default" in config.namespaces


class TestK8sTopologyConfig:
    """拓扑配置聚合行为测试: 验证跨节点计算和导出"""

    def test_production_topology_total_nodes(self):
        topo = K8sTopologyConfig.default_production()
        assert topo.total_nodes == 14  # 2 master + 6 worker + 4 gpu + 2 inference

    def test_production_topology_has_gpu_cards(self):
        topo = K8sTopologyConfig.default_production()
        assert topo.total_gpu_cards > 0

    def test_production_topology_storage_is_positive(self):
        topo = K8sTopologyConfig.default_production()
        assert topo.total_storage_gb > 0

    def test_development_topology_is_smaller(self):
        dev = K8sTopologyConfig.default_development()
        prod = K8sTopologyConfig.default_production()
        assert dev.total_nodes < prod.total_nodes

    def test_get_nodes_by_role_filters_correctly(self):
        topo = K8sTopologyConfig.default_production()
        masters = topo.get_nodes_by_role(NodeRole.MASTER)
        assert len(masters) == 1
        assert masters[0].role == NodeRole.MASTER

    def test_get_resource_summary_contains_all_keys(self):
        topo = K8sTopologyConfig.default_production()
        summary = topo.get_resource_summary()
        required_keys = [
            "cluster_name", "k8s_version", "total_nodes",
            "total_cpu_cores", "total_memory_gb", "total_gpu_cards",
            "cni_type", "az_count",
        ]
        for key in required_keys:
            assert key in summary, f"Missing key: {key}"

    def test_to_markdown_produces_valid_document(self):
        topo = K8sTopologyConfig.default_production()
        md = topo.to_markdown()
        assert "# K8s集群拓扑设计方案" in md
        assert topo.cluster.name in md
        assert topo.cluster.kubernetes_version in md
        assert "节点规格清单" in md
        assert "网络方案" in md
        assert "存储方案" in md
        assert "安全基线" in md

    def test_to_yaml_produces_valid_structure(self):
        topo = K8sTopologyConfig.default_production()
        yaml_str = topo.to_yaml()
        assert '"cluster"' in yaml_str
        assert '"network"' in yaml_str
        assert '"storage"' in yaml_str
        assert '"nodes"' in yaml_str


class TestK8sSecurityConfig:
    """安全基线行为测试: 验证默认安全策略"""

    def test_production_defaults_are_secure(self):
        sec = K8sSecurityConfig()
        assert sec.rbac_enabled is True
        assert sec.network_policy_default_action == "DENY"
        assert sec.secret_encryption_enabled is True
        assert sec.image_scan_enabled is True
        assert sec.pod_security_standard == "restricted"
        assert sec.audit_log_enabled is True

    def test_allowed_registries_not_empty(self):
        sec = K8sSecurityConfig()
        assert len(sec.allowed_registries) > 0


class TestSettings:
    """配置管理行为测试"""

    def test_settings_loads_without_error(self):
        settings = Settings()
        assert settings.app.name is not None
        assert isinstance(settings.app.name, str)

    def test_settings_database_url_uses_asyncpg(self):
        settings = Settings()
        assert "postgresql" in settings.database.url
        assert "asyncpg" in settings.database.url
