"""
全局应用配置 (Pydantic Settings)
================================

集中管理所有系统配置项，支持:
- 环境变量自动映射 (大写+下划线)
- .env文件加载
- 类型安全校验
- 敏感信息隐藏(str repr)

配置分类:
    AppSettings: 应用基础配置
    DatabaseSettings: PostgreSQL连接
    RedisSettings: Redis缓存集群
    KafkaSettings: 消息队列
    LLMAI: AI模型服务
    SecuritySettings: 安全认证

环境变量示例 (.env):
    APP_NAME=pms-ai-selection
    APP_LOG_LEVEL=INFO
    DB_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/pms_db
    REDIS_URL=redis://127.0.0.1:6379/0
    SEC_SECRET_KEY=your-secret-key-here

兼容策略:
    为了平滑迁移，当前仍兼容一小部分旧键名，如:
    - LOG_LEVEL -> APP_LOG_LEVEL
    - API_PREFIX -> APP_API_PREFIX
    - DATABASE_URL -> DB_URL
    - SECRET_KEY -> SEC_SECRET_KEY
    - SECURITY_* -> SEC_*
"""

import json
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REQUIRED_LOCAL_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3100",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


class AppSettings(BaseSettings):
    """应用基础配置。"""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = Field(
        default="pms-ai-selection",
        description="应用名称，用于日志和服务发现标识",
    )
    version: str = Field(
        default="0.1.0",
        description="应用语义化版本号",
    )
    debug: bool = Field(
        default=False,
        description="调试模式开关，生产环境必须为False",
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("APP_LOG_LEVEL", "LOG_LEVEL"),
        description="全局日志级别 (DEBUG/INFO/WARNING/ERROR)",
    )
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENVIRONMENT", "APP_ENV"),
        description="运行环境 (development/staging/production)",
    )
    api_prefix: str = Field(
        default="/api/v1",
        validation_alias=AliasChoices("APP_API_PREFIX", "API_PREFIX"),
        description="API路由前缀",
    )
    cors_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3100",
            "http://127.0.0.1:3100",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        description="CORS允许的来源列表",
    )
    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="应用启动时间",
    )

    @field_validator("cors_origins", mode="after")
    @classmethod
    def ensure_required_local_cors_origins(cls, value: list[str]) -> list[str]:
        merged: list[str] = []
        for origin in [*(value or []), *REQUIRED_LOCAL_CORS_ORIGINS]:
            if origin and origin not in merged:
                merged.append(origin)
        return merged


class DatabaseSettings(BaseSettings):
    """PostgreSQL数据库连接配置。"""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(
        default="postgresql+asyncpg://pms:pms_dev_2024@127.0.0.1:5432/pms_db",
        validation_alias=AliasChoices("DB_URL", "DATABASE_URL"),
        description="异步PostgreSQL连接字符串(使用asyncpg驱动)",
    )
    write_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DB_WRITE_URL", "DB_PRIMARY_URL"),
        description="主库/写库连接字符串；未配置时回退到 DB_URL",
    )
    read_urls: Annotated[list[str], NoDecode] = Field(
        default=[],
        validation_alias=AliasChoices("DB_READ_URLS", "DB_REPLICA_URLS"),
        description="从库/读库连接字符串列表，支持 JSON 数组或逗号分隔",
    )
    read_write_split: bool = Field(
        default=False,
        validation_alias=AliasChoices("DB_READ_WRITE_SPLIT", "DB_ENABLE_RW_SPLIT"),
        description="是否启用 PostgreSQL 读写分离",
    )
    fallback_to_write_for_reads: bool = Field(
        default=True,
        description="当读库不可用时，是否回退到写库执行查询",
    )
    read_strategy: str = Field(
        default="round_robin",
        description="读库负载均衡策略：当前支持 round_robin",
    )
    probe_timeout_seconds: float = Field(
        default=3.0,
        ge=0.5,
        le=30.0,
        description="数据库节点探活超时时间(秒)",
    )
    pool_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="数据库连接池最大连接数",
    )
    max_overflow: int = Field(
        default=10,
        ge=0,
        le=50,
        description="连接池溢出时额外创建的最大连接数",
    )
    echo_sql: bool = Field(
        default=False,
        description="是否输出SQL语句到日志(仅开发环境开启)",
    )

    @field_validator("read_urls", mode="before")
    @classmethod
    def normalize_database_read_urls(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]


