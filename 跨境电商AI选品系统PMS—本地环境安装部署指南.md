# 本地环境安装部署指南

本主题已收口到 `D:/Project/fms/docs/local-runtime/`。
本地重资源统一规则也已收口到该目录：默认放在 `D:\aitools`，不要放在 `C:`。

优先阅读：

- `D:/Project/fms/docs/local-runtime/README.md`
- `D:/Project/fms/docs/local-runtime/01_统一入口与启动总览.md`
- `D:/Project/fms/docs/local-runtime/02_依赖栈与组件说明.md`
- `D:/Project/fms/docs/local-runtime/03_LLM与WSL策略.md`
- `D:/Project/fms/docs/local-runtime/04_验收、变更与排障.md`

当前唯一推荐的三段式入口：

1. `python D:/Project/fms/scripts/install_python_deps.py --run-check`
2. `python D:/Project/fms/scripts/install_local_software.py`
3. `python D:/Project/fms/scripts/start_local_services.py`

应用后端单独走本机 Python 进程，不再默认通过 `docker-compose.yml` 构建 `app` 镜像：

- Windows：`powershell -NoProfile -File D:/Project/fms/scripts/start_local.ps1`
- Linux / WSL：`bash D:/Project/fms/scripts/start_local.sh`
- 等价命令：`python D:/Project/fms/scripts/local_runtime_manager.py up --skip-deps`

Kafka 当前唯一标准入口：

```bash
python D:/Project/fms/scripts/start_local_services.py --with-kafka
```

不要再从 `docker-compose.yml` 启动 Kafka / Zookeeper / Kafka Connect / Debezium。

## 2026-04-23 本地网关补充说明

- 当前本地后端默认运行在宿主机 Python 进程 `18000`，Kong proxy 暴露 `8000`，Kong Admin 暴露 `8001`。
- `k8s/gateway/kong-services.yml` 的本地上游应保持为 `http://host.docker.internal:18000`，不要回退到旧的 `http://app:8000`。
- 网关配置校验入口：`python D:/Project/fms/scripts/validate_gateway_config.py`。
- 网关冒烟入口：`python D:/Project/fms/scripts/gateway_smoke_check.py`。若输出 `local_reboot_required_after_feature_enable` 或 Docker engine timeout，先重启本机 / Docker Desktop，再复验 Kong Admin 与 services drift。
- Docker engine 探测默认 5 秒超时，超时后会清理本次探测创建的子进程；如只想快速跑测试，可临时设置 `OPS_PROBE_DOCKER_TIMEOUT_SECONDS=0.5`。

## 2026-04-23 业务验收执行口径

- 若 Docker Desktop 中现有依赖容器已正常运行，业务功能验收应以现有容器服务为基线，不重复执行 `docker compose up/down`、不重建依赖栈、不把 Docker engine 探测作为业务验收前置条件。
- 业务验收优先运行业务脚本与业务回归，例如 `python D:/Project/fms/scripts/bootstrap_business_scenario_runtime.py`、`python D:/Project/fms/scripts/run_local_external_collection_readiness.py` 以及对应 `pytest` 用例；遇到具体业务链路报错时再定位并修复。
