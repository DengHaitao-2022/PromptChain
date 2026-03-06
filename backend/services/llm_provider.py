"""
LLM Provider 抽象层

支持多个 LLM 提供商的统一接口：
- OpenAI (GPT-4, GPT-4o)
- Anthropic (Claude)
- Ollama (本地模型)
"""
from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator, Any, Type, TypeVar
from pydantic import BaseModel
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv

load_dotenv()

T = TypeVar('T', bound=BaseModel)


class LLMProvider(ABC):
    """LLM 提供商抽象基类"""
    
    @abstractmethod
    def get_model(self, model_name: Optional[str] = None, **kwargs) -> BaseChatModel:
        """获取 LangChain 兼容的模型实例"""
        pass
    
    @abstractmethod
    def get_default_model_name(self) -> str:
        """获取默认模型名称"""
        pass
    
    def get_structured_output_model(
        self, 
        schema: Type[T],
        model_name: Optional[str] = None,
        **kwargs
    ) -> BaseChatModel:
        """获取支持结构化输出的模型"""
        model = self.get_model(model_name, **kwargs)
        return model.with_structured_output(schema)


class OpenAIProvider(LLMProvider):
    """OpenAI 提供商"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY 环境变量未设置")
    
    def get_model(self, model_name: Optional[str] = None, **kwargs) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name or self.get_default_model_name(),
            api_key=self.api_key,
            **kwargs
        )
    
    def get_default_model_name(self) -> str:
        return os.getenv("DEFAULT_MODEL_NAME", "gpt-4o")


class AnthropicProvider(LLMProvider):
    """Anthropic 提供商"""
    
    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY 环境变量未设置")
    
    def get_model(self, model_name: Optional[str] = None, **kwargs) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model_name or self.get_default_model_name(),
            api_key=self.api_key,
            **kwargs
        )
    
    def get_default_model_name(self) -> str:
        return "claude-3-5-sonnet-20241022"


class OllamaProvider(LLMProvider):
    """Ollama 本地模型提供商"""
    
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    def get_model(self, model_name: Optional[str] = None, **kwargs) -> BaseChatModel:
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            model=model_name or self.get_default_model_name(),
            base_url=self.base_url,
            **kwargs
        )
    
    def get_default_model_name(self) -> str:
        return "qwen2.5:14b"


class LLMProviderFactory:
    """LLM 提供商工厂"""
    
    _providers: dict[str, Type[LLMProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
    }
    
    _instances: dict[str, LLMProvider] = {}
    
    @classmethod
    def get_provider(cls, provider_name: Optional[str] = None) -> LLMProvider:
        """
        获取 LLM 提供商实例（单例模式）
        
        Args:
            provider_name: 提供商名称，默认从环境变量读取
        """
        name = provider_name or os.getenv("DEFAULT_LLM_PROVIDER", "openai")
        name = name.lower()
        
        if name not in cls._providers:
            raise ValueError(f"不支持的 LLM 提供商: {name}，支持: {list(cls._providers.keys())}")
        
        if name not in cls._instances:
            cls._instances[name] = cls._providers[name]()
        
        return cls._instances[name]
    
    @classmethod
    def get_model(
        cls, 
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        快捷方法：直接获取模型实例
        """
        provider = cls.get_provider(provider_name)
        return provider.get_model(model_name, **kwargs)
    
    @classmethod
    def get_structured_model(
        cls,
        schema: Type[T],
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        快捷方法：获取支持结构化输出的模型
        """
        provider = cls.get_provider(provider_name)
        return provider.get_structured_output_model(schema, model_name, **kwargs)


# 便捷函数
def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> BaseChatModel:
    """获取 LLM 模型实例"""
    return LLMProviderFactory.get_model(provider, model, **kwargs)


def get_structured_llm(
    schema: Type[T],
    provider: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> BaseChatModel:
    """获取支持结构化输出的 LLM 模型"""
    return LLMProviderFactory.get_structured_model(schema, provider, model, **kwargs)


def get_current_model_info() -> dict:
    """
    获取当前使用的模型配置信息
    
    用于 LLMCallRecord 记录，避免硬编码
    """
    provider_name = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
    try:
        provider = LLMProviderFactory.get_provider(provider_name)
        model_name = provider.get_default_model_name()
    except Exception:
        model_name = os.getenv("DEFAULT_MODEL_NAME", "gpt-4o")
    
    return {
        "provider": provider_name,
        "model": model_name
    }

