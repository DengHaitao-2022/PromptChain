"""
后台管理相关模型

包含模型供应商配置、密钥管理、API Key、审计日志等模型定义
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid


# ==================== 枚举定义 ====================

class ModelProviderType(str, Enum):
    """模型供应商类型"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    LOCAL = "local"
    CUSTOM = "custom"


class AuditAction(str, Enum):
    """审计动作类型"""
    # 用户相关
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_REGISTER = "user.register"
    USER_UPDATE = "user.update"
    USER_PASSWORD_RESET = "user.password_reset"
    
    # 工作空间相关
    WORKSPACE_CREATE = "workspace.create"
    WORKSPACE_UPDATE = "workspace.update"
    WORKSPACE_DELETE = "workspace.delete"
    MEMBER_INVITE = "workspace.member_invite"
    MEMBER_REMOVE = "workspace.member_remove"
    MEMBER_ROLE_CHANGE = "workspace.member_role_change"
    
    # 工作流相关
    WORKFLOW_CREATE = "workflow.create"
    WORKFLOW_UPDATE = "workflow.update"
    WORKFLOW_DELETE = "workflow.delete"
    WORKFLOW_PUBLISH = "workflow.publish"
    WORKFLOW_RUN = "workflow.run"
    
    # 配置相关
    MODEL_PROVIDER_CREATE = "model_provider.create"
    MODEL_PROVIDER_UPDATE = "model_provider.update"
    MODEL_PROVIDER_DELETE = "model_provider.delete"
    SECRET_CREATE = "secret.create"
    SECRET_DELETE = "secret.delete"
    API_KEY_CREATE = "api_key.create"
    API_KEY_REVOKE = "api_key.revoke"


# ==================== 模型供应商配置 ====================

class ModelProviderBase(BaseModel):
    """模型供应商基础模型"""
    provider: ModelProviderType
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    enabled: bool = True


class ModelProviderCreate(ModelProviderBase):
    """创建模型供应商配置"""
    config: Dict[str, Any] = Field(default_factory=dict, description="配置信息，如 api_key, base_url 等")


class ModelProviderUpdate(BaseModel):
    """更新模型供应商配置"""
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


class ModelProvider(ModelProviderBase):
    """模型供应商完整模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    config: Dict[str, Any] = Field(default_factory=dict)  # 注意：返回时需脱敏
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    
    class Config:
        from_attributes = True


# ==================== 密钥管理 ====================

class SecretBase(BaseModel):
    """密钥基础模型"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class SecretCreate(SecretBase):
    """创建密钥"""
    value: str = Field(..., min_length=1, description="密钥值，存储时加密")


class Secret(SecretBase):
    """密钥完整模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    ciphertext: str  # 加密后的密钥
    last4: str  # 最后4位，用于显示
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    
    class Config:
        from_attributes = True


class SecretResponse(SecretBase):
    """密钥响应模型（不包含实际值）"""
    id: str
    workspace_id: str
    last4: str
    created_at: datetime
    updated_at: datetime


# ==================== API Key 管理 ====================

class ApiKeyScope(str, Enum):
    """API Key 权限范围"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ALL = "all"


class ApiKeyBase(BaseModel):
    """API Key 基础模型"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    scopes: List[ApiKeyScope] = Field(default_factory=lambda: [ApiKeyScope.EXECUTE])


class ApiKeyCreate(ApiKeyBase):
    """创建 API Key"""
    expires_in_days: Optional[int] = Field(None, description="有效期（天），不填则永不过期")


class ApiKey(ApiKeyBase):
    """API Key 完整模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    key_hash: str  # Key 的哈希值
    key_prefix: str  # Key 前缀，用于显示 (如 "pc_xxx...xxx")
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    
    class Config:
        from_attributes = True


class ApiKeyCreateResponse(BaseModel):
    """创建 API Key 响应（包含完整 key，仅在创建时返回一次）"""
    id: str
    name: str
    key: str  # 完整的 API Key，仅此一次显示
    key_prefix: str
    scopes: List[ApiKeyScope]
    expires_at: Optional[datetime] = None
    created_at: datetime


class ApiKeyResponse(BaseModel):
    """API Key 响应模型（不包含完整 key）"""
    id: str
    name: str
    description: Optional[str]
    key_prefix: str
    scopes: List[ApiKeyScope]
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime


# ==================== 审计日志 ====================

class AuditLog(BaseModel):
    """审计日志模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    user_id: str
    action: AuditAction
    target_type: Optional[str] = None  # 目标类型，如 "workflow", "user"
    target_id: Optional[str] = None    # 目标ID
    detail: Dict[str, Any] = Field(default_factory=dict)  # 详细信息
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class AuditLogQuery(BaseModel):
    """审计日志查询参数"""
    workspace_id: Optional[str] = None
    user_id: Optional[str] = None
    action: Optional[AuditAction] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ==================== Dashboard 统计 ====================

class DashboardStats(BaseModel):
    """Dashboard 统计数据"""
    # 今日统计
    today_runs: int = 0
    today_success_runs: int = 0
    today_failed_runs: int = 0
    today_avg_duration_ms: float = 0
    
    # 总体统计
    total_workflows: int = 0
    total_runs: int = 0
    total_members: int = 0
    
    # 最近运行
    recent_runs: List[Dict[str, Any]] = Field(default_factory=list)
