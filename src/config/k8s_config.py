"""
K8s集群拓扑配置模块
===================

定义Kubernetes集群的完整拓扑结构，包括:
- 集群规模: Master/Worker/GPU节点数量与规格
- 网络方案: CNI插件/Pod网段/Service网段/VPC规划
- 存储方案: 本地SSD/共享存储/对象存储
- 高可用: etcd集群/Master HA/多AZ部署
- 安全基线: NetworkPolicy/RBAC/Secret管理
- GPU调度: NVIDIA Device Plugin/MIG配置
- Namespace隔离: agent/data/inference/monitoring

此模块是D1(T001)的核心产出:
    - K8s拓扑设计方案的数据结构定义
    - 资源需求清单的代码化表达
    - 高可用方案的参数化配置

使用方式:
    from src.config.k8s_config import K8sTopologyConfig

    topo = K8sTopologyConfig.default_production()
    print(topo.to_markdown())  # 输出完整拓扑文档
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any


class NodeRole(StrEnum):
    """K8s节点角色枚举。"""
    MASTER = "master"
    WORKER_APP = "worker_app"
    WORKER_GPU = "worker_gpu"
    INFERENCE = "inference"


class CNIType(StrEnum):
    """CNI网络插件类型。"""
    CALICO = "calico"
    CILIUM = "cilium"
    FLANNEL = "flannel"


class StorageClassType(StrEnum):
    """存储类型。"""
    LOCAL_SSD = "local_ssd"
    NFS = "nfs"
    CEPH_RBD = "ceph_rbd"
    OSS_S3 = "oss_s3"


@dataclass
class K8sNodeSpec:
    """
    K8s节点规格定义。

    描述单个节点的硬件规格和角色属性，
    用于生成资源申请清单和节点标签。

    Attributes:
        role: 节点角色(master/worker_app/worker_gpu/inference)
        count: 该角色节点数量
        cpu_cores: CPU核心数
        memory_gb: 内存大小(GB)
        gpu_type: GPU型号(如A100-80GB/A10-24GB)，无GPU则为None
        gpu_count: 每节点GPU卡数
        storage_gb: 本地SSD存储大小(GB)
        labels: K8s节点标签字典(用于节点选择器)
        taints: 节点污点列表(用于GPU节点专用调度)

    Example:
        >>> master_node = K8sNodeSpec(
        ...     role=NodeRole.MASTER,
        ...     count=2,
        ...     cpu_cores=4,
        ...     memory_gb=8,
        ... )
        >>> print(master_node.total_memory_gb())
        16
    """

    role: NodeRole
    count: int
    cpu_cores: int
    memory_gb: int
    gpu_type: str | None = None
    gpu_count: int = 0
    storage_gb: int = 100
    labels: dict[str, str] = field(default_factory=dict)
    taints: list[str] = field(default_factory=list)

    def total_cpu_cores(self) -> int:
        """计算该角色所有节点的CPU总核数。"""
        return self.cpu_cores * self.count

    def total_memory_gb(self) -> int:
        """计算该角色所有节点的内存总量(GB)。"""
        return self.memory_gb * self.count

    def total_gpu_count(self) -> int:
        """计算该角色所有节点的GPU总卡数。"""
        return self.gpu_count * self.count

    def to_resource_table_row(self) -> dict[str, Any]:
        """转换为资源清单表格行格式。"""
        return {
            "role": self.role.value,
            "count": self.count,
            "spec": f"{self.cpu_cores}C/{self.memory_gb}G",
            "gpu": f"{self.gpu_type}×{self.gpu_count}" if self.gpu_type else "无",
            "storage": f"{self.storage_gb}GB",
            "total_cpu": self.total_cpu_cores(),
            "total_mem": self.total_memory_gb(),
            "total_gpu": self.total_gpu_count(),
        }


@dataclass
class K8sNetworkConfig:
    """
    K8s网络配置方案。

    定义Pod网络、Service网络、VPC划分等网络相关参数。

    Attributes:
        cni_type: CNI插件选择(Calico/Cilium/Flannel)
        pod_cidr: Pod网段地址范围
        service_cidr: Service网段地址范围
        node_cidr: 节点物理网段
        vpc_cidr: VPC整体网段
        dns_cluster_ip: 集群DNS服务IP
        network_policy_enabled: 是否启用NetworkPolicy默认拒绝策略

    Example:
        >>> net = K8sNetworkConfig.default_calico()
        >>> print(net.pod_cidr)
        10.244.0.0/16
    """

    cni_type: CNIType = CNIType.CALICO
    pod_cidr: str = "10.244.0.0/16"
    service_cidr: str = "10.96.0.0/12"
    node_cidr: str = "172.16.0.0/16"
    vpc_cidr: str = "10.0.0.0/16"
    dns_cluster_ip: str = "10.96.0.10"
    network_policy_enabled: bool = True

    @classmethod
    def default_calico(cls) -> K8sNetworkConfig:
        """创建Calico默认网络配置(推荐生产环境)。"""
        return cls(
            cni_type=CNIType.CALICO,
            pod_cidr="10.244.0.0/16",
            service_cidr="10.96.0.0/12",
            node_cidr="172.16.0.0/16",
            vpc_cidr="10.0.0.0/16",
            dns_cluster_ip="10.96.0.10",
            network_policy_enabled=True,
        )

    @classmethod
    def default_cilium(cls) -> K8sNetworkConfig:
        """创建Cilium默认网络配置(高性能场景推荐)。"""
        return cls(
            cni_type=CNIType.CILIUM,
            pod_cidr="10.244.0.0/16",
            service_cidr="10.96.0.0/12",
            node_cidr="172.16.0.0/16",
            vpc_cidr="10.0.0.0/16",
            dns_cluster_ip="10.96.0.10",
            network_policy_enabled=True,
        )


@dataclass
class K8sStorageConfig:
    """
    K8s存储配置方案。

    定义各类存储的容量和用途分配。

    Attributes:
        local_ssd_per_node_gb: 每节点本地SSD容量(GB)
        shared_storage_type: 共享存储类型(NFS/Ceph/OSS)
        shared_storage_total_gb: 共享存储总容量(GB)
        oss_bucket_name: 对象存储桶名称
        oss_capacity_tb: 对象存储容量(TB)
        storage_classes: 存储类名称映射
    """

    local_ssd_per_node_gb: int = 500
    shared_storage_type: StorageClassType = StorageClassType.NFS
    shared_storage_total_gb: int = 2000
    oss_bucket_name: str = "pms-data-lake"
    oss_capacity_tb: int = 10
    storage_classes: dict[str, str] = field(default_factory=lambda: {
        "fast-ssd": "local-path",
        "shared-nfs": "nfs-standard",
        "object-storage": "aws-s3-compatible",
    })


@dataclass
class K8sSecurityConfig:
    """
    K8s安全基线配置。

    定义集群安全相关的策略和配置项。

    Attributes:
        network_policy_default_action: 默认NetworkPolicy动作(Deny/Allow)
        rbac_enabled: 是否启用RBAC权限控制
        secret_encryption_enabled: 是否启用etcd Secret加密
        image_scan_enabled: 是否强制镜像安全扫描
        pod_security_standard: PodSecurity准入标准
        audit_log_enabled: 是否开启审计日志
        allowed_registries: 允许的镜像仓库白名单
    """

    network_policy_default_action: str = "DENY"
    rbac_enabled: bool = True
    secret_encryption_enabled: bool = True
    image_scan_enabled: bool = True
    pod_security_standard: str = "restricted"
    audit_log_enabled: bool = True
    allowed_registries: list[str] = field(
        default_factory=lambda: [
            "registry.internal.pms.com",
            "docker.io/library",
        ]
    )


@dataclass
class K8sClusterConfig:
    """
    K8s集群核心配置。

    定义集群名称、版本、高可用等核心参数。

    Attributes:
        name: 集群名称(用于资源标识和DNS)
        kubernetes_version: K8s版本号
        master_count: Master节点数量(建议≥2用于HA)
        etcd_count: etcd节点数量(建议3或5)
        ha_vip: 高可用VIP地址(Keepalived虚拟IP)
        ha_vip_port: VIP监听端口(通常6443)
        az_count: 可用区数量(多AZ部署)
        namespaces: 系统Namespace列表
    """

    name: str = "pms-cluster"
    kubernetes_version: str = "1.28"
    master_count: int = 2
    etcd_count: int = 3
    ha_vip: str = "10.0.1.100"
    ha_vip_port: int = 6443
    az_count: int = 2
    namespaces: list[str] = field(
        default_factory=lambda: [
            "agent",
            "data",
            "inference",
            "monitoring",
            "default",
            "kube-system",
        ]
    )


@dataclass
class K8sTopologyConfig:
    """
    K8s集群完整拓扑配置(聚合类)。

    这是D1(T001)的核心产出数据结构，
    聚合了集群、网络、存储、安全和所有节点规格。

    支持从实例导出为Markdown文档、YAML K8s Manifest等格式。

    Attributes:
        cluster: 集群核心配置
        nodes: 所有节点规格列表
        network: 网络配置
        storage: 存储配置
        security: 安全基线配置

    Example:
        >>> topo = K8sTopologyConfig.default_production()
        >>> print(topo.to_markdown())
        >>> topo.to_yaml_file("k8s-topology.yaml")
    """

    cluster: K8sClusterConfig = field(default_factory=K8sClusterConfig)
    nodes: list[K8sNodeSpec] = field(default_factory=list)
    network: K8sNetworkConfig = field(
        default_factory=K8sNetworkConfig.default_calico
    )
    storage: K8sStorageConfig = field(default_factory=K8sStorageConfig)
    security: K8sSecurityConfig = field(default_factory=K8sSecurityConfig)

    @classmethod
    def default_production(cls) -> K8sTopologyConfig:
        """
        创建生产环境默认拓扑配置。

        基于设计文档中的标准资源配置:
        - Master: 2台 × 4核8G (HA)
        - Worker App: 6台 × 8核16G
        - GPU Inference(A100): 推理节点
        - GPU Inference(A10): 多模态/Rerank节点

        Returns:
            K8sTopologyConfig: 生产级完整拓扑配置
        """
        nodes = [
            K8sNodeSpec(
                role=NodeRole.MASTER,
                count=2,
                cpu_cores=4,
                memory_gb=8,
                storage_gb=100,
                labels={"node-role.kubernetes.io/control-plane": ""},
                taints=["node-role.kubernetes.io/control-plane=:NoSchedule"],
            ),
            K8sNodeSpec(
                role=NodeRole.WORKER_APP,
                count=6,
                cpu_cores=8,
                memory_gb=16,
                storage_gb=500,
                labels={"node-type": "app", "pool": "general"},
            ),
            K8sNodeSpec(
                role=NodeRole.WORKER_GPU,
                count=4,
                cpu_cores=16,
                memory_gb=64,
                gpu_type="A100-80GB",
                gpu_count=3,
                storage_gb=500,
                labels={"node-type": "gpu", "gpu-type": "a100", "pool": "llm"},
                taints=["nvidia.com/gpu=true:NoSchedule"],
            ),
            K8sNodeSpec(
                role=NodeRole.INFERENCE,
                count=2,
                cpu_cores=8,
                memory_gb=32,
                gpu_type="A10-24GB",
                gpu_count=2,
                storage_gb=300,
                labels={"node-type": "gpu", "gpu-type": "a10", "pool": "multimodal"},
                taints=["nvidia.com/gpu=true:NoSchedule"],
            ),
        ]
        return cls(nodes=nodes)

    @classmethod
    def default_development(cls) -> K8sTopologyConfig:
        """创建开发环境精简拓扑配置(单Master+少量Worker)。"""
        nodes = [
            K8sNodeSpec(
                role=NodeRole.MASTER,
                count=1,
                cpu_cores=2,
                memory_gb=4,
                storage_gb=50,
                labels={"node-role.kubernetes.io/control-plane": ""},
            ),
            K8sNodeSpec(
                role=NodeRole.WORKER_APP,
                count=2,
                cpu_cores=4,
                memory_gb=8,
                storage_gb=100,
                labels={"node-type": "app"},
            ),
        ]
        return cls(
            cluster=K8sClusterConfig(
                name="pms-dev-cluster",
                master_count=1,
                etcd_count=1,
                az_count=1,
            ),
            nodes=nodes,
            security=K8sSecurityConfig(
                image_scan_enabled=False,
                audit_log_enabled=False,
            ),
        )

    @property
    def total_nodes(self) -> int:
        """返回集群总节点数。"""
        return sum(n.count for n in self.nodes)

    @property
    def total_gpu_cards(self) -> int:
        """返回集群总GPU卡数。"""
        return sum(n.total_gpu_count() for n in self.nodes)

    @property
    def total_storage_gb(self) -> int:
        """返回本地存储总容量(GB)。"""
        return sum(n.storage_gb * n.count for n in self.nodes)

    def get_nodes_by_role(self, role: NodeRole) -> list[K8sNodeSpec]:
        """按角色筛选节点规格。"""
        return [n for n in self.nodes if n.role == role]

    def get_resource_summary(self) -> dict[str, Any]:
        """
        生成资源汇总统计。

        Returns:
            dict: 包含CPU/内存/GPU/存储的汇总信息
        """
        return {
            "cluster_name": self.cluster.name,
            "k8s_version": self.cluster.kubernetes_version,
            "total_nodes": self.total_nodes,
            "master_nodes": self.cluster.master_count,
            "worker_nodes": self.total_nodes - self.cluster.master_count,
            "total_cpu_cores": sum(n.total_cpu_cores() for n in self.nodes),
            "total_memory_gb": sum(n.total_memory_gb() for n in self.nodes),
            "total_gpu_cards": self.total_gpu_cards,
            "total_local_storage_gb": self.total_storage_gb,
            "oss_storage_tb": self.storage.oss_capacity_tb,
            "cni_type": self.network.cni_type.value,
            "az_count": self.cluster.az_count,
            "ha_vip": self.cluster.ha_vip,
        }

    def to_markdown(self) -> str:
        """
        导出为Markdown格式的拓扑文档。

        用于D1产出物《K8s集群拓扑设计方案》文档生成。

        Returns:
            str: 完整的Markdown文档内容
        """
        lines: list[str] = []
        lines.append("# K8s集群拓扑设计方案")
        lines.append("")
        lines.append(f"> **集群名称**: {self.cluster.name}")
        lines.append(f"> **K8s版本**: {self.cluster.kubernetes_version}")
        lines.append("> **文档版本**: v1.0")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 1. 集群概览")
        lines.append("")
        summary = self.get_resource_summary()
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        for k, v in summary.items():
            lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
        lines.append("")

        lines.append("## 2. 节点规格清单")
        lines.append("")
        lines.append("| 角色 | 数量 | 规格(C/M/G) | GPU型号 | 存储 | 总CPU | 总内存 | 总GPU |")
        lines.append("|------|------|-------------|--------|------|-------|--------|-------|")
        for n in self.nodes:
            r = n.to_resource_table_row()
            lines.append(
                f"| {r['role']} | {r['count']} | {r['spec']} "
                f"| {r['gpu']} | {r['storage']} "
                f"| {r['total_cpu']}C | {r['total_mem']}G "
                f"| {r['total_gpu']} |"
            )
        lines.append("")

        lines.append("## 3. 网络方案")
        lines.append("")
        net = self.network
        lines.append(f"- **CNI插件**: {net.cni_type.value}")
        lines.append(f"- **Pod网段**: {net.pod_cidr}")
        lines.append(f"- **Service网段**: {net.service_cidr}")
        lines.append(f"- **节点网段**: {net.node_cidr}")
        lines.append(f"- **VPC网段**: {net.vpc_cidr}")
        lines.append(f"- **集群DNS**: {net.dns_cluster_ip}")
        lines.append(f"- **NetworkPolicy**: {'启用' if net.network_policy_enabled else '禁用'}")
        lines.append("")

        lines.append("## 4. 存储方案")
        lines.append("")
        stg = self.storage
        lines.append(f"- **本地SSD**: {stg.local_ssd_per_node_gb}GB/节点")
        lines.append(f"- **共享存储**: {stg.shared_storage_type.value} ({stg.shared_storage_total_gb}GB)")
        lines.append(f"- **对象存储(OSS)**: {stg.oss_bucket_name} ({stg.oss_capacity_tb}TB)")
        lines.append("")

        lines.append("## 5. 高可用方案")
        lines.append("")
        lines.append(f"- **Master数量**: {self.cluster.master_count} (HA)")
        lines.append(f"- **etcd节点**: {self.cluster.etcd_count} (集群化)")
        lines.append(f"- **HA VIP**: {self.cluster.ha_vip}:{self.cluster.ha_vip_port}")
        lines.append(f"- **可用区**: {self.cluster.az_count}个AZ")
        lines.append("- **负载均衡**: HAProxy + Keepalived")
        lines.append("")

        lines.append("## 6. 安全基线")
        lines.append("")
        sec = self.security
        lines.append(f"- **RBAC**: {'启用' if sec.rbac_enabled else '禁用'}")
        lines.append(f"- **NetworkPolicy默认**: {sec.network_policy_default_action}")
        lines.append(f"- **Secret加密**: {'启用' if sec.secret_encryption_enabled else '禁用'}")
        lines.append(f"- **镜像扫描**: {'强制' if sec.image_scan_enabled else '可选'}")
        lines.append(f"- **PodSecurity**: {sec.pod_security_standard}")
        lines.append(f"- **审计日志**: {'启用' if sec.audit_log_enabled else '禁用'}")
        lines.append("")

        lines.append("## 7. Namespace规划")
        lines.append("")
        for ns in self.cluster.namespaces:
            lines.append(f"- `{ns}`")
        lines.append("")

        lines.append("---")
        lines.append("\n**文档自动生成于**: K8sTopologyConfig.to_markdown()")
        return "\n".join(lines)

    def to_yaml(self) -> str:
        """
        导出为YAML格式的配置文件。

        用于生成K8s部署配置的基础参数文件。

        Returns:
            str: YAML字符串
        """
        import json

        data = {
            "cluster": {
                "name": self.cluster.name,
                "version": self.cluster.kubernetes_version,
                "master_count": self.cluster.master_count,
                "etcd_count": self.cluster.etcd_count,
                "ha_vip": self.cluster.ha_vip,
                "ha_vip_port": self.cluster.ha_vip_port,
                "az_count": self.cluster.az_count,
                "namespaces": self.cluster.namespaces,
            },
            "network": {
                "cni_type": self.network.cni_type.value,
                "pod_cidr": self.network.pod_cidr,
                "service_cidr": self.network.service_cidr,
                "node_cidr": self.network.node_cidr,
                "vpc_cidr": self.network.vpc_cidr,
                "dns_cluster_ip": self.network.dns_cluster_ip,
                "network_policy_enabled": self.network.network_policy_enabled,
            },
            "storage": {
                "local_ssd_per_node_gb": self.storage.local_ssd_per_node_gb,
                "shared_storage_type": self.storage.shared_storage_type.value,
                "shared_storage_total_gb": self.storage.shared_storage_total_gb,
                "oss_bucket_name": self.storage.oss_bucket_name,
                "oss_capacity_tb": self.storage.oss_capacity_tb,
            },
            "security": {
                "network_policy_default_action": self.security.network_policy_default_action,
                "rbac_enabled": self.security.rbac_enabled,
                "secret_encryption_enabled": self.security.secret_encryption_enabled,
                "image_scan_enabled": self.security.image_scan_enabled,
                "pod_security_standard": self.security.pod_security_standard,
                "audit_log_enabled": self.security.audit_log_enabled,
            },
            "nodes": [
                {
                    "role": n.role.value,
                    "count": n.count,
                    "cpu_cores": n.cpu_cores,
                    "memory_gb": n.memory_gb,
                    "gpu_type": n.gpu_type,
                    "gpu_count": n.gpu_count,
                    "storage_gb": n.storage_gb,
                    "labels": n.labels,
                    "taints": n.taints,
                }
                for n in self.nodes
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def save_to_file(self, output_path: Path) -> None:
        """
        将拓扑配置保存为Markdown文档。

        Args:
            output_path: 输出文件路径(.md后缀)

        Raises:
            IOError: 文件写入失败时抛出
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.to_markdown()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

    def validate_topology(self) -> tuple[bool, list[str]]:
        """
        验证拓扑配置的正确性。

        检查项包括:
        - 至少有1个Master节点
        - Pod网段不与Service网段重叠
        - GPU节点有正确的taint配置
        - 总资源满足最低要求

        Returns:
            tuple[bool, list[str]]: (是否通过验证, 错误/警告信息列表)
        """
        errors: list[str] = []
        warnings: list[str] = []

        masters = self.get_nodes_by_role(NodeRole.MASTER)
        if not masters or sum(m.count for m in masters) < 1:
            errors.append("至少需要1个Master节点")

        if self.cluster.master_count < 1:
            errors.append("master_count必须>=1")

        pod_parts = self.network.pod_cidr.split("/")
        svc_parts = self.network.service_cidr.split("/")
        if len(pod_parts) == 2 and len(svc_parts) == 2:
            if pod_parts[0].rsplit(".", 1)[0] == svc_parts[0].rsplit(".", 1)[0]:
                warnings.append(
                    f"Pod网段({self.network.pod_cidr})与Service网段({self.network.service_cidr})"
                    "前缀相同，可能存在路由冲突风险"
                )

        for n in self.nodes:
            if n.gpu_count > 0 and not any(
                "gpu" in t.lower() for t in n.taints
            ):
                warnings.append(
                    f"GPU节点({n.role.value}, gpu={n.gpu_type})未设置GPU专用taint，"
                    "可能导致非GPU工作负载调度到该节点"
                )

        if self.cluster.etcd_count % 2 == 0 and self.cluster.etcd_count > 1:
            warnings.append(
                f"etcd节点数为{self.cluster.etcd_count}(偶数)，"
                "建议使用奇数以避免脑裂风险"
            )

        is_valid = len(errors) == 0
        all_messages = errors + warnings
        return is_valid, all_messages