class RedisSettings(BaseSettings):
    """Redis缓存/会话存储配置。"""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(
        default="redis://127.0.0.1:6379/0",
        description="Redis单节点或Cluster连接URL",
    )
    cluster_mode: bool = Field(
        default=False,
        description="是否启用Redis Cluster模式",
    )
    cluster_nodes: list[str] = Field(
        default=[],
        description="Redis Cluster节点列表(cluster_mode=True时必填)",
    )
    max_connections: int = Field(
        default=20,
        ge=1,
        description="Redis连接池最大连接数",
    )


    sentinel_enabled: bool = Field(
        default=False,
        description="鏄惁鍚敤 Redis Sentinel 楂樺彲鐢ㄦā寮?",
    )
    sentinel_master_name: str = Field(
        default="mymaster",
        description="Redis Sentinel 鐩戞帶鐨?master 鏈嶅姟鍚嶇О",
    )
    sentinel_nodes: Annotated[list[str], NoDecode] = Field(
        default=[],
        description="Redis Sentinel 鑺傜偣鍒楄〃锛屾敮鎸?JSON 鏁扮粍鎴栭€楀彿鍒嗛殧",
    )
    sentinel_username: str | None = Field(
        default=None,
        description="Redis Sentinel 鐢ㄦ埛鍚嶏紙濡傚惎鐢?ACL锛?",
    )
    sentinel_password: str | None = Field(
        default=None,
        description="Redis Sentinel 瀵嗙爜锛堝鍚敤瀵嗙爜鎴?ACL锛?",
    )
    sentinel_db: int = Field(
        default=0,
        ge=0,
        le=15,
        description="Redis Sentinel 鏁版嵁搴?db 缂栧彿",
    )

    @field_validator("cluster_nodes", "sentinel_nodes", mode="before")
    @classmethod
    def normalize_redis_node_lists(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]


class KafkaSettings(BaseSettings):
    """Kafka消息队列配置。"""

    model_config = SettingsConfigDict(
        env_prefix="KAFKA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bootstrap_servers: str = Field(
        default="127.0.0.1:9092",
        description="Kafka Broker地址(多个用逗号分隔)",
    )
    group_id: str = Field(
        default="pms-consumer-group",
        validation_alias=AliasChoices("KAFKA_GROUP_ID", "KAFKA_CONSUMER_GROUP"),
        description="消费者组ID",
    )
    topics_data_collection: str = Field(
        default="pms-data-collection",
        validation_alias=AliasChoices(
            "KAFKA_TOPICS_DATA_COLLECTION",
            "KAFKA_TOPIC_DATA_COLLECTION",
        ),
        description="数据采集主题",
    )
    topics_agent_event: str = Field(
        default="pms-agent-event",
        validation_alias=AliasChoices(
            "KAFKA_TOPICS_AGENT_EVENT",
            "KAFKA_TOPIC_AGENT_EVENT",
        ),
        description="Agent事件主题",
    )
    auto_offset_reset: str = Field(
        default="latest",
        description="消费者偏移重置策略 (earliest/latest)",
    )


