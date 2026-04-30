"""
内容生成节点

功能：
1. 基于提纲分段生成内容
2. 支持流式输出
3. 创建 Artifact 版本
"""

from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate

from models import (
    ArtifactType,
    IntentCard,
    LLMCallRecord,
    NodeRun,
    NodeRunStatus,
    Outline,
    OutlineSection,
)
from services import get_artifact_store, get_current_model_info, get_llm, invoke_with_llm_retry

SECTION_GENERATION_PROMPT = """你是一位专业的内容创作者。请根据以下信息撰写文章的一个章节。

## 文章信息
标题: {article_title}
目标受众: {audience}
风格要求: {tone}

## 当前章节
章节标题: {section_title}
章节摘要/要点: {section_summary}
目标字数: {target_words}

## 已完成章节（上下文）
{previous_sections}

## 要求
1. 严格遵循风格要求
2. 确保与已完成章节的内容连贯
3. 控制字数在目标字数 ±10% 范围内
4. 内容要有深度，避免泛泛而谈
5. 使用适当的段落结构

请开始撰写{section_title}章节的内容："""


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


def _compile_generated_content(outline: Outline, sections: dict[str, str]) -> str:
    compiled_sections: list[str] = []
    for section in outline.get_flat_sections():
        content = sections.get(section.id)
        if not content:
            continue
        compiled_sections.append(f"## {section.title}\n{content}")
    return "\n\n".join(compiled_sections)


async def generate_section(state: dict, section: OutlineSection, previous_content: str = "") -> str:
    """
    生成单个章节内容

    Args:
        state: 工作流状态
        section: 要生成的章节
        previous_content: 已完成章节的内容（上下文）

    Returns:
        生成的章节内容
    """
    intent_card: IntentCard = state["intent_card"]
    outline: Outline = state["outline"]

    llm = get_llm(temperature=0.7)
    prompt = ChatPromptTemplate.from_template(SECTION_GENERATION_PROMPT)
    chain = prompt | llm

    result = await invoke_with_llm_retry(
        lambda: chain.ainvoke(
            {
                "article_title": outline.title,
                "audience": intent_card.audience.value,
                "tone": intent_card.tone.value,
                "section_title": section.title,
                "section_summary": section.summary,
                "target_words": section.target_words,
                "previous_sections": previous_content or "（这是第一个章节）",
            }
        )
    )

    return result.content


async def generate_all_sections(state: dict) -> dict:
    """
    按顺序生成所有章节

    输入 state:
        - intent_card: IntentCard
        - outline: Outline
        - workflow_run_id: str

    输出更新:
        - draft_sections: Dict[str, str]  # {section_id: content}
        - section_artifact_ids: Dict[str, str]  # {section_id: artifact_id}
    """
    outline: Outline = state["outline"]
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="generate_content",
        node_type="process",
        started_at=datetime.utcnow(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[
            artifact_id
            for artifact_id in [
                state.get("intent_card_artifact_id"),
                state.get("outline_artifact_id"),
            ]
            if artifact_id
        ],
    )
    await store.create_node_run(node_run)

    try:
        generated_sections: dict[str, str] = {}
        section_artifact_ids: dict[str, str] = {}
        previous_content = ""

        # 获取扁平化的章节列表
        flat_sections = outline.get_flat_sections()

        for index, section in enumerate(flat_sections):
            # 生成章节内容
            start_time = datetime.utcnow()
            content = await generate_section(state, section, previous_content)
            end_time = datetime.utcnow()

            generated_sections[section.id] = content

            # 记录 LLM 调用（动态获取模型配置）
            model_info = get_current_model_info()
            llm_call = LLMCallRecord(
                model=model_info["model"],
                provider=model_info["provider"],
                latency_ms=int((end_time - start_time).total_seconds() * 1000),
                prompt_preview=section.title,
                response_preview=content[:200] if len(content) > 200 else content,
            )
            node_run.llm_calls.append(llm_call)

            # 创建章节 Artifact
            artifact = await store.create_artifact(
                artifact_type=ArtifactType.SECTION_CONTENT,
                content=_build_section_artifact_content(section, content),
                workflow_run_id=workflow_run_id,
                node_run_id=node_run.id,
                metadata={
                    "section_index": index,
                    "generation_phase": "draft",
                    "outline_artifact_id": state.get("outline_artifact_id"),
                    "previous_section_ids": [
                        previous_section.id for previous_section in flat_sections[:index]
                    ],
                },
            )
            section_artifact_ids[section.id] = artifact.id
            node_run.output_artifact_ids.append(artifact.id)

            # 更新上下文
            previous_content += f"\n\n## {section.title}\n{content}"

        # 完成节点
        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)

        return {
            **state,
            "draft_sections": generated_sections,
            "section_artifact_ids": section_artifact_ids,
            "generated_content": _compile_generated_content(outline, generated_sections),
        }

    except Exception as e:
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise


async def regenerate_section(state: dict) -> dict:
    """
    重新生成指定章节

    输入 state:
        - section_id_to_regenerate: str
        - section_feedback: Optional[str]

    输出更新:
        - draft_sections: 更新指定章节
    """
    section_id = state.get("section_id_to_regenerate")
    feedback = state.get("section_feedback", "")
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()

    if not section_id:
        return state

    outline: Outline = state["outline"]
    draft_sections = state.get("draft_sections", {})
    section_artifact_ids = state.get("section_artifact_ids", {})

    # 找到要重新生成的章节
    target_section = None
    flat_sections = outline.get_flat_sections()
    for section in flat_sections:
        if section.id == section_id:
            target_section = section
            break

    if not target_section:
        return state

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="regenerate_section",
        node_type="process",
        started_at=datetime.utcnow(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[
            artifact_id
            for artifact_id in [
                state.get("outline_artifact_id"),
                section_artifact_ids.get(section_id),
            ]
            if artifact_id
        ],
        is_rerun=True,
    )
    await store.create_node_run(node_run)

    try:
        # 构建上下文（之前章节的内容）
        previous_content = ""
        for section in flat_sections:
            if section.id == section_id:
                break
            if section.id in draft_sections:
                previous_content += f"\n\n## {section.title}\n{draft_sections[section.id]}"

        # 重新生成
        start_time = datetime.utcnow()
        new_content = await generate_section(state, target_section, previous_content)
        end_time = datetime.utcnow()

        # 更新
        draft_sections[section_id] = new_content

        # 创建新版本 Artifact
        parent_artifact_id = section_artifact_ids.get(section_id)
        artifact = await store.create_artifact(
            artifact_type=ArtifactType.SECTION_CONTENT,
            content=_build_section_artifact_content(target_section, new_content),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            parent_version_id=parent_artifact_id,
            metadata={
                "feedback": feedback,
                "generation_phase": "regenerated",
                "is_regeneration": True,
            },
        )
        section_artifact_ids[section_id] = artifact.id

        # 完成节点
        model_info = get_current_model_info()
        llm_call = LLMCallRecord(
            model=model_info["model"],
            provider=model_info["provider"],
            latency_ms=int((end_time - start_time).total_seconds() * 1000),
            prompt_preview=target_section.title,
            response_preview=new_content[:200],
        )
        node_run.llm_calls.append(llm_call)
        node_run.output_artifact_ids.append(artifact.id)
        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)

        return {
            **state,
            "draft_sections": draft_sections,
            "section_artifact_ids": section_artifact_ids,
            "section_id_to_regenerate": None,
            "section_feedback": None,
            "generated_content": _compile_generated_content(outline, draft_sections),
        }

    except Exception as e:
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise
