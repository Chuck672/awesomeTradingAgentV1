from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Tuple, Optional

"""
StrategySchema v2 的 capabilities / unsupported 规则（可配置/可版本化）

说明：
- capabilities 是“策略想要执行所需要的工具集合”（静态审计）
- 工具能力矩阵从 JSON 配置读取（tool_capabilities_v2.json），便于版本化与维护
- Tool Registry 完整实现之前，用此能力矩阵：
  1) 给 LLM 生成提供约束（capabilities_required）
  2) 对 schema 做静态审计：若某些模块/子类型未实现，输出 unsupported_features（带 reason/workaround）
"""


CAPS_FILE_DEFAULT = os.path.join(os.path.dirname(__file__), "tool_capabilities_v2.json")


@lru_cache(maxsize=1)
def load_capabilities_config() -> Dict[str, Any]:
    path = os.environ.get("AWESOMECHART_CAPABILITIES_FILE", "").strip() or CAPS_FILE_DEFAULT
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"capabilities_version": "0", "tools": {}}


def get_tool_capability(tool_name: str) -> Dict[str, Any]:
    cfg = load_capabilities_config()
    tools = cfg.get("tools") if isinstance(cfg.get("tools"), dict) else {}
    entry = tools.get(tool_name) if isinstance(tools, dict) else None
    if isinstance(entry, dict):
        return entry
    return {"status": "unknown", "version": None}


def _is_supported(entry: Dict[str, Any]) -> bool:
    return str(entry.get("status") or "").lower() == "supported"


def build_capabilities_report(normalized_schema: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    返回：
    - capabilities_required: [{tool, version}]
    - unsupported_features: [{feature, required_tool, reason, workaround}]
    - warnings: [{code, message, path}]
    """
    caps: List[str] = []
    unsupported: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # indicators
    for it in (normalized_schema.get("indicators") or []) if isinstance(normalized_schema.get("indicators"), list) else []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip().lower()
        if name:
            caps.append(f"indicator.{name}")

    # structures
    structures = normalized_schema.get("structures") if isinstance(normalized_schema.get("structures"), dict) else {}
    if (structures or {}).get("level_generator"):
        caps.append("structure.level_generator")
        # source-level capabilities（可细化为 structure.level_source.xxx）
        lg = structures.get("level_generator") if isinstance(structures.get("level_generator"), dict) else {}
        sources = lg.get("sources") if isinstance(lg.get("sources"), list) else []
        for s in sources:
            if isinstance(s, dict) and s.get("type"):
                # 目前先统一归属到 level_generator，不再拆更细
                pass

    # patterns
    for p in (normalized_schema.get("patterns") or []) if isinstance(normalized_schema.get("patterns"), list) else []:
        if isinstance(p, dict) and p.get("type"):
            caps.append(f"pattern.{str(p.get('type'))}")

    # action
    action = normalized_schema.get("action") if isinstance(normalized_schema.get("action"), dict) else {}
    act_type = str(action.get("type") or "").strip()
    if act_type:
        caps.append(f"action.{act_type}")

    # context submodules
    context = normalized_schema.get("context") if isinstance(normalized_schema.get("context"), dict) else {}
    if isinstance(context.get("htf_bias"), dict) and bool(context.get("htf_bias", {}).get("enabled", True)):
        caps.append("context.htf_bias")
    if isinstance(context.get("space_filter"), dict) and bool(context.get("space_filter", {}).get("enabled", False)):
        caps.append("context.space_filter")
    micro = context.get("micro_filters") if isinstance(context.get("micro_filters"), dict) else {}
    spread = micro.get("spread") if isinstance(micro.get("spread"), dict) else {}
    if spread and bool(spread.get("enabled", False)):
        caps.append("context.spread_filter")
    if isinstance(context.get("volatility_regime"), dict) and bool(context.get("volatility_regime", {}).get("enabled", False)):
        caps.append("context.volatility_regime")
    if isinstance(context.get("session_filter"), dict) and bool(context.get("session_filter", {}).get("enabled", False)):
        caps.append("context.session_filter")

    # risk
    risk = normalized_schema.get("risk") if isinstance(normalized_schema.get("risk"), dict) else {}
    if risk:
        sl = risk.get("stop_loss") if isinstance(risk.get("stop_loss"), dict) else {}
        sl_method = str(sl.get("method") or "").strip()
        if sl_method:
            caps.append(f"risk.stop_loss.{sl_method}")
        tp = risk.get("take_profit") if isinstance(risk.get("take_profit"), dict) else {}
        tp_method = str(tp.get("method") or "").strip()
        if tp_method:
            caps.append(f"risk.take_profit.{tp_method}")
        if isinstance(risk.get("guards"), dict):
            caps.append("risk.guards")

    # execution
    execution = normalized_schema.get("execution") if isinstance(normalized_schema.get("execution"), dict) else {}
    if execution:
        caps.append("execution.order_builder")

    # normalize unique
    caps = sorted(list(dict.fromkeys([c for c in caps if c])))

    # unsupported
    caps_required: List[Dict[str, Any]] = []
    for c in caps:
        entry = get_tool_capability(c)
        supported = _is_supported(entry)
        caps_required.append(
            {
                "tool": c,
                "status": entry.get("status") or ("supported" if supported else "unknown"),
                "supported": bool(supported),
                "version": entry.get("version"),
                "notes": entry.get("notes"),
            }
        )
        if not supported:
            unsupported.append(
                {
                    "feature": c,
                    "required_tool": c,
                    "reason": entry.get("reason") or "该能力当前未标记为 supported（可能 planned/unknown）",
                    "workaround": entry.get("workaround") or "请先使用已支持的组合，或等待实现后再启用。",
                }
            )

    return caps_required, unsupported, warnings
