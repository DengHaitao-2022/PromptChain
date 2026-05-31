import os

import pytest

# 测试进程使用固定 JWT 密钥，避免单元测试依赖本机或 CI 的生产密钥配置。
os.environ.setdefault("JWT_SECRET_KEY", "promptchain-test-jwt-secret")


@pytest.fixture
def anyio_backend():
    """统一让 async 测试在 AnyIO 的 asyncio 后端执行。"""
    return "asyncio"


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: 使用 AnyIO asyncio 后端运行异步测试")


def pytest_collection_modifyitems(items):
    """兼容既有 pytest.mark.asyncio 标记，避免测试依赖额外插件。"""
    for item in items:
        if item.get_closest_marker("asyncio"):
            item.add_marker(pytest.mark.anyio)
