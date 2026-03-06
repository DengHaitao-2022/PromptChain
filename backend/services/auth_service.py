"""
认证服务

提供密码加密、JWT Token 管理、登录限流等核心认证功能
"""
from typing import Optional, Tuple
from datetime import datetime, timedelta
import os
import uuid
import hashlib
import secrets

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func

from models.auth_models import User, UserStatus, MemberRole, Workspace, Membership
from models.auth_orm import UserORM, WorkspaceORM, MembershipORM, RefreshTokenORM
from models.admin_orm import LoginAttemptORM


# ==================== 配置 ====================

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # Access Token 15分钟过期
REFRESH_TOKEN_EXPIRE_DAYS = 7      # Refresh Token 7天过期

# 登录限流配置
MAX_LOGIN_ATTEMPTS = 5             # 最大尝试次数
LOGIN_LOCKOUT_MINUTES = 15         # 锁定时间（分钟）


# ==================== 密码处理 ====================

def hash_password(password: str) -> str:
    """
    使用 bcrypt 加密密码
    
    Args:
        password: 明文密码
        
    Returns:
        加密后的密码哈希
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码
    
    Args:
        plain_password: 明文密码
        hashed_password: 存储的密码哈希
        
    Returns:
        密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)


# ==================== Token 管理 ====================

def create_access_token(user_id: str, workspace_id: Optional[str] = None, extra_data: dict = None) -> str:
    """
    创建 Access Token
    
    Args:
        user_id: 用户ID
        workspace_id: 当前工作空间ID（可选）
        extra_data: 额外数据
        
    Returns:
        JWT Access Token
    """
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4()),  # Token 唯一标识
    }
    if workspace_id:
        payload["workspace_id"] = workspace_id
    if extra_data:
        payload.update(extra_data)
    
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token() -> Tuple[str, str]:
    """
    创建 Refresh Token
    
    Returns:
        (原始token, token哈希) - 原始token返回给客户端，哈希存数据库
    """
    # 生成安全的随机 token
    token = secrets.token_urlsafe(32)
    # 存储时使用哈希
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


def verify_access_token(token: str) -> Optional[dict]:
    """
    验证 Access Token
    
    Args:
        token: JWT Token
        
    Returns:
        Token payload 或 None（验证失败）
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def hash_token(token: str) -> str:
    """对 token 进行哈希"""
    return hashlib.sha256(token.encode()).hexdigest()


# ==================== 认证服务类 ====================

