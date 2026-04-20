"""
认证与组织相关 SQLAlchemy ORM 模型

从 Pydantic 模型独立出来，便于数据库迁移管理
"""

from datetime import datetime

# 使用现有的 Base
from db.postgres_store import Base
from models.auth_models import MemberRole, UserStatus
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

# ==================== ORM 模型定义 ====================


class UserORM(Base):
    """用户 ORM 模型"""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=True, index=True)
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(20), default=UserStatus.INACTIVE.value)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # 关系
    memberships = relationship("MembershipORM", back_populates="user", lazy="dynamic")
    owned_workspaces = relationship("WorkspaceORM", back_populates="owner", lazy="dynamic")
    refresh_tokens = relationship("RefreshTokenORM", back_populates="user", lazy="dynamic")


class WorkspaceORM(Base):
    """工作空间 ORM 模型"""

    __tablename__ = "workspaces"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(String(500), nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    owner = relationship("UserORM", back_populates="owned_workspaces")
    memberships = relationship("MembershipORM", back_populates="workspace", lazy="dynamic")
    model_providers = relationship("ModelProviderORM", back_populates="workspace", lazy="dynamic")
    secrets = relationship("SecretORM", back_populates="workspace", lazy="dynamic")
    api_keys = relationship("ApiKeyORM", back_populates="workspace", lazy="dynamic")
    audit_logs = relationship("AuditLogORM", back_populates="workspace", lazy="dynamic")


class MembershipORM(Base):
    """成员关系 ORM 模型"""

    __tablename__ = "memberships"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    role = Column(String(20), default=MemberRole.VIEWER.value)
    joined_at = Column(DateTime, default=datetime.utcnow)
    invited_by = Column(String(36), nullable=True)

    # 关系
    user = relationship("UserORM", back_populates="memberships")
    workspace = relationship("WorkspaceORM", back_populates="memberships")


class RefreshTokenORM(Base):
    """刷新令牌 ORM 模型"""

    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(50), nullable=True)

    # 关系
    user = relationship("UserORM", back_populates="refresh_tokens")


class EmailVerificationTokenORM(Base):
    """邮箱验证令牌 ORM 模型"""

    __tablename__ = "email_verification_tokens"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PasswordResetTokenORM(Base):
    """密码重置令牌 ORM 模型"""

    __tablename__ = "password_reset_tokens"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceInviteORM(Base):
    """工作空间邀请 ORM 模型"""

    __tablename__ = "workspace_invites"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    role = Column(String(20), default=MemberRole.VIEWER.value)
    invited_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
