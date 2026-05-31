import os
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-llm-provider")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings
from models import IntentCard, Outline
from services.llm_provider import (
    LLMProviderFactory,
    _build_environment_runtime_config,
    get_current_model_info,
    get_llm,
    get_structured_llm,
)

EXPECTED_SUPPORTED_PROVIDERS = {"openai", "anthropic", "ollama", "google", "github"}


def _reset_provider_cache(monkeypatch):
    get_settings.cache_clear()
    LLMProviderFactory._instances.clear()
    monkeypatch.delenv("DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEFAULT_MODEL_NAME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_MODEL_TOKEN", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)


def test_fake_provider_is_registered_without_credentials(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")
    monkeypatch.setenv("DEFAULT_MODEL_NAME", "gpt-4o")
    get_settings.cache_clear()

    registration = LLMProviderFactory.get_registration("fake")
    provider = LLMProviderFactory.get_provider("fake")
    info = get_current_model_info()

    assert registration.name == "fake"
    assert registration.credential_env is None
    assert "fake" not in LLMProviderFactory.get_supported_provider_names()
    assert provider.get_default_model_name() == "fake-smoke-model"
    assert LLMProviderFactory.get_resolved_model_name("fake") == "fake-smoke-model"
    assert info == {"provider": "fake", "model": "fake-smoke-model"}


def test_fake_environment_runtime_config_ignores_explicit_model_name(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")
    monkeypatch.setenv("DEFAULT_MODEL_NAME", "gpt-4o")
    get_settings.cache_clear()

    runtime = _build_environment_runtime_config("fake", model_name="gpt-4o")

    assert runtime.provider == "fake"
    assert runtime.model == "fake-smoke-model"


def test_fake_provider_model_instance_ignores_explicit_model_name(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")
    get_settings.cache_clear()

    model = get_llm("fake", model="gpt-4o")

    assert model.model_name == "fake-smoke-model"


def test_fake_provider_generates_plain_chat_response(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")
    get_settings.cache_clear()

    model = get_llm("fake")
    response = model.invoke("生成 smoke 内容")

    assert "fake provider" in response.content
    assert "真实模型输出" in response.content


def test_fake_provider_supports_structured_intent_card(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")
    get_settings.cache_clear()

    structured = get_structured_llm(IntentCard, "fake")
    result = structured.invoke({"user_input": "写一篇 PromptChain smoke 验收说明"})

    assert isinstance(result, IntentCard)
    assert result.topic == "写一篇 PromptChain smoke 验收说明"
    assert result.has_uncertainties() is False


def test_fake_provider_structured_include_raw_contract(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")
    get_settings.cache_clear()

    model = get_llm("fake")
    structured = model.with_structured_output(Outline, include_raw=True)
    result = structured.invoke({"topic": "Fake Provider"})

    assert set(result) == {"raw", "parsed", "parsing_error"}
    assert result["parsing_error"] is None
    assert isinstance(result["parsed"], Outline)
    assert result["parsed"].sections
    assert result["raw"].response_metadata["token_usage"]["total_tokens"] > 0


class _NestedSmokeModel(BaseModel):
    label: str
    weight: int


class _GenericSmokeModel(BaseModel):
    enabled: bool
    count: int
    ratio: float
    nested: _NestedSmokeModel
    tags: list[str]
    metadata: dict[str, str]


def test_fake_provider_supports_nested_generic_structured_model(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")
    get_settings.cache_clear()

    structured = get_structured_llm(_GenericSmokeModel, "fake")
    result = structured.invoke({"topic": "nested"})

    assert isinstance(result, _GenericSmokeModel)
    assert isinstance(result.nested, _NestedSmokeModel)
    assert result.metadata == {}


def test_supported_provider_registry_matches_current_runtime_contract(monkeypatch):
    _reset_provider_cache(monkeypatch)

    assert set(LLMProviderFactory.get_supported_provider_names()) == EXPECTED_SUPPORTED_PROVIDERS


def test_github_provider_is_registered(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_MODEL_TOKEN", "github-model-token")
    get_settings.cache_clear()

    registration = LLMProviderFactory.get_registration("github")

    assert registration.name == "github"
    assert registration.credential_env == "GITHUB_MODEL_TOKEN"
    assert registration.default_model_name == "openai/gpt-4.1"


def test_github_provider_uses_github_models_endpoint(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "github")
    monkeypatch.setenv("DEFAULT_MODEL_NAME", "claude-3-5-sonnet-20241022")
    monkeypatch.setenv("GITHUB_MODEL_TOKEN", "github-model-token")
    get_settings.cache_clear()

    captured = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChatOpenAI)

    provider = LLMProviderFactory.get_provider("github")
    provider.get_model(temperature=0.2)

    assert captured["model"] == "openai/gpt-4.1"
    assert captured["api_key"] == os.environ["GITHUB_MODEL_TOKEN"]
    assert captured["base_url"] == "https://models.github.ai/inference"
    assert captured["temperature"] == pytest.approx(0.2)


def test_github_provider_uses_github_models_endpoint_with_question(monkeypatch):
    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "github")
    monkeypatch.setenv("DEFAULT_MODEL_NAME", "openai/gpt-4.1")
    monkeypatch.setenv("GITHUB_MODEL_TOKEN", "github-model-token")
    get_settings.cache_clear()

    captured = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, prompt):
            class _FakeResponse:
                def __init__(self, content: str):
                    self.content = content

            return _FakeResponse(f"mock response to: {prompt}")

    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChatOpenAI)

    # 先创建模型，再通过 invoke 真正获取响应内容
    provider = LLMProviderFactory.get_provider("github")
    model = provider.get_model(temperature=0.2)
    response = model.invoke("你是哪个模型")

    print(response.content)

    # 断言参数与响应都符合预期
    assert "model" in captured
    assert captured["model"] == "openai/gpt-4.1"  # 确保使用的是预期的模型
    assert captured["api_key"] == os.environ["GITHUB_MODEL_TOKEN"]
    assert response.content == "mock response to: 你是哪个模型"


@pytest.mark.skipif(
    os.getenv("RUN_LLM_INTEGRATION") != "1" or not os.getenv("GITHUB_MODEL_TOKEN"),
    reason="需要显式设置 RUN_LLM_INTEGRATION=1 且提供 GITHUB_MODEL_TOKEN 才运行真实集成测试",
)
def test_github_provider_integration_real_response(monkeypatch):
    """真实调用 GitHub Models，观察模型返回内容。"""
    token = os.getenv("GITHUB_MODEL_TOKEN")
    assert token, "运行集成测试前必须先设置 GITHUB_MODEL_TOKEN"

    _reset_provider_cache(monkeypatch)
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "github")
    monkeypatch.setenv("DEFAULT_MODEL_NAME", "openai/gpt-4.1")
    monkeypatch.setenv("GITHUB_MODEL_TOKEN", token)
    get_settings.cache_clear()

    provider = LLMProviderFactory.get_provider("github")
    model = provider.get_model(temperature=0)

    # 使用短而稳定的提示词，尽量减少真实模型输出的波动。
    response = model.invoke("请只回复一句话：你是哪个模型？")

    assert hasattr(response, "content")
    assert isinstance(response.content, str)
    assert response.content.strip()
    print(response.content)
