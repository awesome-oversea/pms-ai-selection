"""
D4-D6 单元测试用例
==================

覆盖范围:
    1. 数据库连接管理 (database.py) - D5-T014 PostgreSQL主从集群
       - Base声明式基类
       - 数据库配置参数验证
       - 健康检查接口
       - 生命周期管理

    2. Redis连接管理 (redis.py) - D6-T022 Redis Sentinel集群
       - CacheService行为验证
       - 健康检查接口
       - 配置参数验证

    3. K8s部署配置验证
       - deployment.yml 结构
       - postgresql.yml 主从配置
       - redis.yml Sentinel配置
       - storage.yml StorageClass
       - gpu.yml NVIDIA Device Plugin

    4. Dockerfile/docker-compose验证
       - Dockerfile多阶段构建
       - docker-compose服务编排

验收标准对照:
    D4: Worker节点就绪 (kubectl get nodes Ready)
    D5: PG主从集群可读写，从节点延迟<1s
    D6: Redis Sentinel高可用，故障自动切换
"""

from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml


class TestDatabaseConnection:
    """
    数据库连接管理测试(D5-T014 PostgreSQL主从集群)。

    验证:
        - Base声明式基类
        - 数据库配置参数
        - 健康检查接口
    """

    def test_base_class_is_declarative_base(self):
        from sqlalchemy.orm import DeclarativeBase
        from src.infrastructure.database import Base

        assert issubclass(Base, DeclarativeBase)

    def test_database_settings_url_contains_asyncpg(self):
        from src.config.settings import get_settings

        settings = get_settings()
        assert "postgresql" in settings.database.url
        assert "asyncpg" in settings.database.url

    def test_database_pool_size_in_valid_range(self):
        from src.config.settings import get_settings

        settings = get_settings()
        assert 1 <= settings.database.pool_size <= 100
        assert 0 <= settings.database.max_overflow <= 50

    @pytest.mark.asyncio
    async def test_check_db_health_returns_dict_with_status(self):
        from src.infrastructure.database import check_db_health

        result = await check_db_health()

        assert isinstance(result, dict)
        assert "status" in result

    @pytest.mark.asyncio
    async def test_close_db_resets_engine_reference(self):
        from src.infrastructure.database import close_db

        await close_db()

        from src.infrastructure.database import _engine
        assert _engine is None


class TestApplicationLifespan:
    """应用生命周期行为测试: 验证启动/关闭流程"""

    @pytest.mark.asyncio
    async def test_lifespan_startup_initializes_dependencies(self, monkeypatch):
        from src.main import app as fastapi_app
        from src.main import lifespan

        init_db = AsyncMock()
        setup_tracing = MagicMock()

        monkeypatch.setattr("src.infrastructure.database.get_engine", lambda: object())
        monkeypatch.setattr("src.infrastructure.database.init_db", init_db)
        monkeypatch.setattr("src.infrastructure.redis.get_redis_connection", lambda: object())
        monkeypatch.setattr("src.infrastructure.qdrant.get_qdrant_client", lambda: object())
        monkeypatch.setattr("src.core.tracing.setup_tracing", setup_tracing)

        async with lifespan(fastapi_app):
            pass

        init_db.assert_awaited_once()
        setup_tracing.assert_called_once()
        args, kwargs = setup_tracing.call_args
        assert args[0] is fastapi_app
        assert kwargs["service_name"]
        assert kwargs["environment"]

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_releases_dependencies(self, monkeypatch):
        from src.main import app as fastapi_app
        from src.main import lifespan

        monkeypatch.setattr("src.infrastructure.database.get_engine", lambda: object())
        monkeypatch.setattr("src.infrastructure.database.init_db", AsyncMock())
        monkeypatch.setattr("src.infrastructure.redis.get_redis_connection", lambda: object())
        monkeypatch.setattr("src.infrastructure.qdrant.get_qdrant_client", lambda: object())
        monkeypatch.setattr("src.core.tracing.setup_tracing", MagicMock())

        close_db = AsyncMock()
        close_redis = AsyncMock()
        close_qdrant = AsyncMock()
        close_kafka = AsyncMock()
        monkeypatch.setattr("src.infrastructure.database.close_db", close_db)
        monkeypatch.setattr("src.infrastructure.redis.close_redis", close_redis)
        monkeypatch.setattr("src.infrastructure.qdrant.close_qdrant", close_qdrant)
        monkeypatch.setattr("src.infrastructure.kafka.close_kafka", close_kafka)

        async with lifespan(fastapi_app):
            pass

        close_db.assert_awaited_once()
        close_redis.assert_awaited_once()
        close_qdrant.assert_awaited_once()
        close_kafka.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_restart_is_idempotent(self, monkeypatch):
        from src.main import app as fastapi_app
        from src.main import lifespan

        init_db = AsyncMock()
        close_db = AsyncMock()
        close_redis = AsyncMock()
        close_qdrant = AsyncMock()
        close_kafka = AsyncMock()

        monkeypatch.setattr("src.infrastructure.database.get_engine", lambda: object())
        monkeypatch.setattr("src.infrastructure.database.init_db", init_db)
        monkeypatch.setattr("src.infrastructure.database.close_db", close_db)
        monkeypatch.setattr("src.infrastructure.redis.get_redis_connection", lambda: object())
        monkeypatch.setattr("src.infrastructure.redis.close_redis", close_redis)
        monkeypatch.setattr("src.infrastructure.qdrant.get_qdrant_client", lambda: object())
        monkeypatch.setattr("src.infrastructure.qdrant.close_qdrant", close_qdrant)
        monkeypatch.setattr("src.infrastructure.kafka.close_kafka", close_kafka)
        monkeypatch.setattr("src.core.tracing.setup_tracing", MagicMock())

        async with lifespan(fastapi_app):
            pass
        async with lifespan(fastapi_app):
            pass

        assert init_db.await_count == 2
        assert close_db.await_count == 2
        assert close_redis.await_count == 2
        assert close_qdrant.await_count == 2
        assert close_kafka.await_count == 2

    @pytest.mark.asyncio
    async def test_close_qdrant_resets_global(self, monkeypatch):
        import src.infrastructure.qdrant as qdrant_module

        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        monkeypatch.setattr(qdrant_module, "_qdrant_client", mock_client)

        await qdrant_module.close_qdrant()

        mock_client.close.assert_awaited_once()
        assert qdrant_module._qdrant_client is None


