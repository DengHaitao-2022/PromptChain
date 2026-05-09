"""敏感配置加解密工具。"""

import base64
import hashlib
import logging
import os
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from services.auth_service import JWT_SECRET_KEY

logger = logging.getLogger(__name__)
ENCRYPTED_VALUE_FLAG = "__encrypted__"
ENCRYPTED_VALUE_FIELD = "ciphertext"


def _derive_fernet_key(source: str) -> bytes:
    """从任意字符串稳定导出 Fernet key。"""
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache
def _get_fernet() -> Fernet:
    """获取密钥加密器，优先使用显式配置的 SECRETS_ENCRYPTION_KEY。"""
    configured_key = os.getenv("SECRETS_ENCRYPTION_KEY", "").strip()
    if configured_key:
        return Fernet(configured_key.encode("utf-8"))

    # 未配置专用密钥时，用 JWT_SECRET_KEY 派生，避免模型配置明文落库。
    logger.warning("SECRETS_ENCRYPTION_KEY 未配置，使用 JWT_SECRET_KEY 派生临时密钥")
    return Fernet(_derive_fernet_key(JWT_SECRET_KEY))


def encrypt_secret(value: str) -> str:
    """加密密钥。"""
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """解密密钥，兼容历史 Base64 存储。"""
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # 历史数据兼容：旧版本用 Base64 存储。
        return base64.b64decode(ciphertext.encode("utf-8")).decode("utf-8")


def encrypt_config_value(value: Any) -> dict[str, Any]:
    """把敏感配置值包装为可识别的加密 JSON 结构。"""
    return {
        ENCRYPTED_VALUE_FLAG: True,
        ENCRYPTED_VALUE_FIELD: encrypt_secret(str(value)),
    }


def decrypt_config_value(value: Any) -> Any:
    """解开加密 JSON 结构；非加密结构原样返回。"""
    if (
        isinstance(value, dict)
        and value.get(ENCRYPTED_VALUE_FLAG) is True
        and isinstance(value.get(ENCRYPTED_VALUE_FIELD), str)
    ):
        return decrypt_secret(value[ENCRYPTED_VALUE_FIELD])
    return value
