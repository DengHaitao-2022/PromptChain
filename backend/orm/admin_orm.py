"""
后台管理相关 SQLAlchemy ORM 模型

包含模型供应商配置、密钥管理、API Key、审计日志等 ORM 定义
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

# 使用现有的 Base
from db.postgres_store import Base

# ==================== ORM 模型定义 ====================


class ModelProviderORM(Base):
    """模型供应商配置 ORM 模型"""

    __tablename__ = "model_providers"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)  # 加密存储敏感配置
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    # 关系
    workspace = relationship("WorkspaceORM", back_populates="model_providers")


class SecretORM(Base):
    """密钥 ORM 模型"""

    __tablename__ = "secrets"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    ciphertext = Column(Text, nullable=False)  # 加密后的密钥
    last4 = Column(String(10), nullable=False)  # 最后4位
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    # 关系
    workspace = relationship("WorkspaceORM", back_populates="secrets")


class ApiKeyORM(Base):
    """API Key ORM 模型"""

    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    key_hash = Column(String(255), nullable=False, unique=True)
    key_prefix = Column(String(20), nullable=False)  # 如 "pc_xxx...xxx"
    scopes = Column(JSON, default=list)  # 权限范围列表
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    # 关系
    workspace = relationship("WorkspaceORM", back_populates="api_keys")


class AuditLogORM(Base):
    """审计日志 ORM 模型"""

    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True)
    event_id = Column(String(64), nullable=True, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    request_id = Column(String(64), nullable=True, index=True)
    trace_id = Column(String(64), nullable=True, index=True)
    span_id = Column(String(32), nullable=True)
    event_category = Column(String(50), nullable=True, index=True)
    event_type = Column(String(50), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    outcome = Column(String(20), nullable=True, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(36), nullable=True)
    actor_snapshot = Column(JSON, default=dict)
    target_snapshot = Column(JSON, default=dict)
    detail = Column(JSON, default=dict)
    metadata_json = Column(JSON, default=dict)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    schema_version = Column(String(20), default="2026-05-02")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 关系
    workspace = relationship("WorkspaceORM", back_populates="audit_logs")


# ==================== 登录限流表 ====================


class LoginAttemptORM(Base):
    """登录尝试记录（用于限流）"""

    __tablename__ = "login_attempts"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(50), nullable=False, index=True)
    success = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
