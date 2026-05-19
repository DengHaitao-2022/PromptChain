"""
统一错误码注册表。
"""

from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus


class ErrorDomain(StrEnum):
    """错误所属业务域。"""

    COMMON = "COMMON"
    AUTH = "AUTH"
    WORKSPACE = "WORKSPACE"
    WORKFLOW = "WORKFLOW"
    TRACE = "TRACE"
    ADMIN = "ADMIN"
    INFRA = "INFRA"


class ErrorCategory(StrEnum):
    """错误类别。"""

    DOMAIN = "domain"
    APPLICATION = "application"
    INFRASTRUCTURE = "infrastructure"


class ConsumerAction(StrEnum):
    """调用方建议处理方向。"""

    FIX_INPUT = "fix_input"
    REAUTHENTICATE = "reauthenticate"
    RETRY_LATER = "retry_later"
    CONTACT_ADMIN = "contact_admin"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class ErrorCodeDefinition:
    """错误码注册项。"""

    code: str
    domain: ErrorDomain
    category: ErrorCategory
    http_status: int
    default_message: str
    consumer_action: ConsumerAction
    description: str = ""


COMMON_BAD_REQUEST = "COMMON_BAD_REQUEST"
COMMON_VALIDATION_ERROR = "COMMON_VALIDATION_ERROR"
COMMON_UNAUTHORIZED = "COMMON_UNAUTHORIZED"
COMMON_FORBIDDEN = "COMMON_FORBIDDEN"
COMMON_NOT_FOUND = "COMMON_NOT_FOUND"
COMMON_CONFLICT = "COMMON_CONFLICT"
COMMON_INTERNAL_ERROR = "COMMON_INTERNAL_ERROR"

AUTH_UNAUTHENTICATED = "AUTH_UNAUTHENTICATED"
AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
AUTH_EMAIL_NOT_VERIFIED = "AUTH_EMAIL_NOT_VERIFIED"
AUTH_ACCOUNT_SUSPENDED = "AUTH_ACCOUNT_SUSPENDED"
AUTH_REGISTRATION_CONFLICT = "AUTH_REGISTRATION_CONFLICT"
AUTH_LOGIN_LOCKED = "AUTH_LOGIN_LOCKED"

WORKSPACE_CONTEXT_REQUIRED = "WORKSPACE_CONTEXT_REQUIRED"
WORKSPACE_ACCESS_DENIED = "WORKSPACE_ACCESS_DENIED"
WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
WORKSPACE_MEMBER_NOT_FOUND = "WORKSPACE_MEMBER_NOT_FOUND"
WORKSPACE_MEMBER_CONFLICT = "WORKSPACE_MEMBER_CONFLICT"
WORKSPACE_INVITE_INVALID = "WORKSPACE_INVITE_INVALID"
WORKSPACE_MEMBER_STATE_INVALID = "WORKSPACE_MEMBER_STATE_INVALID"

WORKFLOW_NOT_FOUND = "WORKFLOW_NOT_FOUND"
WORKFLOW_VERSION_NOT_FOUND = "WORKFLOW_VERSION_NOT_FOUND"
WORKFLOW_VALIDATION_FAILED = "WORKFLOW_VALIDATION_FAILED"
WORKFLOW_STATE_CONFLICT = "WORKFLOW_STATE_CONFLICT"
WORKFLOW_GATE_CONFLICT = "WORKFLOW_GATE_CONFLICT"

TRACE_RESOURCE_NOT_FOUND = "TRACE_RESOURCE_NOT_FOUND"

ADMIN_FORBIDDEN = "ADMIN_FORBIDDEN"
ADMIN_RESOURCE_NOT_FOUND = "ADMIN_RESOURCE_NOT_FOUND"

INFRA_DATABASE_ERROR = "INFRA_DATABASE_ERROR"
INFRA_CACHE_ERROR = "INFRA_CACHE_ERROR"
INFRA_MODEL_SERVICE_ERROR = "INFRA_MODEL_SERVICE_ERROR"
INFRA_EMAIL_SERVICE_ERROR = "INFRA_EMAIL_SERVICE_ERROR"
INFRA_EXTERNAL_SERVICE_ERROR = "INFRA_EXTERNAL_SERVICE_ERROR"


def _entry(
    code: str,
    domain: ErrorDomain,
    category: ErrorCategory,
    http_status: int,
    default_message: str,
    consumer_action: ConsumerAction,
    description: str = "",
) -> ErrorCodeDefinition:
    return ErrorCodeDefinition(
        code=code,
        domain=domain,
        category=category,
        http_status=http_status,
        default_message=default_message,
        consumer_action=consumer_action,
        description=description,
    )


