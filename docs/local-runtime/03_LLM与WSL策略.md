# LLM与WSL策略

> 当前本地 AI 基线只保留一条主路径：WSL2 + Docker Compose 启动 Ollama，本地 CPU 模型由宿主机 backend Python 进程加载。

## 1. 当前推荐策略

当前仓库本地运行按下面的边界收口：

1. Windows 宿主管理代码、Python、前端和 Docker Desktop
2. WSL2 + Docker Compose 承载本地依赖栈
3. 文本对话与多模态默认使用 Compose 方式启动的 Ollama
4. `bge-reranker-base` 与 `Whisper tiny` 作为宿主机 backend 进程内 CPU 模型运行
5. vLLM / Triton 仅作为兼容扩展路线，不是当前默认前提

对应配置中心：

- `D:/Project/fms/.env.example`
- `D:/Project/fms/docker-compose.local-llm.yml`
- `D:/Project/fms/scripts/start_local_services.py`
- `D:/Project/fms/scripts/local_runtime_manager.py`

## 2. Ollama 当前标准入口

标准启动命令：

```bash
python D:/Project/fms/scripts/start_local_services.py --with-ollama
```

对应 Compose 文件：

- `D:/Project/fms/docker-compose.local-llm.yml`

当前约定：

- 宿主机访问 Ollama：`http://localhost:11434`
- 显式启用 `app` 镜像模式时，容器内访问 Ollama：`http://ollama:11434`
- Ollama 挂到共享网络 `pms-network`
- Ollama 模型目录默认持久化到 `D:/aitools/fms/ollama`
- CPU 模型缓存默认持久化到 `D:/aitools/fms/model-cache`

这意味着：

- 日常开发不再依赖宿主机手工安装 Ollama
- 宿主机 backend 直接使用 `LLM_OLLAMA_ENDPOINT=http://localhost:11434`
- 只有显式启用 `app` 镜像模式时，才使用 `DOCKER_APP_LLM_OLLAMA_ENDPOINT=http://ollama:11434`
- 重建容器不会丢失已下载模型，除非主动删除 `D:\aitools` 下对应目录
- 本地重资源默认不再落到 `C:`

## 3. 本地模型基线

当前 `.env.example` 中的本地模型基线为：

```env
LLM_PRIMARY_MODEL=qwen2.5:1.5b-instruct
LLM_OLLAMA_ENDPOINT=http://localhost:11434
DOCKER_APP_LLM_OLLAMA_ENDPOINT=http://ollama:11434
LLM_MULTIMODAL_MODEL=qwen3.5:2b
LLM_RERANK_MODEL=bge-reranker-base
LLM_SPEECH_MODEL=whisper-tiny
```

说明：

- `Qwen2.5-1.5B` 走 Ollama 文本模型链路
- `Qwen3.5-2B` 走 Ollama 多模态链路，仓内落地模型名为 `qwen3.5:2b`
- `bge-reranker-base` 与 `Whisper tiny` 由宿主机 backend Python 运行时加载，不再单独拆分服务
- `LLM_OLLAMA_ENDPOINT` 面向宿主机 / WSL 直连调试
- `DOCKER_APP_LLM_OLLAMA_ENDPOINT` 只给显式启用的 `app` 镜像模式使用
- `LLM_VLLM_ENDPOINT` 和 `LLM_TRITON_ENDPOINT` 仍保留，但不是当前本地主链路

## 4. WSL2 基础要求

建议至少满足：

- WSL2 已安装，发行版为 `Ubuntu-22.04`
- Docker Desktop 已启用 WSL2 backend
- Docker Desktop 已对目标 Ubuntu 发行版开启 WSL integration

最小检查命令：

```bash
rtk wsl --status
rtk docker --version
rtk docker compose version
```

对应自动检查脚本：

```bash
python D:/Project/fms/scripts/install_local_software.py
```

## 5. 推荐验证方式

### 5.1 启动本地 Ollama 栈

```bash
python D:/Project/fms/scripts/start_local_services.py --with-ollama
```

当前入口会额外做三件事：

- 启动 `docker-compose.local-llm.yml` 里的 Ollama 服务
- 拉取缺失的 Ollama 模型：`qwen2.5:1.5b-instruct`、`qwen3.5:2b`
- 预加载 CPU 模型缓存：`bge-reranker-base`、`whisper-tiny`

对应宿主机目录：

- `LOCAL_OLLAMA_DATA_DIR=D:/aitools/fms/ollama`
- `LOCAL_MODEL_CACHE_DIR=D:/aitools/fms/model-cache`

### 5.2 看运行状态

```bash
rtk python D:/Project/fms/scripts/local_runtime_manager.py check --probes
```

### 5.3 做 warmup / benchmark

```bash
rtk python D:/Project/fms/scripts/tmp_ollama_warmup.py
```

应用层联调入口：

- `POST /api/v1/llm/ollama/benchmark`

仓内已有相关实现：

- 状态服务：`src/services/ollama_status_service.py`
- API 入口：`src/api/v1/endpoints/llm.py`
- 回归用例：`tests/test_api_integration.py::test_ollama_benchmark_endpoint`

## 6. 服务模式建议

本地默认：

```env
LOCAL_RUNTIME_SCENARIO_MODE=local-real
SERVICE_MODE_LLM_MODE=in-process
SERVICE_MODE_ENABLE_FALLBACK=true
```

需要远端服务时：

```env
LOCAL_RUNTIME_SCENARIO_MODE=remote-service
SERVICE_MODE_LLM_MODE=remote-service
LLM_API_KEY=...
LLM_API_MODEL_NAME=...
```

## 7. 当前边界

- 仓库不再把“Windows 本机手工安装 Ollama”作为默认实施方案
- 如果你机器上已经装过宿主机 Ollama，可以手工停掉或卸载，但仓库不再依赖它
- 如果为了 GPU 驱动、显存调优、极致吞吐而坚持使用宿主机 / 原生部署，那属于显式自定义路线，不是当前标准本地方案

## 8. 常见误区

### 8.1 不要让容器继续使用 `localhost:11434`

`localhost` 在容器内指向容器自己，不指向宿主机，也不指向另一个 Compose 服务。当前标准做法是让容器走 `http://ollama:11434`。

### 8.2 不要同时保留多套 Ollama 入口

最容易出问题的情况就是：

- 宿主机起一个 Ollama
- WSL 或容器里再起一个 Ollama
- 最后谁在响应 `11434` 变得不清楚

当前建议是只保留 Compose 这一套本地标准入口。

### 8.3 Compose 化是当前更合理的本地做法

原因很直接：

- 与 Kafka、Kong、OpenSearch、Neo4j 等本地依赖的启动方式一致
- 便于统一入口、统一网络、统一持久化卷、统一清理
- 更容易避免“机器上装过什么”带来的隐性差异
- 文本/多模态与 CPU 模型缓存都能被验收脚本和 `D:\aitools` 下的绑定挂载目录收口，不再依赖人工下载

## 9. `D:\aitools` 边界说明

- 当前仓库已经把 Ollama 模型与 CPU 模型缓存切到 `D:\aitools`。
- Docker 镜像层本身仍由 Docker Desktop 管理；如果你要求镜像层也不落在 `C:`，请把 Docker Desktop 磁盘镜像迁移到 `D:\aitools`。
- WSL 发行版磁盘同理；如果你要求 WSL 也不占用 `C:`，请把目标发行版导入或迁移到 `D:\aitools`。

只有在你明确追求宿主机 GPU 专项调优时，原生安装才更值得单独维护。
