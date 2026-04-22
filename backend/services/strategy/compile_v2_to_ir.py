from __future__ import annotations

"""
Schema v2 -> IR v1 编译器（最小可用版）

原则：
- 只做结构化拆解与依赖图生成，不做实盘执行
- 输出：
  1) ir_graph: 可执行 DAG steps（供后续 Executor）
  2) dsl_text: 由 IR 渲染的可读 DSL
  3) compilation_report: 汇总 warnings/unsupported/capabilities/normalization_fixes
"""

from typing import Any, Dict, Tuple, List

from backend.services.strategy.ir_v1 import IRGraph, IRStep, CompilationReport, render_text_dsl
from backend.services.strategy.schema_validate import validate_schema_v2


def compile_schema_v2_to_ir(spec: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    入参：StrategySchema v2（允许非规范输入；validate 会做 normalize + canonical）
    返回：
      ok, {
        status, normalized_schema, ir_graph, dsl_text, compilation_report
      }
    """
    ok, rep = validate_schema_v2(spec)
    if not ok or rep.get("status") == "error":
        return False, {
            "status": "error",
            "validation": rep,
            "normalized_schema": rep.get("normalized_spec"),
            "ir_graph": None,
            "dsl_text": None,
            "compilation_report": {
                "status": "error",
                "warnings": rep.get("warnings") or [],
                "unsupported_features": rep.get("unsupported_features") or [],
                "capabilities_required": rep.get("capabilities_required") or [],
                "normalization_fixes": rep.get("normalization_fixes") or [],
            },
        }

    normalized = rep.get("normalized_spec") or {}
    caps = rep.get("capabilities_required") or []
    unsupported = rep.get("unsupported_features") or []
    warnings = rep.get("warnings") or []
    fixes = rep.get("normalization_fixes") or []

    # ---- Build IR steps (minimal skeleton) ----
    steps: List[IRStep] = []

    # 1) load_data
    uni = (normalized.get("universe") or {}) if isinstance(normalized.get("universe"), dict) else {}
    data = (normalized.get("data") or {}) if isinstance(normalized.get("data"), dict) else {}
    steps.append(
        IRStep(
            id="load_data",
            kind="data.load_bars",
            params={
                "symbols": uni.get("symbols") or [],
                "primary_timeframe": uni.get("primary_timeframe"),
                "history_lookback_bars": data.get("history_lookback_bars"),
                "higher_timeframes": data.get("higher_timeframes") or [],
            },
            outputs={"bars_by_tf": "bars_by_tf"},
            notes="加载 K 线数据（主周期 + 可选高周期）",
        )
    )

    # 2) indicators
    inds = normalized.get("indicators") if isinstance(normalized.get("indicators"), list) else []
    if inds:
        steps.append(
            IRStep(
                id="indicators",
                kind="indicator.compute_batch",
                depends_on=["load_data"],
                inputs={"bars_by_tf": "load_data.bars_by_tf"},
                params={"decls": inds},
                outputs={"series": "indicator_series_map"},
                notes="计算指标（声明式）",
            )
        )

    # 3) structures
    structures = normalized.get("structures") if isinstance(normalized.get("structures"), dict) else None
    if structures and structures.get("level_generator"):
        deps = ["load_data"] + (["indicators"] if inds else [])
        steps.append(
            IRStep(
                id="structures",
                kind="structure.level_generator",
                depends_on=deps,
                inputs={"bars_by_tf": "load_data.bars_by_tf", "indicator_series": "indicators.series" if inds else None},
                params={"level_generator": structures.get("level_generator"), "primary_timeframe": uni.get("primary_timeframe")},
                outputs={"levels": "levels[]", "zones": "zones[]"},
                notes="生成结构位/区间（levels/zones）",
            )
        )

    # 4) patterns
    patterns = normalized.get("patterns") if isinstance(normalized.get("patterns"), list) else []
    if patterns:
        deps = ["load_data"] + (["indicators"] if inds else []) + (["structures"] if any(s.id == "structures" for s in steps) else [])
        steps.append(
            IRStep(
                id="patterns",
                kind="pattern.detect_batch",
                depends_on=deps,
                inputs={
                    "bars_by_tf": "load_data.bars_by_tf",
                    "indicator_series": "indicators.series" if inds else None,
                    # 注意：executor 只支持 step.key 形式引用。这里显式传入 levels/zones，
                    # 由 pattern.detect_batch 组装为 structures，避免把字符串 "structures" 误当作结构数据。
                    "levels": "structures.levels" if any(s.id == "structures" for s in steps) else None,
                    "zones": "structures.zones" if any(s.id == "structures" for s in steps) else None,
                },
                params={"detectors": patterns},
                outputs={"pattern_pack": "pattern_pack"},
                notes="检测形态并产出 evidence pack（pattern_pack）",
            )
        )

    # 5) action planning
    action = (normalized.get("action") or {}) if isinstance(normalized.get("action"), dict) else {}
    deps = []
    for sid in ("patterns", "structures", "indicators", "load_data"):
        if sid in [s.id for s in steps]:
            deps.append(sid)
    steps.append(
        IRStep(
            id="plan_action",
            kind=f"action.plan.{action.get('type') or 'unknown'}",
            depends_on=deps,
            inputs={
                "bars_by_tf": "load_data.bars_by_tf",
                "indicator_series": "indicators.series" if "indicators" in deps else None,
                "levels": "structures.levels" if "structures" in deps else None,
                "pattern_pack": "patterns.pattern_pack" if "patterns" in deps else None,
            },
            params={"action": action, "entry": normalized.get("entry"), "context": normalized.get("context"), "risk": normalized.get("risk"), "execution": normalized.get("execution")},
            outputs={"trade_intents": "trade_intents[]"},
            notes="将策略模块组合成可执行的 trade intents（仅规划，不下单）",
        )
    )

    ir = IRGraph(steps=steps)
    dsl = render_text_dsl(ir)

    report = CompilationReport(
        status="warning" if unsupported else "ok",
        summary={
            "steps": len(ir.steps),
            "has_indicators": bool(inds),
            "has_structures": bool(structures and structures.get("level_generator")),
            "patterns_count": len(patterns),
            "action_type": action.get("type"),
        },
        warnings=warnings,
        unsupported_features=unsupported,
        capabilities_required=caps,
        normalization_fixes=fixes,
    )

    return True, {
        "status": report.status,
        "normalized_schema": normalized,
        "ir_graph": ir.dict(),
        "dsl_text": dsl,
        "compilation_report": report.dict(),
        "validation": rep,
    }
