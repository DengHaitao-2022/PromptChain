"""
LLM Provider 抽象层

支持多个 LLM 提供商的统一接口:
- OpenAI (GPT-4, GPT-4o)
- Anthropic (Claude)
- Ollama (本地模型)
- Google (Gemini)
- GitHub Models (GitHub Copilot)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from core.config import get_settings

DEFAULT_PROVIDER_NAME = "openai"
DEFAULT_FALLBACK_MODEL = "gpt-4o"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"


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


@dataclass(frozen=True)
class ProviderRegistration:
    """Provider registry 的最小元数据。"""

    name: str
    provider_class: type[LLMProvider]
    default_model_name: str
    credential_env: str | None = None


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
}


class LLMProviderFactory:
    """LLM 提供商工厂"""

    _registry: ClassVar[dict[str, ProviderRegistration]] = PROVIDER_REGISTRY
    _instances: ClassVar[dict[str, LLMProvider]] = {}

    @classmethod
    def get_supported_provider_names(cls) -> list[str]:
        """返回当前支持的 provider 名称列表。"""
        return list(cls._registry.keys())

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
