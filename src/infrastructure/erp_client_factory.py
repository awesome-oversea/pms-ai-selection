from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.infrastructure.base_erp_client import BaseERPClient
from src.models.enums import ERPSystemType

logger = get_logger(__name__)

_DOMAIN_CLIENT_MAP: dict[str, str] = {
    "scm": "src.infrastructure.scm_client:SCMClient",
    "wms": "src.infrastructure.wms_client:WMSClient",
    "oms": "src.infrastructure.oms_client:OMSClient",
    "crm": "src.infrastructure.crm_client:CRMClient",
    "bi": "src.infrastructure.bi_client:BIClient",
    "pdm": "src.infrastructure.pdm_client:PDMClient",
    "som": "src.infrastructure.som_client:SOMClient",
    "fms": "src.infrastructure.fms_client:FMSClient",
    "paas": "src.infrastructure.paas_client:PAASClient",
}


class ERPClientFactory:
    """
    ERP 客户端工厂。

    根据 ERP 域类型和配置，创建对应的客户端实例。
    支持懒加载和缓存，避免重复创建。
    """

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def get_client(
        self,
        domain: ERPSystemType | str,
        *,
        api_endpoint: str,
        api_key: str,
        secret_key: str | None = None,
        inbound_path: str = "/inbound",
        outbound_path: str = "/outbound",
        timeout_seconds: float = 10.0,
    ) -> BaseERPClient:
        domain_code = domain.value if isinstance(domain, ERPSystemType) else str(domain)
        cache_key = f"{domain_code}:{api_endpoint}"

        if cache_key in self._clients:
            return self._clients[cache_key]

        client = self._create_client(
            domain_code=domain_code,
            api_endpoint=api_endpoint,
            api_key=api_key,
            secret_key=secret_key or api_key,
            inbound_path=inbound_path,
            outbound_path=outbound_path,
            timeout_seconds=timeout_seconds,
        )
        self._clients[cache_key] = client
        return client

    def get_client_from_config(self, domain: ERPSystemType | str, config: Any) -> BaseERPClient:
        domain_code = domain.value if isinstance(domain, ERPSystemType) else str(domain)
        extra = config.extra_config or {}

        return self.get_client(
            domain=domain_code,
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            secret_key=config.secret_key,
            inbound_path=extra.get("inbound_path", "/inbound"),
            outbound_path=extra.get("outbound_path", "/outbound"),
            timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
        )

    def clear_cache(self) -> None:
        self._clients.clear()

    def _create_client(
        self,
        *,
        domain_code: str,
        api_endpoint: str,
        api_key: str,
        secret_key: str,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> BaseERPClient:
        client_class = self._resolve_client_class(domain_code)

        if client_class is not None:
            return client_class(
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                inbound_path=inbound_path,
                outbound_path=outbound_path,
                timeout_seconds=timeout_seconds,
            )

        logger.warning("域 %s 无专用客户端，使用 BaseERPClient", domain_code)
        return BaseERPClient(
            base_url=api_endpoint,
            domain=domain_code,
            api_key=api_key,
            secret_key=secret_key,
            connect_timeout_seconds=min(timeout_seconds, 5.0),
            read_timeout_seconds=max(timeout_seconds, 5.0),
        )

    @staticmethod
    def _resolve_client_class(domain_code: str) -> type | None:
        client_path = _DOMAIN_CLIENT_MAP.get(domain_code)
        if client_path is None:
            return None

        module_path, class_name = client_path.rsplit(":", 1)
        try:
            import importlib
            module = importlib.import_module(module_path)
            return getattr(module, class_name, None)
        except (ImportError, AttributeError) as e:
            logger.warning("无法加载域客户端 %s: %s", domain_code, e)
            return None


_factory: ERPClientFactory | None = None


def get_erp_client_factory() -> ERPClientFactory:
    global _factory
    if _factory is None:
        _factory = ERPClientFactory()
    return _factory