class SecuritySettings(BaseSettings):
    """安全认证与授权配置。"""

    model_config = SettingsConfigDict(
        env_prefix="SEC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY_MIN_32_CHARS!!",
        validation_alias=AliasChoices("SEC_SECRET_KEY", "SECRET_KEY"),
        description="JWT签名密钥，生产环境必须更换为强随机值",
    )
    algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("SEC_ALGORITHM", "SECURITY_ALGORITHM"),
        description="JWT签名算法(HS256/RS256)",
    )
    access_token_expire_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices(
            "SEC_ACCESS_TOKEN_EXPIRE_MINUTES",
            "SECURITY_ACCESS_TOKEN_EXPIRE_MINUTES",
        ),
        ge=1,
        le=1440,
        description="Access Token有效期(分钟)",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        validation_alias=AliasChoices(
            "SEC_REFRESH_TOKEN_EXPIRE_DAYS",
            "SECURITY_REFRESH_TOKEN_EXPIRE_DAYS",
        ),
        ge=1,
        le=365,
        description="Refresh Token有效期(天)",
    )
    password_min_length: int = Field(
        default=8,
        ge=6,
        description="密码最小长度要求",
    )
    require_explicit_tenant: bool = Field(
        default=True,
        description="是否要求请求或上下文显式提供 tenant_id，开启后禁止默认租户静默回退",
    )
    llm_ip_allowlist: Annotated[list[str], NoDecode] = Field(
        default=[],
        description="LLM 高风险入口允许访问的客户端 IP 列表；为空时不启用白名单拦截",
    )
    llm_prompt_guard_enabled: bool = Field(
        default=True,
        description="是否启用 LLM Prompt 注入关键字拦截",
    )
    llm_prompt_guard_keywords: Annotated[list[str], NoDecode] = Field(
        default=[
            "ignore previous instructions",
            "ignore all previous instructions",
            "system prompt",
            "developer instructions",
            "reveal prompt",
            "泄露系统提示",
            "忽略之前的指令",
            "忽略所有之前的指令",
            "输出系统提示",
            "绕过安全策略",
        ],
        description="LLM Prompt 注入拦截关键字列表",
    )
    llm_output_guard_keywords: Annotated[list[str], NoDecode] = Field(
        default=[
            "password",
            "secret_key",
            "api_key",
            "内部密钥",
            "管理员口令",
        ],
        description="LLM 输出敏感词过滤关键字列表",
    )
    pii_field_patterns: Annotated[list[str], NoDecode] = Field(
        default=[],
        description="PII 字段识别规则扩展列表；用于补充默认脱敏字段模式",
    )
    local_bootstrap_superuser_enabled: bool = Field(
        default=False,
        description="是否启用仅本地/开发环境可用的受控 superuser 登录种子",
    )
    local_bootstrap_superuser_username: str | None = Field(
        default=None,
        description="本地/开发环境 superuser 种子用户名",
    )
    local_bootstrap_superuser_password: str | None = Field(
        default=None,
        description="本地/开发环境 superuser 种子密码，仅用于受控测试与本地验收",
    )
    local_bootstrap_superuser_email: str | None = Field(
        default=None,
        description="本地/开发环境 superuser 种子邮箱",
    )
    oidc_enabled: bool = Field(
        default=False,
        description="是否启用 OIDC / OAuth2 SSO 基础框架",
    )
    oidc_issuer_url: str | None = Field(
        default=None,
        description="OIDC Issuer URL",
    )
    oidc_client_id: str | None = Field(
        default=None,
        description="OIDC Client ID",
    )
    oidc_client_secret: str | None = Field(
        default=None,
        description="OIDC Client Secret",
    )
    oidc_authorize_path: str = Field(
        default="/authorize",
        description="OIDC 授权端点路径",
    )
    oidc_token_path: str = Field(
        default="/token",
        description="OIDC Token 端点路径",
    )
    oidc_userinfo_path: str = Field(
        default="/userinfo",
        description="OIDC UserInfo 端点路径",
    )
    oidc_discovery_url: str | None = Field(
        default=None,
        description="OIDC Well-Known Discovery URL；未配置时由 issuer 自动推导",
    )
    oidc_jwks_uri: str | None = Field(
        default=None,
        description="OIDC JWKS URI；未配置时优先使用 discovery 文档中的 jwks_uri",
    )
    oidc_audience: str | None = Field(
        default=None,
        description="OIDC Access Token 期望 audience；Okta 等场景建议显式配置",
    )
    oidc_username_claims: Annotated[list[str], NoDecode] = Field(
        default=["preferred_username", "email", "sub"],
        description="从 OIDC claim 中提取用户名的优先级顺序",
    )
    oidc_role_claim_paths: Annotated[list[str], NoDecode] = Field(
        default=[
            "roles",
            "groups",
            "realm_access.roles",
            "resource_access.{client_id}.roles",
        ],
        description="从 OIDC claim 中提取角色的字段路径列表，支持 {client_id} 占位符",
    )
    oidc_role_mapping: Annotated[dict[str, str], NoDecode] = Field(
        default_factory=dict,
        description="OIDC 角色到本地 RBAC 角色的映射，支持 JSON 或 key=value 逗号格式",
    )
    oidc_tenant_id_claim: str = Field(
        default="tenant_id",
        description="OIDC claim 中的 tenant_id 字段路径",
    )
    oidc_tenant_key_claim: str = Field(
        default="tenant_key",
        description="OIDC claim 中的 tenant_key 字段路径",
    )
    oidc_tenant_name_claim: str = Field(
        default="tenant_name",
        description="OIDC claim 中的 tenant_name 字段路径",
    )
    oidc_default_tenant_id: str | None = Field(
        default=None,
        description="当 OIDC token 未显式提供 tenant_id 时使用的默认租户 ID",
    )
    oidc_default_tenant_key: str | None = Field(
        default=None,
        description="当 OIDC token 未显式提供 tenant_key 时使用的默认租户 key",
    )
    oidc_default_tenant_name: str | None = Field(
        default=None,
        description="当 OIDC token 未显式提供 tenant_name 时使用的默认租户名称",
    )
    oidc_http_timeout_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=60.0,
        description="OIDC discovery/JWKS 请求超时时间(秒)",
    )
    oidc_cache_ttl_seconds: int = Field(
        default=300,
        ge=0,
        le=86400,
        description="OIDC discovery/JWKS 本地缓存 TTL(秒)，0 表示禁用缓存",
    )
    channel_callback_verification_enabled: bool = Field(
        default=False,
        description="是否启用企业机器人回调 URL 验签/验真",
    )
    channel_callback_ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="企业机器人回调签名允许的最大时间漂移（秒）",
    )
    dingtalk_callback_token: str | None = Field(
        default=None,
        description="钉钉机器人回调 Token",
    )
    dingtalk_callback_secret: str | None = Field(
        default=None,
        description="钉钉机器人回调签名密钥",
    )
    wechat_callback_token: str | None = Field(
        default=None,
        description="企业微信机器人回调 Token",
    )
    wechat_callback_secret: str | None = Field(
        default=None,
        description="企业微信机器人回调签名密钥",
    )

    oidc_scope: str = Field(
        default="openid profile email",
        description="OIDC / OAuth2 授权 scope",
    )

    @field_validator(
        "llm_ip_allowlist",
        "llm_prompt_guard_keywords",
        "llm_output_guard_keywords",
        "pii_field_patterns",
        "oidc_username_claims",
        "oidc_role_claim_paths",
        mode="before",
    )
    @classmethod
    def normalize_list_settings(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]

    @field_validator("oidc_role_mapping", mode="before")
    @classmethod
    def normalize_oidc_role_mapping(cls, value: Any) -> dict[str, str]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return {
                str(key).strip(): str(mapped).strip()
                for key, mapped in value.items()
                if str(key).strip() and str(mapped).strip()
            }
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            if text.startswith("{"):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    return {
                        str(key).strip(): str(mapped).strip()
                        for key, mapped in parsed.items()
                        if str(key).strip() and str(mapped).strip()
                    }
            mapping: dict[str, str] = {}
            for item in text.split(","):
                raw_item = item.strip()
                if not raw_item:
                    continue
                if "=" in raw_item:
                    source, target = raw_item.split("=", 1)
                elif ":" in raw_item:
                    source, target = raw_item.split(":", 1)
                else:
                    continue
                source_text = source.strip()
                target_text = target.strip()
                if source_text and target_text:
                    mapping[source_text] = target_text
            return mapping
        return {}

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """
        校验 Secret Key 安全性。

        - production 环境: 弱密钥(< 32 位或包含 CHANGE_ME) → 抛出 ValueError 阻止启动
        - 其他环境: 弱密钥 → 仅发出警告
        """
        import os
        env = os.environ.get("APP_ENVIRONMENT", os.environ.get("APP_ENV", "development"))
        is_weak = len(v) < 32 or "CHANGE_ME" in v

        if is_weak and env == "production":
            raise ValueError(
                "production 环境禁止使用弱 SECRET_KEY！"
                "请设置 SEC_SECRET_KEY 为至少 32 位的强随机密钥。"
            )
        elif is_weak:
            import warnings
            warnings.warn(
                "SECRET_KEY使用了不安全的默认值！"
                "生产环境请设置强随机密钥(≥32字符)",
                stacklevel=2,
            )
        return v


