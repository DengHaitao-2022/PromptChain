"""
统一错误码注册表。
"""

from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus


class ErrorDomain(StrEnum):
    """错误域枚举。"""

    COMMON = "COMMON"
    AUTH = "AUTH"
    WORKSPACE = "WORKSPACE"
    WORKFLOW = "WORKFLOW"
    TRACE = "TRACE"
    ADMIN = "ADMIN"
    INFRA = "INFRA"


class ErrorCategory(StrEnum):
    """错误类别枚举。"""

    DOMAIN = "domain"
    APPLICATION = "application"
    INFRASTRUCTURE = "infrastructure"


class ConsumerAction(StrEnum):
    """调用方处理方向。"""

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
    description: str
    default_message: str
    consumer_action: ConsumerAction


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
    *,
    code: str,
    domain: ErrorDomain,
    category: ErrorCategory,
    http_status: int,
    description: str,
    default_message: str,
    consumer_action: ConsumerAction,
) -> ErrorCodeDefinition:
    return ErrorCodeDefinition(
        code=code,
        domain=domain,
        category=category,
        http_status=http_status,
        description=description,
        default_message=default_message,
        consumer_action=consumer_action,
    )


ERROR_REGISTRY: dict[str, ErrorCodeDefinition] = {
    COMMON_BAD_REQUEST: _entry(
        code=COMMON_BAD_REQUEST,
        domain=ErrorDomain.COMMON,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.BAD_REQUEST,
        description="通用请求错误。",
        default_message="请求参数不合法",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    COMMON_VALIDATION_ERROR: _entry(
        code=COMMON_VALIDATION_ERROR,
        domain=ErrorDomain.COMMON,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.UNPROCESSABLE_ENTITY,
        description="请求体验证失败。",
        default_message="请求参数校验失败",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    COMMON_UNAUTHORIZED: _entry(
        code=COMMON_UNAUTHORIZED,
        domain=ErrorDomain.COMMON,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.UNAUTHORIZED,
        description="调用方尚未通过身份校验。",
        default_message="未登录或登录已过期",
        consumer_action=ConsumerAction.REAUTHENTICATE,
    ),
    COMMON_FORBIDDEN: _entry(
        code=COMMON_FORBIDDEN,
        domain=ErrorDomain.COMMON,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.FORBIDDEN,
        description="调用方无权访问目标资源。",
        default_message="当前账号无权执行该操作",
        consumer_action=ConsumerAction.REAUTHENTICATE,
    ),
    COMMON_NOT_FOUND: _entry(
        code=COMMON_NOT_FOUND,
        domain=ErrorDomain.COMMON,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.NOT_FOUND,
        description="目标资源不存在。",
        default_message="资源不存在",
        consumer_action=ConsumerAction.NOT_FOUND,
    ),
    COMMON_CONFLICT: _entry(
        code=COMMON_CONFLICT,
        domain=ErrorDomain.COMMON,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.CONFLICT,
        description="当前资源状态与请求冲突。",
        default_message="当前状态不允许执行该操作",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    COMMON_INTERNAL_ERROR: _entry(
        code=COMMON_INTERNAL_ERROR,
        domain=ErrorDomain.COMMON,
        category=ErrorCategory.INFRASTRUCTURE,
        http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
        description="未归类的内部错误。",
        default_message="服务器开小差了，请稍后重试",
        consumer_action=ConsumerAction.CONTACT_ADMIN,
    ),
    AUTH_UNAUTHENTICATED: _entry(
        code=AUTH_UNAUTHENTICATED,
        domain=ErrorDomain.AUTH,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.UNAUTHORIZED,
        description="认证上下文缺失或失效。",
        default_message="请先登录后再继续",
        consumer_action=ConsumerAction.REAUTHENTICATE,
    ),
    AUTH_INVALID_CREDENTIALS: _entry(
        code=AUTH_INVALID_CREDENTIALS,
        domain=ErrorDomain.AUTH,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.UNAUTHORIZED,
        description="用户名或密码不正确。",
        default_message="邮箱或密码错误",
        consumer_action=ConsumerAction.REAUTHENTICATE,
    ),
    AUTH_EMAIL_NOT_VERIFIED: _entry(
        code=AUTH_EMAIL_NOT_VERIFIED,
        domain=ErrorDomain.AUTH,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.FORBIDDEN,
        description="账号尚未完成邮箱验证。",
        default_message="请先完成邮箱验证",
        consumer_action=ConsumerAction.REAUTHENTICATE,
    ),
    AUTH_ACCOUNT_SUSPENDED: _entry(
        code=AUTH_ACCOUNT_SUSPENDED,
        domain=ErrorDomain.AUTH,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.FORBIDDEN,
        description="账号已被停用。",
        default_message="账号已被停用",
        consumer_action=ConsumerAction.CONTACT_ADMIN,
    ),
    AUTH_REGISTRATION_CONFLICT: _entry(
        code=AUTH_REGISTRATION_CONFLICT,
        domain=ErrorDomain.AUTH,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.BAD_REQUEST,
        description="注册信息与现有账号冲突。",
        default_message="账号注册信息已存在",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    AUTH_LOGIN_LOCKED: _entry(
        code=AUTH_LOGIN_LOCKED,
        domain=ErrorDomain.AUTH,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.BAD_REQUEST,
        description="登录尝试次数过多，当前登录被暂时锁定。",
        default_message="登录尝试次数过多，请稍后再试",
        consumer_action=ConsumerAction.RETRY_LATER,
    ),
    WORKSPACE_CONTEXT_REQUIRED: _entry(
        code=WORKSPACE_CONTEXT_REQUIRED,
        domain=ErrorDomain.WORKSPACE,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.BAD_REQUEST,
        description="请求缺少工作空间上下文。",
        default_message="请先选择工作空间",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    WORKSPACE_ACCESS_DENIED: _entry(
        code=WORKSPACE_ACCESS_DENIED,
        domain=ErrorDomain.WORKSPACE,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.FORBIDDEN,
        description="当前用户无权访问目标工作空间。",
        default_message="您无权访问该工作空间",
        consumer_action=ConsumerAction.REAUTHENTICATE,
    ),
    WORKSPACE_NOT_FOUND: _entry(
        code=WORKSPACE_NOT_FOUND,
        domain=ErrorDomain.WORKSPACE,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.NOT_FOUND,
        description="工作空间不存在。",
        default_message="工作空间不存在",
        consumer_action=ConsumerAction.NOT_FOUND,
    ),
    WORKSPACE_MEMBER_NOT_FOUND: _entry(
        code=WORKSPACE_MEMBER_NOT_FOUND,
        domain=ErrorDomain.WORKSPACE,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.NOT_FOUND,
        description="目标成员关系不存在。",
        default_message="成员关系不存在",
        consumer_action=ConsumerAction.NOT_FOUND,
    ),
    WORKSPACE_MEMBER_CONFLICT: _entry(
        code=WORKSPACE_MEMBER_CONFLICT,
        domain=ErrorDomain.WORKSPACE,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.BAD_REQUEST,
        description="成员关系或邀请状态与当前请求冲突。",
        default_message="当前成员状态不允许执行该操作",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    WORKSPACE_INVITE_INVALID: _entry(
        code=WORKSPACE_INVITE_INVALID,
        domain=ErrorDomain.WORKSPACE,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.BAD_REQUEST,
        description="工作空间邀请链接无效或已过期。",
        default_message="邀请链接无效或已过期",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    WORKSPACE_MEMBER_STATE_INVALID: _entry(
        code=WORKSPACE_MEMBER_STATE_INVALID,
        domain=ErrorDomain.WORKSPACE,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.BAD_REQUEST,
        description="成员角色或访问状态非法。",
        default_message="成员状态无效",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    WORKFLOW_NOT_FOUND: _entry(
        code=WORKFLOW_NOT_FOUND,
        domain=ErrorDomain.WORKFLOW,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.NOT_FOUND,
        description="工作流运行记录不存在。",
        default_message="工作流不存在",
        consumer_action=ConsumerAction.NOT_FOUND,
    ),
    WORKFLOW_VERSION_NOT_FOUND: _entry(
        code=WORKFLOW_VERSION_NOT_FOUND,
        domain=ErrorDomain.WORKFLOW,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.NOT_FOUND,
        description="工作流版本快照不存在。",
        default_message="工作流版本不存在",
        consumer_action=ConsumerAction.NOT_FOUND,
    ),
    WORKFLOW_VALIDATION_FAILED: _entry(
        code=WORKFLOW_VALIDATION_FAILED,
        domain=ErrorDomain.WORKFLOW,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.BAD_REQUEST,
        description="工作流定义未通过发布或执行前校验。",
        default_message="工作流未通过校验",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    WORKFLOW_STATE_CONFLICT: _entry(
        code=WORKFLOW_STATE_CONFLICT,
        domain=ErrorDomain.WORKFLOW,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.CONFLICT,
        description="工作流状态冲突。",
        default_message="当前工作流状态不允许执行该操作",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    WORKFLOW_GATE_CONFLICT: _entry(
        code=WORKFLOW_GATE_CONFLICT,
        domain=ErrorDomain.WORKFLOW,
        category=ErrorCategory.APPLICATION,
        http_status=HTTPStatus.CONFLICT,
        description="工作流当前停留在人工 Gate，不能执行目标操作。",
        default_message="当前工作流正等待人工处理",
        consumer_action=ConsumerAction.FIX_INPUT,
    ),
    TRACE_RESOURCE_NOT_FOUND: _entry(
        code=TRACE_RESOURCE_NOT_FOUND,
        domain=ErrorDomain.TRACE,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.NOT_FOUND,
        description="Trace 相关资源不存在。",
        default_message="Trace 资源不存在",
        consumer_action=ConsumerAction.NOT_FOUND,
    ),
    ADMIN_FORBIDDEN: _entry(
        code=ADMIN_FORBIDDEN,
        domain=ErrorDomain.ADMIN,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.FORBIDDEN,
        description="当前账号无管理员权限。",
        default_message="仅管理员可执行该操作",
        consumer_action=ConsumerAction.REAUTHENTICATE,
    ),
    ADMIN_RESOURCE_NOT_FOUND: _entry(
        code=ADMIN_RESOURCE_NOT_FOUND,
        domain=ErrorDomain.ADMIN,
        category=ErrorCategory.DOMAIN,
        http_status=HTTPStatus.NOT_FOUND,
        description="管理后台目标资源不存在。",
        default_message="管理后台资源不存在",
        consumer_action=ConsumerAction.NOT_FOUND,
    ),
    INFRA_DATABASE_ERROR: _entry(
        code=INFRA_DATABASE_ERROR,
        domain=ErrorDomain.INFRA,
        category=ErrorCategory.INFRASTRUCTURE,
        http_status=HTTPStatus.SERVICE_UNAVAILABLE,
        description="数据库不可用或调用失败。",
        default_message="数据库暂时不可用，请稍后重试",
        consumer_action=ConsumerAction.RETRY_LATER,
    ),
    INFRA_CACHE_ERROR: _entry(
        code=INFRA_CACHE_ERROR,
        domain=ErrorDomain.INFRA,
        category=ErrorCategory.INFRASTRUCTURE,
        http_status=HTTPStatus.SERVICE_UNAVAILABLE,
        description="缓存系统不可用或调用失败。",
        default_message="缓存服务暂时不可用，请稍后重试",
        consumer_action=ConsumerAction.RETRY_LATER,
    ),
    INFRA_MODEL_SERVICE_ERROR: _entry(
        code=INFRA_MODEL_SERVICE_ERROR,
        domain=ErrorDomain.INFRA,
        category=ErrorCategory.INFRASTRUCTURE,
        http_status=HTTPStatus.SERVICE_UNAVAILABLE,
        description="模型服务不可用或调用失败。",
        default_message="模型服务暂时不可用，请稍后重试",
        consumer_action=ConsumerAction.RETRY_LATER,
    ),
    INFRA_EMAIL_SERVICE_ERROR: _entry(
        code=INFRA_EMAIL_SERVICE_ERROR,
        domain=ErrorDomain.INFRA,
        category=ErrorCategory.INFRASTRUCTURE,
        http_status=HTTPStatus.SERVICE_UNAVAILABLE,
        description="邮件服务不可用或调用失败。",
        default_message="邮件服务暂时不可用，请稍后重试",
        consumer_action=ConsumerAction.RETRY_LATER,
    ),
    INFRA_EXTERNAL_SERVICE_ERROR: _entry(
        code=INFRA_EXTERNAL_SERVICE_ERROR,
        domain=ErrorDomain.INFRA,
        category=ErrorCategory.INFRASTRUCTURE,
        http_status=HTTPStatus.SERVICE_UNAVAILABLE,
        description="外部依赖服务不可用。",
        default_message="外部依赖暂时不可用，请稍后重试",
        consumer_action=ConsumerAction.RETRY_LATER,
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
