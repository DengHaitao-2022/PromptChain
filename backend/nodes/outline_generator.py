"""
提纲生成节点

功能：
1. 基于意图卡生成文章提纲
2. 支持 Human-in-the-Loop 确认
3. 创建 Artifact 版本
"""
from typing import Any, Optional
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate

from models import IntentCard, Outline, OutlineSection, ArtifactType, NodeRun, NodeRunStatus, LLMCallRecord, HumanDecision
from services import get_llm, get_structured_llm, get_artifact_store, get_current_model_info


OUTLINE_GENERATION_PROMPT = """基于以下意图卡，生成一份结构清晰、逻辑连贯的文章提纲。

## 意图卡
目标: {goal}
主题: {topic}
受众: {audience}
风格: {tone}
目标字数: {length}
必须包含: {must_include}
禁止内容: {must_exclude}

## 要求
1. 提纲应包含3-7个主要章节
2. 每个章节应有明确的目标和字数分配
3. 章节之间应有逻辑递进关系
4. 确保覆盖所有"必须包含"的项目
5. 避免"禁止内容"中的项目
6. 总字数分配应接近目标字数

## 输出格式
请生成完整的提纲结构，包括：
- title: 文章标题
- abstract: 概述/导语（50-100字的内容摘要）
- sections: 章节列表，每个章节包含 id, title, summary, target_words
- total_target_words: 总目标字数"""


async def generate_outline(state: dict) -> dict:
    """
    生成提纲
    
    输入 state:
        - intent_card: IntentCard
        - workflow_run_id: str
        - outline_feedback: Optional[str]  # 用户反馈（用于重新生成）
    
    输出更新:
        - outline: Outline
        - outline_artifact_id: str
        - awaiting_outline_approval: bool
    """
    intent_card: IntentCard = state["intent_card"]
    workflow_run_id = state["workflow_run_id"]
    outline_feedback = state.get("outline_feedback", "")
    store = get_artifact_store()
    
    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="generate_outline",
        node_type="llm_call",
        started_at=datetime.utcnow(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[state.get("intent_card_artifact_id", "")]
    )
    await store.create_node_run(node_run)
    
    try:
        # 构建 prompt
        prompt_template = OUTLINE_GENERATION_PROMPT
        if outline_feedback:
            prompt_template += f"\n\n## 用户反馈（请根据此反馈调整提纲）\n{outline_feedback}"
        
        llm = get_structured_llm(Outline)
        prompt = ChatPromptTemplate.from_template(prompt_template)
        chain = prompt | llm
        
        # 调用 LLM
        start_time = datetime.utcnow()
        outline: Outline = await chain.ainvoke({
            "goal": intent_card.goal,
            "topic": intent_card.topic,
            "audience": intent_card.audience.value,
            "tone": intent_card.tone.value,
            "length": intent_card.length,
            "must_include": ", ".join(intent_card.must_include) or "无特殊要求",
            "must_exclude": ", ".join(intent_card.must_exclude) or "无"
        })
        end_time = datetime.utcnow()
        
        # 记录 LLM 调用（动态获取模型配置）
        model_info = get_current_model_info()
        llm_call = LLMCallRecord(
            model=model_info["model"],
            provider=model_info["provider"],
            latency_ms=int((end_time - start_time).total_seconds() * 1000),
            prompt_preview=intent_card.topic[:100],
            response_preview=outline.title[:100]
        )
        node_run.llm_calls.append(llm_call)
        
        # 创建 Artifact
        parent_artifact_id = state.get("outline_artifact_id")  # 如果是重新生成
        artifact = await store.create_artifact(
            type=ArtifactType.OUTLINE,
            content=outline.model_dump(),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            parent_version_id=parent_artifact_id,
            metadata={"feedback": outline_feedback} if outline_feedback else {}
        )
        
        # 更新节点运行记录（标记为中断，等待用户确认）
        node_run.output_artifact_ids.append(artifact.id)
        node_run.status = NodeRunStatus.INTERRUPTED  # 等待用户确认
        await store.update_node_run(node_run)
        
        return {
            **state,
            "outline": outline,
            "outline_artifact_id": artifact.id,
            "outline_node_run_id": node_run.id,
            "awaiting_outline_approval": True,
            "outline_feedback": None  # 清除反馈
        }
        
    except Exception as e:
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise


async def approve_outline(state: dict) -> dict:
    """
    处理用户对提纲的审批决策
    
    输入 state:
        - outline: Outline
        - user_decision: dict  # {action: "approve"|"modify"|"regenerate", ...}
    
    输出更新:
        - outline: Outline (如果修改)
        - outline_approved: bool
        - outline_feedback: str (如果需要重新生成)
    """
    outline: Outline = state["outline"]
    user_decision = state.get("user_decision", {"action": "approve"})
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()
    
    action = user_decision.get("action", "approve")
    
    # 获取原节点运行记录
    node_run_id = state.get("outline_node_run_id")
    if node_run_id:
        node_run = await store.get_node_run(node_run_id)
        if node_run:
            # 记录人工决策
            node_run.human_decision = HumanDecision(
                decision_type=action,
                user_input=user_decision.get("feedback", ""),
                modified_content=user_decision.get("modified_outline")
            )
    
    if action == "approve":
        # 用户确认，标记提纲已批准
        outline.is_approved = True
        
        if node_run:
            node_run.complete(NodeRunStatus.COMPLETED)
            await store.update_node_run(node_run)
        
        return {
            **state,
            "outline": outline,
            "outline_approved": True,
            "awaiting_outline_approval": False
        }
    
    elif action == "modify":
        # 用户修改了提纲
        modified_data = user_decision.get("modified_outline", outline.model_dump())
        modified_outline = Outline.model_validate(modified_data)
        modified_outline.version = outline.version + 1
        modified_outline.is_approved = True
        
        # 创建新版本 Artifact
        artifact = await store.create_artifact(
            type=ArtifactType.OUTLINE,
            content=modified_outline.model_dump(),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id if node_run else "",
            parent_version_id=state.get("outline_artifact_id"),
            metadata={"action": "user_modified"}
        )
        
        if node_run:
            node_run.output_artifact_ids.append(artifact.id)
            node_run.complete(NodeRunStatus.COMPLETED)
            await store.update_node_run(node_run)
        
        return {
            **state,
            "outline": modified_outline,
            "outline_artifact_id": artifact.id,
            "outline_approved": True,
            "awaiting_outline_approval": False
        }
    
    else:  # regenerate
        # 用户要求重新生成
        if node_run:
            node_run.complete(NodeRunStatus.COMPLETED)
            await store.update_node_run(node_run)
        
        return {
            **state,
            "outline": None,
            "outline_approved": False,
            "awaiting_outline_approval": False,
            "outline_feedback": user_decision.get("feedback", "请重新生成提纲")
        }
