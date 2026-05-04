"""
认证与组织相关模型

包含用户、工作空间、成员关系、刷新令牌等模型定义
采用 Workspace 级别 RBAC 权限模型
"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field

from core.time import utc_now_naive

# ==================== 枚举定义 ====================


class UserStatus(StrEnum):
    """用户状态"""

    ACTIVE = "active"  # 正常
    INACTIVE = "inactive"  # 未激活
    SUSPENDED = "suspended"  # 已停用


class MemberRole(StrEnum):
    """成员角色 - Workspace 级 RBAC"""

    OWNER = "owner"  # 工作空间最高权限（成员/计费/密钥/删除空间）
    ADMIN = "admin"  # 管理应用、工作流、模型配置、知识库、密钥
    EDITOR = "editor"  # 创建/编辑工作流与模板，运行任务，查看运行记录
    VIEWER = "viewer"  # 只读权限


# ==================== Pydantic 模型 ====================


class UserBase(BaseModel):
    """用户基础模型"""

    email: EmailStr
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None


class UserCreate(UserBase):
    """用户创建模型"""

    password: str = Field(..., min_length=8, description="密码，至少8位")


class UserLogin(BaseModel):
    """登录请求模型"""

    email: EmailStr
    password: str


class User(UserBase):
    """用户完整模型"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: UserStatus = UserStatus.INACTIVE
    email_verified: bool = False
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)
    last_login_at: datetime | None = None

    class Config:
        from_attributes = True


class WorkspaceBase(BaseModel):
    """工作空间基础模型"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    logo_url: str | None = None


class WorkspaceCreate(WorkspaceBase):
    """工作空间创建模型"""

    pass


class Workspace(WorkspaceBase):
    """工作空间完整模型"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)

    class Config:
        from_attributes = True


class MembershipBase(BaseModel):
    """成员关系基础模型"""

    role: MemberRole = MemberRole.VIEWER


class Membership(MembershipBase):
    """成员关系完整模型"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    workspace_id: str
    joined_at: datetime = Field(default_factory=utc_now_naive)
    invited_by: str | None = None

    class Config:
        from_attributes = True


class RefreshToken(BaseModel):
    """刷新令牌模型"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now_naive)
    user_agent: str | None = None  # 记录登录设备信息
    ip_address: str | None = None  # 记录登录IP

    class Config:
        from_attributes = True


class EmailVerificationToken(BaseModel):
    """邮箱验证令牌模型"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now_naive)

    class Config:
        from_attributes = True


class PasswordResetToken(BaseModel):
    """密码重置令牌模型"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now_naive)

    class Config:
        from_attributes = True


# ==================== 响应模型 ====================


class TokenResponse(BaseModel):
    """Token 响应模型（仅用于告知前端登录成功，实际 token 在 HttpOnly Cookie 中）"""

    message: str = "登录成功"
    user: User
    workspace: Workspace | None = None


class UserWithWorkspaces(User):
    """用户带工作空间列表"""

    workspaces: list[Workspace] = []
    current_workspace: Workspace | None = None
    current_role: MemberRole | None = None


# ==================== 工作空间邀请 ====================


class WorkspaceInvite(BaseModel):
    """工作空间邀请"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    email: EmailStr
    role: MemberRole = MemberRole.VIEWER
    invited_by: str
    token_hash: str
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now_naive)

    class Config:
        from_attributes = True
