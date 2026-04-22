from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.services.ai.openai_compat import chat_completions
from backend.services.strategy.schema_v2 import schema_json
from backend.services.strategy.normalize_v2 import normalize_schema_v2_input


def _extract_first_json(text: str) -> Optional[Dict[str, Any]]:
    """
    容错：从 LLM 输出中提取第一个 JSON 对象。
    支持：
      - 纯 JSON
      - ```json ... ```
      - 文本 + JSON
    """
    s = (text or "").strip()
    if not s:
        return None

    # fenced block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        try:
            obj = json.loads(cand)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

    # attempt whole
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # scan for first {...} with simple brace balance
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                cand = s[start : i + 1]
                try:
                    obj = json.loads(cand)
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None


def _tool_schema_emit_strategy() -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "emit_strategy_schema_v2",
            "description": "输出严格符合 StrategySchema v2 的 JSON 对象（不要输出多余字段）。",
            "parameters": schema_json(),
        },
    }


def _coerce_json_like(v: Any) -> Any:
    """把可能被 LLM 包成字符串的 JSON 再解析回来。"""
    if isinstance(v, str):
        s = v.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                return json.loads(s)
            except Exception:
                return v
    return v


def _coerce_top_level(schema: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Qwen 等模型在 tool_call.arguments 中有时会把 object/list 字段“二次 JSON stringify”，
    导致后续校验出现：value is not a valid dict。
    这里做一次容错归一化（只作用于顶层字段）。
    """
    coerced: List[str] = []
    keys = ["meta", "universe", "data", "structures", "action", "entry", "context", "risk", "execution", "outputs", "indicators", "patterns"]
    out = dict(schema)
    for k in keys:
        if k in out:
            nv = _coerce_json_like(out.get(k))
            if nv is not out.get(k):
                coerced.append(k)
            # 将一些“空/错误类型”的可选模块归一化为 None
            if k in ("structures", "entry", "context", "risk", "execution"):
                if nv == [] or nv == "" or nv == {}:
                    nv = None
            # 将 patterns/indicators 容错为 list
            if k in ("patterns", "indicators"):
                if nv is None or nv == "":
                    nv = []
                elif isinstance(nv, dict):
                    nv = [nv]
            out[k] = nv
    return out, coerced


def _sanitize_common_mistakes(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    修正常见 LLM 输出误差（不改变用户意图，只做“去歧义/去占位”）：
    - indicator_ref 写成 'none'/'null'：视为未启用该阈值，移除 threshold
    """
    out = dict(schema)
    try:
        action = out.get("action")
        if isinstance(action, dict) and action.get("type") == "breakout":
            br = action.get("breakout")
            if isinstance(br, dict):
                vb = br.get("valid_breakout")
                if isinstance(vb, dict):
                    dr = vb.get("displacement_rule")
                    if isinstance(dr, dict):
                        th = dr.get("threshold")
                        if isinstance(th, dict) and th.get("type") == "indicator_ref":
                            ref = str(th.get("ref") or "").strip().lower()
                            if ref in ("none", "null", "undefined", ""):
                                dr["threshold"] = None
                                vb["displacement_rule"] = dr
                                br["valid_breakout"] = vb
                                action["breakout"] = br
                                out["action"] = action
    except Exception:
        return out
    return out


def ai_parse_to_schema_v2(
    *,
    prompt: str,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float = 0.2,
    timeout_sec: int = 120,
    system_append: str = "",
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    使用 OpenAI-compatible LLM 将自然语言策略描述转换为 StrategySchema v2。
    返回：(strategy_schema, parse_meta)
    """
    user_prompt = (prompt or "").strip()
    if not user_prompt:
        return None, {"status": "error", "error": "prompt is empty"}

    sys = (
        "你是量化交易策略编译器。你的任务：把用户的策略描述转换为严格的 StrategySchema v2 JSON。\n"
        "要求：\n"
        "1) 只输出 JSON（通过工具 emit_strategy_schema_v2 返回），不要写解释文字。\n"
        "2) 不确定的字段请使用保守默认值，并在 meta.notes 中写明假设。\n"
        "3) breakout 不是顶层：请使用 action.type 表达（breakout/pullback/mean_reversion/continuation/range/custom）。\n"
        "4) indicators 是数组，可为空；如果 action/context/risk 里引用 indicator_ref，必须在 indicators 声明对应 id。\n"
        "5) symbols/timeframe 若用户未明确，默认 symbols=[\"XAUUSDz\"], primary_timeframe=\"30m\"。\n"
    )
    if system_append:
        sys = sys + "\n" + str(system_append).strip() + "\n"

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys},
        {"role": "user", "content": user_prompt},
    ]

    tools = [_tool_schema_emit_strategy()]
    try:
        raw = chat_completions(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            timeout_sec=int(timeout_sec),
        )
    except Exception as e:
        # 典型：TimeoutError / HTTPError 等
        return None, {"status": "error", "error": str(e), "via": "llm_error"}

    # 1) tool_calls 优先
    try:
        choice = (raw.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        for tc in tool_calls:
            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
            if fn.get("name") == "emit_strategy_schema_v2":
                args = fn.get("arguments")
                if isinstance(args, str):
                    obj = json.loads(args)
                else:
                    obj = args
                if isinstance(obj, dict):
                    obj2, coerced = _coerce_top_level(obj)
                    obj2 = _sanitize_common_mistakes(obj2)
                    obj2, fixes = normalize_schema_v2_input(obj2, source="ai")
                    meta = {"status": "ok", "via": "tool_calls"}
                    if coerced:
                        meta["coerced_fields"] = coerced
                    if fixes:
                        meta["fixes"] = fixes
                    return obj2, meta
    except Exception:
        pass

    # 2) fallback：从 content 提取 JSON
    try:
        choice = (raw.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = str(msg.get("content") or "")
        obj = _extract_first_json(content)
        if isinstance(obj, dict):
            obj2, coerced = _coerce_top_level(obj)
            obj2 = _sanitize_common_mistakes(obj2)
            obj2, fixes = normalize_schema_v2_input(obj2, source="ai")
            meta = {"status": "ok", "via": "content_json"}
            if coerced:
                meta["coerced_fields"] = coerced
            if fixes:
                meta["fixes"] = fixes
            return obj2, meta
    except Exception:
        pass

    return None, {"status": "error", "error": "no json found in llm response", "raw": raw}
