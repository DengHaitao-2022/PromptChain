"""
统一配置模块

通过集中管理所有环境变量和配置项
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

        # 数据库配置
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain",
        )

        # Redis / 事件总线配置。默认继续使用 memory，避免本地开发强依赖 Redis。
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6380/0")
        self.WORKFLOW_EVENT_BUS_BACKEND: str = os.getenv(
            "WORKFLOW_EVENT_BUS_BACKEND",
            "memory",
        ).lower()
        if self.WORKFLOW_EVENT_BUS_BACKEND not in {"memory", "redis"}:
            raise RuntimeError("WORKFLOW_EVENT_BUS_BACKEND 仅支持 memory 或 redis")
        self.WORKFLOW_EVENT_BUS_REDIS_CHANNEL_PREFIX: str = os.getenv(
            "WORKFLOW_EVENT_BUS_REDIS_CHANNEL_PREFIX",
            "promptchain:workflow-events",
        )

        # LLM 配置 - 关键修改：这里现在在 __init__ 中读取，支持 monkeypatch
        self.DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
        self.DEFAULT_MODEL_NAME: str = os.getenv("DEFAULT_MODEL_NAME", "gpt-4o")
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        self.ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        self.GITHUB_MODEL_TOKEN: str = os.getenv("GITHUB_MODEL_TOKEN", "")
        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        # CORS 配置：带 Cookie 的跨源请求不能使用 "*"，
        # 本地默认显式允许前端来源。
        self.CORS_ORIGINS: list[str] = [
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            ).split(",")
            if origin.strip()
        ]
        if "*" in self.CORS_ORIGINS:
            raise RuntimeError("CORS_ORIGINS 不能包含通配符 *，跨源 Cookie 请求必须显式配置 Origin")

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

        # 知识库 / RAG 配置。默认使用确定性本地 embedding，避免开发和测试强依赖外部服务。
        self.KNOWLEDGE_STORAGE_DIR: str = os.getenv(
            "KNOWLEDGE_STORAGE_DIR",
            str(Path(__file__).resolve().parents[1] / ".data" / "knowledge"),
        )
        self.KNOWLEDGE_EMBEDDING_PROVIDER: str = os.getenv(
            "KNOWLEDGE_EMBEDDING_PROVIDER",
            "hash",
        ).lower()
        self.KNOWLEDGE_EMBEDDING_MODEL: str = os.getenv(
            "KNOWLEDGE_EMBEDDING_MODEL",
            "promptchain-hash-embedding-v1",
        )
        self.KNOWLEDGE_EMBEDDING_DIMENSION: int = int(
            os.getenv("KNOWLEDGE_EMBEDDING_DIMENSION", "1536")
        )
        self.KNOWLEDGE_CHUNK_TARGET_TOKENS: int = int(
            os.getenv("KNOWLEDGE_CHUNK_TARGET_TOKENS", "1000")
        )
        self.KNOWLEDGE_CHUNK_OVERLAP_TOKENS: int = int(
            os.getenv("KNOWLEDGE_CHUNK_OVERLAP_TOKENS", "150")
        )
        self.KNOWLEDGE_MAX_UPLOAD_BYTES: int = int(
            os.getenv("KNOWLEDGE_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))
        )
        self.KNOWLEDGE_MAX_DOCUMENTS_PER_KB: int = int(
            os.getenv("KNOWLEDGE_MAX_DOCUMENTS_PER_KB", "200")
        )
        self.KNOWLEDGE_INDEX_WORKER_ENABLED: bool = (
            os.getenv("KNOWLEDGE_INDEX_WORKER_ENABLED", "true").lower() == "true"
        )
        self.KNOWLEDGE_INDEX_WORKER_INTERVAL_SECONDS: float = float(
            os.getenv("KNOWLEDGE_INDEX_WORKER_INTERVAL_SECONDS", "2")
        )
        self.KNOWLEDGE_INDEX_WORKER_BATCH_SIZE: int = int(
            os.getenv("KNOWLEDGE_INDEX_WORKER_BATCH_SIZE", "5")
        )


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例"""
    return Settings()