class LLMSettings(BaseSettings):
    """AI大语言模型服务配置。"""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    primary_model: str = Field(
        default="qwen2.5:1.5b-instruct",
        description="主推理模型名称",
    )
    vllm_endpoint: str = Field(
        default="http://127.0.0.1:8000/v1",
        description="兼容保留的vLLM推理服务端点",
    )
    triton_endpoint: str = Field(
        default="http://127.0.0.1:8000",
        description="兼容保留的Triton推理服务端点(多模态/Rerank)",
    )
    triton_enabled: bool = Field(
        default=False,
        description="是否启用 Triton 推理服务",
    )
    triton_timeout_seconds: float = Field(
        default=5.0,
        ge=0.5,
        le=60.0,
        description="Triton 请求超时时间(秒)",
    )
    ollama_endpoint: str = Field(
        default="http://127.0.0.1:11434",
        description="Ollama轻量模型端点",
    )
    embedding_model: str = Field(
        default="bge-large-zh",
        description="Embedding向量模型名称",
    )
    multimodal_model: str = Field(
        default="qwen3.5:2b",
        description="本地多模态/视频模型名称",
    )
    rerank_model: str = Field(
        default="bge-reranker-base",
        description="Rerank精排模型名称",
    )
    speech_model: str = Field(
        default="whisper-tiny",
        description="本地 CPU 语音转录模型名称",
    )
    speech_device: str = Field(
        default="cpu",
        description="本地语音转录运行设备",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="LLM请求超时时间(秒)",
    )
    api_key: str | None = Field(
        default=None,
        description="上游代理/模型服务 API Key",
    )
    api_auth_header: str = Field(
        default="Authorization",
        description="上游代理鉴权 Header 名称",
    )
    api_auth_scheme: str = Field(
        default="Bearer",
        description="上游代理鉴权 Scheme，如 Bearer / Token",
    )
    api_model_name: str | None = Field(
        default=None,
        description="真实代理调用时优先使用的模型名",
    )
    request_retry_count: int = Field(
        default=1,
        ge=0,
        le=5,
        description="真实代理调用失败后的重试次数",
    )
    max_tokens: int = Field(
        default=4096,
        ge=256,
        le=32768,
        description="单次请求最大Token数",
    )


