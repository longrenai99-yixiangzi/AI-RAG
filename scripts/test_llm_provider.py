from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from app.config import Settings


REPORT_PATH = Path("docs") / "LLM_AUTHENTICATION_RECOVERY_REPORT.md"


def main() -> int:
    settings = Settings.load()
    config = {
        "RAG_API_BASE_URL": settings.api_base_url,
        "RAG_CHAT_MODEL": settings.chat_model,
        "RAG_API_KEY_present": bool(settings.api_key),
        "RAG_API_KEY_source": _setting_source("RAG_API_KEY"),
        "RAG_API_BASE_URL_source": _setting_source("RAG_API_BASE_URL"),
        "RAG_CHAT_MODEL_source": _setting_source("RAG_CHAT_MODEL"),
        "proxy": {
            name: bool(os.getenv(name))
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
        },
    }
    network = _tcp_check(settings.api_base_url)
    headers = (
        {"Authorization": f"Bearer {settings.api_key}"}
        if settings.api_key
        else {}
    )
    get_result = _get_models(settings.api_base_url, headers)
    post_result = _post_chat(settings, headers)
    report = {
        "config": config,
        "network": network,
        "get_models": get_result,
        "post_chat_completions": post_result,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report={REPORT_PATH.resolve()}")
    return 0 if get_result["authentication"] == "passed" and post_result["authentication"] == "passed" else 1


def _setting_source(name: str) -> str:
    if os.getenv(name):
        return "process_environment"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
        return "windows_user_environment" if str(value).strip() else "missing"
    except (ImportError, OSError):
        return "missing"


def _tcp_check(base_url: str) -> dict[str, object]:
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
        return {
            "host": host,
            "port": port,
            "tcp_succeeded": True,
            "elapsed_ms": round((time.perf_counter() - started) * 1_000),
        }
    except OSError as error:
        return {
            "host": host,
            "port": port,
            "tcp_succeeded": False,
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_ms": round((time.perf_counter() - started) * 1_000),
        }


def _get_models(base_url: str, headers: dict[str, str]) -> dict[str, object]:
    return _request(
        method="GET",
        url=f"{base_url}/models",
        headers=headers,
    )


def _post_chat(settings: Settings, headers: dict[str, str]) -> dict[str, object]:
    question = _gold_question()
    payload = {
        "model": settings.chat_model,
        "messages": [
            {
                "role": "system",
                "content": "只依据用户问题回答，返回简短中文结果。",
            },
            {"role": "user", "content": question},
        ],
        "temperature": 0,
        "max_tokens": 512,
    }
    result = _request(
        method="POST",
        url=f"{settings.api_base_url}/chat/completions",
        headers={**headers, "Content-Type": "application/json"},
        json_body=payload,
    )
    result["question_used"] = question
    return result


def _request(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, object] | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    try:
        with httpx.Client(
            timeout=httpx.Timeout(60.0, connect=15.0),
            trust_env=True,
        ) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                json=json_body,
            )
        result: dict[str, object] = {
            "request_succeeded": True,
            "http_status": response.status_code,
            "elapsed_ms": round((time.perf_counter() - started) * 1_000),
            "authentication": (
                "passed"
                if response.status_code not in {401, 403}
                else "failed"
            ),
            "response_format": "not_checked",
        }
        if response.status_code in {401, 403}:
            result["error_summary"] = "authentication rejected by provider"
            return result
        try:
            body = response.json()
        except ValueError:
            result["response_format"] = "invalid_json"
            result["error_summary"] = "response is not JSON"
            return result
        result["response_format"] = "json"
        if method == "GET":
            result["models_shape_valid"] = isinstance(body, dict) and isinstance(body.get("data"), list)
        else:
            choices = body.get("choices") if isinstance(body, dict) else None
            message = choices[0].get("message") if isinstance(choices, list) and choices else None
            content = message.get("content") if isinstance(message, dict) else None
            reasoning = message.get("reasoning_content") if isinstance(message, dict) else None
            result["finish_reason"] = (
                choices[0].get("finish_reason")
                if isinstance(choices, list) and choices and isinstance(choices[0], dict)
                else None
            )
            result["chat_shape_valid"] = isinstance(content, str) and bool(content.strip())
            result["content_chars"] = len(content or "") if isinstance(content, str) else 0
            result["reasoning_content_chars"] = len(reasoning or "") if isinstance(reasoning, str) else 0
            if not result["chat_shape_valid"]:
                result["response_format"] = "json_but_empty_content"
        return result
    except httpx.HTTPError as error:
        return {
            "request_succeeded": False,
            "authentication": "not_reached",
            "response_format": "not_reached",
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_ms": round((time.perf_counter() - started) * 1_000),
        }