ERROR_REGISTRY: dict[str, ErrorCodeDefinition] = {
    COMMON_BAD_REQUEST: _entry(
        COMMON_BAD_REQUEST,
        ErrorDomain.COMMON,
        ErrorCategory.APPLICATION,
        HTTPStatus.BAD_REQUEST,
        "请求参数不合法",
        ConsumerAction.FIX_INPUT,
    ),
    COMMON_VALIDATION_ERROR: _entry(
        COMMON_VALIDATION_ERROR,
        ErrorDomain.COMMON,
        ErrorCategory.APPLICATION,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        "请求参数校验失败",
        ConsumerAction.FIX_INPUT,
    ),
    COMMON_UNAUTHORIZED: _entry(
        COMMON_UNAUTHORIZED,
        ErrorDomain.COMMON,
        ErrorCategory.APPLICATION,
        HTTPStatus.UNAUTHORIZED,
        "未登录或登录已过期",
        ConsumerAction.REAUTHENTICATE,
    ),
    COMMON_FORBIDDEN: _entry(
        COMMON_FORBIDDEN,
        ErrorDomain.COMMON,
        ErrorCategory.DOMAIN,
        HTTPStatus.FORBIDDEN,
        "当前账号无权执行该操作",
        ConsumerAction.REAUTHENTICATE,
    ),
    COMMON_NOT_FOUND: _entry(
        COMMON_NOT_FOUND,
        ErrorDomain.COMMON,
        ErrorCategory.DOMAIN,
        HTTPStatus.NOT_FOUND,
        "资源不存在",
        ConsumerAction.NOT_FOUND,
    ),
    COMMON_CONFLICT: _entry(
        COMMON_CONFLICT,
        ErrorDomain.COMMON,
        ErrorCategory.APPLICATION,
        HTTPStatus.CONFLICT,
        "当前状态不允许执行该操作",
        ConsumerAction.FIX_INPUT,
    ),
    COMMON_INTERNAL_ERROR: _entry(
        COMMON_INTERNAL_ERROR,
        ErrorDomain.COMMON,
        ErrorCategory.INFRASTRUCTURE,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "服务器开小差了，请稍后重试",
        ConsumerAction.CONTACT_ADMIN,
    ),
    AUTH_UNAUTHENTICATED: _entry(
        AUTH_UNAUTHENTICATED,
        ErrorDomain.AUTH,
        ErrorCategory.APPLICATION,
        HTTPStatus.UNAUTHORIZED,
        "请先登录后再继续",
        ConsumerAction.REAUTHENTICATE,
    ),
    AUTH_INVALID_CREDENTIALS: _entry(
        AUTH_INVALID_CREDENTIALS,
        ErrorDomain.AUTH,
        ErrorCategory.DOMAIN,
        HTTPStatus.UNAUTHORIZED,
        "邮箱或密码错误",
        ConsumerAction.REAUTHENTICATE,
    ),
    AUTH_EMAIL_NOT_VERIFIED: _entry(
        AUTH_EMAIL_NOT_VERIFIED,
        ErrorDomain.AUTH,
        ErrorCategory.DOMAIN,
        HTTPStatus.FORBIDDEN,
        "请先完成邮箱验证",
        ConsumerAction.REAUTHENTICATE,
    ),
    AUTH_ACCOUNT_SUSPENDED: _entry(
        AUTH_ACCOUNT_SUSPENDED,
        ErrorDomain.AUTH,
        ErrorCategory.DOMAIN,
        HTTPStatus.FORBIDDEN,
        "账号已被停用",
        ConsumerAction.CONTACT_ADMIN,
    ),
    AUTH_REGISTRATION_CONFLICT: _entry(
        AUTH_REGISTRATION_CONFLICT,
        ErrorDomain.AUTH,
        ErrorCategory.DOMAIN,
        HTTPStatus.BAD_REQUEST,
        "账号注册信息已存在",
        ConsumerAction.FIX_INPUT,
    ),
    AUTH_LOGIN_LOCKED: _entry(
        AUTH_LOGIN_LOCKED,
        ErrorDomain.AUTH,
        ErrorCategory.APPLICATION,
        HTTPStatus.BAD_REQUEST,
        "登录尝试次数过多，请稍后再试",
        ConsumerAction.RETRY_LATER,
    ),
    WORKSPACE_CONTEXT_REQUIRED: _entry(
        WORKSPACE_CONTEXT_REQUIRED,
        ErrorDomain.WORKSPACE,
        ErrorCategory.APPLICATION,
        HTTPStatus.BAD_REQUEST,
        "请先选择工作空间",
        ConsumerAction.FIX_INPUT,
    ),
    WORKSPACE_ACCESS_DENIED: _entry(
        WORKSPACE_ACCESS_DENIED,
        ErrorDomain.WORKSPACE,
        ErrorCategory.DOMAIN,
        HTTPStatus.FORBIDDEN,
        "您无权访问该工作空间",
        ConsumerAction.REAUTHENTICATE,
    ),
    WORKSPACE_NOT_FOUND: _entry(
        WORKSPACE_NOT_FOUND,
        ErrorDomain.WORKSPACE,
        ErrorCategory.DOMAIN,
        HTTPStatus.NOT_FOUND,
        "工作空间不存在",
        ConsumerAction.NOT_FOUND,
    ),
    WORKSPACE_MEMBER_NOT_FOUND: _entry(
        WORKSPACE_MEMBER_NOT_FOUND,
        ErrorDomain.WORKSPACE,
        ErrorCategory.DOMAIN,
        HTTPStatus.NOT_FOUND,
        "成员关系不存在",
        ConsumerAction.NOT_FOUND,
    ),
    WORKSPACE_MEMBER_CONFLICT: _entry(
        WORKSPACE_MEMBER_CONFLICT,
        ErrorDomain.WORKSPACE,
        ErrorCategory.APPLICATION,
        HTTPStatus.BAD_REQUEST,
        "当前成员状态不允许执行该操作",
        ConsumerAction.FIX_INPUT,
    ),
    WORKSPACE_INVITE_INVALID: _entry(
        WORKSPACE_INVITE_INVALID,
        ErrorDomain.WORKSPACE,
        ErrorCategory.APPLICATION,
        HTTPStatus.BAD_REQUEST,
        "邀请链接无效或已过期",
        ConsumerAction.FIX_INPUT,
    ),
    WORKSPACE_MEMBER_STATE_INVALID: _entry(
        WORKSPACE_MEMBER_STATE_INVALID,
        ErrorDomain.WORKSPACE,
        ErrorCategory.APPLICATION,
        HTTPStatus.BAD_REQUEST,
        "成员状态无效",
        ConsumerAction.FIX_INPUT,
    ),
    WORKFLOW_NOT_FOUND: _entry(
        WORKFLOW_NOT_FOUND,
        ErrorDomain.WORKFLOW,
        ErrorCategory.DOMAIN,
        HTTPStatus.NOT_FOUND,
        "工作流不存在",
        ConsumerAction.NOT_FOUND,
    ),
    WORKFLOW_VERSION_NOT_FOUND: _entry(
        WORKFLOW_VERSION_NOT_FOUND,
        ErrorDomain.WORKFLOW,
        ErrorCategory.DOMAIN,
        HTTPStatus.NOT_FOUND,
        "工作流版本不存在",
        ConsumerAction.NOT_FOUND,
    ),
    WORKFLOW_VALIDATION_FAILED: _entry(
        WORKFLOW_VALIDATION_FAILED,
        ErrorDomain.WORKFLOW,
        ErrorCategory.APPLICATION,
        HTTPStatus.BAD_REQUEST,
        "工作流未通过校验",
        ConsumerAction.FIX_INPUT,
    ),
    WORKFLOW_STATE_CONFLICT: _entry(
        WORKFLOW_STATE_CONFLICT,
        ErrorDomain.WORKFLOW,
        ErrorCategory.APPLICATION,
        HTTPStatus.CONFLICT,
        "当前工作流状态不允许执行该操作",
        ConsumerAction.FIX_INPUT,
    ),
    WORKFLOW_GATE_CONFLICT: _entry(
        WORKFLOW_GATE_CONFLICT,
        ErrorDomain.WORKFLOW,
        ErrorCategory.APPLICATION,
        HTTPStatus.CONFLICT,
        "当前工作流正等待人工处理",
        ConsumerAction.FIX_INPUT,
    ),
    TRACE_RESOURCE_NOT_FOUND: _entry(
        TRACE_RESOURCE_NOT_FOUND,
        ErrorDomain.TRACE,
        ErrorCategory.DOMAIN,
        HTTPStatus.NOT_FOUND,
        "Trace 资源不存在",
        ConsumerAction.NOT_FOUND,
    ),
    ADMIN_FORBIDDEN: _entry(
        ADMIN_FORBIDDEN,
        ErrorDomain.ADMIN,
        ErrorCategory.DOMAIN,
        HTTPStatus.FORBIDDEN,
        "仅管理员可执行该操作",
        ConsumerAction.REAUTHENTICATE,
    ),
    ADMIN_RESOURCE_NOT_FOUND: _entry(
        ADMIN_RESOURCE_NOT_FOUND,
        ErrorDomain.ADMIN,
        ErrorCategory.DOMAIN,
        HTTPStatus.NOT_FOUND,
        "管理后台资源不存在",
        ConsumerAction.NOT_FOUND,
    ),
    INFRA_DATABASE_ERROR: _entry(
        INFRA_DATABASE_ERROR,
        ErrorDomain.INFRA,
        ErrorCategory.INFRASTRUCTURE,
        HTTPStatus.SERVICE_UNAVAILABLE,
        "数据库暂时不可用，请稍后重试",
        ConsumerAction.RETRY_LATER,
    ),
    INFRA_CACHE_ERROR: _entry(
        INFRA_CACHE_ERROR,
        ErrorDomain.INFRA,
        ErrorCategory.INFRASTRUCTURE,
        HTTPStatus.SERVICE_UNAVAILABLE,
        "缓存服务暂时不可用，请稍后重试",
        ConsumerAction.RETRY_LATER,
    ),
    INFRA_MODEL_SERVICE_ERROR: _entry(
        INFRA_MODEL_SERVICE_ERROR,
        ErrorDomain.INFRA,
        ErrorCategory.INFRASTRUCTURE,
        HTTPStatus.SERVICE_UNAVAILABLE,
        "模型服务暂时不可用，请稍后重试",
        ConsumerAction.RETRY_LATER,
    ),
    INFRA_EMAIL_SERVICE_ERROR: _entry(
        INFRA_EMAIL_SERVICE_ERROR,
        ErrorDomain.INFRA,
        ErrorCategory.INFRASTRUCTURE,
        HTTPStatus.SERVICE_UNAVAILABLE,
        "邮件服务暂时不可用，请稍后重试",
        ConsumerAction.RETRY_LATER,
    ),
    INFRA_EXTERNAL_SERVICE_ERROR: _entry(
        INFRA_EXTERNAL_SERVICE_ERROR,
        ErrorDomain.INFRA,
        ErrorCategory.INFRASTRUCTURE,
        HTTPStatus.SERVICE_UNAVAILABLE,
        "外部依赖暂时不可用，请稍后重试",
        ConsumerAction.RETRY_LATER,
    ),
}


