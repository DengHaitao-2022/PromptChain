"""
Self-Refine 自检修订节点

功能：
1. 生成→反馈→精炼循环
2. 自动评估内容质量
3. 创建 Artifact 版本
"""

from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models import ArtifactType, IntentCard, LLMCallRecord, NodeRun, NodeRunStatus, OutlineSection
from services import (
    format_workflow_error,
    get_artifact_store,
    get_current_model_info_for_workspace,
    get_llm_for_workspace,
    get_structured_llm_for_workspace,
    invoke_with_llm_retry,
    is_llm_rate_limit_error,
)


class RefinementFeedback(BaseModel):
    """自检反馈"""

    section_id: str = Field(..., description="章节ID")
    issues: list[str] = Field(default_factory=list, description="发现的问题")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")
    quality_score: float = Field(..., ge=0, le=10, description="质量评分 0-10")
    needs_revision: bool = Field(..., description="是否需要修订")


FEEDBACK_PROMPT = """作为一个严格的编辑，请审阅以下文章段落。

## 文章要求
目标受众: {audience}
风格要求: {tone}
目标字数: {target_words}

## 章节标题
{section_title}

## 待审阅内容
{content}

## 评估维度
1. 内容准确性：是否存在事实错误或逻辑漏洞
2. 风格一致性：是否符合风格要求
3. 结构清晰度：段落组织是否合理
4. 语言流畅度：表达是否自然通顺
5. 字数控制：是否符合目标字数 (当前: {current_words} 字)

请输出结构化的反馈，包括：
- section_id: "{section_id}"
- issues: 发现的问题列表
- suggestions: 改进建议列表
- quality_score: 0-10分的质量评分（8分以上为优秀，不需修订）
- needs_revision: 是否需要修订（quality_score < 8 时为 true）"""


REFINE_PROMPT = """请根据以下反馈，修订文章内容。

## 原始内容
{original_content}

## 反馈意见
{feedback}

## 修订要求
1. 仅修改反馈中指出的问题
2. 保持整体结构和风格一致
3. 确保修改后的内容更优质
4. 不要改变原文的核心观点

请输出修订后的完整内容（仅输出修订后的正文，不需要其他说明）："""


def _build_section_lookup(state: dict) -> dict[str, OutlineSection]:
    outline = state["outline"]
    return {section.id: section for section in outline.get_flat_sections()}


def _build_section_artifact_content(section: OutlineSection, content: str) -> dict:
    return {
        "section_id": section.id,
        "section_title": section.title,
        "section_summary": section.summary,
        "target_words": section.target_words,
        "dependencies": list(section.dependencies),
        "content": content,
        "word_count": len(content),
    }


def _build_compiled_content(state: dict, sections: dict[str, str]) -> str:
    compiled_sections: list[str] = []
    for section in state["outline"].get_flat_sections():
        content = sections.get(section.id)
        if not content:
            continue
        compiled_sections.append(f"## {section.title}\n{content}")
    return "\n\n".join(compiled_sections)


def _build_section_order(state: dict, sections: dict[str, str]) -> list[str]:
    return [
        section.id for section in state["outline"].get_flat_sections() if section.id in sections
    ]


async def _create_final_content_artifact(
    store,
    state: dict,
    workflow_run_id: str,
    node_run_id: str,
    sections: dict[str, str],
    section_artifact_ids: dict[str, str],
    refinement_history: list[dict],
    *,
    skipped_reason: str | None = None,
):
    return await store.create_artifact(
        artifact_type=ArtifactType.FINAL_CONTENT,
        content={
            "sections": sections,
            "section_order": _build_section_order(state, sections),
            "compiled_content": _build_compiled_content(state, sections),
            "refinement_history": refinement_history,
            "total_iterations": len(refinement_history),
            "refinement_skipped_reason": skipped_reason,
        },
        workflow_run_id=workflow_run_id,
        node_run_id=node_run_id,
        parent_version_id=state.get("final_content_artifact_id"),
        metadata={
            "section_artifact_ids": section_artifact_ids,
            "total_iterations": len(refinement_history),
            "refinement_skipped": skipped_reason is not None,
            "refinement_skipped_reason": skipped_reason,
        },
    )


