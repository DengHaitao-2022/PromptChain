"""模型供应商连通性测试服务。"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from pydantic import BaseModel, Field

from services.llm_provider import (
    DEFAULT_GITHUB_MODELS_BASE_URL,
    DEFAULT_OLLAMA_BASE_URL,
    LLMProviderFactory,
    RuntimeModelConfig,
    _bind_structured_output_model,
    _build_model_from_runtime_config,
    _build_workspace_runtime_config,
    _resolve_effective_structured_output_method,
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
ANTHROPIC_VERSION = "2023-06-01"
GITHUB_API_VERSION = "2026-03-10"
DEFAULT_TEST_PROMPT = "请只回复 OK。"
_STRUCTURED_OUTPUT_TEST_PROMPT = (
    "请严格按照结构化输出要求返回结果：status 字段固定为 ok，"
    "message 字段固定为 structured_output_ok。"
)
_OPENAI_COMPATIBLE_PROVIDERS = {"openai", "github"}

StepStatus = str


class StructuredOutputProbe(BaseModel):
    """结构化输出连通性测试模型。"""

    status: str = Field(description="固定返回 ok")
    message: str = Field(description="固定返回 structured_output_ok")


def _now_ms() -> float:
    return time.perf_counter() * 1000


def _step(
    name: str,
    label: str,
    status: StepStatus,
    message: str,
    *,
    started_at: float | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "status": status,
        "message": message,
        "duration_ms": round(_now_ms() - started_at) if started_at is not None else None,
        "detail": detail or {},
    }


def _skip_step(name: str, label: str, message: str) -> dict[str, Any]:
    return _step(name, label, "skipped", message)


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _ollama_url(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api"):
        return _join_url(normalized, path)
    return _join_url(normalized, f"api/{path.lstrip('/')}")


def _github_catalog_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    path = parsed.path
    if "/inference" in path:
        path = path.split("/inference", 1)[0]
    return urlunparse((parsed.scheme, parsed.netloc, path.rstrip("/"), "", "", ""))


def _resolve_base_url(runtime_config: RuntimeModelConfig) -> str:
    if runtime_config.base_url:
        return runtime_config.base_url.rstrip("/")
    if runtime_config.provider == "openai":
        return DEFAULT_OPENAI_BASE_URL
    if runtime_config.provider == "anthropic":
        return DEFAULT_ANTHROPIC_BASE_URL
    if runtime_config.provider == "google":
        return DEFAULT_GOOGLE_BASE_URL
    if runtime_config.provider == "github":
        return DEFAULT_GITHUB_MODELS_BASE_URL
    if runtime_config.provider == "ollama":
        return DEFAULT_OLLAMA_BASE_URL
    return ""


def _is_valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _sanitize_message(message: str, credential: str | None) -> str:
    normalized = message.replace("\n", " ").strip()
    if credential:
        normalized = normalized.replace(credential, "***")
    return normalized[:500]


async def _read_response_payload(response: httpx.Response, credential: str | None) -> Any:
    try:
        return response.json()
    except ValueError:
        return _sanitize_message(response.text, credential)


def _extract_error_message(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return "供应商返回了非预期响应"

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail") or error.get("type")
        if message:
            return str(message)
    if isinstance(error, str):
        return error

    detail = payload.get("detail") or payload.get("message")
    return str(detail) if detail else "供应商返回了错误响应"


def _normalize_model_name(provider: str, model: str) -> str:
    value = model.strip()
    if provider == "google" and value.startswith("models/"):
        return value.removeprefix("models/")
    return value


def _model_matches(selected_model: str, available_models: list[str], provider: str) -> bool:
    selected = _normalize_model_name(provider, selected_model)
    normalized_available = {_normalize_model_name(provider, model) for model in available_models}
    return selected in normalized_available


async def _check_base_url(
    client: httpx.AsyncClient,
    base_url: str,
    credential: str | None,
) -> dict[str, Any]:
    started_at = _now_ms()
    try:
        response = await client.get(base_url)
    except httpx.HTTPError as exc:
        return _step(
            "base_url_reachable",
            "Base URL 可达",
            "failed",
            f"无法连接 Base URL：{_sanitize_message(str(exc), credential)}",
            started_at=started_at,
        )

    if response.status_code >= 500:
        return _step(
            "base_url_reachable",
            "Base URL 可达",
            "warning",
            f"Base URL 已响应，但返回 HTTP {response.status_code}",
            started_at=started_at,
            detail={"status_code": response.status_code},
        )

    return _step(
        "base_url_reachable",
        "Base URL 可达",
        "success",
        f"Base URL 已响应 HTTP {response.status_code}",
        started_at=started_at,
        detail={"status_code": response.status_code},
    )


def _openai_headers(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"}


def _anthropic_headers(credential: str) -> dict[str, str]:
    return {
        "x-api-key": credential,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


def _github_headers(credential: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {credential}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "Content-Type": "application/json",
    }


async def _list_models(
    client: httpx.AsyncClient,
    runtime_config: RuntimeModelConfig,
    base_url: str,
) -> tuple[httpx.Response | None, list[str], str | None]:
    credential = runtime_config.credential
    provider = runtime_config.provider

    if provider == "openai":
        response = await client.get(
            _join_url(base_url, "models"),
            headers=_openai_headers(credential or ""),
        )
        payload = await _read_response_payload(response, credential)
        models = [
            str(item.get("id"))
            for item in (payload.get("data", []) if isinstance(payload, dict) else [])
            if isinstance(item, dict) and item.get("id")
        ]
        return response, models, None

    if provider == "anthropic":
        response = await client.get(
            _join_url(base_url, "v1/models"),
            headers=_anthropic_headers(credential or ""),
        )
        payload = await _read_response_payload(response, credential)
        models = [
            str(item.get("id"))
            for item in (payload.get("data", []) if isinstance(payload, dict) else [])
            if isinstance(item, dict) and item.get("id")
        ]
        return response, models, None

    if provider == "google":
        response = await client.get(
            _join_url(base_url, "models"),
            params={"key": credential or ""},
        )
        payload = await _read_response_payload(response, credential)
        models = [
            _normalize_model_name(provider, str(item.get("name")))
            for item in (payload.get("models", []) if isinstance(payload, dict) else [])
            if isinstance(item, dict) and item.get("name")
        ]
        return response, models, None

    if provider == "github":
        catalog_url = _join_url(_github_catalog_base_url(base_url), "catalog/models")
        response = await client.get(catalog_url, headers=_github_headers(credential or ""))
        payload = await _read_response_payload(response, credential)
        models = [
            str(item.get("id"))
            for item in (payload if isinstance(payload, list) else [])
            if isinstance(item, dict) and item.get("id")
        ]
        return response, models, None

    if provider == "ollama":
        response = await client.get(_ollama_url(base_url, "tags"))
        payload = await _read_response_payload(response, credential)
        models = [
            str(item.get("name") or item.get("model"))
            for item in (payload.get("models", []) if isinstance(payload, dict) else [])
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        ]
        return response, models, None

    return None, [], f"暂不支持测试 {provider} 供应商"


async def _send_short_prompt(
    client: httpx.AsyncClient,
    runtime_config: RuntimeModelConfig,
    base_url: str,
    model: str,
    prompt: str,
) -> tuple[httpx.Response, Any]:
    credential = runtime_config.credential
    provider = runtime_config.provider

    if provider == "openai":
        response = await client.post(
            _join_url(base_url, "chat/completions"),
            headers={**_openai_headers(credential or ""), "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8,
                "temperature": 0,
                "stream": False,
            },
        )
        return response, await _read_response_payload(response, credential)

    if provider == "anthropic":
        response = await client.post(
            _join_url(base_url, "v1/messages"),
            headers=_anthropic_headers(credential or ""),
            json={
                "model": model,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return response, await _read_response_payload(response, credential)

    if provider == "google":
        google_model = model if model.startswith("models/") else f"models/{model}"
        response = await client.post(
            _join_url(base_url, f"{google_model}:generateContent"),
            params={"key": credential or ""},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 8, "temperature": 0},
            },
        )
        return response, await _read_response_payload(response, credential)

    if provider == "github":
        response = await client.post(
            _join_url(base_url, "chat/completions"),
            headers=_github_headers(credential or ""),
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8,
                "temperature": 0,
                "stream": False,
            },
        )
        return response, await _read_response_payload(response, credential)

    if provider == "ollama":
        response = await client.post(
            _ollama_url(base_url, "chat"),
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0, "num_predict": 8},
            },
        )
        return response, await _read_response_payload(response, credential)

    raise ValueError(f"暂不支持测试 {provider} 供应商")


def _extract_prompt_preview(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict) and message.get("content"):
                return str(message["content"]).strip()

    content = payload.get("content")
    if isinstance(content, list) and content:
        first_content = content[0]
        if isinstance(first_content, dict) and first_content.get("text"):
            return str(first_content["text"]).strip()

    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        first_candidate = candidates[0]
        if isinstance(first_candidate, dict):
            candidate_content = first_candidate.get("content")
            if isinstance(candidate_content, dict):
                parts = candidate_content.get("parts")
                if isinstance(parts, list) and parts:
                    first_part = parts[0]
                    if isinstance(first_part, dict) and first_part.get("text"):
                        return str(first_part["text"]).strip()

    message = payload.get("message")
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"]).strip()

    return None


def _stringify_structured_result(value: Any) -> str:
    """把结构化结果转成可展示文本。"""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False)


async def _probe_structured_output(
    runtime_config: RuntimeModelConfig,
    model: str,
    *,
    method_override: str | None = None,
) -> tuple[Any, str | None]:
    """用当前 LangChain 配置直接探测结构化输出可用性。"""
    llm = _build_model_from_runtime_config(
        replace(runtime_config, model=model),
        temperature=0,
        max_tokens=64,
    )
    structured_llm = _bind_structured_output_model(
        llm,
        StructuredOutputProbe,
        runtime_config,
        method_override=method_override,
    )
    result = await structured_llm.ainvoke(_STRUCTURED_OUTPUT_TEST_PROMPT)
    return result, _resolve_effective_structured_output_method(
        runtime_config,
        method_override=method_override,
    )


async def _build_structured_output_step(
    runtime_config: RuntimeModelConfig,
    model: str,
    *,
    name: str,
    label: str,
    method_override: str | None = None,
    failure_status: StepStatus = "failed",
) -> dict[str, Any]:
    """生成单个结构化输出测试步骤。"""
    started_at = _now_ms()
    try:
        result, effective_method = await _probe_structured_output(
            runtime_config,
            model,
            method_override=method_override,
        )
    except Exception as exc:
        method_text = method_override or runtime_config.structured_output_method or "default"
        return _step(
            name,
            label,
            failure_status,
            f"结构化输出调用失败：{_sanitize_message(str(exc), runtime_config.credential)}",
            started_at=started_at,
            detail={"method": method_text},
        )

    preview = _stringify_structured_result(result)
    method_text = effective_method or "default"
    return _step(
        name,
        label,
        "success",
        "结构化输出调用成功",
        started_at=started_at,
        detail={
            "method": method_text,
            "response_text": preview[:500],
            "response_preview": preview[:120],
        },
    )


async def test_model_provider(
    provider_row: Any,
    *,
    selected_model: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """按固定顺序测试模型供应商配置，并返回可展示的分步结果。"""
    started_at = _now_ms()
    steps: list[dict[str, Any]] = []

    try:
        runtime_config = _build_workspace_runtime_config(provider_row)
        registration = LLMProviderFactory.get_registration(runtime_config.provider)
    except Exception as exc:
        steps.append(
            _step(
                "static_validation",
                "静态校验",
                "failed",
                f"模型供应商配置无效：{exc}",
            )
        )
        steps.extend(
            [
                _skip_step("base_url_reachable", "Base URL 可达", "静态校验未通过"),
                _skip_step("api_key_valid", "API Key 有效", "静态校验未通过"),
                _skip_step("models_list", "获取模型列表", "静态校验未通过"),
                _skip_step("short_prompt", "短 Prompt 测试", "静态校验未通过"),
            ]
        )
        return {
            "ok": False,
            "provider_id": provider_row.id,
            "provider": getattr(provider_row, "provider", None),
            "model": selected_model,
            "models": [],
            "steps": steps,
            "duration_ms": round(_now_ms() - started_at),
        }

    credential = runtime_config.credential
    base_url = _resolve_base_url(runtime_config)
    model = (selected_model or runtime_config.model or "").strip()
    prompt_text = (prompt or DEFAULT_TEST_PROMPT).strip() or DEFAULT_TEST_PROMPT
    static_errors: list[str] = []

    if not _is_valid_http_url(base_url):
        static_errors.append("Base URL 必须是 http 或 https 地址")
    if registration.credential_env and not credential:
        static_errors.append(f"缺少 {registration.credential_env} 或已保存的 API Key")

    if static_errors:
        steps.append(
            _step(
                "static_validation",
                "静态校验",
                "failed",
                "；".join(static_errors),
            )
        )
        steps.extend(
            [
                _skip_step("base_url_reachable", "Base URL 可达", "静态校验未通过"),
                _skip_step("api_key_valid", "API Key 有效", "静态校验未通过"),
                _skip_step("models_list", "获取模型列表", "静态校验未通过"),
                _skip_step("short_prompt", "短 Prompt 测试", "静态校验未通过"),
            ]
        )
        return {
            "ok": False,
            "provider_id": provider_row.id,
            "provider": runtime_config.provider,
            "model": model or None,
            "models": [],
            "steps": steps,
            "duration_ms": round(_now_ms() - started_at),
        }

    steps.append(
        _step(
            "static_validation",
            "静态校验",
            "success",
            "供应商、Base URL、凭证和模型字段格式有效",
            detail={"base_url": base_url, "model": model or None},
        )
    )

    timeout = httpx.Timeout(20.0, connect=5.0, read=20.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        base_step = await _check_base_url(client, base_url, credential)
        steps.append(base_step)

        models: list[str] = []
        list_started_at = _now_ms()
        try:
            list_response, models, unsupported_message = await _list_models(
                client,
                runtime_config,
                base_url,
            )
        except httpx.HTTPError as exc:
            list_response = None
            unsupported_message = _sanitize_message(str(exc), credential)

        if unsupported_message:
            steps.append(
                _step(
                    "api_key_valid",
                    "API Key 有效",
                    "failed",
                    unsupported_message,
                    started_at=list_started_at,
                )
            )
            steps.append(
                _step(
                    "models_list",
                    "获取模型列表",
                    "failed",
                    unsupported_message,
                )
            )
        elif list_response is None:
            steps.append(
                _step(
                    "api_key_valid",
                    "API Key 有效",
                    "failed",
                    "模型列表请求未收到响应",
                    started_at=list_started_at,
                )
            )
            steps.append(
                _step(
                    "models_list",
                    "获取模型列表",
                    "failed",
                    "模型列表请求未收到响应",
                )
            )
        else:
            payload = await _read_response_payload(list_response, credential)
            if list_response.status_code in {401, 403}:
                message = _sanitize_message(_extract_error_message(payload), credential)
                steps.append(
                    _step(
                        "api_key_valid",
                        "API Key 有效",
                        "failed",
                        f"凭证未通过供应商校验：{message}",
                        started_at=list_started_at,
                        detail={"status_code": list_response.status_code},
                    )
                )
                steps.append(
                    _step(
                        "models_list",
                        "获取模型列表",
                        "skipped",
                        "API Key 校验失败，未继续解析模型列表",
                    )
                )
            elif list_response.is_success:
                model_message = f"已获取 {len(models)} 个模型"
                if model and models:
                    model_message += (
                        "，当前模型在列表中"
                        if _model_matches(model, models, runtime_config.provider)
                        else "，当前模型未出现在列表中，将仍尝试短 Prompt"
                    )
                api_key_message = (
                    "Ollama 本地服务无需 API Key，模型列表接口已响应"
                    if runtime_config.provider == "ollama"
                    else "凭证已通过模型列表接口校验"
                )
                steps.append(
                    _step(
                        "api_key_valid",
                        "API Key 有效",
                        "success",
                        api_key_message,
                        started_at=list_started_at,
                        detail={"status_code": list_response.status_code},
                    )
                )
                steps.append(
                    _step(
                        "models_list",
                        "获取模型列表",
                        "success" if models else "warning",
                        model_message,
                        detail={"count": len(models), "sample": models[:10]},
                    )
                )
            else:
                message = _sanitize_message(_extract_error_message(payload), credential)
                steps.append(
                    _step(
                        "api_key_valid",
                        "API Key 有效",
                        "warning",
                        f"凭证请求返回 HTTP {list_response.status_code}",
                        started_at=list_started_at,
                        detail={"status_code": list_response.status_code},
                    )
                )
                steps.append(
                    _step(
                        "models_list",
                        "获取模型列表",
                        "failed",
                        f"模型列表获取失败：{message}",
                        detail={"status_code": list_response.status_code},
                    )
                )

        if not model:
            steps.append(_skip_step("short_prompt", "短 Prompt 测试", "未选择模型，跳过短 Prompt"))
        elif any(step["name"] == "api_key_valid" and step["status"] == "failed" for step in steps):
            steps.append(
                _skip_step("short_prompt", "短 Prompt 测试", "API Key 校验失败，跳过短 Prompt")
            )
        else:
            prompt_started_at = _now_ms()
            try:
                prompt_response, prompt_payload = await _send_short_prompt(
                    client,
                    runtime_config,
                    base_url,
                    model,
                    prompt_text,
                )
            except (httpx.HTTPError, ValueError) as exc:
                steps.append(
                    _step(
                        "short_prompt",
                        "短 Prompt 测试",
                        "failed",
                        f"短 Prompt 调用失败：{_sanitize_message(str(exc), credential)}",
                        started_at=prompt_started_at,
                    )
                )
            else:
                if prompt_response.is_success:
                    preview = _extract_prompt_preview(prompt_payload)
                    steps.append(
                        _step(
                            "short_prompt",
                            "短 Prompt 测试",
                            "success",
                            "短 Prompt 调用成功",
                            started_at=prompt_started_at,
                            detail={
                                "status_code": prompt_response.status_code,
                                "prompt_text": prompt_text,
                                "response_text": preview[:500] if preview else None,
                                "response_preview": preview[:120] if preview else None,
                            },
                        )
                    )
                else:
                    message = _sanitize_message(_extract_error_message(prompt_payload), credential)
                    steps.append(
                        _step(
                            "short_prompt",
                            "短 Prompt 测试",
                            "failed",
                            f"短 Prompt 返回 HTTP {prompt_response.status_code}：{message}",
                            started_at=prompt_started_at,
                            detail={
                                "status_code": prompt_response.status_code,
                                "prompt_text": prompt_text,
                                "response_text": message,
                            },
                        )
                    )

        if not model:
            steps.append(
                _skip_step(
                    "structured_output_json_mode",
                    "json_mode 结构化输出",
                    "未选择模型，跳过结构化输出测试",
                )
            )
            steps.append(
                _skip_step(
                    "structured_output_json_schema",
                    "json_schema 结构化输出",
                    "未选择模型，跳过结构化输出测试",
                )
            )
            steps.append(
                _skip_step(
                    "structured_output_configured",
                    "当前结构化输出配置",
                    "未选择模型，跳过结构化输出测试",
                )
            )
        elif any(step["name"] == "api_key_valid" and step["status"] == "failed" for step in steps):
            steps.append(
                _skip_step(
                    "structured_output_json_mode",
                    "json_mode 结构化输出",
                    "API Key 校验失败，跳过结构化输出测试",
                )
            )
            steps.append(
                _skip_step(
                    "structured_output_json_schema",
                    "json_schema 结构化输出",
                    "API Key 校验失败，跳过结构化输出测试",
                )
            )
            steps.append(
                _skip_step(
                    "structured_output_configured",
                    "当前结构化输出配置",
                    "API Key 校验失败，跳过结构化输出测试",
                )
            )
        elif runtime_config.provider not in _OPENAI_COMPATIBLE_PROVIDERS:
            steps.append(
                _skip_step(
                    "structured_output_json_mode",
                    "json_mode 结构化输出",
                    "当前供应商不是 OpenAI-compatible 路径，跳过该测试",
                )
            )
            steps.append(
                _skip_step(
                    "structured_output_json_schema",
                    "json_schema 结构化输出",
                    "当前供应商不是 OpenAI-compatible 路径，跳过该测试",
                )
            )
            steps.append(
                _skip_step(
                    "structured_output_configured",
                    "当前结构化输出配置",
                    "当前供应商不是 OpenAI-compatible 路径，跳过该测试",
                )
            )
        else:
            json_mode_step = await _build_structured_output_step(
                runtime_config,
                model,
                name="structured_output_json_mode",
                label="json_mode 结构化输出",
                method_override="json_mode",
                failure_status="warning",
            )
            steps.append(json_mode_step)

            json_schema_step = await _build_structured_output_step(
                runtime_config,
                model,
                name="structured_output_json_schema",
                label="json_schema 结构化输出",
                method_override="json_schema",
                failure_status="warning",
            )
            steps.append(json_schema_step)

            try:
                configured_method = _resolve_effective_structured_output_method(runtime_config)
            except ValueError as exc:
                steps.append(
                    _step(
                        "structured_output_configured",
                        "当前结构化输出配置",
                        "failed",
                        str(exc),
                        detail={
                            "method": runtime_config.structured_output_method or "default",
                        },
                    )
                )
                configured_method = None

            if steps and steps[-1]["name"] == "structured_output_configured":
                pass
            elif configured_method == "json_mode":
                configured_step = {
                    **json_mode_step,
                    "name": "structured_output_configured",
                    "label": "当前结构化输出配置",
                    "status": "success" if json_mode_step["status"] == "success" else "failed",
                    "message": (
                        "当前配置对应的结构化输出调用成功"
                        if json_mode_step["status"] == "success"
                        else "当前配置的结构化输出调用失败"
                    ),
                }
            elif configured_method == "json_schema":
                configured_step = {
                    **json_schema_step,
                    "name": "structured_output_configured",
                    "label": "当前结构化输出配置",
                    "status": "success" if json_schema_step["status"] == "success" else "failed",
                    "message": (
                        "当前配置对应的结构化输出调用成功"
                        if json_schema_step["status"] == "success"
                        else "当前配置的结构化输出调用失败"
                    ),
                }
            else:
                configured_step = await _build_structured_output_step(
                    runtime_config,
                    model,
                    name="structured_output_configured",
                    label="当前结构化输出配置",
                )
                if configured_step["status"] == "success":
                    configured_step["message"] = "当前配置对应的结构化输出调用成功"
                else:
                    configured_step["message"] = "当前配置的结构化输出调用失败"
            if steps and steps[-1]["name"] != "structured_output_configured":
                steps.append(configured_step)

    ok = bool(steps) and all(step["status"] in {"success", "skipped"} for step in steps)
    return {
        "ok": ok,
        "provider_id": provider_row.id,
        "provider": runtime_config.provider,
        "model": model or None,
        "models": models[:50],
        "steps": steps,
        "duration_ms": round(_now_ms() - started_at),
    }