class TestRedisConnection:
    """
    Redis连接管理测试(D6-T022 Redis Sentinel集群)。

    验证:
        - 模块可导入性
        - CacheService行为
        - 健康检查接口
        - 配置参数
    """

    def test_redis_module_exports_required_symbols(self):
        from src.infrastructure.redis import (
            check_redis_health,
            get_redis_connection,
        )
        assert callable(get_redis_connection)
        assert callable(check_redis_health)

    def test_redis_settings_url_format(self):
        from src.config.settings import get_settings

        settings = get_settings()
        assert "redis://" in settings.redis.url

    def test_redis_settings_pool_size_in_range(self):
        from src.config.settings import get_settings

        settings = get_settings()
        assert 1 <= settings.redis.max_connections <= 200

    @pytest.mark.asyncio
    async def test_cache_service_delegates_to_redis(self):
        from src.infrastructure.redis import CacheService

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=b'"cached_value"')
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        mock_redis.ttl = AsyncMock(return_value=300)
        mock_redis.incrby = AsyncMock(return_value=5)
        mock_redis.aclose = AsyncMock()

        service = CacheService(mock_redis)

        assert await service.get("key") is not None
        assert await service.set("key", "val") is True
        assert await service.delete("key") == 1
        assert await service.exists("key") == 1
        assert await service.expire("key", 60) is True
        assert await service.ttl("key") == 300
        assert await service.increment("counter") == 5

    @pytest.mark.asyncio
    async def test_cache_service_hash_operations(self):
        from src.infrastructure.redis import CacheService

        mock_redis = MagicMock()
        mock_redis.hget = AsyncMock(return_value="field_val")
        mock_redis.hset = AsyncMock(return_value=True)
        mock_redis.hgetall = AsyncMock(return_value={"k": "v"})
        mock_redis.aclose = AsyncMock()

        service = CacheService(mock_redis)

        assert await service.hget("h", "k") == "field_val"
        assert await service.hset("h", "k", "v") is True
        assert await service.hgetall("h") == {"k": "v"}

    @pytest.mark.asyncio
    async def test_cache_service_list_operations(self):
        from src.infrastructure.redis import CacheService

        mock_redis = MagicMock()
        mock_redis.lpush = AsyncMock(return_value=2)
        mock_redis.lrange = AsyncMock(return_value=["a", "b"])
        mock_redis.aclose = AsyncMock()

        service = CacheService(mock_redis)

        assert await service.lpush("list", "a", "b") == 2
        assert await service.lrange("list", 0, -1) == ["a", "b"]

    @pytest.mark.asyncio
    async def test_check_redis_health_returns_dict_with_status(self):
        from src.infrastructure.redis import check_redis_health

        result = await check_redis_health()

        assert isinstance(result, dict)
        assert "status" in result

    @pytest.mark.asyncio
    async def test_close_redis_resets_global(self):
        from src.infrastructure.redis import close_redis

        await close_redis()

        from src.infrastructure.redis import _redis_client
        assert _redis_client is None


