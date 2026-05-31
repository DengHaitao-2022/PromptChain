"""知识库 API 路由。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

import routes.workflow_helpers as workflow_helpers
from db.postgres_store import get_postgres_store
from models.knowledge import (
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeDocument,
    KnowledgeDocumentLifecycleStatus,
    KnowledgeScope,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from services.knowledge_service import KnowledgeService

router = APIRouter(tags=["knowledge"])
MAX_KNOWLEDGE_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应。"""

    knowledge_bases: list[KnowledgeBase]


class CreateKnowledgeBaseRequest(BaseModel):
    """创建知识库请求。"""

    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = None
    scope: KnowledgeScope = KnowledgeScope.WORKSPACE


class UpdateKnowledgeBaseRequest(BaseModel):
    """更新知识库请求。"""

    name: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = None
    status: KnowledgeBaseStatus | None = None


class KnowledgeDocumentListResponse(BaseModel):
    """文档列表响应。"""

    documents: list[KnowledgeDocument]


class UpdateKnowledgeDocumentRequest(BaseModel):
    """更新文档状态请求。"""

    status: KnowledgeDocumentLifecycleStatus


class KnowledgeDeleteResponse(BaseModel):
    """删除操作响应。"""

    message: str


def _coerce_scopes(scopes: str | None) -> list[KnowledgeScope] | None:
    """解析逗号分隔 scope，供列表查询使用。"""
    if not scopes:
        return None
    parsed: list[KnowledgeScope] = []
    for raw_scope in scopes.split(","):
        value = raw_scope.strip()
        if not value:
            continue
        try:
            parsed.append(KnowledgeScope(value))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"不支持的知识库范围: {value}") from exc
    return parsed or None


def _normalize_service_error(exc: ValueError, *, not_found: bool = False) -> HTTPException:
    """把服务层业务错误转换为稳定 HTTP 响应。"""
    message = str(exc)
    if "无权访问" in message or "没有 knowledge_base" in message:
        return HTTPException(status_code=403, detail=message)
    if not_found or "不存在" in message:
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)


async def _knowledge_context(
    request: Request,
    *,
    action: str = "read",
) -> tuple[str, str, object]:
    user_id, workspace_id, role = await workflow_helpers.require_workspace_permission(
        request,
        "knowledge_base",
        action,
    )
    return user_id, workspace_id, role


async def _workspace_member_context(request: Request) -> tuple[str, str, object]:
    """仅确认当前用户属于工作空间，细粒度知识库权限由服务层按 scope 判断。"""
    return await _knowledge_context(request, action="read")


def _postgres_store():
    """集中获取已支持迁移初始化的 PostgreSQL store。"""
    return get_postgres_store()


async def _read_upload_file_bounded(file: UploadFile) -> bytes:
    """边读边限制上传大小，避免超大文件一次性占满 worker 内存。"""
    total_bytes = 0
    chunks: list[bytes] = []
    while chunk := await file.read(UPLOAD_CHUNK_SIZE):
        total_bytes += len(chunk)
        if total_bytes > MAX_KNOWLEDGE_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="知识库单文件大小不能超过 20MB")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get(
    "/workspaces/{workspace_id}/knowledge-bases",
    response_model=KnowledgeBaseListResponse,
)
async def list_workspace_knowledge_bases(
    workspace_id: str,
    request: Request,
    scopes: str | None = None,
) -> KnowledgeBaseListResponse:
    """列出当前用户在工作空间内可见的知识库。"""
    user_id, current_workspace_id, _ = await _knowledge_context(request, action="read")
    if workspace_id != current_workspace_id:
        raise HTTPException(status_code=403, detail="您无权访问该工作空间的知识库")

    async with _postgres_store().initialized_session() as session:
        service = KnowledgeService(session)
        knowledge_bases = await service.list_knowledge_bases(
            workspace_id=workspace_id,
            user_id=user_id,
            scopes=_coerce_scopes(scopes),
        )
        return KnowledgeBaseListResponse(knowledge_bases=knowledge_bases)


@router.post(
    "/workspaces/{workspace_id}/knowledge-bases",
    response_model=KnowledgeBase,
)
async def create_workspace_knowledge_base(
    workspace_id: str,
    request: Request,
    body: CreateKnowledgeBaseRequest,
) -> KnowledgeBase:
    """创建工作空间或个人知识库。"""
    if body.scope == KnowledgeScope.RUN_UPLOAD:
        raise HTTPException(status_code=400, detail="本次运行资料只能随工作流启动上传")
    user_id, current_workspace_id, role = await _workspace_member_context(request)
    if workspace_id != current_workspace_id:
        raise HTTPException(status_code=403, detail="您无权在该工作空间创建知识库")

    async with _postgres_store().initialized_session() as session:
        try:
            return await KnowledgeService(session).create_knowledge_base(
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
                name=body.name,
                description=body.description,
                scope=body.scope,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc) from exc


