"""工具输入输出脱敏工具。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED_VALUE = "***REDACTED***"

SENSITIVE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "password",
    "provider_config",
    "refresh",
    "refresh_token",
    "secret",
    "token",
}


def is_sensitive_field_name(value: Any) -> bool:
    """判断字段名是否属于工具配置和预览中禁止暴露的敏感字段。"""
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in SENSITIVE_FIELD_NAMES:
        return True
    return any(
        marker in normalized
        for marker in ("api_key", "access_token", "refresh_token", "secret", "credential")
    )


def redact_sensitive_payload(value: Any) -> Any:
    """递归脱敏工具输入输出，避免 Gate 预览和审计记录泄露密钥。"""
    if isinstance(value, Mapping):
        return {
            key: REDACTED_VALUE if is_sensitive_field_name(key) else redact_sensitive_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_sensitive_payload(item) for item in value]
    return value


def sensitive_payload_fingerprint(value: Any) -> str:
    """生成不可逆输入指纹，用于审批复用校验而不落库原始敏感值。"""
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