class SelectionExecutionSettings(BaseSettings):
    """选品任务执行模式配置（Phase 6 Worker 基线）。"""

    model_config = SettingsConfigDict(
        env_prefix="SELECTION_EXECUTION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: str = Field(default="worker", description="选品任务执行模式：worker/background")
    enable_api_background_dispatch: bool = Field(
        default=False,
        description="是否允许 API 进程直接通过 BackgroundTasks 启动任务",
    )
    enable_celery_dispatch: bool = Field(
        default=False,
        description="是否允许 API 进程通过 Celery 投递选品任务",
    )
    celery_broker_url: str = Field(
        default="redis://127.0.0.1:6379/1",
        description="Celery Broker URL",
    )
    celery_result_backend: str = Field(
        default="redis://127.0.0.1:6379/2",
        description="Celery Result Backend URL",
    )
    celery_queue_name: str = Field(
        default="selection_tasks",
        description="选品任务 Celery 队列名称",
    )
    worker_poll_interval_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Worker 轮询待执行任务的时间间隔（秒）",
    )
    worker_batch_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="单次轮询最多领取的待执行任务数",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        description="任务执行最大重试次数（超过后进入死信）",
    )
    task_timeout_seconds: float = Field(
        default=120.0,
        ge=1.0,
        le=3600.0,
        description="单个任务执行超时时间（秒）",
    )
    tenant_max_parallelism: int = Field(
        default=2,
        ge=1,
        le=100,
        description="单租户最大并行执行任务数",
    )
    task_type_max_parallelism: int = Field(
        default=4,
        ge=1,
        le=100,
        description="单任务类型最大并行执行任务数（当前 selection 统一类型）",
    )
    queue_backlog_warning_threshold: int = Field(
        default=10,
        ge=1,
        le=10000,
        description="任务队列堆积告警阈值",
    )
    enable_bi_daily_kpi_scheduler: bool = Field(
        default=False,
        description="是否在 API 进程内启用 BI 每日 KPI 调度器",
    )
    bi_daily_kpi_interval_seconds: float = Field(
        default=86400.0,
        ge=60.0,
        le=604800.0,
        description="BI 每日 KPI 调度器轮询间隔（秒）",
    )
    bi_daily_kpi_bootstrap_delay_seconds: float = Field(
        default=5.0,
        ge=0.0,
        le=600.0,
        description="应用启动后首次执行 BI 每日 KPI 的延迟（秒）",
    )