def _gold_question() -> str:
    path = Path("tests") / "gold_questions" / "full_corpus_gold_questions.yaml"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return str(payload["questions"][0]["question"])
    except (OSError, KeyError, IndexError, TypeError, yaml.YAMLError):
        return "设计管理指南如何定义项目设计管理的主要职责？"


def _render_report(report: dict[str, object]) -> str:
    config = report["config"]
    network = report["network"]
    get_result = report["get_models"]
    post_result = report["post_chat_completions"]
    lines = [
        "# LLM Authentication Recovery Report",
        "",
        "> 本报告只诊断 OpenAI-compatible LLM Provider，不修改 Retriever、Answer Engine、8000 服务或正式 Qdrant。",
        "",
        "## 1. 配置检查",
        "",
        f"- API Base URL：{config['RAG_API_BASE_URL']}",
        f"- Model Name：{config['RAG_CHAT_MODEL']}",
        f"- API Key 存在性：{config['RAG_API_KEY_present']}",
        f"- API Key 来源：{config['RAG_API_KEY_source']}",
        f"- Base URL 来源：{config['RAG_API_BASE_URL_source']}",
        f"- Model 来源：{config['RAG_CHAT_MODEL_source']}",
        f"- Proxy 环境变量存在性：{json.dumps(config['proxy'], ensure_ascii=False)}",
        "- API Key 明文：未输出。",
        "",
        "## 2. 网络状态",
        "",
        f"- TCP 目标：{network['host']}:{network['port']}",
        f"- TCP 结果：{network['tcp_succeeded']}",
        f"- TCP 耗时：{network['elapsed_ms']} ms",
        "",
        "## 3. GET /v1/models",
        "",
        f"- HTTP 状态码：{get_result.get('http_status', 'N/A')}",
        f"- 认证结果：{get_result.get('authentication')}",
        f"- 响应格式：{get_result.get('response_format')}",
        f"- Models 响应结构：{get_result.get('models_shape_valid', 'N/A')}",
        f"- 错误摘要：{get_result.get('error_summary', get_result.get('error', '无'))}",
        "",
        "## 4. POST /v1/chat/completions",
        "",
        f"- HTTP 状态码：{post_result.get('http_status', 'N/A')}",
        f"- 认证结果：{post_result.get('authentication')}",
        f"- 响应格式：{post_result.get('response_format')}",
        f"- Chat 响应结构：{post_result.get('chat_shape_valid', 'N/A')}",
        f"- 返回内容字符数：{post_result.get('content_chars', 'N/A')}",
        f"- 错误摘要：{post_result.get('error_summary', post_result.get('error', '无'))}",
        "",
        "## 5. 诊断结论",
        "",
        _conclusion(get_result, post_result),
        "",
        "## 6. 边界确认",
        "",
        "- 未修改正式 Retriever。",
        "- 未修改 Answer Engine。",
        "- 未修改 8000 服务。",
        "- 未修改正式 Qdrant。",
        "- 未输出 API Key。",
        "",
        "**TASK-015.2：LLM Authentication Recovery 诊断完成。**",
        "",
    ]
    return "\n".join(lines)


def _conclusion(get_result: dict[str, object], post_result: dict[str, object]) -> str:
    if get_result.get("authentication") == "passed" and post_result.get("authentication") == "passed":
        return "认证通过，GET /v1/models 和 POST /v1/chat/completions 均已进入响应格式验证。"
    if get_result.get("http_status") in {401, 403} or post_result.get("http_status") in {401, 403}:
        return "网络可达，但 Provider 拒绝认证。需要刷新或更换 API Key，并确认 Model Name 权限。"
    return "Provider 请求未完成认证验证，需要先修复网络或服务端可达性。"


if __name__ == "__main__":
    raise SystemExit(main())
