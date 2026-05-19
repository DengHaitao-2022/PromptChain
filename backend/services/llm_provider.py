"""
LLM Provider 抽象层

支持多个 LLM 提供商的统一接口:
- OpenAI (GPT-4, GPT-4o)
- Anthropic (Claude)
- Ollama (本地模型)
- Google (Gemini)
- GitHub Models (GitHub Copilot)
- Fake (smoke 验收专用)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.future import select

from core.config import get_settings
from services.secret_crypto import decrypt_config_value
from services.structured_output_prompt import build_structured_chat_prompt

DEFAULT_PROVIDER_NAME = "openai"
DEFAULT_FALLBACK_MODEL = "gpt-4o"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"
INTERNAL_PROVIDER_NAMES = {"fake"}


def _read_env(name: str) -> str:
    """从统一配置源读取字段并去除首尾空白。"""
    value = getattr(get_settings(), name, "")
    return str(value).strip() if value is not None else ""


def _resolve_provider_name(provider_name: str | None = None) -> str:
    """统一解析当前 provider 名称。"""
    return (provider_name or _read_env("DEFAULT_LLM_PROVIDER") or DEFAULT_PROVIDER_NAME).lower()


def _resolve_model_override() -> str | None:
    """统一解析全局模型覆盖值。"""
    value = _read_env("DEFAULT_MODEL_NAME")
    return value or None


def _build_unsupported_provider_error(
    provider_name: str,
    supported_providers: list[str],
) -> ValueError:
    """生成不支持 provider 的统一错误。"""
    supported_list = ", ".join(supported_providers)
    return ValueError(f"不支持的 LLM 提供商: {provider_name}，支持: {supported_list}")


def _build_missing_credential_error(provider_name: str, env_name: str) -> ValueError:
    """生成缺少凭证的统一错误。"""
    return ValueError(f"{provider_name} provider 初始化失败: 缺少 {env_name} 环境变量")


class LLMProvider(ABC):
    """LLM 提供商抽象基类"""

    def __init__(self, registration: ProviderRegistration):
        self.registration = registration

    @abstractmethod
    def get_model(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        """获取 LangChain 兼容的模型实例"""
        raise NotImplementedError

    def get_default_model_name(self) -> str:
        """获取默认模型名称。"""
        return _resolve_model_override() or self.registration.default_model_name

    def resolve_model_name(self, model_name: str | None = None) -> str:
        """统一解析显式模型、全局覆盖值和 provider 默认值。"""
        return model_name or self.get_default_model_name()

    def require_credential(self) -> str:
        """按 provider 元数据读取并校验必需凭证。"""
        env_name = self.registration.credential_env
        if not env_name:
            raise ValueError(f"{self.registration.name} provider 未声明凭证字段")

        credential = _read_env(env_name)
        if not credential:
            raise _build_missing_credential_error(self.registration.name, env_name)
        return credential

    def get_structured_output_model(
        self,
        schema: type[BaseModel],
        model_name: str | None = None,
        **kwargs,
    ) -> BaseChatModel:
        """获取支持结构化输出的模型"""
        model = self.get_model(model_name, **kwargs)
        return model.with_structured_output(schema)


class OpenAIProvider(LLMProvider):
    """OpenAI 提供商"""

    def __init__(self, registration: ProviderRegistration):
        super().__init__(registration)
        self.api_key = self.require_credential()

    def get_model(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.resolve_model_name(model_name),
            api_key=self.api_key,
            **kwargs,
        )


class AnthropicProvider(LLMProvider):
    """Anthropic 提供商"""

    def __init__(self, registration: ProviderRegistration):
        super().__init__(registration)
        self.api_key = self.require_credential()

    def get_model(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=self.resolve_model_name(model_name),
            api_key=self.api_key,
            **kwargs,
        )


class OllamaProvider(LLMProvider):
    """Ollama 本地模型提供商"""

    def __init__(self, registration: ProviderRegistration):
        super().__init__(registration)
        self.base_url = _read_env("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL

    def get_model(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=self.resolve_model_name(model_name),
            base_url=self.base_url,
            **kwargs,
        )


class GoogleProvider(LLMProvider):
    """Google Gemini 提供商"""

    def __init__(self, registration: ProviderRegistration):
        super().__init__(registration)
        self.api_key = self.require_credential()

    def get_model(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Source: LangChain Google 集成文档; 显式传递 google_api_key，避免依赖第三方环境变量回退。
        return ChatGoogleGenerativeAI(
            model=self.resolve_model_name(model_name),
            google_api_key=self.api_key,
            **kwargs,
        )


class GitHubProvider(LLMProvider):
    """GitHub Models 提供商"""

    def __init__(self, registration: ProviderRegistration):
        super().__init__(registration)
        self.api_key = self.require_credential()
        self.base_url = DEFAULT_GITHUB_MODELS_BASE_URL

    def get_default_model_name(self) -> str:
        """GitHub Models 使用自身默认模型，避免被全局默认模型覆盖。"""
        return self.registration.default_model_name

    def get_model(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.resolve_model_name(model_name),
            base_url=self.base_url,
            api_key=self.api_key,
            **kwargs,
        )


class FakeProvider(LLMProvider):
    """Smoke 验收专用 provider；必须显式选择，不参与生产 provider 回退。"""

    def get_default_model_name(self) -> str:
        return self.registration.default_model_name

    def get_model(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        from services.fake_llm_provider import FakeSmokeChatModel

        return FakeSmokeChatModel(model_name=model_name or self.get_default_model_name())


@dataclass(frozen=True)
class ProviderRegistration:
    """Provider registry 的最小元数据。"""

    name: str
    provider_class: type[LLMProvider]
    default_model_name: str
    credential_env: str | None = None


@dataclass(frozen=True)
class RuntimeModelConfig:
    """运行时实际使用的模型配置。"""

    provider: str
    model: str
    credential: str | None = None
    base_url: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    source: str = "environment"
    structured_output_method: str | None = None


@dataclass(frozen=True)
class StructuredLLMRuntime:
    """结构化输出运行时信息。"""

    llm: Any
    runtime_config: RuntimeModelConfig
    effective_method: str | None


# 统一 registry 只声明支持列表与默认元数据，避免分支判断散落到 helper 中。
PROVIDER_REGISTRY: dict[str, ProviderRegistration] = {
    "openai": ProviderRegistration(
        name="openai",
        provider_class=OpenAIProvider,
        default_model_name="gpt-4o",
        credential_env="OPENAI_API_KEY",
    ),
    "anthropic": ProviderRegistration(
        name="anthropic",
        provider_class=AnthropicProvider,
        default_model_name="claude-3-5-sonnet-20241022",
        credential_env="ANTHROPIC_API_KEY",
    ),
    "ollama": ProviderRegistration(
        name="ollama",
        provider_class=OllamaProvider,
        default_model_name="qwen2.5:14b",
    ),
    "google": ProviderRegistration(
        name="google",
        provider_class=GoogleProvider,
        default_model_name="gemini-2.5-flash",
        credential_env="GEMINI_API_KEY",
    ),
    "github": ProviderRegistration(
        name="github",
        provider_class=GitHubProvider,
        default_model_name="openai/gpt-4.1",
        credential_env="GITHUB_MODEL_TOKEN",
    ),
    "fake": ProviderRegistration(
        name="fake",
        provider_class=FakeProvider,
        default_model_name="fake-smoke-model",
    ),
}


class LLMProviderFactory:
    """LLM 提供商工厂"""

    _registry: ClassVar[dict[str, ProviderRegistration]] = PROVIDER_REGISTRY
    _instances: ClassVar[dict[str, LLMProvider]] = {}

    @classmethod
    def get_supported_provider_names(cls) -> list[str]:
        """返回当前支持的 provider 名称列表。"""
        return [name for name in cls._registry if name not in INTERNAL_PROVIDER_NAMES]

    @classmethod
    def get_registration(cls, provider_name: str | None = None) -> ProviderRegistration:
        """根据 provider 名称读取 registry 元数据。"""
        resolved_name = _resolve_provider_name(provider_name)
        registration = cls._registry.get(resolved_name)
        if registration is None:
            raise _build_unsupported_provider_error(
                resolved_name,
                cls.get_supported_provider_names(),
            )
        return registration

    @classmethod
    def get_provider(cls, provider_name: str | None = None) -> LLMProvider:
        """
        获取 LLM 提供商实例（单例模式）

        Args:
            provider_name: 提供商名称，默认从环境变量读取
        """
        registration = cls.get_registration(provider_name)
        if registration.name not in cls._instances:
            cls._instances[registration.name] = registration.provider_class(registration)
        return cls._instances[registration.name]

    @classmethod
    def get_resolved_model_name(
        cls,
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> str:
        """统一解析当前 provider 实际使用的模型名称。"""
        if model_name:
            return model_name

        registration = cls.get_registration(provider_name)
        if registration.name in INTERNAL_PROVIDER_NAMES:
            return registration.default_model_name
        return _resolve_model_override() or registration.default_model_name

    @classmethod
    def get_model(
        cls,
        provider_name: str | None = None,
        model_name: str | None = None,
        **kwargs,
    ) -> BaseChatModel:
        """
        快捷方法: 直接获取模型实例
        """
        provider = cls.get_provider(provider_name)
        return provider.get_model(model_name, **kwargs)

    @classmethod
    def get_structured_model(
        cls,
        schema: type[BaseModel],
        provider_name: str | None = None,
        model_name: str | None = None,
        **kwargs,
    ) -> BaseChatModel:
        """
        快捷方法: 获取支持结构化输出的模型
        """
        provider = cls.get_provider(provider_name)
        return provider.get_structured_output_model(schema, model_name, **kwargs)


_MODEL_CONFIG_KEYS = ("model", "model_name")
_BASE_URL_CONFIG_KEYS = ("base_url", "endpoint", "api_base")
_STRUCTURED_OUTPUT_METHOD_KEYS = ("structured_output_method", "response_format_method")
_CREDENTIAL_CONFIG_KEYS: dict[str, tuple[str, ...]] = {
    "openai": ("api_key", "openai_api_key"),
    "anthropic": ("api_key", "anthropic_api_key"),
    "google": ("api_key", "google_api_key", "gemini_api_key"),
    "github": ("api_key", "github_model_token", "token"),
}
_RUNTIME_DEFAULT_CONFIG_KEY = "_runtime_default"
_ALLOWED_STRUCTURED_OUTPUT_METHODS = {"json_schema", "json_mode", "function_calling"}
_OPENAI_COMPATIBLE_METHOD_PROVIDERS = {"openai", "github"}


def _clean_config_value(value: Any) -> str | None:
    """读取用户配置值，兼容加密结构和空白值。"""
    raw_value = decrypt_config_value(value)
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized or None


def _pick_config_value(config: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """按候选 key 读取第一个有效配置值。"""
    for key in keys:
        if key in config:
            value = _clean_config_value(config[key])
            if value:
                return value
    return None


def _is_runtime_default(config: dict[str, Any] | None) -> bool:
    """判断配置是否被标记为运行默认。"""
    return bool((config or {}).get(_RUNTIME_DEFAULT_CONFIG_KEY))


def _normalize_structured_output_method(value: str | None) -> str | None:
    """标准化结构化输出模式配置。"""
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _supports_explicit_structured_output_method(runtime_config: RuntimeModelConfig) -> bool:
    """当前仅对 langchain-openai 路径显式传 method，避免影响其它 provider。"""
    return runtime_config.provider in _OPENAI_COMPATIBLE_METHOD_PROVIDERS


def _resolve_effective_structured_output_method(
    runtime_config: RuntimeModelConfig,
    *,
    method_override: str | None = None,
) -> str | None:
    """解析最终生效的结构化输出模式。"""
    method = _normalize_structured_output_method(method_override)
    if method is None:
        method = _normalize_structured_output_method(runtime_config.structured_output_method)

    if method == "auto":
        method = None

    if method is not None and method not in _ALLOWED_STRUCTURED_OUTPUT_METHODS:
        supported = ", ".join(sorted(_ALLOWED_STRUCTURED_OUTPUT_METHODS))
        raise ValueError(f"不支持的 structured_output_method: {method}，支持: {supported}")

    if method is not None:
        return method if _supports_explicit_structured_output_method(runtime_config) else None

    base_url = (runtime_config.base_url or "").lower()
    if _supports_explicit_structured_output_method(runtime_config) and "hf.space" in base_url:
        return "json_mode"

    return None


def _bind_structured_output_model(
    llm: BaseChatModel,
    schema: type[BaseModel],
    runtime_config: RuntimeModelConfig,
    *,
    method_override: str | None = None,
):
    """按运行时配置绑定结构化输出模式。"""
    method = _resolve_effective_structured_output_method(
        runtime_config,
        method_override=method_override,
    )
    if method:
        return llm.with_structured_output(schema, method=method, include_raw=True)
    return llm.with_structured_output(schema, include_raw=True)


def _build_environment_runtime_config(
    provider_name: str | None = None,
    model_name: str | None = None,
) -> RuntimeModelConfig:
    """构建环境变量来源的运行时配置。"""
    registration = LLMProviderFactory.get_registration(provider_name)
    credential = _read_env(registration.credential_env) if registration.credential_env else None
    base_url = _read_env("OLLAMA_BASE_URL") if registration.name == "ollama" else None
    if registration.name == "github":
        base_url = DEFAULT_GITHUB_MODELS_BASE_URL
    resolved_model = (
        model_name
        or (
            registration.default_model_name
            if registration.name == "fake"
            else _resolve_model_override()
        )
        or registration.default_model_name
    )

    return RuntimeModelConfig(
        provider=registration.name,
        model=resolved_model,
        credential=credential,
        base_url=base_url,
        source="environment",
    )


def _build_workspace_runtime_config(provider_row: Any) -> RuntimeModelConfig:
    """从工作空间模型供应商记录构建运行时配置。"""
    registration = LLMProviderFactory.get_registration(provider_row.provider)
    config = dict(provider_row.config or {})
    credential_keys = _CREDENTIAL_CONFIG_KEYS.get(registration.name, ())
    credential = _pick_config_value(config, credential_keys)
    if credential is None and registration.credential_env:
        credential = _read_env(registration.credential_env)

    base_url = _pick_config_value(config, _BASE_URL_CONFIG_KEYS)
    if base_url is None:
        if registration.name == "ollama":
            base_url = _read_env("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL
        elif registration.name == "github":
            base_url = DEFAULT_GITHUB_MODELS_BASE_URL

    return RuntimeModelConfig(
        provider=registration.name,
        model=_pick_config_value(config, _MODEL_CONFIG_KEYS) or registration.default_model_name,
        credential=credential,
        base_url=base_url,
        provider_id=provider_row.id,
        provider_name=provider_row.name,
        source="workspace",
        structured_output_method=_pick_config_value(config, _STRUCTURED_OUTPUT_METHOD_KEYS),
    )


def _build_model_from_runtime_config(
    runtime_config: RuntimeModelConfig,
    **kwargs,
) -> BaseChatModel:
    """根据运行时配置创建 LangChain 模型实例。"""
    if runtime_config.provider == "openai":
        from langchain_openai import ChatOpenAI

        if not runtime_config.credential:
            raise _build_missing_credential_error("openai", "OPENAI_API_KEY")
        openai_kwargs: dict[str, Any] = {
            "model": runtime_config.model,
            "api_key": runtime_config.credential,
            **kwargs,
        }
        openai_kwargs.setdefault("stream_usage", True)
        if runtime_config.base_url:
            openai_kwargs["base_url"] = runtime_config.base_url
        return ChatOpenAI(**openai_kwargs)

    if runtime_config.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not runtime_config.credential:
            raise _build_missing_credential_error("anthropic", "ANTHROPIC_API_KEY")
        return ChatAnthropic(
            model=runtime_config.model,
            api_key=runtime_config.credential,
            **kwargs,
        )

    if runtime_config.provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not runtime_config.credential:
            raise _build_missing_credential_error("google", "GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(
            model=runtime_config.model,
            google_api_key=runtime_config.credential,
            **kwargs,
        )

    if runtime_config.provider == "github":
        from langchain_openai import ChatOpenAI

        if not runtime_config.credential:
            raise _build_missing_credential_error("github", "GITHUB_MODEL_TOKEN")
        github_kwargs: dict[str, Any] = {
            "model": runtime_config.model,
            "base_url": runtime_config.base_url or DEFAULT_GITHUB_MODELS_BASE_URL,
            "api_key": runtime_config.credential,
            **kwargs,
        }
        github_kwargs.setdefault("stream_usage", True)
        return ChatOpenAI(**github_kwargs)

    if runtime_config.provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=runtime_config.model,
            base_url=runtime_config.base_url or DEFAULT_OLLAMA_BASE_URL,
            **kwargs,
        )

    if runtime_config.provider == "fake":
        from services.fake_llm_provider import FakeSmokeChatModel

        return FakeSmokeChatModel(model_name=runtime_config.model)

    raise _build_unsupported_provider_error(
        runtime_config.provider,
        LLMProviderFactory.get_supported_provider_names(),
    )


def _runtime_config_to_info(runtime_config: RuntimeModelConfig) -> dict[str, Any]:
    """转换为可返回给前端或写入 LLMCallRecord 的脱敏读模型。"""
    try:
        effective_structured_output_method = _resolve_effective_structured_output_method(
            runtime_config
        )
    except ValueError:
        effective_structured_output_method = runtime_config.structured_output_method

    return {
        "provider": runtime_config.provider,
        "model": runtime_config.model,
        "source": runtime_config.source,
        "provider_id": runtime_config.provider_id,
        "provider_name": runtime_config.provider_name,
        "structured_output_method": runtime_config.structured_output_method,
        "effective_structured_output_method": effective_structured_output_method,
    }


async def get_workspace_runtime_model_config(
    workspace_id: str | None = None,
    model_name: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
) -> RuntimeModelConfig:
    """读取当前工作空间运行默认模型配置，缺省时回退到环境变量。"""
    if not workspace_id:
        if model_provider_id:
            raise ValueError("选择模型供应商配置需要工作空间上下文")
        return _build_environment_runtime_config(
            provider_name=model_provider_name,
            model_name=model_name,
        )

    if model_provider_name and not model_provider_id:
        return _build_environment_runtime_config(
            provider_name=model_provider_name,
            model_name=model_name,
        )

    from db.postgres_store import get_postgres_store
    from models.admin_orm import ModelProviderORM

    store = get_postgres_store()
    async with store.async_session() as session:
        supported_providers = set(LLMProviderFactory.get_supported_provider_names())
        selected_provider = None
        if model_provider_id:
            selected_result = await session.execute(
                select(ModelProviderORM).where(
                    ModelProviderORM.id == model_provider_id,
                    ModelProviderORM.workspace_id == workspace_id,
                )
            )
            selected_provider = selected_result.scalar_one_or_none()
            if selected_provider is None:
                raise ValueError("模型供应商配置不存在或不属于当前工作空间")
            if not selected_provider.enabled:
                raise ValueError("模型供应商配置已停用，无法用于本次运行")
            if selected_provider.provider not in supported_providers:
                raise ValueError(f"模型供应商类型暂不支持: {selected_provider.provider}")

        result = await session.execute(
            select(ModelProviderORM)
            .where(
                ModelProviderORM.workspace_id == workspace_id,
                ModelProviderORM.enabled.is_(True),
            )
            .order_by(desc(ModelProviderORM.updated_at), desc(ModelProviderORM.created_at))
        )
        enabled_providers = list(result.scalars().all())
        providers = [
            provider for provider in enabled_providers if provider.provider in supported_providers
        ]

    if selected_provider is None and not providers:
        if enabled_providers:
            unsupported_types = sorted({str(provider.provider) for provider in enabled_providers})
            raise ValueError(
                "当前工作空间启用的模型供应商暂不支持运行: " + ", ".join(unsupported_types)
            )
        return _build_environment_runtime_config(model_name=model_name)

    selected_provider = selected_provider or next(
        (provider for provider in providers if _is_runtime_default(provider.config)),
        providers[0],
    )
    runtime_config = _build_workspace_runtime_config(selected_provider)
    if model_name:
        return RuntimeModelConfig(
            provider=runtime_config.provider,
            model=model_name,
            credential=runtime_config.credential,
            base_url=runtime_config.base_url,
            provider_id=runtime_config.provider_id,
            provider_name=runtime_config.provider_name,
            source=runtime_config.source,
            structured_output_method=runtime_config.structured_output_method,
        )
    return runtime_config


async def get_llm_for_workspace(
    workspace_id: str | None = None,
    model: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """按工作空间动态配置获取 LLM；未配置时沿用环境变量。"""
    runtime_config = await get_workspace_runtime_model_config(
        workspace_id,
        model,
        model_provider_id,
        model_provider_name,
    )
    return _build_model_from_runtime_config(runtime_config, **kwargs)


async def get_structured_llm_for_workspace(
    schema: type[BaseModel],
    workspace_id: str | None = None,
    model: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
    *,
    method_override: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """按工作空间动态配置获取结构化输出 LLM。"""
    runtime = await get_structured_llm_runtime_for_workspace(
        schema,
        workspace_id,
        model,
        model_provider_id,
        model_provider_name,
        method_override=method_override,
        **kwargs,
    )
    return runtime.llm


async def get_structured_llm_runtime_for_workspace(
    schema: type[BaseModel],
    workspace_id: str | None = None,
    model: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
    *,
    method_override: str | None = None,
    **kwargs,
) -> StructuredLLMRuntime:
    """按工作空间动态配置获取结构化输出 LLM 及最终生效模式。"""
    runtime_config = await get_workspace_runtime_model_config(
        workspace_id,
        model,
        model_provider_id,
        model_provider_name,
    )
    llm = _build_model_from_runtime_config(runtime_config, **kwargs)
    effective_method = _resolve_effective_structured_output_method(
        runtime_config,
        method_override=method_override,
    )
    structured_llm = _bind_structured_output_model(
        llm,
        schema,
        runtime_config,
        method_override=method_override,
    )
    return StructuredLLMRuntime(
        llm=structured_llm,
        runtime_config=runtime_config,
        effective_method=effective_method,
    )


async def build_structured_chain_for_workspace(
    schema: type[BaseModel],
    prompt_template: str,
    workspace_id: str | None = None,
    model: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
    *,
    method_override: str | None = None,
    **kwargs,
) -> tuple[Any, StructuredLLMRuntime]:
    """按工作空间动态配置构建结构化输出 chain。"""
    runtime = await get_structured_llm_runtime_for_workspace(
        schema,
        workspace_id,
        model,
        model_provider_id,
        model_provider_name,
        method_override=method_override,
        **kwargs,
    )
    prompt = build_structured_chat_prompt(
        prompt_template,
        runtime.effective_method,
        schema=schema,
    )
    return prompt | runtime.llm, runtime


async def get_current_model_info_for_workspace(
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model: str | None = None,
    model_provider_name: str | None = None,
) -> dict[str, Any]:
    """获取当前工作空间实际运行模型读模型，供 trace 和设置页展示。"""
    try:
        return _runtime_config_to_info(
            await get_workspace_runtime_model_config(
                workspace_id,
                model,
                model_provider_id,
                model_provider_name,
            )
        )
    except Exception as exc:
        if model_provider_id or model_provider_name:
            raise ValueError(f"无法读取指定模型供应商配置: {exc}") from exc
        return {
            **get_current_model_info(),
            "source": "environment",
            "provider_id": None,
            "provider_name": None,
            "structured_output_method": None,
            "effective_structured_output_method": None,
        }


# 便捷函数
def get_llm(
    provider: str | None = None,
    model: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """获取 LLM 模型实例"""
    return LLMProviderFactory.get_model(provider, model, **kwargs)


def get_structured_llm(
    schema: type[BaseModel],
    provider: str | None = None,
    model: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """获取支持结构化输出的 LLM 模型"""
    return LLMProviderFactory.get_structured_model(schema, provider, model, **kwargs)


def get_current_model_info() -> dict:
    """
    获取当前使用的模型配置信息

    用于 LLMCallRecord 记录，避免硬编码
    """
    provider_name = _resolve_provider_name()
    resolved_provider_name = provider_name
    try:
        provider = LLMProviderFactory.get_provider(provider_name)
        resolved_provider_name = provider.registration.name
        model_name = provider.get_default_model_name()
    except Exception:
        try:
            LLMProviderFactory.get_registration(provider_name)
            model_name = LLMProviderFactory.get_resolved_model_name(provider_name)
        except Exception:
            resolved_provider_name = DEFAULT_PROVIDER_NAME
            model_name = _resolve_model_override() or DEFAULT_FALLBACK_MODEL

    return {
        "provider": resolved_provider_name,
        "model": model_name,
    }
