"""
统一配置模块

通过集中管理所有环境变量和配置项
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """应用配置（从环境变量读取）

    在 __init__ 时读取环境变量，确保每次创建新实例都获取当前的环境值。
    这样便于单元测试中通过 monkeypatch 动态修改环境变量。
    """

    # ...existing code...
    APP_TITLE: str = "PromptChain API"
    APP_DESCRIPTION: str = "基于 Prompt Chain 的自动化内容生成系统"
    APP_VERSION: str = "1.0.0"

    def __init__(self):
        """在初始化时动态读取环境变量，支持测试中的 monkeypatch。"""
        # 服务配置
        self.API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
        self.API_PORT: int = int(os.getenv("API_PORT", "8000"))
        self.DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

        # 数据库配置
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain",
        )

        # LLM 配置 - 关键修改：这里现在在 __init__ 中读取，支持 monkeypatch
        self.DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
        self.DEFAULT_MODEL_NAME: str = os.getenv("DEFAULT_MODEL_NAME", "gpt-4o")
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        self.ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        self.GITHUB_MODEL_TOKEN: str = os.getenv("GITHUB_MODEL_TOKEN", "")
        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        # CORS 配置
        self.CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")

        # 邮件配置
        self.SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USER: str = os.getenv("SMTP_USER", "")
        self.SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
        self.SMTP_FROM: str = os.getenv("SMTP_FROM", self.SMTP_USER or "noreply@promptchain.com")
        self.SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        # 465 端口使用直连 SSL；587 端口通常使用 STARTTLS，二者不要同时启用。
        self.SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
        self.SMTP_TIMEOUT_SECONDS: float = float(os.getenv("SMTP_TIMEOUT_SECONDS", "20"))
        self.APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/")
        self.EMAIL_DEV_LOG_BODY: bool = os.getenv("EMAIL_DEV_LOG_BODY", "false").lower() == "true"


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例"""
    return Settings()
