# 本地运行文档

本目录是当前仓库唯一有效的本地运行入口说明。

当前本地运行只认下面三类脚本：

1. `python D:/Project/fms/scripts/install_python_deps.py --run-check`
2. `python D:/Project/fms/scripts/install_local_software.py`
3. `python D:/Project/fms/scripts/start_local_services.py`

当前约束：

- Docker Compose 只负责本地中间件与可选 Ollama / Kafka 栈。
- backend 默认通过宿主机 Python 进程启动，不再默认构建 `docker-compose.yml` 里的 `app` 服务。

## 重资源落盘规则

- 本地拉取型资源、软件缓存、模型文件默认统一放在 `D:\aitools`，不要再放到 `C:`。
- 当前仓库已经将 `LOCAL_OLLAMA_DATA_DIR` 与 `LOCAL_MODEL_CACHE_DIR` 收口到 `D:\aitools\fms\...`。
- 如果你要求 Docker 镜像层和 WSL VHD 也完全不落到 `C:`，需要额外把 Docker Desktop 磁盘镜像和 WSL 发行版迁移到 `D:\aitools`；Compose 只能控制绑定挂载，不能替你改 Docker Desktop 自身的数据盘位置。

废弃资源清理入口：

- `python D:/Project/fms/scripts/cleanup_local_runtime.py`
- `python D:/Project/fms/scripts/cleanup_local_runtime.py --apply`

本机 backend 启动入口：

- Windows: `powershell -NoProfile -File D:/Project/fms/scripts/start_local.ps1`
- Linux / WSL: `bash D:/Project/fms/scripts/start_local.sh`
- 等价命令：`python D:/Project/fms/scripts/local_runtime_manager.py up --skip-deps`

## Kafka 统一口径

Kafka 本地栈现在只保留一套：

- Compose 文件：`D:/Project/fms/docker-compose.local-kafka.yml`
- 标准入口：`python D:/Project/fms/scripts/start_local_services.py --with-kafka`
- 底层启动脚本：`python D:/Project/fms/scripts/bootstrap_local_kafka_debezium.py --startup-only`

这套栈包含：

- `zookeeper`
- `kafka`
- `kafka-init`
- `kafka-connect`
- `debezium-init`

关键约束：

- 不再从 `docker-compose.yml` 启动 Kafka / Zookeeper / Kafka Connect / Debezium。
- `app` 和其他业务容器继续按原语义使用 `kafka:29092`。
- `kafka-connect` 也继续可通过 `kafka-connect:8083` 访问。
- 这是通过共享网络 `pms-network` 上的别名完成的，业务配置不需要改。

## 文档导航

- [01_统一入口与启动总览](./01_统一入口与启动总览.md)
- [02_依赖栈与组件说明](./02_依赖栈与组件说明.md)
- [03_LLM与WSL策略](./03_LLM与WSL策略.md)
- [04_验收、变更与排障](./04_验收、变更与排障.md)
- 非本地环境规划见：`D:/Project/fms/docs/environments/README.md`