HTTP_STATUS_CODE_FALLBACKS: dict[int, str] = {
    HTTPStatus.BAD_REQUEST: COMMON_BAD_REQUEST,
    HTTPStatus.UNAUTHORIZED: COMMON_UNAUTHORIZED,
    HTTPStatus.FORBIDDEN: COMMON_FORBIDDEN,
    HTTPStatus.NOT_FOUND: COMMON_NOT_FOUND,
    HTTPStatus.CONFLICT: COMMON_CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY: COMMON_VALIDATION_ERROR,
}


LEGACY_NUMERIC_ERROR_CODES: dict[str, int] = {
    COMMON_BAD_REQUEST: 40000,
    COMMON_VALIDATION_ERROR: 40000,
    COMMON_UNAUTHORIZED: 40100,
    AUTH_UNAUTHENTICATED: 40100,
    AUTH_INVALID_CREDENTIALS: 40100,
    COMMON_FORBIDDEN: 40300,
    AUTH_EMAIL_NOT_VERIFIED: 40300,
    AUTH_ACCOUNT_SUSPENDED: 40300,
    WORKSPACE_ACCESS_DENIED: 40300,
    ADMIN_FORBIDDEN: 40300,
    COMMON_NOT_FOUND: 40400,
    WORKSPACE_NOT_FOUND: 40400,
    WORKSPACE_MEMBER_NOT_FOUND: 40400,
    WORKFLOW_NOT_FOUND: 40400,
    WORKFLOW_VERSION_NOT_FOUND: 40400,
    TRACE_RESOURCE_NOT_FOUND: 40400,
    ADMIN_RESOURCE_NOT_FOUND: 40400,
    WORKFLOW_VALIDATION_FAILED: 40000,
    COMMON_CONFLICT: 40900,
    WORKFLOW_STATE_CONFLICT: 40900,
    WORKFLOW_GATE_CONFLICT: 40900,
    COMMON_INTERNAL_ERROR: 50000,
    INFRA_DATABASE_ERROR: 50000,
    INFRA_CACHE_ERROR: 50000,
    INFRA_MODEL_SERVICE_ERROR: 50000,
    INFRA_EMAIL_SERVICE_ERROR: 50000,
    INFRA_EXTERNAL_SERVICE_ERROR: 50000,
}


def get_error_definition(code: str) -> ErrorCodeDefinition:
    """按稳定错误码读取注册项。"""

    return ERROR_REGISTRY[code]


def get_fallback_code_for_status(http_status: int) -> str:
    """根据 HTTP 状态码选择最小兜底错误码。"""

    return HTTP_STATUS_CODE_FALLBACKS.get(http_status, COMMON_INTERNAL_ERROR)


def get_legacy_numeric_code(code: str) -> int:
    """兼容旧 Result 风格的数字错误码。"""

    return LEGACY_NUMERIC_ERROR_CODES.get(code, 50000)
