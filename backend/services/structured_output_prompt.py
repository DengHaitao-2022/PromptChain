from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

JSON_MODE_OUTPUT_INSTRUCTION = """\
## JSON 输出要求
请只输出合法 JSON 对象。
不要输出 Markdown 代码块。
不要输出解释、前缀或后缀文本。
所有字段必须符合当前结构化输出模型要求。
"""


def needs_json_mode_instruction(effective_method: str | None) -> bool:
    """只有最终生效模式是 json_mode 时，才需要 JSON 指令。"""
    return effective_method == "json_mode"


def ensure_json_mode_instruction_text(
    prompt_template: str,
    effective_method: str | None,
) -> str:
    """仅在 json_mode 生效时追加 JSON 指令，并避免重复追加。"""
    if not needs_json_mode_instruction(effective_method):
        return prompt_template

    if "json" in prompt_template.lower():
        return prompt_template

    return f"{prompt_template.rstrip()}\n\n{JSON_MODE_OUTPUT_INSTRUCTION}"


def build_structured_chat_prompt(
    prompt_template: str,
    effective_method: str | None,
) -> ChatPromptTemplate:
    """按最终结构化输出模式构建 Prompt。"""
    if not needs_json_mode_instruction(effective_method):
        return ChatPromptTemplate.from_template(prompt_template)

    if "json" in prompt_template.lower():
        return ChatPromptTemplate.from_template(prompt_template)

    return ChatPromptTemplate.from_messages(
        [
            ("system", JSON_MODE_OUTPUT_INSTRUCTION),
            ("human", prompt_template),
        ]
    )
