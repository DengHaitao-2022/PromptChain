"""LLM 调用异常归一化工具。"""

from collections.abc import Iterator


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_llm_rate_limit_error(exc: BaseException) -> bool:
    """识别 OpenAI/GitHub Models 等兼容接口的限流类错误。"""
    for chained in _iter_exception_chain(exc):
        status_code = getattr(chained, "status_code", None)
        if status_code == 429:
            return True

        name = chained.__class__.__name__.lower()
        message = str(chained).lower()
        if "ratelimit" in name or "rate limit" in message or "too many requests" in message:
            return True

    return False


def is_llm_service_error(exc: BaseException) -> bool:
    """识别第三方模型服务异常，避免原始错误穿透到工作流接口。"""
    if is_llm_rate_limit_error(exc):
        return True

    provider_modules = ("openai", "anthropic", "google", "langchain")
    provider_class_names = (
        "APIError",
        "APIConnectionError",
        "APITimeoutError",
        "AuthenticationError",
        "BadRequestError",
        "PermissionDeniedError",
    )

    for chained in _iter_exception_chain(exc):
        module = chained.__class__.__module__.lower()
        class_name = chained.__class__.__name__
        if module.startswith(provider_modules):
            return True
        if class_name in provider_class_names:
            return True

    return False


def is_retryable_llm_error(exc: BaseException) -> bool:
    """识别适合短暂退避后重试的模型服务异常。"""
    retryable_status_codes = {408, 409, 429, 500, 502, 503, 504}
    retryable_class_names = {
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "ServiceUnavailableError",
    }

    for chained in _iter_exception_chain(exc):
        status_code = getattr(chained, "status_code", None)
        if status_code in retryable_status_codes:
            return True
        if chained.__class__.__name__ in retryable_class_names:
            return True

    return is_llm_rate_limit_error(exc)


def format_workflow_error(exc: BaseException) -> str:
    """生成可给用户展示的稳定错误文案。"""
    if is_llm_rate_limit_error(exc):
        return "模型服务请求过于频繁，请稍后重试或切换模型供应商。"

    if is_llm_service_error(exc):
        return "模型服务暂时不可用，请稍后重试。"

    return str(exc) or exc.__class__.__name__
