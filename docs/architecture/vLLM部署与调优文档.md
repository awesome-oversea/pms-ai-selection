# vLLM部署与调优文档

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: AI推理服务部署文档
> **子任务**: D8-D9 - vLLM推理服务部署与性能优化
> **文档版本**: v1.0
>
> **更新说明（2026-04-19）**: 当前本地默认部署基线已切换为 `WSL + Ollama + Qwen2.5-1.5B (GGUF量化)`。本文保留为历史高配 / GPU 扩展路线参考，不再作为本地默认执行方案。

---

## 1. 概述

vLLM是系统的大语言模型推理引擎，部署Qwen2.5-72B-Instruct模型，为Multi-Agent系统提供高性能LLM推理能力。

| 项目 | 规格 |
|------|------|
| 模型 | Qwen2.5-72B-Instruct (~140GB) |
| 推理引擎 | vLLM v0.3.0 |
| 张量并行 | TP=4 (4张GPU分片) |
| 流水线并行 | PP=2 |
| GPU规格 | NVIDIA A100 80GB × 4 |
| API兼容 | OpenAI Compatible API |

---

## 2. 服务架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    vLLM推理服务                                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    API层                                 │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ OpenAI   │ │ 自定义API │ │ WebSocket │               │   │
│  │  │ 兼容API  │ │          │ │          │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    推理引擎                              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ PagedAtt │ │ Scheduler │ │ KV Cache │               │   │
│  │  │ ention   │ │          │ │ Manager  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    模型层                                │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │           Qwen2.5-72B-Instruct                    │  │   │
│  │  │           (TP=4, PP=2)                            │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**核心组件说明**:
- **PagedAttention**: vLLM核心技术，通过分页管理KV Cache减少GPU显存浪费
- **Scheduler**: 连续批处理调度器，动态合并并发请求提升吞吐
- **KV Cache Manager**: 管理注意力键值缓存的分配、回收与Prefix Caching

---

## 3. K8s Deployment部署配置

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: pms-ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm
  template:
    metadata:
      labels:
        app: vllm
    spec:
      nodeSelector:
        node-role.kubernetes.io/worker-gpu: ""
      containers:
        - name: vllm
          image: vllm/vllm-openai:v0.3.0
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: 4
          env:
            - name: MODEL_NAME
              value: "Qwen/Qwen2.5-72B-Instruct"
          command:
            - python
            - -m
            - vllm.entrypoints.openai.api_server
          args:
            - --model
            - /models/Qwen2.5-72B-Instruct
            - --tensor-parallel-size
            - "4"
            - --pipeline-parallel-size
            - "2"
            - --max-model-len
            - "8192"
            - --gpu-memory-utilization
            - "0.9"
            - --enable-prefix-caching
          volumeMounts:
            - name: model-storage
              mountPath: /models
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 300
            periodSeconds: 30
      volumes:
        - name: model-storage
          persistentVolumeClaim:
            claimName: model-pvc
```

---

## 4. 性能优化配置

### 4.1 推理参数配置

```python
vllm_config = {
    "model": "Qwen/Qwen2.5-72B-Instruct",
    "tensor_parallel_size": 4,        # 4张GPU张量并行
    "pipeline_parallel_size": 2,       # 2级流水线并行
    "max_model_len": 8192,            # 最大序列长度
    "gpu_memory_utilization": 0.9,     # GPU显存利用率90%
    "enable_prefix_caching": True,     # 开启前缀缓存(重复前缀复用)
    "enforce_eager": False,            # 使用CUDA Graph加速
    "max_num_batched_tokens": 32768,   # 最大批处理token数
    "max_num_seqs": 256,              # 最大并发序列数
    "swap_space": 4                    # CPU交换空间4GB
}
```

### 4.2 关键优化策略

| 优化项 | 配置 | 效果 |
|--------|------|------|
| Tensor Parallel | TP=4 | 72B模型分片到4张A100，单卡~35GB显存 |
| Pipeline Parallel | PP=2 | 流水线并行进一步提升吞吐 |
| Prefix Caching | enabled | 相同前缀请求第二次更快 |
| Dynamic Batching | max_num_seqs=256 | 动态合并并发请求 |
| PagedAttention | 默认开启 | KV Cache分页管理减少浪费 |
| CUDA Graph | enforce_eager=False | 静态图加速推理 |

---

## 5. 性能基准测试

### 5.1 测试命令

```bash
# 启动vLLM后执行基准测试
python benchmark_serving.py \
  --backend vllm \
  --model Qwen/Qwen2.5-72B-Instruct \
  --dataset-name sharegpt \
  --num-prompts 1000 \
  --request-rate 10
```

### 5.2 性能目标

| 指标 | 目标值 | 测试条件 |
|------|--------|---------|
| P50延迟 | <1s | 100次请求, input=500tokens |
| P99延迟 | <3s | 100次请求, output=200tokens |
| 吞吐量 | >30 tokens/s | TP=4, batch=1 |
| GPU利用率 | >70% | 持续负载 |

---

## 6. 验收检查清单

| 检查项 | 预期结果 | 状态 |
|--------|---------|------|
| vLLM容器运行 | 无OOMKilled, RestartCount=0 | ☐ |
| 模型加载完成 | 日志显示"Model loaded." | ☐ |
| TP=4生效 | nvidia-smi显示4张GPU均~35GB显存 | ☐ |
| PP=2生效 | pipeline_parallel_size=2配置确认 | ☐ |
| /v1/models API | 返回模型列表 | ☐ |
| Chat Completion | 推理请求返回正常文本 | ☐ |
| Prefix Caching | 重复前缀请求第二次更快 | ☐ |
| P99延迟<3s | 100次请求统计P99<3000ms | ☐ |
| 吞吐量>30 tok/s | TP=4, batch=1 | ☐ |

---

**文档状态**: ✅ 已完成
