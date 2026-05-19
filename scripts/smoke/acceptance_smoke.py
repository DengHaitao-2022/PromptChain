#!/usr/bin/env python3
"""MVP smoke harness：本地基础设施 + fake provider 验收。

输出 JSON 结果，便于直接贴入 PR 描述；真实 provider live smoke 不由此脚本宣称通过。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@dataclass
class SmokeStep:
    name: str
    status: str
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


class SmokeBlockedError(RuntimeError):
    def __init__(self, reason: str, evidence: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence or {}


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _step(name: str, status: str, detail: str = "", **evidence: Any) -> SmokeStep:
    return SmokeStep(name=name, status=status, detail=detail, evidence=evidence)


def _print_result(result: dict[str, Any]) -> None:
    print(_json_dump(result))


async def _check_database() -> dict[str, Any]:
    from core.config import get_settings
    from db.postgres_store import get_postgres_store
    from sqlalchemy import text

    database_url = get_settings().DATABASE_URL
    store = get_postgres_store()
    try:
        async with store.async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise SmokeBlockedError(
            "PostgreSQL 不可用，请先确认 DATABASE_URL 与 docker compose postgres 状态。",
            {"database_url": _mask_database_url(database_url), "error": str(exc)},
        ) from exc
    return {"database_url": _mask_database_url(database_url)}


async def _check_redis_if_enabled() -> dict[str, Any]:
    from core.config import get_settings

    settings = get_settings()
    if settings.WORKFLOW_EVENT_BUS_BACKEND != "redis":
        return {"backend": settings.WORKFLOW_EVENT_BUS_BACKEND, "checked": False}

    try:
        from redis import asyncio as redis_asyncio
    except ImportError as exc:
        raise SmokeBlockedError(
            "Redis 事件总线已启用，但 redis Python 客户端不可用。",
            {"backend": settings.WORKFLOW_EVENT_BUS_BACKEND},
        ) from exc

    client = redis_asyncio.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        raise SmokeBlockedError(
            "Redis 不可用，请先确认 REDIS_URL 与 docker compose redis 状态。",
            {"redis_url": settings.REDIS_URL, "error": str(exc)},
        ) from exc
    finally:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        result = close()
        if hasattr(result, "__await__"):
            await result
    return {"backend": "redis", "redis_url": settings.REDIS_URL, "checked": True}


def _check_fake_provider_env() -> dict[str, Any]:
    from core.config import get_settings

    settings = get_settings()
    provider = settings.DEFAULT_LLM_PROVIDER.strip().lower()
    if provider != "fake":
        raise SmokeBlockedError(
            "Local fake smoke 必须用 DEFAULT_LLM_PROVIDER=fake 启动后端服务。",
            {"DEFAULT_LLM_PROVIDER": provider or "<empty>"},
        )
    return {"DEFAULT_LLM_PROVIDER": provider, "DEFAULT_MODEL_NAME": settings.DEFAULT_MODEL_NAME}


def _mask_database_url(url: str) -> str:
    if "@" not in url:
        return url
    prefix, suffix = url.rsplit("@", 1)
    scheme = prefix.split("://", 1)[0] if "://" in prefix else "postgresql"
    return f"{scheme}://***:***@{suffix}"


def _workflow_definition_payload(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": "自动 smoke 验收创建的最小发布工作流",
        "nodes": [
            {
                "id": "input",
                "type": "input",
                "position": {"x": 0, "y": 0},
                "data": {"label": "输入", "config": {}},
            },
            {
                "id": "outline",
                "type": "process",
                "position": {"x": 220, "y": 0},
                "data": {"label": "提纲", "config": {"modelName": "fake-smoke-model"}},
            },
            {
                "id": "outline_gate",
                "type": "gate",
                "position": {"x": 440, "y": 0},
                "data": {"label": "提纲确认", "config": {"gateType": "approval", "timeout": 600}},
            },
            {
                "id": "content",
                "type": "process",
                "position": {"x": 660, "y": 0},
                "data": {"label": "正文", "config": {"modelName": "fake-smoke-model"}},
            },
            {
                "id": "checker",
                "type": "checker",
                "position": {"x": 880, "y": 0},
                "data": {"label": "事实核查", "config": {"confidenceThreshold": 0.8}},
            },
            {
                "id": "output",
                "type": "output",
                "position": {"x": 1100, "y": 0},
                "data": {"label": "输出", "config": {"outputFormat": "docx"}},
            },
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "outline"},
            {"id": "e2", "source": "outline", "target": "outline_gate"},
            {"id": "e3", "source": "outline_gate", "target": "content"},
            {"id": "e4", "source": "content", "target": "checker"},
            {"id": "e5", "source": "checker", "target": "output"},
        ],
    }


async def _activate_test_user(email: str) -> dict[str, Any]:
    import models.admin_orm  # noqa: F401 触发模型注册，避免 SQLAlchemy relationship 延迟解析失败。
    from db.postgres_store import get_postgres_store
    from models.auth_models import UserStatus
    from models.auth_orm import UserORM
    from sqlalchemy import func
    from sqlalchemy.future import select

    store = get_postgres_store()
    async with store.async_session() as session:
        normalized_email = str(email).strip().lower()
        result = await session.execute(
            select(UserORM).where(func.lower(UserORM.email) == normalized_email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise SmokeBlockedError("注册接口未创建测试用户。", {"email": email})
        user.status = UserStatus.ACTIVE.value
        user.email_verified = True
        await session.commit()
        return {"user_id": user.id, "email": user.email}


async def _wait_for_status(
    client: httpx.AsyncClient,
    workflow_run_id: str,
    *,
    expected: set[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = await client.get(f"/api/workflow/{workflow_run_id}")
        if response.status_code == 200:
            last_payload = response.json()
            status = last_payload.get("status")
            if status in expected:
                return last_payload
        await asyncio.sleep(1)
    raise SmokeBlockedError(
        "等待工作流状态超时。",
        {"workflow_run_id": workflow_run_id, "expected": sorted(expected), "last": last_payload},
    )


async def run_smoke(api_url: str, timeout_seconds: float) -> dict[str, Any]:
    steps: list[SmokeStep] = []
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    try:
        steps.append(
            _step("provider_env", "pass", "fake provider 已显式启用", **_check_fake_provider_env())
        )
        steps.append(_step("postgres", "pass", "PostgreSQL 可连接", **await _check_database()))
        steps.append(_step("redis", "pass", "Redis 前置检查完成", **await _check_redis_if_enabled()))

        async with httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            timeout=timeout_seconds,
            follow_redirects=False,
        ) as client:
            root_response = await client.get("/")
            if root_response.status_code != 200:
                raise SmokeBlockedError(
                    "后端 API 不可访问。",
                    {"status_code": root_response.status_code, "body": root_response.text[:500]},
                )
            steps.append(_step("api_health", "pass", "后端 API 可访问"))

            suffix = uuid.uuid4().hex[:8]
            email = f"smoke-{suffix}@example.com"
            password = "SmokePass123!"
            register_response = await client.post(
                "/api/auth/register",
                json={"email": email, "password": password, "display_name": f"Smoke {suffix}"},
            )
            if register_response.status_code not in {200, 400}:
                raise SmokeBlockedError(
                    "注册接口未返回可继续状态。",
                    {
                        "status_code": register_response.status_code,
                        "body": register_response.text[:500],
                    },
                )
            steps.append(
                _step(
                    "register",
                    "pass",
                    "注册接口已调用",
                    status_code=register_response.status_code,
                )
            )

            user_evidence = await _activate_test_user(email)
            steps.append(_step("activate_test_user", "pass", "测试账号已激活", **user_evidence))

            login_response = await client.post(
                "/api/auth/login",
                json={"email": email, "password": password},
            )
            if login_response.status_code != 200:
                raise SmokeBlockedError(
                    "登录接口失败。",
                    {"status_code": login_response.status_code, "body": login_response.text[:500]},
                )
            auth_context = login_response.json()
            workspace_id = (auth_context.get("workspace") or {}).get("id")
            steps.append(_step("login", "pass", "测试账号已登录", workspace_id=workspace_id))

            runtime_response = await client.get("/api/admin/model-providers/runtime")
            if runtime_response.status_code != 200:
                raise SmokeBlockedError(
                    "无法读取后端模型运行配置。",
                    {
                        "status_code": runtime_response.status_code,
                        "body": runtime_response.text[:800],
                    },
                )
            runtime = runtime_response.json().get("runtime") or {}
            if runtime.get("provider") != "fake":
                raise SmokeBlockedError(
                    "后端服务进程未使用 fake provider，请用 DEFAULT_LLM_PROVIDER=fake 重启后端。",
                    {"runtime": runtime},
                )
            steps.append(
                _step(
                    "backend_runtime_provider",
                    "pass",
                    "后端运行配置确认为 fake provider",
                    runtime=runtime,
                )
            )

            workflow_name = f"Smoke 工作流 {suffix}"
            create_response = await client.post(
                "/api/workflows",
                json=_workflow_definition_payload(workflow_name),
            )
            if create_response.status_code != 200:
                raise SmokeBlockedError(
                    "创建工作流失败。",
                    {"status_code": create_response.status_code, "body": create_response.text[:800]},
                )
            workflow = create_response.json()["data"]
            workflow_id = workflow["id"]
            steps.append(
                _step("create_workflow", "pass", "工作流草稿已创建", workflow_id=workflow_id)
            )

            publish_response = await client.post(
                f"/api/workflows/{workflow_id}/publish",
                json={"change_log": "smoke harness publish"},
            )
            if publish_response.status_code != 200:
                raise SmokeBlockedError(
                    "发布工作流失败。",
                    {"status_code": publish_response.status_code, "body": publish_response.text[:1000]},
                )
            publish_body = publish_response.json()
            if publish_body.get("code") != 0:
                raise SmokeBlockedError("发布校验未通过。", {"body": publish_body})
            workflow_version_id = publish_body["data"]["published_version_id"]
            steps.append(
                _step(
                    "publish_workflow",
                    "pass",
                    "工作流已发布",
                    workflow_id=workflow_id,
                    workflow_version_id=workflow_version_id,
                )
            )

            start_response = await client.post(
                "/api/workflow/start",
                json={
                    "user_input": "写一篇 PromptChain smoke 验收说明",
                    "workflow_definition_id": workflow_id,
                    "workflow_version_id": workflow_version_id,
                },
            )
            if start_response.status_code != 200:
                raise SmokeBlockedError(
                    "启动工作流失败。",
                    {"status_code": start_response.status_code, "body": start_response.text[:1000]},
                )
            workflow_run_id = start_response.json()["workflow_run_id"]
            steps.append(_step("start_run", "pass", "运行已启动", workflow_run_id=workflow_run_id))

            outline_wait = await _wait_for_status(
                client,
                workflow_run_id,
                expected={"awaiting_outline_approval", "completed", "failed"},
                timeout_seconds=timeout_seconds,
            )
            if outline_wait["status"] == "failed":
                raise SmokeBlockedError("工作流进入 failed。", {"workflow": outline_wait})
            if outline_wait["status"] == "awaiting_outline_approval":
                approve_response = await client.post(
                    f"/api/workflow/{workflow_run_id}/approve-outline",
                    json={"action": "approve"},
                )
                if approve_response.status_code != 200:
                    raise SmokeBlockedError(
                        "提纲 Gate 审批失败。",
                        {
                            "status_code": approve_response.status_code,
                            "body": approve_response.text[:1000],
                        },
                    )
                steps.append(_step("outline_gate", "pass", "提纲 Gate 已审批"))
            else:
                steps.append(_step("outline_gate", "pass", "运行未停在提纲 Gate，继续后续检查"))

            completed = await _wait_for_status(
                client,
                workflow_run_id,
                expected={"completed", "failed"},
                timeout_seconds=timeout_seconds,
            )
            if completed["status"] != "completed":
                raise SmokeBlockedError("工作流未完成。", {"workflow": completed})
            steps.append(
                _step(
                    "run_completed",
                    "pass",
                    "fake LLM 运行已完成",
                    workflow_status=completed["status"],
                )
            )

            rerun_options = await client.get(f"/api/workflow/{workflow_run_id}/rerun-options")
            if rerun_options.status_code != 200:
                raise SmokeBlockedError(
                    "获取重跑选项失败。",
                    {"status_code": rerun_options.status_code, "body": rerun_options.text[:800]},
                )
            options = rerun_options.json().get("options") or []
            from_node = next(
                (
                    item.get("node_name")
                    for item in options
                    if item.get("node_name") in {"generate_content", "generate_outline"}
                ),
                "generate_outline",
            )
            rerun_response = await client.post(
                f"/api/workflow/{workflow_run_id}/rerun",
                json={"from_node": from_node, "reason": "smoke rerun"},
            )
            if rerun_response.status_code != 200:
                raise SmokeBlockedError(
                    "重跑接口失败。",
                    {"status_code": rerun_response.status_code, "body": rerun_response.text[:1000]},
                )
            steps.append(
                _step(
                    "rerun",
                    "pass",
                    "重跑接口已创建新运行",
                    from_node=from_node,
                    new_workflow_run_id=rerun_response.json().get("new_workflow_run_id"),
                )
            )

            export_response = await client.get(f"/api/workflow/{workflow_run_id}/exports/docx")
            if export_response.status_code != 200:
                raise SmokeBlockedError(
                    "DOCX 导出失败。",
                    {"status_code": export_response.status_code, "body": export_response.text[:800]},
                )
            steps.append(
                _step(
                    "export_docx",
                    "pass",
                    "DOCX 导出成功",
                    content_type=export_response.headers.get("content-type"),
                    bytes=len(export_response.content),
                )
            )

    except SmokeBlockedError as exc:
        steps.append(_step("blocked", "blocked", exc.reason, **exc.evidence))
        return _build_result("blocked", started_at, steps, api_url)
    except Exception as exc:
        steps.append(_step("unexpected_error", "fail", str(exc), error_type=type(exc).__name__))
        return _build_result("fail", started_at, steps, api_url)

    return _build_result("pass", started_at, steps, api_url)


def _build_result(
    status: str,
    started_at: str,
    steps: list[SmokeStep],
    api_url: str,
) -> dict[str, Any]:
    return {
        "suite": "local_fake_llm",
        "status": status,
        "started_at": started_at,
        "api_url": api_url,
        "provider": "fake",
        "live_provider_smoke": "not_run",
        "steps": [step.__dict__ for step in steps],
        "pr_summary": {
            "ci_fake_contract": "not_run_by_script",
            "local_fake_llm": status,
            "manual_live_provider": "not_run",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PromptChain MVP smoke harness")
    parser.add_argument("--api-url", default=os.getenv("SMOKE_API_URL", "http://localhost:8000"))
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.getenv("SMOKE_TIMEOUT_SECONDS", "90")),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(run_smoke(args.api_url, args.timeout_seconds))
    _print_result(result)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