class TestK8sDeploymentConfig:
    """
    K8s部署配置验证(D4/D5/D6基础设施)。

    验证:
        - deployment.yml 应用Deployment结构
        - postgresql.yml PG主从StatefulSet
        - redis.yml Sentinel集群配置
        - storage.yml SSD存储类
        - gpu.yml NVIDIA Device Plugin
    """

    def _load_yaml(self, filename):
        filepath = f"D:/Project/fms/k8s/{filename}"
        with open(filepath, encoding="utf-8") as f:
            return list(yaml.safe_load_all(f))

    def test_deployment_has_namespace(self):
        docs = self._load_yaml("deployment.yml")
        ns_doc = next(d for d in docs if d and d.get("kind") == "Namespace")
        assert ns_doc["metadata"]["name"] == "pms-system"

    def test_deployment_has_configmap(self):
        docs = self._load_yaml("deployment.yml")
        cm_docs = [d for d in docs if d and d.get("kind") == "ConfigMap"]
        assert len(cm_docs) >= 1
        data = cm_docs[0]["data"]
        assert "APP_ENVIRONMENT" in data
        assert "DB_URL" in data
        assert "REDIS_URL" in data

    def test_deployment_has_secret(self):
        docs = self._load_yaml("deployment.yml")
        secret_docs = [d for d in docs if d and d.get("kind") == "Secret"]
        assert len(secret_docs) >= 1
        assert secret_docs[0]["type"] == "Opaque"

    def test_deployment_replicas_and_resources(self):
        docs = self._load_yaml("deployment.yml")
        dep = next(d for d in docs if d and d.get("kind") == "Deployment")
        spec = dep["spec"]["template"]["spec"]["containers"][0]
        assert dep["spec"]["replicas"] == 3
        assert "resources" in spec
        assert "requests" in spec["resources"]
        assert "limits" in spec["resources"]

    def test_deployment_has_liveness_probe(self):
        docs = self._load_yaml("deployment.yml")
        dep = next(d for d in docs if d and d.get("kind") == "Deployment")
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        assert container["livenessProbe"]["httpGet"]["path"] == "/live"

    def test_deployment_has_readiness_probe(self):
        docs = self._load_yaml("deployment.yml")
        dep = next(d for d in docs if d and d.get("kind") == "Deployment")
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "readinessProbe" in container
        assert container["readinessProbe"]["httpGet"]["path"] == "/ready"

    def test_deployment_has_service_account(self):
        docs = self._load_yaml("deployment.yml")
        dep = next(d for d in docs if d and d.get("kind") == "Deployment")
        assert dep["spec"]["template"]["spec"]["serviceAccountName"] == "pms-app-sa"

    def test_deployment_has_hpa(self):
        docs = self._load_yaml("deployment.yml")
        hpa = next((d for d in docs if d and d.get("kind") == "HorizontalPodAutoscaler"), None)
        assert hpa is not None
        assert hpa["spec"]["minReplicas"] == 3
        assert hpa["spec"]["maxReplicas"] == 20

    def test_deployment_has_ingress(self):
        docs = self._load_yaml("deployment.yml")
        ingress = next((d for d in docs if d and d.get("kind") == "Ingress"), None)
        assert ingress is not None
        assert "tls" in ingress["spec"]

    def test_postgresql_primary_statefulset(self):
        docs = self._load_yaml("postgresql.yml")
        primary = next(
            (d for d in docs if d and d.get("metadata", {}).get("name") == "pms-pg-primary"),
            None,
        )
        assert primary is not None
        assert primary["kind"] == "StatefulSet"
        assert primary["spec"]["replicas"] == 1
        assert "volumeClaimTemplates" in primary["spec"]

    def test_postgresql_replica_count(self):
        docs = self._load_yaml("postgresql.yml")
        replica = next(
            (d for d in docs if d and d.get("metadata", {}).get("name") == "pms-pg-replica"),
            None,
        )
        assert replica is not None
        assert replica["spec"]["replicas"] == 2

    def test_postgresql_pgbouncer_deployment(self):
        docs = self._load_yaml("postgresql.yml")
        pgbouncer = next(
            (d for d in docs if d and d.get("metadata", {}).get("name") == "pms-pgbouncer"),
            None,
        )
        assert pgbouncer is not None
        assert pgbouncer["kind"] == "Deployment"
        container = pgbouncer["spec"]["template"]["spec"]["containers"][0]
        assert container["ports"][0]["containerPort"] == 6432

    def test_postgresql_services(self):
        docs = self._load_yaml("postgresql.yml")
        services = [d for d in docs if d and d.get("kind") == "Service"]
        svc_names = {s["metadata"]["name"] for s in services}
        assert "pms-pg-primary-svc" in svc_names
        assert "pms-pg-replica-svc" in svc_names

    def test_redis_master_statefulset(self):
        docs = self._load_yaml("redis.yml")
        master = next(
            (d for d in docs if d and d.get("metadata", {}).get("name") == "pms-redis-master"),
            None,
        )
        assert master is not None
        assert master["kind"] == "StatefulSet"
        assert "volumeClaimTemplates" in master["spec"]

    def test_redis_slave_replicas(self):
        docs = self._load_yaml("redis.yml")
        slave = next(
            (d for d in docs if d and d.get("metadata", {}).get("name") == "pms-redis-slave"),
            None,
        )
        assert slave is not None
        assert slave["spec"]["replicas"] == 2

    def test_redis_sentinel_deployment(self):
        docs = self._load_yaml("redis.yml")
        sentinel = next(
            (d for d in docs if d and d.get("metadata", {}).get("name") == "pms-redis-sentinel"),
            None,
        )
        assert sentinel is not None
        assert sentinel["spec"]["replicas"] == 3

    def test_redis_sentinel_monitor_config(self):
        docs = self._load_yaml("redis.yml")
        configmap = next(
            (d for d in docs if d and d.get("kind") == "ConfigMap"),
            None,
        )
        assert configmap is not None
        sentinel_conf = configmap["data"]["sentinel.conf"]
        assert "sentinel monitor mymaster" in sentinel_conf
        assert "down-after-milliseconds" in sentinel_conf
        assert "failover-timeout" in sentinel_conf

    def test_redis_pdb_for_availability(self):
        docs = self._load_yaml("redis.yml")
        pdb = next(
            (d for d in docs if d and d.get("kind") == "PodDisruptionBudget"),
            None,
        )
        assert pdb is not None
        assert pdb["spec"]["minAvailable"] == 2

    def test_storage_local_ssd_class(self):
        docs = self._load_yaml("storage.yml")
        sc = next(
            (d for d in docs if d and d.get("kind") == "StorageClass"),
            None,
        )
        assert sc is not None
        assert sc["metadata"]["name"] == "local-ssd"
        assert sc["provisioner"] == "kubernetes.io/no-provisioner"
        assert sc["volumeBindingMode"] == "WaitForFirstConsumer"

    def test_storage_persistent_volumes(self):
        docs = self._load_yaml("storage.yml")
        pvs = [d for d in docs if d and d.get("kind") == "PersistentVolume"]
        assert len(pvs) >= 2
        for pv in pvs:
            assert pv["spec"]["storageClassName"] == "local-ssd"
            assert pv["spec"]["capacity"]["storage"].endswith("Gi")

    def test_gpu_nvidia_device_plugin_daemonset(self):
        docs = self._load_yaml("gpu.yml")
        ds = next(
            (d for d in docs if d and d.get("kind") == "DaemonSet"),
            None,
        )
        assert ds is not None
        tolerations = ds["spec"]["template"]["spec"]["tolerations"]
        has_gpu_taint = any(
            t.get("key") == "nvidia.com/gpu" or t.get("key", "").startswith("nvidia")
            for t in tolerations
        )
        assert has_gpu_taint, "NVIDIA Device Plugin应有GPU taint容忍度"

    def test_gpu_resource_quota(self):
        docs = self._load_yaml("gpu.yml")
        quota = next(
            (d for d in docs if d and d.get("kind") == "ResourceQuota"),
            None,
        )
        assert quota is not None
        hard = quota["spec"]["hard"]
        assert "requests.nvidia.com/gpu" in hard
        assert "limits.nvidia.com/gpu" in hard

    def test_gpu_vllm_inference_deployment(self):
        docs = self._load_yaml("gpu.yml")
        vllm = next(
            (d for d in docs if d and d.get("metadata", {}).get("name") == "pms-vllm-inference"),
            None,
        )
        assert vllm is not None
        resources = vllm["spec"]["template"]["spec"]["containers"][0]["resources"]
        assert resources["limits"]["nvidia.com/gpu"] == "3"