@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBase)
async def get_knowledge_base(kb_id: str, request: Request) -> KnowledgeBase:
    """获取知识库详情。"""
    user_id, workspace_id, _ = await _knowledge_context(request, action="read")
    async with _postgres_store().initialized_session() as session:
        try:
            row = await KnowledgeService(session).get_knowledge_base(
                kb_id=kb_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            from services.knowledge_service import _row_to_knowledge_base

            return _row_to_knowledge_base(row)
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.patch("/knowledge-bases/{kb_id}", response_model=KnowledgeBase)
async def update_knowledge_base(
    kb_id: str,
    request: Request,
    body: UpdateKnowledgeBaseRequest,
) -> KnowledgeBase:
    """更新知识库名称、描述或状态。"""
    user_id, workspace_id, role = await _workspace_member_context(request)
    async with _postgres_store().initialized_session() as session:
        try:
            return await KnowledgeService(session).update_knowledge_base(
                kb_id=kb_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
                name=body.name,
                description=body.description,
                status=body.status,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.delete("/knowledge-bases/{kb_id}", response_model=KnowledgeDeleteResponse)
async def delete_knowledge_base(kb_id: str, request: Request) -> KnowledgeDeleteResponse:
    """删除知识库及其文档、Chunk 与向量。"""
    user_id, workspace_id, role = await _workspace_member_context(request)
    async with _postgres_store().initialized_session() as session:
        try:
            await KnowledgeService(session).delete_knowledge_base(
                kb_id=kb_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
            )
            return KnowledgeDeleteResponse(message="知识库已删除")
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.get(
    "/knowledge-bases/{kb_id}/documents",
    response_model=KnowledgeDocumentListResponse,
)
async def list_knowledge_documents(
    kb_id: str,
    request: Request,
) -> KnowledgeDocumentListResponse:
    """列出知识库文档。"""
    user_id, workspace_id, _ = await _knowledge_context(request, action="read")
    async with _postgres_store().initialized_session() as session:
        try:
            documents = await KnowledgeService(session).list_documents(
                kb_id=kb_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            return KnowledgeDocumentListResponse(documents=documents)
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=KnowledgeDocument,
)
async def upload_knowledge_document(
    kb_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
    metadata_json: Annotated[str | None, Form()] = None,
) -> KnowledgeDocument:
    """上传并同步索引文档。"""
    user_id, workspace_id, role = await _workspace_member_context(request)
    content = await _read_upload_file_bounded(file)
    metadata: dict[str, Any] = {}
    if metadata_json:
        import json

        try:
            parsed = json.loads(metadata_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="metadata_json 不是合法 JSON") from exc
        if isinstance(parsed, dict):
            metadata = parsed
        else:
            raise HTTPException(status_code=422, detail="metadata_json 必须是对象")

    async with _postgres_store().initialized_session() as session:
        try:
            return await KnowledgeService(session).add_document(
                kb_id=kb_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
                file_name=file.filename or "untitled.txt",
                content=content,
                metadata=metadata,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.get("/documents/{document_id}", response_model=KnowledgeDocument)
async def get_knowledge_document(
    document_id: str,
    request: Request,
) -> KnowledgeDocument:
    """获取文档元数据。"""
    user_id, workspace_id, _ = await _knowledge_context(request, action="read")
    async with _postgres_store().initialized_session() as session:
        try:
            row = await KnowledgeService(session).get_document(
                document_id=document_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            from services.knowledge_service import _row_to_document

            return _row_to_document(row)
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.patch("/documents/{document_id}", response_model=KnowledgeDocument)
async def update_knowledge_document(
    document_id: str,
    request: Request,
    body: UpdateKnowledgeDocumentRequest,
) -> KnowledgeDocument:
    """停用、启用或归档单个文档。"""
    user_id, workspace_id, role = await _workspace_member_context(request)
    async with _postgres_store().initialized_session() as session:
        try:
            return await KnowledgeService(session).update_document_status(
                document_id=document_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
                status=body.status,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.delete("/documents/{document_id}", response_model=KnowledgeDeleteResponse)
async def delete_knowledge_document(
    document_id: str,
    request: Request,
) -> KnowledgeDeleteResponse:
    """删除文档及其索引。"""
    user_id, workspace_id, role = await _workspace_member_context(request)
    async with _postgres_store().initialized_session() as session:
        try:
            await KnowledgeService(session).delete_document(
                document_id=document_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
            )
            return KnowledgeDeleteResponse(message="文档已删除")
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.post("/documents/{document_id}/reindex", response_model=KnowledgeDocument)
async def reindex_knowledge_document(
    document_id: str,
    request: Request,
) -> KnowledgeDocument:
    """重建文档索引。"""
    user_id, workspace_id, role = await _workspace_member_context(request)
    async with _postgres_store().initialized_session() as session:
        try:
            return await KnowledgeService(session).reindex_document(
                document_id=document_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.post("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    request: Request,
    body: KnowledgeSearchRequest,
) -> KnowledgeSearchResponse:
    """在当前工作空间和当前用户权限范围内检索知识。"""
    user_id, workspace_id, _ = await _knowledge_context(request, action="read")
    if body.workspace_id and body.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="您无权检索该工作空间的知识库")

    async with _postgres_store().initialized_session() as session:
        try:
            return await KnowledgeService(session).search(
                request=body,
                workspace_id=workspace_id,
                user_id=user_id,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc) from exc