class SearchSettings(BaseSettings):
    """OpenSearch/Elasticsearch 关键词检索配置。"""

    model_config = SettingsConfigDict(
        env_prefix="SEARCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=False, description="是否启用正式关键词检索后端")
    backend: str = Field(default="memory", description="search backend: memory/opensearch/elasticsearch")
    endpoint: str | None = Field(default=None, description="OpenSearch/Elasticsearch endpoint")
    username: str | None = Field(default=None, description="搜索引擎用户名")
    password: str | None = Field(default=None, description="搜索引擎密码")
    index_prefix: str = Field(default="pms_knowledge_", description="索引前缀")
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=60.0, description="搜索请求超时")


class LocalRuntimeSettings(BaseSettings):
    """Local runtime profile and scenario selection."""

    model_config = SettingsConfigDict(
        env_prefix="LOCAL_RUNTIME_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    profile: str = Field(
        default="windows-host+linux-deps",
        description="Runtime profile label used by local bootstrap tooling",
    )
    preferred_os: str = Field(
        default="linux-wsl",
        description="Preferred dependency OS: auto/windows/linux/linux-wsl",
    )
    scenario_mode: str = Field(
        default="local-real",
        description="Local runtime scenario: mock/local-real/remote-service",
    )

    @field_validator("preferred_os")
    @classmethod
    def validate_preferred_os(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"auto", "windows", "linux", "linux-wsl"}
        if normalized not in allowed:
            raise ValueError(f"LOCAL_RUNTIME_PREFERRED_OS must be one of {sorted(allowed)}")
        return normalized

    @field_validator("scenario_mode")
    @classmethod
    def validate_scenario_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"mock", "local-real", "remote-service"}
        if normalized not in allowed:
            raise ValueError(f"LOCAL_RUNTIME_SCENARIO_MODE must be one of {sorted(allowed)}")
        return normalized


class ServiceModeSettings(BaseSettings):
    """RAG/LLM/Agent/Embedding 独立服务化双模式配置。"""

    model_config = SettingsConfigDict(
        env_prefix="SERVICE_MODE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    rag_mode: str = Field(default="in-process", description="RAG service mode: in-process/remote-service")
    rag_base_url: str = Field(default="http://127.0.0.1:8000/api/v1", description="RAG 远程服务基础地址")
    rag_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0, description="RAG 远程调用超时")
    llm_mode: str = Field(default="in-process", description="LLM service mode: in-process/remote-service")
    llm_base_url: str = Field(default="http://127.0.0.1:8000/api/v1", description="LLM 远程服务基础地址")
    llm_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0, description="LLM 远程调用超时")
    agent_mode: str = Field(default="in-process", description="Agent service mode: in-process/remote-service")
    agent_base_url: str = Field(default="http://127.0.0.1:8000/api/v1", description="Agent 远程服务基础地址")
    agent_timeout_seconds: float = Field(default=10.0, ge=1.0, le=120.0, description="Agent 远程调用超时")
    embedding_mode: str = Field(default="in-process", description="Embedding service mode: in-process/remote-service")
    embedding_base_url: str = Field(default="http://127.0.0.1:8000/api/v1", description="Embedding 远程服务基础地址")
    embedding_timeout_seconds: float = Field(default=10.0, ge=1.0, le=120.0, description="Embedding 远程调用超时")
    enable_fallback: bool = Field(default=True, description="远程服务失败时是否回退到 in-process")


