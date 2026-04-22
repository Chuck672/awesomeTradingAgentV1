from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple, Optional


def _json_parse_if_possible(v: Any) -> Any:
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return v
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            return json.loads(s)
        except Exception:
            return v
    return v


def _add_fix(fixes: List[Dict[str, Any]], *, code: str, path: str, before: Any, after: Any, reason: str):
    fixes.append({"code": code, "path": path, "before": before, "after": after, "reason": reason})


def normalize_schema_v2_input(spec: Dict[str, Any], *, source: str = "user") -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    将“非规范但可推断”的输入归一化为更稳定的结构，避免 LLM/用户输入的常见类型错误。

    归一化目标（输入侧）：
    - 顶层对象字段允许被 JSON stringify：自动反解析
    - patterns/indicators 允许单个 dict：自动包成 list
    - 可选模块（structures/entry/context/risk/execution）若为 []/{}：统一置为 None（表示省略）
    - indicator_ref 常见占位：ref=none/null/undefined 视为未启用（置 None），避免引用校验失败

    返回：(normalized_input, fixes[])
    """
    if not isinstance(spec, dict):
        return {}, [{"code": "TYPE_ERROR", "path": "", "before": type(spec).__name__, "after": "dict", "reason": "spec 必须为对象"}]

    out: Dict[str, Any] = dict(spec)
    fixes: List[Dict[str, Any]] = []

    # 1) 顶层字段反解析（LLM tool_calls 二次 stringify）
    top_keys = ["meta", "universe", "data", "structures", "action", "entry", "context", "risk", "execution", "outputs", "indicators", "patterns"]
    for k in top_keys:
        if k not in out:
            continue
        before = out.get(k)
        after = _json_parse_if_possible(before)
        if after is not before:
            _add_fix(fixes, code="PARSE_JSON_STRING", path=k, before=type(before).__name__, after=type(after).__name__, reason="顶层字段疑似被二次 stringify")
        out[k] = after

    # 2) 可选 object 模块：[]/{} -> None
    for k in ("structures", "entry", "context", "risk", "execution"):
        if k not in out:
            continue
        v = out.get(k)
        if v == [] or v == {} or v == "":
            _add_fix(fixes, code="EMPTY_OBJECT_TO_NULL", path=k, before=v, after=None, reason="可选模块为空，规范化为省略(null)")
            out[k] = None

    # 3) patterns/indicators：dict -> [dict]；None -> []
    for k in ("patterns", "indicators"):
        if k not in out:
            continue
        v = out.get(k)
        if v is None or v == "":
            _add_fix(fixes, code="MISSING_LIST_TO_EMPTY", path=k, before=v, after=[], reason="数组字段缺失/空字符串，规范化为空数组")
            out[k] = []
        elif isinstance(v, dict):
            _add_fix(fixes, code="DICT_TO_LIST", path=k, before="dict", after="list", reason="数组字段被输出为对象，自动包成数组")
            out[k] = [v]

    # 4) 常见 indicator_ref 占位
    def _walk_and_fix_indicator_ref(node: Any, path: str) -> Any:
        if node is None:
            return None
        if isinstance(node, list):
            return [_walk_and_fix_indicator_ref(x, f"{path}[]") for x in node]
        if isinstance(node, dict):
            # indicator_ref dict
            if node.get("type") == "indicator_ref":
                ref = str(node.get("ref") or "").strip().lower()
                if ref in ("none", "null", "undefined", ""):
                    _add_fix(fixes, code="INDICATOR_REF_NONE", path=path, before=node, after=None, reason="indicator_ref 为占位值，视为未启用")
                    return None
            # recurse
            newd = dict(node)
            for kk, vv in list(newd.items()):
                newd[kk] = _walk_and_fix_indicator_ref(vv, f"{path}.{kk}" if path else kk)
            return newd
        return node

    for k in ("action", "context", "risk", "execution"):
        if k in out:
            out[k] = _walk_and_fix_indicator_ref(out.get(k), k)

    # 5) 附加：在 parse_ai 重试第二次时，我们希望 prompt 中未用模块尽量省略
    # 这里不强制删除用户字段，仅做输入纠错；canonical 输出交给 validate 的 post-normalize。

    # 增加 source 标注（供上层 parse_meta 使用，不写入 schema）
    if source:
        _add_fix(fixes, code="SOURCE", path="", before=None, after=source, reason="normalize 入口来源标记")

    return out, fixes


def canonicalize_schema_v2_output(normalized_spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    将 pydantic 输出的 normalized_spec 进一步 canonicalize，保证：
    - indicators/patterns 永远输出数组（存在则 []）
    - 可选模块若“全为空/全为 None”，则输出为 null（而不是 {}）
    """
    out = dict(normalized_spec or {})
    fixes: List[Dict[str, Any]] = []

    # ensure all top-level keys exist (full schema output)
    # 这些键对应 StrategySchemaV2 的模块结构。即便用户/LLM 省略，normalized 输出也要稳定含有这些键。
    full_defaults: Dict[str, Any] = {
        "spec_version": "2.0",
        "meta": None,
        "universe": None,
        "data": None,
        "indicators": [],
        "structures": None,
        "patterns": [],
        "action": None,
        "entry": None,
        "context": None,
        "risk": None,
        "execution": None,
        "outputs": None,
    }
    for k, dv in full_defaults.items():
        if k not in out:
            out[k] = dv
            _add_fix(fixes, code="CANON_ADD_MISSING_KEY", path=k, before=None, after=dv, reason="canonical: 补齐顶层键（稳定 full schema 输出）")

    # force arrays
    for k in ("indicators", "patterns"):
        v = out.get(k)
        if v is None:
            out[k] = []
            _add_fix(fixes, code="CANON_ARRAY", path=k, before=None, after=[], reason="canonical: 数组字段固定输出 []")

    # optional modules: {} -> None if empty
    def _is_effectively_empty(obj: Any) -> bool:
        if obj is None:
            return True
        if isinstance(obj, dict):
            return all(_is_effectively_empty(v) for v in obj.values())
        if isinstance(obj, list):
            return len(obj) == 0
        return False

    for k in ("structures", "entry", "context", "risk", "execution"):
        if k in out:
            v = out.get(k)
            if isinstance(v, dict) and _is_effectively_empty(v):
                out[k] = None
                _add_fix(fixes, code="CANON_EMPTY_OBJECT_TO_NULL", path=k, before="{}", after=None, reason="canonical: 空对象模块输出为 null")

    return out, fixes
