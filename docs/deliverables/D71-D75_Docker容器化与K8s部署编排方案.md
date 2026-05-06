# Docker容器化与K8s部署编排方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D71-D75 Docker容器化与K8s部署编排
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. Docker镜像设计](#2-docker镜像设计)
- [3. Kubernetes部署设计](#3-kubernetes部署设计)
- [4. 配置管理](#4-配置管理)
- [5. 服务网格配置](#5-服务网格配置)
- [6. 部署流水线](#6-部署流水线)
- [7. 运维手册](#7-运维手册)

---

## 1. 概述

### 1.1 容器化目标

实现AI选品系统的容器化部署，支持弹性伸缩、滚动更新和高可用运行。

### 1.2 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Docker | 24.0+ | 容器运行时 |
| Kubernetes | 1.28+ | 容器编排 |
| Helm | 3.12+ | 包管理 |
| Istio | 1.19+ | 服务网格 |
| Harbor | 2.9+ | 镜像仓库 |

---

## 2. Docker镜像设计

### 2.1 镜像分层设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application Layer                        │
│  - 应用代码                                                      │
│  - 配置文件                                                      │
│  - 启动脚本                                                      │
├─────────────────────────────────────────────────────────────────┤
│                        Runtime Layer                            │
│  - Python 3.11                                                  │
│  - uvicorn/gunicorn                                             │
│  - 依赖包                                                        │
├─────────────────────────────────────────────────────────────────┤
│                        Base Layer                               │
│  - Ubuntu 22.04                                                 │
│  - 系统工具                                                      │
│  - 安全补丁                                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Dockerfile设计

#### API服务镜像

```dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY src/ ./src/
COPY config/ ./config/
COPY scripts/entrypoint.sh .

RUN chmod +x scripts/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Agent服务镜像

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements-agent.txt .
RUN pip install --no-cache-dir -r requirements-agent.txt

COPY src/agents/ ./agents/
COPY src/core/ ./core/
COPY config/ ./config/

ENV AGENT_TYPE=generic
ENV LOG_LEVEL=INFO

CMD ["python", "-m", "agents.main"]
```

#### LLM服务镜像

```dockerfile
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-llm.txt .
RUN pip3 install --no-cache-dir -r requirements-llm.txt

COPY src/llm/ ./llm/
COPY models/ ./models/

ENV MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
ENV MAX_MODEL_LEN=8192

EXPOSE 8000

CMD ["python3", "-m", "llm.server"]
```

### 2.3 镜像构建策略

```yaml
docker:
  registry: "harbor.fms.example.com/fms"
  
  images:
    api:
      dockerfile: "Dockerfile.api"
      context: "."
      tags:
        - "${VERSION}"
        - "latest"
    
    agent:
      dockerfile: "Dockerfile.agent"
      context: "."
      tags:
        - "${VERSION}"
        - "latest"
    
    llm:
      dockerfile: "Dockerfile.llm"
      context: "."
      tags:
        - "${VERSION}"
        - "latest"
  
  build_args:
    - "BUILD_DATE=${BUILD_DATE}"
    - "VERSION=${VERSION}"
    - "GIT_COMMIT=${GIT_COMMIT}"
```

---

## 3. Kubernetes部署设计

### 3.1 Namespace规划

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: fms-production
  labels:
    name: fms-production
    environment: production
---
apiVersion: v1
kind: Namespace
metadata:
  name: fms-staging
  labels:
    name: fms-staging
    environment: staging
```

### 3.2 Deployment配置

#### API服务部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pms-api
  namespace: pms-production
  labels:
    app: pms-api
    version: v1
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pms-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: pms-api
        version: v1
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
    spec:
      serviceAccountName: pms-api
      containers:
        - name: api
          image: harbor.fms.example.com/fms/api:v1.0.0
          ports:
            - containerPort: 8000
              name: http
          env:
            - name: ENVIRONMENT
              value: "production"
            - name: LOG_LEVEL
              value: "INFO"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: fms-db-secret
                  key: url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: pms-redis-secret
                  key: url
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2000m"
              memory: "4Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - name: config
              mountPath: /app/config
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: pms-api-config
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: pms-api
                topologyKey: kubernetes.io/hostname
```

#### Agent服务部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pms-agent
  namespace: pms-production
spec:
  replicas: 5
  selector:
    matchLabels:
      app: pms-agent
  template:
    metadata:
      labels:
        app: pms-agent
    spec:
      containers:
        - name: agent
          image: harbor.fms.example.com/fms/agent:v1.0.0
          env:
            - name: AGENT_TYPE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.labels['agent-type']
            - name: KAFKA_BROKERS
              value: "kafka-0.kafka:9092,kafka-1.kafka:9092,kafka-2.kafka:9092"
          resources:
            requests:
              cpu: "1000m"
              memory: "2Gi"
            limits:
              cpu: "4000m"
              memory: "8Gi"
```

#### LLM服务部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pms-llm
  namespace: pms-production
spec:
  replicas: 2
  selector:
    matchLabels:
      app: pms-llm
  template:
    metadata:
      labels:
        app: pms-llm
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      containers:
        - name: llm
          image: harbor.fms.example.com/fms/llm:v1.0.0
          ports:
            - containerPort: 8000
          resources:
            requests:
              nvidia.com/gpu: 1
              memory: "64Gi"
            limits:
              nvidia.com/gpu: 1
              memory: "128Gi"
          volumeMounts:
            - name: model-cache
              mountPath: /app/models
      volumes:
        - name: model-cache
          persistentVolumeClaim:
            claimName: llm-model-cache
```

### 3.3 Service配置

```yaml
apiVersion: v1
kind: Service
metadata:
  name: pms-api
  namespace: pms-production
spec:
  type: ClusterIP
  selector:
    app: pms-api
  ports:
    - port: 80
      targetPort: 8000
      name: http
---
apiVersion: v1
kind: Service
metadata:
  name: pms-llm
  namespace: pms-production
spec:
  type: ClusterIP
  selector:
    app: pms-llm
  ports:
    - port: 80
      targetPort: 8000
      name: http
```

### 3.4 Ingress配置

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fms-ingress
  namespace: pms-production
  annotations:
    kubernetes.io/ingress.class: "nginx"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  tls:
    - hosts:
        - api.fms.example.com
      secretName: fms-tls-secret
  rules:
    - host: api.fms.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: pms-api
                port:
                  number: 80
```

---

## 4. 配置管理

### 4.1 ConfigMap设计

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pms-api-config
  namespace: pms-production
data:
  app.yaml: |
    server:
      host: "0.0.0.0"
      port: 8000
      workers: 4
    
    database:
      pool_size: 20
      max_overflow: 10
    
    redis:
      max_connections: 100
    
    kafka:
      bootstrap_servers: "kafka-0.kafka:9092,kafka-1.kafka:9092,kafka-2.kafka:9092"
      consumer_group: "pms-api"
    
    logging:
      level: "INFO"
      format: "json"
```

### 4.2 Secret管理

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: fms-db-secret
  namespace: pms-production
type: Opaque
stringData:
  url: "postgresql+asyncpg://pms:password@postgres.fms-data:5432/fms"
  username: "fms"
  password: "<encrypted>"
---
apiVersion: v1
kind: Secret
metadata:
  name: pms-redis-secret
  namespace: pms-production
type: Opaque
stringData:
  url: "redis://:password@redis.fms-data:6379/0"
  password: "<encrypted>"
```

---

## 5. 服务网格配置

### 5.1 Istio配置

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: pms-api
  namespace: pms-production
spec:
  hosts:
    - pms-api
  http:
    - route:
        - destination:
            host: pms-api
            subset: v1
          weight: 90
        - destination:
            host: pms-api
            subset: v2
          weight: 10
      retries:
        attempts: 3
        perTryTimeout: 10s
      timeout: 30s
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: pms-api
  namespace: pms-production
spec:
  host: pms-api
  subsets:
    - name: v1
      labels:
        version: v1
    - name: v2
      labels:
        version: v2
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        h2UpgradePolicy: UPGRADE
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
```

### 5.2 流量管理

```yaml
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: fms-gateway
  namespace: pms-production
spec:
  selector:
    istio: ingressgateway
  servers:
    - port:
        number: 443
        name: https
        protocol: HTTPS
      tls:
        mode: SIMPLE
        credentialName: fms-tls-secret
      hosts:
        - "*.fms.example.com"
```

---

## 6. 部署流水线

### 6.1 Helm Chart结构

```
helm/fms/
├── Chart.yaml
├── values.yaml
├── values-production.yaml
├── values-staging.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment-api.yaml
│   ├── deployment-agent.yaml
│   ├── deployment-llm.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── hpa.yaml
│   └── servicemonitor.yaml
└── charts/
    ├── postgresql/
    ├── redis/
    └── kafka/
```

### 6.2 Helm Values

```yaml
global:
  imageRegistry: "harbor.fms.example.com/fms"
  imagePullSecrets:
    - name: harbor-secret

api:
  replicaCount: 3
  image:
    repository: api
    tag: "v1.0.0"
    pullPolicy: Always
  
  resources:
    requests:
      cpu: "500m"
      memory: "1Gi"
    limits:
      cpu: "2000m"
      memory: "4Gi"
  
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70

agent:
  replicaCount: 5
  image:
    repository: agent
    tag: "v1.0.0"

llm:
  replicaCount: 2
  image:
    repository: llm
    tag: "v1.0.0"
  
  resources:
    limits:
      nvidia.com/gpu: 1
```

### 6.3 部署脚本

```bash
#!/bin/bash
set -e

VERSION=${1:-"v1.0.0"}
ENVIRONMENT=${2:-"production"}

echo "Deploying FMS version $VERSION to $ENVIRONMENT..."

helm upgrade --install fms ./helm/fms \
  --namespace fms-$ENVIRONMENT \
  --values ./helm/fms/values-$ENVIRONMENT.yaml \
  --set api.image.tag=$VERSION \
  --set agent.image.tag=$VERSION \
  --set llm.image.tag=$VERSION \
  --wait \
  --timeout 10m

echo "Deployment completed successfully!"
```

---

## 7. 运维手册

### 7.1 常用命令

```bash
kubectl get pods -n fms-production
kubectl logs -f deployment/pms-api -n fms-production
kubectl describe pod <pod-name> -n fms-production
kubectl exec -it <pod-name> -n fms-production -- /bin/bash

kubectl scale deployment pms-api --replicas=5 -n fms-production
kubectl rollout status deployment/pms-api -n fms-production
kubectl rollout undo deployment/pms-api -n fms-production

helm list -n fms-production
helm history fms -n fms-production
helm rollback fms 1 -n fms-production
```

### 7.2 故障排查

| 问题 | 排查步骤 |
|------|---------|
| Pod启动失败 | 检查镜像、资源限制、配置 |
| 服务无法访问 | 检查Service、Ingress配置 |
| 性能问题 | 检查资源使用、HPA配置 |
| 镜像拉取失败 | 检查镜像仓库、Secret配置 |

---

## 附录

### A. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