class TestDockerAndCompose:
    """Dockerfile和docker-compose验证"""

    def test_dockerfile_has_multistage_build(self):
        with open("D:/Project/fms/Dockerfile", encoding="utf-8") as f:
            content = f.read()
        assert "FROM python:3.11-slim AS builder" in content
        assert "FROM python:3.11-slim AS runtime" in content
        assert "COPY --from=builder" in content

    def test_dockerfile_non_root_user(self):
        with open("D:/Project/fms/Dockerfile", encoding="utf-8") as f:
            content = f.read()
        assert "USER appuser" in content
        assert "groupadd -r appuser" in content

    def test_dockerfile_has_healthcheck(self):
        with open("D:/Project/fms/Dockerfile", encoding="utf-8") as f:
            content = f.read()
        assert "HEALTHCHECK" in content
        assert "/health" in content

    def test_dockerfile_exposes_port_8000(self):
        with open("D:/Project/fms/Dockerfile", encoding="utf-8") as f:
            content = f.read()
        assert "EXPOSE 8000" in content

    def test_docker_compose_has_pg_service(self):
        with open("D:/Project/fms/docker-compose.yml", encoding="utf-8") as f:
            compose = yaml.safe_load(f)
        services = compose.get("services", {})
        assert "postgres" in services
        pg = services["postgres"]
        assert "image" in pg
        assert "environment" in pg
        assert "healthcheck" in pg

    def test_docker_compose_has_redis_service(self):
        with open("D:/Project/fms/docker-compose.yml", encoding="utf-8") as f:
            compose = yaml.safe_load(f)
        services = compose.get("services", {})
        assert "redis" in services
        assert "healthcheck" in services["redis"]

    def test_docker_compose_has_qdrant_service(self):
        with open("D:/Project/fms/docker-compose.yml", encoding="utf-8") as f:
            compose = yaml.safe_load(f)
        services = compose.get("services", {})
        assert "qdrant" in services

    def test_docker_compose_has_app_service(self):
        with open("D:/Project/fms/docker-compose.yml", encoding="utf-8") as f:
            compose = yaml.safe_load(f)
        services = compose.get("services", {})
        assert "app" in services
        app = services["app"]
        assert "build" in app
        assert "depends_on" in app

    def test_docker_compose_network_defined(self):
        with open("D:/Project/fms/docker-compose.yml", encoding="utf-8") as f:
            compose = yaml.safe_load(f)
        assert "networks" in compose
        assert compose["networks"]["default"]["name"] == "pms-network"

    def test_docker_compose_has_volumes(self):
        with open("D:/Project/fms/docker-compose.yml", encoding="utf-8") as f:
            compose = yaml.safe_load(f)
        assert "volumes" in compose
        volumes = compose["volumes"]
        assert "pg_data" in volumes
        assert "redis_data" in volumes
        assert "qdrant_data" in volumes


class TestInfrastructureIntegration:
    """基础设施集成测试: 验证模块导出和配置文件"""

    def test_infrastructure_module_exports(self):
        from src.infrastructure import (
            get_async_session,
            get_db,
            get_redis,
            get_redis_connection,
            init_db,
        )
        assert callable(get_async_session)
        assert callable(get_db)
        assert callable(init_db)
        assert callable(get_redis)
        assert callable(get_redis_connection)

    def test_env_example_file_has_required_keys(self):
        with open("D:/Project/fms/.env.example", encoding="utf-8") as f:
            content = f.read()
        required_keys = [
            "APP_NAME",
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY",
            "LLM_PRIMARY_MODEL",
        ]
        for key in required_keys:
            assert key in content, f".env.example缺少 {key}"

    def test_k8s_directory_structure(self):
        k8s_dir = "D:/Project/fms/k8s"
        expected_files = [
            "deployment.yml",
            "postgresql.yml",
            "redis.yml",
            "storage.yml",
            "gpu.yml",
        ]
        for filename in expected_files:
            filepath = os.path.join(k8s_dir, filename)
            assert os.path.isfile(filepath), f"缺少K8s配置文件: {filename}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
