"""LLM usage 提取与兜底工具。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def extract_usage_metadata(response: Any) -> dict[str, int]:
    """从 AIMessage / raw dict / OpenAI-compatible metadata 中提取 token usage。"""
    usage = getattr(response, "usage_metadata", None)

    if not usage:
        response_metadata = getattr(response, "response_metadata", None) or {}
        usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}

    if not usage and isinstance(response, dict):
        usage = response.get("usage") or {}

    prompt_tokens = (
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("prompt_token_count")
        or 0
    )
    completion_tokens = (
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("completion_token_count")
        or 0
    )
    total_tokens = (
        usage.get("total_tokens")
        or usage.get("total_token_count")
        or _as_int(prompt_tokens) + _as_int(completion_tokens)
    )

    return {
        "prompt_tokens": _as_int(prompt_tokens),
        "completion_tokens": _as_int(completion_tokens),
        "total_tokens": _as_int(total_tokens),
    }


def estimate_tokens(text: str) -> int:
    """在供应商未返回 usage 时做一个粗粒度估算，避免 UI 长期显示 0。"""
    normalized = text.strip()
    if not normalized:
        return 0
    return max(1, len(normalized) // 2)


def ensure_usage_metadata(
    usage: dict[str, int] | None,
    *,
    prompt_text: str = "",
    completion_text: str = "",
) -> dict[str, int]:
    """若真实 usage 缺失，则回退到基于文本长度的近似估算。"""
    normalized = {
        "prompt_tokens": _as_int((usage or {}).get("prompt_tokens")),
        "completion_tokens": _as_int((usage or {}).get("completion_tokens")),
        "total_tokens": _as_int((usage or {}).get("total_tokens")),
    }
    if normalized["total_tokens"] > 0:
        return normalized

    prompt_tokens = estimate_tokens(prompt_text)
    completion_tokens = estimate_tokens(completion_text)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


async def invoke_structured_with_usage(
    chain: Any,
    payload: dict[str, Any],
    *,
    schema: type[BaseModel] | None = None,
    normalizer=None,
) -> tuple[Any, dict[str, int]]:
    """执行结构化输出调用，同时把 raw usage 提出来。"""
    result = await chain.ainvoke(payload)

    if isinstance(result, dict) and "raw" in result:
        raw = result.get("raw")
        usage = extract_usage_metadata(raw)
        parsed = result.get("parsed")
        parsing_error = result.get("parsing_error")
        if parsed is not None:
            return parsed, usage

        if schema is not None:
            data = _parse_raw_structured_payload(raw)
            if normalizer is not None:
                data = normalizer(data)
            return schema.model_validate(data), usage

        if isinstance(parsing_error, BaseException):
            raise parsing_error
        if parsing_error:
            raise ValueError(str(parsing_error))
        raise ValueError("结构化输出解析失败")

    return result, extract_usage_metadata(result)


def _parse_raw_structured_payload(raw: Any) -> dict[str, Any]:
    """把结构化输出 raw 响应解析成 dict。"""
    if isinstance(raw, dict):
        return raw

    content = getattr(raw, "content", "")
    if isinstance(content, str):
        return json.loads(_strip_code_fence(content))

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return json.loads(_strip_code_fence("".join(text_parts)))

    raise ValueError("结构化输出解析失败：raw content 不是可解析 JSON 文本")


def _strip_code_fence(text: str) -> str:
    normalized = text.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
    return normalized
