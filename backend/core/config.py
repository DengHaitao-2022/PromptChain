"""
统一配置模块

通过集中管理所有环境变量和配置项
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """应用配置（从环境变量读取）"""

    # 服务配置
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # 数据库配置
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain",
    )

    # LLM 配置
    DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
    DEFAULT_MODEL_NAME: str = os.getenv("DEFAULT_MODEL_NAME", "gpt-4o")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GITHUB_MODEL_TOKEN: str = os.getenv("GITHUB_MODEL_TOKEN", "")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # CORS 配置
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")

    # 应用信息
    APP_TITLE: str = "PromptChain API"
    APP_DESCRIPTION: str = "基于 Prompt Chain 的自动化内容生成系统"
    APP_VERSION: str = "1.0.0"


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例"""
    return Settings()
