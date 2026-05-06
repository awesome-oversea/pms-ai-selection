"""
自定义异常体系
=============

定义PMS系统所有自定义异常的基类和具体异常类型。
所有业务异常应继承自 PMSBaseException，便于统一处理和日志记录。

异常层次结构:
    PMSBaseException (基类)
    ├── ConfigurationError      # 配置错误
    ├── ResourceNotFoundError   # 资源未找到
    ├── ValidationError         # 数据校验失败
    ├── AuthenticationError     # 认证失败
    ├── AuthorizationError      # 权限不足
    ├── ExternalServiceError    # 外部服务调用失败
    └── AgentExecutionError     # Agent执行错误
"""

from typing import Any


class PMSBaseException(Exception):  # noqa: N818
    """
    PMS系统基础异常类。

    所有业务异常的根类，携带:
    - error_code: 错误码，用于API响应和前端展示
    - message: 人类可读的错误描述
    - detail: 额外的详细上下文信息

    Attributes:
        error_code: 标准化错误码 (如 "E001", "AUTH_001")
        message: 错误消息
        detail: 详细信息字典
        http_status: 映射的HTTP状态码(默认500)

    Example:
        >>> raise ConfigurationError(
        ...     "DB_URL",
        ...     "数据库连接字符串未配置",
        ...     hint="请在 .env 文件中设置 DB_URL"
        ... )
    """

    def __init__(
        self,
        message: str = "未知错误",
        error_code: str = "E000",
        detail: dict[str, Any] | None = None,
        http_status: int = 500,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.detail = detail or {}
        self.http_status = http_status
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """将异常转换为标准化的API响应字典格式。"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "detail": self.detail,
        }

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"http_status={self.http_status})"
        )


class ConfigurationError(PMSBaseException):
    """配置项缺失或无效时抛出。"""

    def __init__(
        self,
        config_key: str,
        message: str = "",
        hint: str = "",
    ) -> None:
        full_message = (
            f"配置错误 [{config_key}]: {message}"
            if message
            else f"配置项 [{config_key}] 未正确设置"
        )
        if hint:
            full_message += f" (提示: {hint})"
        super().__init__(
            message=full_message,
            error_code="CONFIG_ERROR",
            http_status=500,
        )
        self.config_key = config_key


class ResourceNotFoundError(PMSBaseException):
    """请求的资源不存在时抛出。"""

    def __init__(
        self,
        resource_type: str,
        resource_id: Any,
        message: str = "",
    ) -> None:
        full_message = (
            message
            or f"{resource_type} [id={resource_id}] 不存在"
        )
        super().__init__(
            message=full_message,
            error_code="NOT_FOUND",
            http_status=404,
        )
        self.resource_type = resource_type
        self.resource_id = resource_id


class ValidationError(PMSBaseException):
    """数据校验失败时抛出。"""

    def __init__(
        self,
        field: str,
        message: str,
        errors: list[dict] | None = None,
    ) -> None:
        full_message = f"字段 [{field}] 校验失败: {message}"
        super().__init__(
            message=full_message,
            error_code="VALIDATION_ERROR",
            http_status=422,
            detail={"field": field, "errors": errors or []},
        )


class AuthenticationError(PMSBaseException):
    """认证失败时抛出。"""

    def __init__(self, message: str = "认证凭证无效或已过期") -> None:
        super().__init__(
            message=message,
            error_code="AUTH_FAILED",
            http_status=401,
        )


class AuthorizationError(PMSBaseException):
    """权限不足时抛出。"""

    def __init__(
        self,
        action: str = "",
        resource: str = "",
    ) -> None:
        msg = "权限不足"
        if action and resource:
            msg += f": 无权执行 [{action}] 操作于 [{resource}]"
        elif action:
            msg += f": 无权执行 [{action}] 操作"
        super().__init__(
            message=msg,
            error_code="FORBIDDEN",
            http_status=403,
        )


class ExternalServiceError(PMSBaseException):
    """外部服务调用失败时抛出。"""

    def __init__(
        self,
        service_name: str,
        message: str = "",
        original_error: Exception | None = None,
    ) -> None:
        full_message = (
            f"外部服务[{service_name}]调用失败"
            if not message
            else f"外部服务[{service_name}]: {message}"
        )
        super().__init__(
            message=full_message,
            error_code="EXTERNAL_ERROR",
            http_status=502,
            detail={"service": service_name},
        )
        self.service_name = service_name
        self.original_error = original_error


class AgentExecutionError(PMSBaseException):
    """AI Agent执行过程中出错时抛出。"""

    def __init__(
        self,
        agent_name: str,
        message: str,
        step: str = "",
    ) -> None:
        full_message = f"Agent[{agent_name}]执行失败"
        if step:
            full_message += f"(步骤: {step})"
        full_message += f": {message}"
        super().__init__(
            message=full_message,
            error_code="AGENT_ERROR",
            http_status=500,
            detail={"agent": agent_name, "step": step},
        )


class LLMBudgetExceededError(PMSBaseException):
    """租户 LLM 预算/配额不足时抛出。"""

    def __init__(self, tenant_id: str, quota_type: str, requested: float, remaining: float) -> None:
        super().__init__(
            message=f"租户模型预算不足: {quota_type}，请求 {requested:.6f}，剩余 {remaining:.6f}",
            error_code="QUOTA_EXCEEDED",
            http_status=429,
            detail={
                "tenant_id": tenant_id,
                "quota_type": quota_type,
                "requested": requested,
                "remaining": remaining,
            },
        )


class IPAllowlistDeniedError(PMSBaseException):
    """客户端 IP 不在白名单时抛出。"""

    def __init__(self, client_ip: str, target: str = "llm.route") -> None:
        super().__init__(
            message=f"客户端 IP 未被允许访问高风险接口: {client_ip}",
            error_code="IP_NOT_ALLOWED",
            http_status=403,
            detail={"client_ip": client_ip, "target": target},
        )


class PromptInjectionDetectedError(PMSBaseException):
    """检测到高风险 Prompt 注入特征时抛出。"""

    def __init__(self, matched_keyword: str) -> None:
        super().__init__(
            message="Prompt 存在高风险注入特征，已拒绝执行",
            error_code="PROMPT_INJECTION_DETECTED",
            http_status=400,
            detail={"matched_keyword": matched_keyword},
        )


class RequestBlockedByWAFError(PMSBaseException):
    """请求命中 WAF 规则时抛出。"""

    def __init__(self, reason: str, matched_keyword: str, location: str) -> None:
        super().__init__(
            message=f"请求命中 WAF 防护规则，已拒绝执行: {reason}",
            error_code="WAF_BLOCKED",
            http_status=400,
            detail={
                "reason": reason,
                "matched_keyword": matched_keyword,
                "location": location,
            },
        )
