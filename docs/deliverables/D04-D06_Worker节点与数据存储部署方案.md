# Worker节点与数据存储部署方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D4-D6 Worker节点与数据存储
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. Worker节点部署](#2-worker节点部署)
- [3. GPU节点配置](#3-gpu节点配置)
- [4. PostgreSQL集群部署](#4-postgresql集群部署)
- [5. Redis集群部署](#5-redis集群部署)
- [6. 存储配置](#6-存储配置)

---

## 1. 概述

### 1.1 部署目标

完成K8s Worker节点、GPU节点、数据库和缓存的部署，为系统提供计算和存储能力。

### 1.2 资源规划

| 资源类型 | 数量 | 规格 | 用途 |
|---------|------|------|------|
| 应用Worker | 3 | 8核16G | API/Agent服务 |
| GPU Worker | 2 | 8核32G + A10 | LLM推理 |
| PostgreSQL | 3 | 4核16G + 500G SSD | 主数据库 |
| Redis | 6 | 4核8G | 缓存集群 |

---

## 2. Worker节点部署

### 2.1 应用Worker节点

```yaml
apiVersion: v1
kind: Node
metadata:
  name: worker-app-01
  labels:
    node-role.kubernetes.io/worker-app: ""
    node-type: application
spec:
  taints: []
```

**部署步骤**:

```bash
# 1. 准备节点环境
sudo apt-get update
sudo apt-get install -y containerd kubelet kubeadm kubectl

# 2. 配置containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml
sudo systemctl restart containerd

# 3. 加入集群
sudo kubeadm join <control-plane-endpoint>:6443 \
  --token <token> \
  --discovery-token-ca-cert-hash sha256:<hash>

# 4. 打标签
kubectl label node worker-app-01 node-role.kubernetes.io/worker-app=""
kubectl label node worker-app-01 node-type=application
```

### 2.2 节点验证

```bash
# 检查节点状态
kubectl get nodes -l node-role.kubernetes.io/worker-app

# 输出示例
NAME            STATUS   ROLES           AGE   VERSION
worker-app-01   Ready    worker-app      1h    v1.28.0
worker-app-02   Ready    worker-app      1h    v1.28.0
worker-app-03   Ready    worker-app      1h    v1.28.0
```

---

## 3. GPU节点配置

### 3.1 NVIDIA驱动安装

```bash
# 安装NVIDIA驱动
sudo apt-get install -y nvidia-driver-535

# 验证安装
nvidia-smi

# 输出示例
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.104.05   Driver Version: 535.104.05   CUDA Version: 12.2     |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA A10          Off  | 00000000:00:1E.0 Off |                    0 |
|  0%   25C    P8    15W / 150W |      0MiB / 23028MiB |      0%      Default |
+-------------------------------+----------------------+----------------------+
```

### 3.2 NVIDIA Device Plugin

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-device-plugin-daemonset
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: nvidia-device-plugin-ds
  template:
    metadata:
      labels:
        name: nvidia-device-plugin-ds
    spec:
      nodeSelector:
        node-role.kubernetes.io/worker-gpu: ""
      containers:
        - name: nvidia-device-plugin-ctr
          image: nvcr.io/nvidia/k8s-device-plugin:v0.14.0
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: device-plugin
              mountPath: /var/lib/kubelet/device-plugins
      volumes:
        - name: device-plugin
          hostPath:
            path: /var/lib/kubelet/device-plugins
```

### 3.3 MIG配置

```bash
# 启用MIG模式
sudo nvidia-smi -i 0 -mig 1

# 创建MIG实例
sudo nvidia-smi mig -cgi 1g.10gb,1g.10gb,1g.10gb,1g.10gb -C

# 验证MIG实例
nvidia-smi -L
```

### 3.4 GPU节点标签

```bash
# 打GPU标签
kubectl label node gpu-worker-01 node-role.kubernetes.io/worker-gpu=""
kubectl label node gpu-worker-01 nvidia.com/gpu.present=true

# 验证GPU资源
kubectl describe node gpu-worker-01 | grep -A 10 "Allocatable"
```

---

## 4. PostgreSQL集群部署

### 4.1 集群架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    PostgreSQL集群架构                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    PgBouncer连接池                        │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 读写入口  │ │ 只读入口  │ │ 管理入口  │               │   │
│  │  │ :5432    │ │ :5433    │ │ :5434    │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    PostgreSQL实例                         │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Primary  │ │ Replica1 │ │ Replica2 │               │   │
│  │  │ (读写)   │ │ (只读)   │ │ (只读)   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Primary节点配置

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres-primary
  namespace: pms-data
spec:
  serviceName: postgres-primary
  replicas: 1
  selector:
    matchLabels:
      app: postgres
      role: primary
  template:
    metadata:
      labels:
        app: postgres
        role: primary
    spec:
      containers:
        - name: postgres
          image: postgres:15.4
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: username
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: password
            - name: POSTGRES_DB
              value: fms
          args:
            - "-c"
            - "wal_level=replica"
            - "-c"
            - "max_wal_senders=10"
            - "-c"
            - "max_replication_slots=10"
          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: postgres-data
          persistentVolumeClaim:
            claimName: postgres-primary-pvc
```

### 4.3 Replica节点配置

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres-replica
  namespace: pms-data
spec:
  serviceName: postgres-replica
  replicas: 2
  selector:
    matchLabels:
      app: postgres
      role: replica
  template:
    metadata:
      labels:
        app: postgres
        role: replica
    spec:
      containers:
        - name: postgres
          image: postgres:15.4
          ports:
            - containerPort: 5432
          env:
            - name: PGUSER
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: username
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: password
            - name: PRIMARY_HOST
              value: postgres-primary-0.postgres-primary.fms-data.svc.cluster.local
          command:
            - /bin/bash
            - -c
            - |
              until pg_basebackup -h $PRIMARY_HOST -D /var/lib/postgresql/data -U replicator -Fp -Xs -P -R; do
                echo "Waiting for primary..."
                sleep 5
              done
              exec postgres -c hot_standby=on
          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: postgres-data
          persistentVolumeClaim:
            claimName: postgres-replica-pvc
```

### 4.4 PgBouncer配置

```ini
[databases]
fms = host=postgres-primary port=5432 dbname=fms
fms_readonly = host=postgres-replica port=5432 dbname=fms

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 5432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
min_pool_size = 5
reserve_pool_size = 5
```

---

## 5. Redis集群部署

### 5.1 集群架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Redis Sentinel架构                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Sentinel集群                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │Sentinel-1│ │Sentinel-2│ │Sentinel-3│               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Redis实例                             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Master-1 │ │ Master-2 │ │ Master-3 │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Slave-1  │ │ Slave-2  │ │ Slave-3  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Redis Master配置

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-master
  namespace: pms-data
spec:
  serviceName: redis-master
  replicas: 3
  selector:
    matchLabels:
      app: redis
      role: master
  template:
    metadata:
      labels:
        app: redis
        role: master
    spec:
      containers:
        - name: redis
          image: redis:7.2
          ports:
            - containerPort: 6379
            - containerPort: 16379
          command:
            - redis-server
            - --cluster-enabled yes
            - --cluster-config-file nodes.conf
            - --cluster-node-timeout 5000
            - --appendonly yes
            - --maxmemory 4gb
            - --maxmemory-policy allkeys-lru
          volumeMounts:
            - name: redis-data
              mountPath: /data
      volumes:
        - name: redis-data
          persistentVolumeClaim:
            claimName: redis-data-pvc
```

### 5.3 Sentinel配置

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-sentinel
  namespace: pms-data
spec:
  replicas: 3
  selector:
    matchLabels:
      app: redis-sentinel
  template:
    metadata:
      labels:
        app: redis-sentinel
    spec:
      containers:
        - name: sentinel
          image: redis:7.2
          ports:
            - containerPort: 26379
          command:
            - redis-sentinel
            - /etc/redis/sentinel.conf
          volumeMounts:
            - name: sentinel-config
              mountPath: /etc/redis
      volumes:
        - name: sentinel-config
          configMap:
            name: sentinel-config
```

```ini
# sentinel.conf
sentinel monitor mymaster redis-master-0.redis-master 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 60000
sentinel parallel-syncs mymaster 1
```

---

## 6. 存储配置

### 6.1 StorageClass定义

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-ssd
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
---
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: standard-ssd
provisioner: kubernetes.io/gce-pd
parameters:
  type: pd-ssd
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
```

### 6.2 PVC配置

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-primary-pvc
  namespace: pms-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard-ssd
  resources:
    requests:
      storage: 500Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-data-pvc
  namespace: pms-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-ssd
  resources:
    requests:
      storage: 100Gi
```

### 6.3 性能验证

```bash
# PostgreSQL性能测试
pgbench -h postgres-primary -U fms -c 100 -j 4 -T 60 fms

# Redis性能测试
redis-benchmark -h redis-master -p 6379 -t set,get -n 100000 -c 50
```

---

## 附录

### A. 验收检查清单

```markdown
## D4-D6 验收检查清单

### Worker节点
- [ ] 3个应用Worker节点Ready
- [ ] 2个GPU Worker节点Ready
- [ ] nvidia-smi可用
- [ ] GPU资源可调度

### PostgreSQL
- [ ] Primary节点运行正常
- [ ] 2个Replica节点同步正常
- [ ] 流复制延迟<1s
- [ ] PgBouncer连接池可用

### Redis
- [ ] 3个Master节点运行
- [ ] 3个Slave节点同步
- [ ] Sentinel监控正常
- [ ] 故障切换测试通过

### 存储
- [ ] StorageClass创建成功
- [ ] PVC绑定成功
- [ ] IOPS性能达标
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