class DifySettings(BaseSettings):
    """Dify workflow HTTP runtime settings."""

    model_config = SettingsConfigDict(
        env_prefix="DIFY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=False, description="Enable real Dify workflow HTTP runtime")
    base_url: str = Field(default="http://127.0.0.1:58080", description="Dify API base URL")
    api_key: str | None = Field(default=None, description="Dify workflow/app API key")
    workflow_run_path: str = Field(default="/v1/workflows/run", description="Workflow run endpoint path")
    timeout_seconds: float = Field(default=20.0, ge=1.0, le=300.0, description="HTTP timeout in seconds")
    response_mode: str = Field(default="blocking", description="Dify response mode")
    user_prefix: str = Field(default="pms", description="Prefix for Dify request user identifier")
    prefer_compatible_fallback: bool = Field(default=True, description="Fall back to dify-compatible when HTTP runtime is unavailable")


class QdrantSettings(BaseSettings):
    """Qdrant向量数据库配置(D7-T018)。"""

    model_config = SettingsConfigDict(
        env_prefix="QDRANT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(
        default="127.0.0.1",
        description="Qdrant服务地址",
    )
    port: int = Field(
        default=6333,
        ge=1,
        le=65535,
        description="Qdrant gRPC/REST端口",
    )
    url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("QDRANT_URL", "QDRANT_BASE_URL"),
        description="Qdrant基础URL；未配置时使用 host + port 组合",
    )
    write_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("QDRANT_WRITE_URL", "QDRANT_PRIMARY_URL"),
        description="Qdrant写入节点URL；未配置时回退到 QDRANT_URL/host:port",
    )
    read_urls: Annotated[list[str], NoDecode] = Field(
        default=[],
        validation_alias=AliasChoices("QDRANT_READ_URLS", "QDRANT_REPLICA_URLS"),
        description="Qdrant只读/查询节点URL列表，支持 JSON 数组或逗号分隔",
    )
    cluster_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("QDRANT_CLUSTER_ENABLED", "QDRANT_ENABLE_CLUSTER"),
        description="是否启用 Qdrant 多节点/高可用模式",
    )
    api_key: str | None = Field(
        default=None,
        description="API密钥(生产环境必填)",
    )
    timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=120.0,
        description="请求超时时间(秒)",
    )
    prefer_local_fallback: bool = Field(
        default=True,
        description="远端Qdrant不可用时是否回退到本地嵌入式存储",
    )
    read_strategy: str = Field(
        default="round_robin",
        description="Qdrant读节点选择策略：当前支持 round_robin",
    )
    collection_prefix: str = Field(
        default="pms_",
        description="Collection名称前缀",
    )
    shard_number: int = Field(
        default=1,
        ge=1,
        le=64,
        description="新建Collection默认分片数",
    )
    replication_factor: int = Field(
        default=1,
        ge=1,
        le=16,
        description="新建Collection默认副本数",
    )
    write_consistency_factor: int = Field(
        default=1,
        ge=1,
        le=16,
        description="新建Collection默认写一致性因子",
    )

    @field_validator("read_urls", mode="before")
    @classmethod
    def normalize_qdrant_read_urls(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]


class Neo4jSettings(BaseSettings):
    """Neo4j图数据库配置。"""

    model_config = SettingsConfigDict(
        env_prefix="NEO4J_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=False, description="是否启用 Neo4j 真实图数据库")
    uri: str = Field(default="bolt://127.0.0.1:17687", description="Neo4j Bolt 地址")
    username: str | None = Field(default=None, description="Neo4j 用户名")
    password: str | None = Field(default=None, description="Neo4j 密码")
    database: str = Field(default="neo4j", description="Neo4j 数据库名")
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=60.0, description="Neo4j 连接超时")
    prefer_local_fallback: bool = Field(default=True, description="Neo4j 不可用时是否回退本地图存储")


