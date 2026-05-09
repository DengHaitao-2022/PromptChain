"""兼容导出：统一使用 orm/admin_orm 作为 ORM 单一事实源。"""

from orm.admin_orm import (
    ApiKeyORM,
    AuditLogORM,
    LoginAttemptORM,
    ModelProviderORM,
    SecretORM,
)

__all__ = [
    "ApiKeyORM",
    "AuditLogORM",
    "LoginAttemptORM",
    "ModelProviderORM",
    "SecretORM",
]
