"""
向后兼容入口

实际应用入口已迁移到 app.py，此文件保留以兼容旧的 `uvicorn main:app` 启动方式。
推荐使用: uv run uvicorn app:app --reload --port 8000
"""

from app import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    from core.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