class CollectionAPISettings(BaseSettings):
    """数据采集官方 API / 外部接口配置。"""

    model_config = SettingsConfigDict(
        env_prefix="COLLECTION_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    amazon_endpoint: str = Field(default="https://sellingpartnerapi-na.amazon.com", description="Amazon SP-API 端点")
    amazon_api_key: str | None = Field(default=None, description="Amazon SP-API API Key / Access Token")
    amazon_marketplace: str = Field(default="ATVPDKIKX0DER", description="Amazon Marketplace ID")
    amazon_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0, description="Amazon SP-API 超时")

    tiktok_endpoint: str = Field(default="https://business-api.tiktok.com", description="TikTok Business API 端点")
    tiktok_api_key: str | None = Field(default=None, description="TikTok Business API Token")
    tiktok_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0, description="TikTok Business API 超时")

    ali1688_endpoint: str = Field(default="https://api.1688.com", description="1688 Open API 端点")
    ali1688_api_key: str | None = Field(default=None, description="1688 Open API Key")
    ali1688_secret_key: str | None = Field(default=None, description="1688 Open API Secret")
    ali1688_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0, description="1688 Open API 超时")

    google_trends_endpoint: str = Field(default="https://trends.google.com", description="Google Trends 端点")
    google_trends_api_key: str | None = Field(default=None, description="Google Trends 代理/接口密钥")
    google_trends_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0, description="Google Trends 超时")
    http_max_attempts: int = Field(default=3, ge=1, le=5, description="外部采集 HTTP 最大尝试次数")
    http_base_backoff_seconds: float = Field(default=0.5, ge=0.0, le=30.0, description="外部采集 HTTP 首次退避秒数")
    http_max_backoff_seconds: float = Field(default=3.0, ge=0.0, le=60.0, description="外部采集 HTTP 最大退避秒数")

    proxy_provider: str = Field(default="none", description="代理提供商：none/static/self_hosted/brightdata/oxylabs")
    proxy_list: str | None = Field(default=None, description="静态代理列表，支持逗号/分号/换行分隔")
    proxy_endpoint: str | None = Field(default=None, description="代理服务端点(host:port 或 scheme://host:port)")
    proxy_username: str | None = Field(default=None, description="代理服务用户名")
    proxy_password: str | None = Field(default=None, description="代理服务密码")
    proxy_zone: str | None = Field(default=None, description="代理服务 zone/session 标识")
    proxy_country: str | None = Field(default=None, description="代理国家/地区代码")
    proxy_probe_url: str = Field(default="https://httpbin.org/ip", description="代理连通性探测 URL")
    proxy_probe_timeout_seconds: float = Field(default=8.0, ge=1.0, le=60.0, description="代理探测超时")


class OpsProbeSettings(BaseSettings):
    """网关/监控远端探测配置。"""

    model_config = SettingsConfigDict(
        env_prefix="OPS_PROBE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    kong_test_url: str | None = Field(default=None, description="测试环境 Kong 探测地址")
    kong_preprod_url: str | None = Field(default=None, description="预发环境 Kong 探测地址")
    kong_prod_url: str | None = Field(default=None, description="生产环境 Kong 探测地址")
    prometheus_url: str | None = Field(default=None, description="Prometheus 探测地址")
    grafana_url: str | None = Field(default=None, description="Grafana 探测地址")
    alertmanager_url: str | None = Field(default=None, description="Alertmanager 探测地址")


class Settings(BaseSettings):
    """
    全局设置聚合类。

    聚合所有子配置域，提供统一入口访问。
    通过 get_settings() 单例模式获取实例。
    """

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    selection_execution: SelectionExecutionSettings = Field(default_factory=SelectionExecutionSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    local_runtime: LocalRuntimeSettings = Field(default_factory=LocalRuntimeSettings)
    service_mode: ServiceModeSettings = Field(default_factory=ServiceModeSettings)
    dify: DifySettings = Field(default_factory=DifySettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    collection_api: CollectionAPISettings = Field(default_factory=CollectionAPISettings)
    ops_probe: OpsProbeSettings = Field(default_factory=OpsProbeSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    获取全局配置单例。

    使用 lru_cache 缓存确保整个进程只创建一次，
    避免重复读取环境变量和.env文件。

    Returns:
        Settings: 全局唯一配置实例

    Example:
        >>> settings = get_settings()
        >>> print(settings.app.name)       # pms-ai-selection
        >>> print(settings.database.url)   # postgresql+...
    """
    return Settings()
