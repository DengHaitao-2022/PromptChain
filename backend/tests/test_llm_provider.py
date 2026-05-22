import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings
from services.llm_provider import LLMProviderFactory

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
