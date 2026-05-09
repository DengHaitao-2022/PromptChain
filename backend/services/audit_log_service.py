"""
结构化审计日志服务。

审计事件按 OpenTelemetry/ECS 的思路建模：低基数字段用于过滤，
动态上下文放入 JSON 快照，避免把审计表做成不可追溯的纯文本日志。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.time import to_utc_iso
from models.admin_models import AuditAction
from models.admin_orm import AuditLogORM
from models.auth_orm import MembershipORM, UserORM
from services.permission_service import resolve_membership_role

AuditOutcome = Literal["success", "failure", "unknown"]

SCHEMA_VERSION = "2026-05-02"
REDACTED = "[已脱敏]"
SENSITIVE_KEY_MARKERS = (
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "access_token",
    "refresh_token",
    "ciphertext",
)


def _action_value(action: AuditAction | str) -> str:
    return action.value if isinstance(action, AuditAction) else action


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return to_utc_iso(value)
    if isinstance(value, dict):
        return {
            str(key): REDACTED if _is_sensitive_key(str(key)) else _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value") and not isinstance(value, str):
        return value.value
    return value


def _category_for_action(action: str) -> str:
    if action.startswith("user.") or "member" in action:
        return "iam"
    if action.startswith("workspace."):
        return "configuration"
    if action.startswith("workflow."):
        return (
            "configuration"
            if action
            in {"workflow.create", "workflow.update", "workflow.delete", "workflow.publish"}
            else "api"
        )
    if action.startswith(("model_provider.", "secret.", "api_key.")):
        return "configuration"
    return "api"


def _type_for_action(action: str) -> str:
    suffix = action.rsplit(".", 1)[-1]
    if suffix in {"create", "register", "member_invite", "member_accept"}:
        return "creation"
    if suffix in {"update", "role_change", "publish", "restore"}:
        return "change"
    if suffix in {"delete", "remove", "revoke"}:
        return "deletion"
    if suffix in {"login", "logout"}:
        return "authentication"
    if suffix in {"run", "pause", "resume", "approve", "clarify", "rerun"}:
        return "access"
    return "info"


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None


def _trace_context(request: Request | None) -> dict[str, str | None]:
    if request is None:
        return {"request_id": None, "trace_id": None, "span_id": None}

    traceparent = request.headers.get("traceparent")
    trace_id: str | None = None
    span_id: str | None = None
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 4:
            trace_id = parts[1] or None
            span_id = parts[2] or None

    request_id = (
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or trace_id
    )
    return {"request_id": request_id, "trace_id": trace_id, "span_id": span_id}


def _request_metadata(request: Request | None) -> dict[str, Any]:
    if request is None:
        return {}
    return {
        "http": {
            "method": request.method,
            "path": request.url.path,
            "query": str(request.url.query) if request.url.query else None,
        }
    }


class AuditLogService:
    """审计日志服务，统一处理写入、查询、脱敏和快照序列化。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def build_user_snapshot(
        self,
        user_id: str | None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """构建事件发生时的用户快照，保证后续角色变更后仍可追溯。"""
        if not user_id:
            return {}

        user_result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
        user = user_result.scalar_one_or_none()
        snapshot: dict[str, Any] = {"id": user_id}

        if user:
            snapshot.update(
                {
                    "email": user.email,
                    "username": user.username,
                    "display_name": user.display_name,
                    "status": user.status,
                    "email_verified": bool(user.email_verified),
                }
            )

        if workspace_id:
            membership_result = await self.session.execute(
                select(MembershipORM).where(
                    and_(
                        MembershipORM.user_id == user_id,
                        MembershipORM.workspace_id == workspace_id,
                    )
                )
            )
            membership = membership_result.scalar_one_or_none()
            if membership:
                role, is_suspended = resolve_membership_role(membership.role)
                snapshot["workspace_role"] = role.value if role else membership.role
                snapshot["workspace_access"] = "suspended" if is_suspended else "active"
                snapshot["membership_id"] = membership.id

        return _json_safe(snapshot)

    async def record(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        action: AuditAction | str,
        request: Request | None = None,
        outcome: AuditOutcome = "success",
        target_type: str | None = None,
        target_id: str | None = None,
        detail: dict[str, Any] | None = None,
        actor_snapshot: dict[str, Any] | None = None,
        target_snapshot: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        event_category: str | None = None,
        event_type: str | None = None,
    ) -> AuditLogORM:
        """追加一条审计事件。调用方负责和业务变更一起提交事务。"""
        action_text = _action_value(action)
        trace = _trace_context(request)
        event_id = str(uuid.uuid4())
        merged_metadata = {
            **_request_metadata(request),
            **(metadata or {}),
        }

        if actor_snapshot is None:
            actor_snapshot = await self.build_user_snapshot(actor_user_id, workspace_id)

        # 写入意图说明：同事务追加审计事件，业务成功才持久化，避免伪成功审计。
        audit_log = AuditLogORM(
            id=str(uuid.uuid4()),
            event_id=event_id,
            workspace_id=workspace_id,
            user_id=actor_user_id,
            request_id=trace["request_id"],
            trace_id=trace["trace_id"],
            span_id=trace["span_id"],
            event_category=event_category or _category_for_action(action_text),
            event_type=event_type or _type_for_action(action_text),
            action=action_text,
            outcome=outcome,
            target_type=target_type,
            target_id=target_id,
            actor_snapshot=_json_safe(actor_snapshot or {}),
            target_snapshot=_json_safe(target_snapshot or {}),
            detail=_json_safe(detail or {}),
            metadata_json=_json_safe(merged_metadata),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent") if request else None,
            schema_version=SCHEMA_VERSION,
        )
        self.session.add(audit_log)
        return audit_log

    async def list_logs(
        self,
        *,
        workspace_id: str,
        page: int,
        page_size: int,
        action: str | None = None,
        outcome: str | None = None,
        user_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        request_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """分页查询审计日志，并返回与当前过滤条件一致的总数。"""
        filters = [AuditLogORM.workspace_id == workspace_id]
        if action:
            filters.append(AuditLogORM.action == action)
        if outcome:
            filters.append(AuditLogORM.outcome == outcome)
        if user_id:
            filters.append(AuditLogORM.user_id == user_id)
        if target_type:
            filters.append(AuditLogORM.target_type == target_type)
        if target_id:
            filters.append(AuditLogORM.target_id == target_id)
        if request_id:
            filters.append(AuditLogORM.request_id == request_id)
        if start_time:
            filters.append(AuditLogORM.created_at >= start_time)
        if end_time:
            filters.append(AuditLogORM.created_at <= end_time)

        result = await self.session.execute(
            select(AuditLogORM)
            .where(and_(*filters))
            .order_by(desc(AuditLogORM.created_at), desc(AuditLogORM.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        logs = result.scalars().all()

        count_result = await self.session.execute(
            select(func.count(AuditLogORM.id)).where(and_(*filters))
        )
        total = count_result.scalar() or 0

        return {
            "logs": [self.serialize(log) for log in logs],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def serialize(self, log: AuditLogORM) -> dict[str, Any]:
        """将 ORM 转为前端可直接渲染的结构。"""
        return {
            "id": log.id,
            "event_id": log.event_id or log.id,
            "workspace_id": log.workspace_id,
            "user_id": log.user_id,
            "request_id": log.request_id,
            "trace_id": log.trace_id,
            "span_id": log.span_id,
            "event_category": log.event_category,
            "event_type": log.event_type,
            "action": log.action,
            "outcome": log.outcome or "success",
            "target_type": log.target_type,
            "target_id": log.target_id,
            "actor_snapshot": log.actor_snapshot or {},
            "target_snapshot": log.target_snapshot or {},
            "detail": log.detail or {},
            "metadata": log.metadata_json or {},
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "schema_version": log.schema_version or "legacy",
            "created_at": to_utc_iso(log.created_at) if log.created_at else None,
        }
