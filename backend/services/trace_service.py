"""
Trace 回放服务

功能：
1. 可视化展示工作流执行过程
2. 点击任意节点查看输入/输出 Artifact
3. 对比不同版本的差异
4. 支持从任意节点 rerun
"""
from typing import List, Optional
from datetime import datetime

from models.artifact import (
    Artifact, 
    NodeRun, 
    WorkflowRun, 
    NodeRunStatus
)
from services.artifact_store import ArtifactStore, get_artifact_store


class TraceService:
    """Trace 回放服务"""
    
    def __init__(self, artifact_store: Optional[ArtifactStore] = None):
        self.store = artifact_store or get_artifact_store()
    
    async def get_workflow_trace(self, workflow_run_id: str) -> dict:
        """
        获取完整的工作流执行追踪
        
        返回结构：
        {
            "workflow": WorkflowRun,
            "nodes": [NodeRun, ...],  # 按执行顺序
            "artifacts": {artifact_id: Artifact, ...},
            "timeline": [
                {"timestamp": ..., "event": "node_started", "node": "parse_intent"},
                {"timestamp": ..., "event": "llm_call", "tokens": 1234},
                {"timestamp": ..., "event": "artifact_created", "artifact_id": "..."},
                ...
            ]
        }
        """
        workflow = await self.store.get_workflow_run(workflow_run_id)
        if not workflow:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")
        
        nodes = await self.store.get_node_runs_by_workflow(workflow_run_id)
        
        # 收集所有关联的 Artifacts
        artifact_ids = set()
        for node in nodes:
            artifact_ids.update(node.input_artifact_ids)
            artifact_ids.update(node.output_artifact_ids)
        
        artifacts = {}
        for aid in artifact_ids:
            artifact = await self.store.get_artifact(aid)
            if artifact:
                artifacts[aid] = artifact
        
        # 构建时间线
        timeline = self._build_timeline(nodes, artifacts)
        
        return {
            "workflow": workflow.model_dump(),
            "nodes": [n.model_dump() for n in nodes],
            "artifacts": {k: v.model_dump() for k, v in artifacts.items()},
            "timeline": timeline
        }
    
    def _build_timeline(
        self, 
        nodes: List[NodeRun], 
        artifacts: dict[str, Artifact]
    ) -> list:
        """构建执行时间线"""
        events = []
        
        for node in nodes:
            # 节点开始
            events.append({
                "timestamp": node.started_at.isoformat(),
                "event": "node_started",
                "node": node.node_name,
                "node_run_id": node.id
            })
            
            # LLM 调用
            for llm_call in node.llm_calls:
                events.append({
                    "timestamp": llm_call.created_at.isoformat(),
                    "event": "llm_call",
                    "model": llm_call.model,
                    "provider": llm_call.provider,
                    "tokens": llm_call.total_tokens,
                    "latency_ms": llm_call.latency_ms
                })
            
            # 人工决策
            if node.human_decision:
                events.append({
                    "timestamp": node.human_decision.timestamp.isoformat(),
                    "event": "human_decision",
                    "decision_type": node.human_decision.decision_type,
                    "node": node.node_name
                })
            
            # Artifact 创建
            for artifact_id in node.output_artifact_ids:
                artifact = artifacts.get(artifact_id)
                if artifact:
                    events.append({
                        "timestamp": artifact.created_at.isoformat(),
                        "event": "artifact_created",
                        "artifact_id": artifact_id,
                        "artifact_type": artifact.type.value,
                        "version": artifact.version
                    })
            
            # 节点完成
            if node.completed_at:
                events.append({
                    "timestamp": node.completed_at.isoformat(),
                    "event": "node_completed",
                    "node": node.node_name,
                    "status": node.status.value,
                    "duration_ms": node.duration_ms
                })
        
        # 按时间排序
        events.sort(key=lambda e: e["timestamp"])
        return events
    
    async def get_node_detail(self, node_run_id: str) -> dict:
        """
        获取节点运行详情（用于点击展开）
        
        包含完整的输入/输出 Artifact 内容
        """
        node = await self.store.get_node_run(node_run_id)
        if not node:
            raise ValueError(f"NodeRun not found: {node_run_id}")
        
        input_artifacts = []
        for aid in node.input_artifact_ids:
            artifact = await self.store.get_artifact(aid)
            if artifact:
                input_artifacts.append(artifact.model_dump())
        
        output_artifacts = []
        for aid in node.output_artifact_ids:
            artifact = await self.store.get_artifact(aid)
            if artifact:
                # 附带版本历史
                history = await self.store.get_version_history(aid)
                output_artifacts.append({
                    **artifact.model_dump(),
                    "version_history": [h.model_dump() for h in history]
                })
        
        return {
            "node": node.model_dump(),
            "input_artifacts": input_artifacts,
            "output_artifacts": output_artifacts
        }
    
    async def get_artifact_history(self, artifact_id: str) -> List[dict]:
        """获取 Artifact 的版本历史"""
        history = await self.store.get_version_history(artifact_id)
        return [h.model_dump() for h in history]
    
    async def compare_artifact_versions(
        self,
        version_a_id: str,
        version_b_id: str
    ) -> dict:
        """对比两个版本的差异"""
        a = await self.store.get_artifact(version_a_id)
        b = await self.store.get_artifact(version_b_id)
        
        if not a or not b:
            raise ValueError("Artifact not found")
        
        # 使用 deepdiff 对比差异
        try:
            from deepdiff import DeepDiff
            diff = DeepDiff(a.content, b.content, ignore_order=True)
            differences = diff.to_dict()
        except ImportError:
            # 如果没有 deepdiff，使用简单对比
            differences = {
                "content_a": a.content,
                "content_b": b.content,
                "hash_a": a.content_hash,
                "hash_b": b.content_hash,
                "is_different": a.content_hash != b.content_hash
            }
        
        return {
            "version_a": {
                "id": a.id,
                "version": a.version,
                "created_at": a.created_at.isoformat()
            },
            "version_b": {
                "id": b.id,
                "version": b.version,
                "created_at": b.created_at.isoformat()
            },
            "differences": differences
        }
    
    async def get_rerun_options(self, workflow_run_id: str) -> list:
        """
        获取可重跑的节点列表
        
        返回每个节点及其最新 Artifact 版本，供用户选择重跑起点
        """
        trace = await self.get_workflow_trace(workflow_run_id)
        
        options = []
        for node in trace["nodes"]:
            if node["status"] == NodeRunStatus.COMPLETED.value:
                # 获取该节点的输出 Artifact
                output_artifacts = [
                    trace["artifacts"][aid]
                    for aid in node["output_artifact_ids"]
                    if aid in trace["artifacts"]
                ]
                
                options.append({
                    "node_name": node["node_name"],
                    "node_run_id": node["id"],
                    "completed_at": node["completed_at"],
                    "output_artifacts": output_artifacts,
                    "can_rerun": True
                })
        
        return options


# 便捷函数
def get_trace_service() -> TraceService:
    """获取 TraceService 实例"""
    return TraceService()
