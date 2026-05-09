"""
Artifact 版本化存储服务

核心原则：
1. 写入即不可变（Write-Once）
2. 版本链可追溯
3. rerun 创建新版本，不覆盖旧版本
"""

import hashlib
import json
import os
from typing import Any

from db.postgres_store import PostgresArtifactStore, get_postgres_store
from models.artifact import Artifact, ArtifactType, NodeRun, WorkflowRun


class ArtifactStore:
    """
    Artifact 版本化存储服务

    当前实现使用内存存储，后续可替换为 SQLite/PostgreSQL
    """

    def __init__(self):
        # 内存存储（开发阶段）
        self._artifacts: dict[str, Artifact] = {}
        self._node_runs: dict[str, NodeRun] = {}
        self._workflow_runs: dict[str, WorkflowRun] = {}

    def _compute_hash(self, content: Any) -> str:
        """计算内容哈希"""
        content_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    async def create_artifact(
        self,
        artifact_type: ArtifactType | None = None,
        *,
        content: Any,
        workflow_run_id: str,
        node_run_id: str,
        parent_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Artifact:
        """
        创建新的 Artifact 版本

        - 如果是首次创建，version = 1
        - 如果是 rerun/修改，version = parent.version + 1
        """
        # 兼容旧调用：历史代码可能使用 `type=` 传参，这里统一归一为 artifact_type。
        if artifact_type is None:
            artifact_type = kwargs.get("type")
        if artifact_type is None:
            raise ValueError("artifact_type is required")

        metadata = metadata or {}

        # 计算版本号
        if parent_version_id:
            parent = await self.get_artifact(parent_version_id)
            version = parent.version + 1 if parent else 1
        else:
            # 查询同类型同工作流的最大版本号
            max_version = await self._get_max_version(workflow_run_id, artifact_type)
            version = max_version + 1 if max_version else 1

        artifact = Artifact(
            type=artifact_type,
            version=version,
            content=content,
            content_hash=self._compute_hash(content),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run_id,
            parent_version=parent_version_id,
            metadata=metadata,
        )

        # 持久化（不可覆盖）
        self._artifacts[artifact.id] = artifact

        return artifact

    async def _get_max_version(self, workflow_run_id: str, artifact_type: ArtifactType) -> int:
        """获取指定工作流中某类型的最大版本号"""
        versions = [
            a.version
            for a in self._artifacts.values()
            if a.workflow_run_id == workflow_run_id and a.type == artifact_type
        ]
        return max(versions) if versions else 0

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        """获取指定 Artifact"""
        return self._artifacts.get(artifact_id)

    async def get_version_history(self, artifact_id: str) -> list[Artifact]:
        """
        获取 Artifact 的完整版本历史链

        返回从最早版本到当前版本的有序列表
        """
        history = []
        current = await self.get_artifact(artifact_id)

        while current:
            history.append(current)
            if current.parent_version:
                current = await self.get_artifact(current.parent_version)
            else:
                break

        return list(reversed(history))  # 从旧到新

    async def get_latest_by_type(
        self, workflow_run_id: str, artifact_type: ArtifactType
    ) -> Artifact | None:
        """获取指定工作流中某类型的最新版本"""
        artifacts = [
            a
            for a in self._artifacts.values()
            if a.workflow_run_id == workflow_run_id and a.type == artifact_type
        ]
        if not artifacts:
            return None
        return max(artifacts, key=lambda a: a.version)

    async def get_artifacts_by_workflow(self, workflow_run_id: str) -> list[Artifact]:
        """获取工作流的所有 Artifacts"""
        return [a for a in self._artifacts.values() if a.workflow_run_id == workflow_run_id]

    # NodeRun 相关方法
    async def create_node_run(self, node_run: NodeRun) -> NodeRun:
        """创建节点运行记录"""
        self._node_runs[node_run.id] = node_run
        return node_run

    async def update_node_run(self, node_run: NodeRun) -> NodeRun:
        """更新节点运行记录"""
        self._node_runs[node_run.id] = node_run
        return node_run

    async def get_node_run(self, node_run_id: str) -> NodeRun | None:
        """获取节点运行记录"""
        return self._node_runs.get(node_run_id)

    async def get_node_runs_by_workflow(self, workflow_run_id: str) -> list[NodeRun]:
        """获取工作流的所有节点运行记录（按时间排序）"""
        runs = [r for r in self._node_runs.values() if r.workflow_run_id == workflow_run_id]
        return sorted(runs, key=lambda r: r.started_at)

    # WorkflowRun 相关方法
    async def create_workflow_run(self, workflow_run: WorkflowRun) -> WorkflowRun:
        """创建工作流运行记录"""
        self._workflow_runs[workflow_run.id] = workflow_run
        return workflow_run

    async def update_workflow_run(self, workflow_run: WorkflowRun) -> WorkflowRun:
        """更新工作流运行记录"""
        self._workflow_runs[workflow_run.id] = workflow_run
        return workflow_run

    async def get_workflow_run(self, workflow_run_id: str) -> WorkflowRun | None:
        """获取工作流运行记录"""
        return self._workflow_runs.get(workflow_run_id)

    async def list_workflow_runs(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
    ) -> list[WorkflowRun]:
        """按当前工作空间和用户范围返回可见的运行记录。"""
        runs = []
        for workflow_run in self._workflow_runs.values():
            metadata = workflow_run.metadata or {}
            if metadata.get("workspace_id") != workspace_id:
                continue
            if user_id is not None and metadata.get("user_id") != user_id:
                continue
            runs.append(workflow_run)
        return sorted(runs, key=lambda run: run.started_at, reverse=True)

    async def get_all_workflow_runs(self) -> list[WorkflowRun]:
        """获取所有工作流运行记录（按时间倒序）"""
        runs = list(self._workflow_runs.values())
        return sorted(runs, key=lambda r: r.started_at, reverse=True)


# 全局单例
_artifact_store: ArtifactStore | PostgresArtifactStore | None = None
DEFAULT_RUNTIME_STORE_BACKEND = "postgres"


def _resolve_runtime_store_backend() -> str:
    """解析运行态存储后端。"""
    backend = os.getenv("RUNTIME_STORE_BACKEND", DEFAULT_RUNTIME_STORE_BACKEND)
    return backend.strip().lower() or DEFAULT_RUNTIME_STORE_BACKEND


def get_artifact_store() -> ArtifactStore | PostgresArtifactStore:
    """获取运行态存储单例，默认使用 PostgreSQL。"""
    global _artifact_store
    if _artifact_store is None:
        backend = _resolve_runtime_store_backend()
        _artifact_store = ArtifactStore() if backend == "memory" else get_postgres_store()
    assert _artifact_store is not None
    return _artifact_store