class AuthService:
    """认证服务"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def register_user(
        self,
        email: str,
        password: str,
        username: Optional[str] = None,
        display_name: Optional[str] = None
    ) -> User:
        """
        注册新用户
        
        Args:
            email: 邮箱
            password: 密码
            username: 用户名（可选）
            display_name: 显示名称（可选）
            
        Returns:
            创建的用户
            
        Raises:
            ValueError: 邮箱或用户名已存在
        """
        # 检查邮箱是否已存在
        result = await self.session.execute(
            select(UserORM).where(UserORM.email == email)
        )
        if result.scalar_one_or_none():
            raise ValueError("该邮箱已被注册")
        
        # 检查用户名是否已存在
        if username:
            result = await self.session.execute(
                select(UserORM).where(UserORM.username == username)
            )
            if result.scalar_one_or_none():
                raise ValueError("该用户名已被使用")
        
        # 创建用户
        user_id = str(uuid.uuid4())
        user_orm = UserORM(
            id=user_id,
            email=email,
            username=username,
            display_name=display_name or email.split("@")[0],
            password_hash=hash_password(password),
            status=UserStatus.INACTIVE.value,  # 需要邮箱验证后激活
            email_verified=False,
        )
        self.session.add(user_orm)
        await self.session.commit()
        
        # 创建默认工作空间
        workspace = await self._create_default_workspace(user_id, display_name or email.split("@")[0])
        
        return User(
            id=user_id,
            email=email,
            username=username,
            display_name=display_name or email.split("@")[0],
            status=UserStatus.INACTIVE,
            email_verified=False,
        )
    
    async def _create_default_workspace(self, user_id: str, user_name: str) -> Workspace:
        """为用户创建默认工作空间"""
        workspace_id = str(uuid.uuid4())
        workspace_orm = WorkspaceORM(
            id=workspace_id,
            name=f"{user_name} 的工作空间",
            owner_id=user_id,
        )
        self.session.add(workspace_orm)
        
        # 添加用户为工作空间 Owner
        membership_orm = MembershipORM(
            id=str(uuid.uuid4()),
            user_id=user_id,
            workspace_id=workspace_id,
            role=MemberRole.OWNER.value,
        )
        self.session.add(membership_orm)
        await self.session.commit()
        
        return Workspace(
            id=workspace_id,
            name=f"{user_name} 的工作空间",
            owner_id=user_id,
        )
    
    async def authenticate_user(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None
    ) -> Optional[UserORM]:
        """
        验证用户登录
        
        Args:
            email: 邮箱
            password: 密码
            ip_address: 客户端IP（用于限流）
            
        Returns:
            用户ORM对象或None
            
        Raises:
            ValueError: 登录被锁定
        """
        # 检查登录限流
        if ip_address:
            is_locked = await self._check_login_lockout(email, ip_address)
            if is_locked:
                raise ValueError("登录尝试次数过多，请稍后再试")
        
        # 查找用户
        result = await self.session.execute(
            select(UserORM).where(UserORM.email == email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await self._record_login_attempt(email, ip_address, success=False)
            return None
        
        # 验证密码
        if not verify_password(password, user.password_hash):
            await self._record_login_attempt(email, ip_address, success=False)
            return None
        
        # 检查用户状态
        if user.status == UserStatus.SUSPENDED.value:
            raise ValueError("账号已被停用")
        
        # 记录成功登录
        await self._record_login_attempt(email, ip_address, success=True)
        
        # 更新最后登录时间
        user.last_login_at = datetime.utcnow()
        await self.session.commit()
        
        return user
    
    async def _check_login_lockout(self, email: str, ip_address: str) -> bool:
        """检查是否被登录锁定"""
        lockout_time = datetime.utcnow() - timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        
        result = await self.session.execute(
            select(func.count(LoginAttemptORM.id)).where(
                and_(
                    LoginAttemptORM.email == email,
                    LoginAttemptORM.ip_address == ip_address,
                    LoginAttemptORM.success == False,
                    LoginAttemptORM.created_at > lockout_time
                )
            )
        )
        failed_attempts = result.scalar() or 0
        
        return failed_attempts >= MAX_LOGIN_ATTEMPTS
    
    async def _record_login_attempt(
        self,
        email: str,
        ip_address: Optional[str],
        success: bool
    ):
        """记录登录尝试"""
        if not ip_address:
            return
        
        attempt = LoginAttemptORM(
            id=str(uuid.uuid4()),
            email=email,
            ip_address=ip_address,
            success=success,
        )
        self.session.add(attempt)
        await self.session.commit()
    
    async def create_refresh_token_record(
        self,
        user_id: str,
        token_hash: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> RefreshTokenORM:
        """创建 Refresh Token 记录"""
        expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        token_orm = RefreshTokenORM(
            id=str(uuid.uuid4()),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.session.add(token_orm)
        await self.session.commit()
        
        return token_orm
    
    async def validate_refresh_token(self, token: str) -> Optional[UserORM]:
        """验证 Refresh Token 并返回用户"""
        token_hash = hash_token(token)
        
        result = await self.session.execute(
            select(RefreshTokenORM).where(
                and_(
                    RefreshTokenORM.token_hash == token_hash,
                    RefreshTokenORM.revoked_at.is_(None),
                    RefreshTokenORM.expires_at > datetime.utcnow()
                )
            )
        )
        token_orm = result.scalar_one_or_none()
        
        if not token_orm:
            return None
        
        # 获取用户
        result = await self.session.execute(
            select(UserORM).where(UserORM.id == token_orm.user_id)
        )
        return result.scalar_one_or_none()
    
    async def revoke_refresh_token(self, token: str) -> bool:
        """撤销 Refresh Token"""
        token_hash = hash_token(token)
        
        result = await self.session.execute(
            select(RefreshTokenORM).where(RefreshTokenORM.token_hash == token_hash)
        )
        token_orm = result.scalar_one_or_none()
        
        if token_orm:
            token_orm.revoked_at = datetime.utcnow()
            await self.session.commit()
            return True
        
        return False
    
    async def revoke_all_user_tokens(self, user_id: str):
        """撤销用户所有 Refresh Token（用于密码重置后）"""
        result = await self.session.execute(
            select(RefreshTokenORM).where(
                and_(
                    RefreshTokenORM.user_id == user_id,
                    RefreshTokenORM.revoked_at.is_(None)
                )
            )
        )
        tokens = result.scalars().all()
        
        for token in tokens:
            token.revoked_at = datetime.utcnow()
        
        await self.session.commit()
    
    async def get_user_by_id(self, user_id: str) -> Optional[UserORM]:
        """根据ID获取用户"""
        result = await self.session.execute(
            select(UserORM).where(UserORM.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_workspaces(self, user_id: str) -> list:
        """获取用户的所有工作空间"""
        result = await self.session.execute(
            select(MembershipORM, WorkspaceORM).join(
                WorkspaceORM, MembershipORM.workspace_id == WorkspaceORM.id
            ).where(MembershipORM.user_id == user_id)
        )
        return result.all()
    
    async def activate_user(self, user_id: str):
        """激活用户（邮箱验证后）"""
        result = await self.session.execute(
            select(UserORM).where(UserORM.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.status = UserStatus.ACTIVE.value
            user.email_verified = True
            await self.session.commit()