async def generate_feedback(state: dict, section_id: str, content: str) -> RefinementFeedback:
    """为单个章节生成反馈"""
    intent_card: IntentCard = state["intent_card"]
    outline = state["outline"]

    # 找到对应章节
    section_title = ""
    target_words = 300
    for section in outline.get_flat_sections():
        if section.id == section_id:
            section_title = section.title
            target_words = section.target_words
            break

    llm = await get_structured_llm_for_workspace(
        RefinementFeedback,
        state.get("workspace_id"),
        model=state.get("model_name"),
        model_provider_id=state.get("model_provider_id"),
    )
    prompt = ChatPromptTemplate.from_template(FEEDBACK_PROMPT)
    chain = prompt | llm

    feedback = await invoke_with_llm_retry(
        lambda: chain.ainvoke(
            {
                "audience": intent_card.audience.value,
                "tone": intent_card.tone.value,
                "target_words": target_words,
                "section_title": section_title,
                "section_id": section_id,
                "content": content,
                "current_words": len(content),
            }
        )
    )

    return feedback


async def refine_section(
    state: dict, section_id: str, original_content: str, feedback: RefinementFeedback
) -> str:
    """根据反馈修订章节"""
    llm = await get_llm_for_workspace(
        state.get("workspace_id"),
        model=state.get("model_name"),
        model_provider_id=state.get("model_provider_id"),
        temperature=0.5,
    )  # 降低温度以保持一致性
    prompt = ChatPromptTemplate.from_template(REFINE_PROMPT)
    chain = prompt | llm

    # 格式化反馈
    feedback_text = f"""
问题:
{chr(10).join(f"- {issue}" for issue in feedback.issues)}

建议:
{chr(10).join(f"- {sug}" for sug in feedback.suggestions)}

质量评分: {feedback.quality_score}/10
"""

    result = await invoke_with_llm_retry(
        lambda: chain.ainvoke({"original_content": original_content, "feedback": feedback_text})
    )

    return result.content


