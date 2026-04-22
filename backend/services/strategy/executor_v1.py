from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple, Optional

from backend.services.strategy.tool_registry_v1 import tool_registry_v1
from backend.services.strategy.tool_registry_bootstrap_v1 import bootstrap_tool_registry_v1  # noqa: F401


_REF_RE = re.compile(r"^([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$")


def _resolve_ref(value: Any, step_outputs: Dict[str, Dict[str, Any]]) -> Any:
    """
    解析 compile_v2_to_ir 里生成的 'step.output' 引用。
    """
    if value is None:
        return None
    if isinstance(value, str):
        m = _REF_RE.match(value.strip())
        if not m:
            return value
        sid, key = m.group(1), m.group(2)
        return (step_outputs.get(sid) or {}).get(key)
    return value


def execute_ir_v1(
    ir_graph: Dict[str, Any],
    *,
    bars_override: Optional[Dict[str, Any]] = None,
    stop_on_error: bool = False,
    debug_tools: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    steps = ir_graph.get("steps") if isinstance(ir_graph, dict) else None
    if not isinstance(steps, list):
        return False, {"status": "error", "error": "invalid ir_graph.steps"}

    trace: List[Dict[str, Any]] = []
    outputs: Dict[str, Dict[str, Any]] = {}
    had_error = False

    for s in steps:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "")
        kind = str(s.get("kind") or "")
        depends = s.get("depends_on") or []
        params = s.get("params") if isinstance(s.get("params"), dict) else {}
        inputs = s.get("inputs") if isinstance(s.get("inputs"), dict) else {}

        # resolve inputs
        resolved_inputs: Dict[str, Any] = {}
        for k, v in inputs.items():
            if v is None:
                continue
            resolved_inputs[k] = _resolve_ref(v, outputs)

        payload = {**resolved_inputs, **params}
        if debug_tools:
            payload["_debug"] = True

        # inject bars_override only for load_data
        if kind == "data.load_bars" and bars_override is not None:
            payload["bars_override"] = bars_override

        try:
            out, telem = tool_registry_v1.run(kind, payload)
            outputs[sid] = out
            trace.append({"step": sid, "kind": kind, "ok": True, "telem": telem, "depends_on": depends})
        except Exception as e:
            had_error = True
            trace.append({"step": sid, "kind": kind, "ok": False, "error": str(e), "depends_on": depends})
            if stop_on_error:
                return False, {"status": "error", "error": f"step {sid} failed: {e}", "trace": trace, "outputs": outputs}
            # best-effort: continue

    return True, {"status": ("ok" if not had_error else "warning"), "had_error": had_error, "trace": trace, "outputs": outputs}
