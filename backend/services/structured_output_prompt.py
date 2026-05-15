from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

JSON_MODE_OUTPUT_INSTRUCTION = """\
## JSON 输出要求
请只输出合法 JSON 对象。
不要输出 Markdown 代码块。
不要输出解释、前缀或后缀文本。
"""

JSON_MODE_SCHEMA_PREFIX = "## JSON Schema"


def needs_json_mode_instruction(effective_method: str | None) -> bool:
    """只有最终生效模式是 json_mode 时，才需要 JSON 指令。"""
    return effective_method == "json_mode"


def ensure_json_mode_instruction_text(
    prompt_template: str,
    effective_method: str | None,
    *,
    schema: type[BaseModel] | None = None,
) -> str:
    """仅在 json_mode 生效时追加 JSON 指令，并避免重复追加。"""
    if not needs_json_mode_instruction(effective_method):
        return prompt_template

    if JSON_MODE_OUTPUT_INSTRUCTION in prompt_template:
        return prompt_template

    return f"{prompt_template.rstrip()}\n\n{_build_json_mode_instruction(schema)}"


def build_structured_chat_prompt(
    prompt_template: str,
    effective_method: str | None,
    *,
    schema: type[BaseModel] | None = None,
) -> ChatPromptTemplate:
    """按最终结构化输出模式构建 Prompt。"""
    if not needs_json_mode_instruction(effective_method):
        return ChatPromptTemplate.from_template(prompt_template)

    if JSON_MODE_OUTPUT_INSTRUCTION in prompt_template:
        return ChatPromptTemplate.from_template(prompt_template)

    return ChatPromptTemplate.from_messages(
        [
            ("system", _build_json_mode_instruction(schema)),
            ("human", prompt_template),
        ]
    )


def _build_json_mode_instruction(schema: type[BaseModel] | None) -> str:
    """构建带 schema 约束的 json_mode 指令。"""
    instruction = JSON_MODE_OUTPUT_INSTRUCTION.rstrip()
    if schema is None:
        return instruction

    schema_payload = json.dumps(schema.model_json_schema(), ensure_ascii=False, sort_keys=True)
    return (
        f"{instruction}\n"
        "所有字段、类型、必填项和枚举值必须严格符合以下 JSON Schema。\n\n"
        f"{JSON_MODE_SCHEMA_PREFIX}\n{schema_payload}"
    )