async def self_refine_loop(state: dict, max_iterations: int = 2) -> dict:
    """
    生成→反馈→精炼循环

    输入 state:
        - draft_sections: Dict[str, str]
        - intent_card: IntentCard
        - workflow_run_id: str

    输出更新:
        - final_content: Dict[str, str]
        - refinement_history: List[dict]
    """
    draft_sections: dict[str, str] = state.get("draft_sections", {})
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="self_refine",
        node_type="process",
        started_at=datetime.utcnow(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=list(state.get("section_artifact_ids", {}).values()),
    )
    await store.create_node_run(node_run)

    current_content = dict(draft_sections)
    refinement_history: list[dict] = []
    latest_section_artifact_ids = dict(state.get("section_artifact_ids", {}))

    try:
        section_lookup = _build_section_lookup(state)

        for iteration in range(max_iterations):
            iteration_record = {
                "iteration": iteration + 1,
                "feedbacks": [],
                "revised_sections": [],
            }

            # Step 1: 生成反馈
            feedback_list: list[RefinementFeedback] = []
            for section_id, content in current_content.items():
                start_time = datetime.utcnow()
                feedback = await generate_feedback(state, section_id, content)
                end_time = datetime.utcnow()

                feedback_list.append(feedback)
                feedback_artifact = await store.create_artifact(
                    artifact_type=ArtifactType.REFINEMENT_FEEDBACK,
                    content={
                        "iteration": iteration + 1,
                        "section_id": section_id,
                        "feedback": feedback.model_dump(),
                        "content_snapshot": content,
                    },
                    workflow_run_id=workflow_run_id,
                    node_run_id=node_run.id,
                    metadata={
                        "source_section_artifact_id": latest_section_artifact_ids.get(section_id),
                        "quality_score": feedback.quality_score,
                        "needs_revision": feedback.needs_revision,
                    },
                )
                node_run.output_artifact_ids.append(feedback_artifact.id)
                iteration_record["feedbacks"].append(
                    {
                        **feedback.model_dump(),
                        "artifact_id": feedback_artifact.id,
                    }
                )

                # 记录 LLM 调用（动态获取模型配置）
                model_info = await get_current_model_info_for_workspace(
                    state.get("workspace_id"),
                    model_provider_id=state.get("model_provider_id"),
                    model=state.get("model_name"),
                )
                llm_call = LLMCallRecord(
                    model=model_info["model"],
                    provider=model_info["provider"],
                    latency_ms=int((end_time - start_time).total_seconds() * 1000),
                    prompt_preview=f"Feedback for {section_id}",
                    response_preview=f"Score: {feedback.quality_score}",
                )
                node_run.llm_calls.append(llm_call)

            # Step 2: 检查是否需要继续修订
            sections_needing_revision = [f for f in feedback_list if f.needs_revision]

            if not sections_needing_revision:
                # 质量已满足要求，停止循环
                refinement_history.append(iteration_record)
                break

            # Step 3: 执行修订
            for feedback in sections_needing_revision:
                section = section_lookup[feedback.section_id]
                start_time = datetime.utcnow()
                refined_content = await refine_section(
                    state, feedback.section_id, current_content[feedback.section_id], feedback
                )
                end_time = datetime.utcnow()

                current_content[feedback.section_id] = refined_content
                refined_section_artifact = await store.create_artifact(
                    artifact_type=ArtifactType.SECTION_CONTENT,
                    content=_build_section_artifact_content(section, refined_content),
                    workflow_run_id=workflow_run_id,
                    node_run_id=node_run.id,
                    parent_version_id=latest_section_artifact_ids.get(feedback.section_id),
                    metadata={
                        "generation_phase": "refined",
                        "iteration": iteration + 1,
                        "quality_score": feedback.quality_score,
                    },
                )
                latest_section_artifact_ids[feedback.section_id] = refined_section_artifact.id
                node_run.output_artifact_ids.append(refined_section_artifact.id)
                iteration_record["revised_sections"].append(
                    {
                        "section_id": feedback.section_id,
                        "artifact_id": refined_section_artifact.id,
                    }
                )

                # 记录 LLM 调用（动态获取模型配置）
                model_info = await get_current_model_info_for_workspace(
                    state.get("workspace_id"),
                    model_provider_id=state.get("model_provider_id"),
                    model=state.get("model_name"),
                )
                llm_call = LLMCallRecord(
                    model=model_info["model"],
                    provider=model_info["provider"],
                    latency_ms=int((end_time - start_time).total_seconds() * 1000),
                    prompt_preview=f"Refine {feedback.section_id}",
                    response_preview=refined_content[:100],
                )
                node_run.llm_calls.append(llm_call)

            refinement_history.append(iteration_record)

        # 创建最终内容 Artifact
        artifact = await _create_final_content_artifact(
            store,
            state,
            workflow_run_id,
            node_run.id,
            current_content,
            latest_section_artifact_ids,
            refinement_history,
        )
        node_run.output_artifact_ids.append(artifact.id)

        # 完成节点
        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)

        return {
            **state,
            "final_content": current_content,
            "final_content_artifact_id": artifact.id,
            "refinement_history": refinement_history,
            "section_artifact_ids": latest_section_artifact_ids,
        }

    except Exception as e:
        if is_llm_rate_limit_error(e) and current_content:
            skipped_reason = format_workflow_error(e)
            refinement_history.append(
                {
                    "iteration": len(refinement_history) + 1,
                    "feedbacks": [],
                    "revised_sections": [],
                    "skipped": True,
                    "reason": skipped_reason,
                }
            )
            artifact = await _create_final_content_artifact(
                store,
                state,
                workflow_run_id,
                node_run.id,
                current_content,
                latest_section_artifact_ids,
                refinement_history,
                skipped_reason=skipped_reason,
            )
            node_run.output_artifact_ids.append(artifact.id)
            node_run.complete(NodeRunStatus.COMPLETED)
            await store.update_node_run(node_run)
            return {
                **state,
                "final_content": current_content,
                "final_content_artifact_id": artifact.id,
                "refinement_history": refinement_history,
                "section_artifact_ids": latest_section_artifact_ids,
                "refinement_skipped_reason": skipped_reason,
            }

        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise
