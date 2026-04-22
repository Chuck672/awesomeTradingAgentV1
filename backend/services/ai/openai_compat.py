from __future__ import annotations

import json
import ssl
import urllib.request
import urllib.parse
from typing import Generator, Iterable
from typing import Any, Dict, List, Optional


def _join_url(base_url: str, path: str) -> str:
    b = (base_url or "").strip()
    if not b:
        raise ValueError("base_url is required")
    # 允许用户填：https://api.openai.com 或 https://api.openai.com/v1
    if b.endswith("/"):
        b = b[:-1]
    if b.endswith("/v1"):
        root = b
    else:
        root = b + "/v1"
    return root + path


def chat_completions(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = "auto",
    temperature: float = 0.2,
    timeout_sec: int = 45,
) -> Dict[str, Any]:
    """
    OpenAI-compatible `/v1/chat/completions` 调用（无第三方依赖）。
    适配：OpenAI / DeepSeek / Qwen / 任何 OpenAI-compatible 网关。
    """

    if not api_key:
        raise ValueError("api_key is required")
    if not model:
        raise ValueError("model is required")

    url = _join_url(base_url, "/chat/completions")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    # 兼容某些网关习惯用的 header（不影响 OpenAI）
    req.add_header("X-API-Key", api_key)

    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def chat_completions_stream(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = "auto",
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Generator[Dict[str, Any], None, None]:
    """
    OpenAI-compatible `/v1/chat/completions` 流式调用（SSE）。

    产出为“chunk JSON”（每行 data: {...}），调用方负责从 delta 中拼装 content/tool_calls。
    """
    if not api_key:
        raise ValueError("api_key is required")
    if not model:
        raise ValueError("model is required")

    url = _join_url(base_url, "/chat/completions")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("X-API-Key", api_key)

    ctx = ssl.create_default_context()
    resp = urllib.request.urlopen(req, timeout=timeout_sec, context=ctx)

    # NOTE: resp is a file-like object. We read it line by line.
    try:
        while True:
            line = resp.readline()
            if not line:
                break
            s = line.decode("utf-8", errors="replace").strip()
            if not s:
                continue
            if not s.startswith("data:"):
                continue
            data_str = s[len("data:") :].strip()
            if data_str == "[DONE]":
                break
            try:
                obj = json.loads(data_str)
            except Exception:
                # ignore malformed chunk
                continue
            yield obj
    finally:
        try:
            resp.close()
        except Exception:
            pass
