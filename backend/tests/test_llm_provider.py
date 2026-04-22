import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings
from services.llm_provider import LLMProviderFactory


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
    assert captured["api_key"] == "github-model-token"
    assert captured["base_url"] == "https://models.github.ai/inference"
    assert captured["temperature"] == pytest.approx(0.2)
