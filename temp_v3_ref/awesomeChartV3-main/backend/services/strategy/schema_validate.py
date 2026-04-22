from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pydantic.v1 import ValidationError

from backend.services.strategy.schema_v2 import StrategySchemaV2, schema_json
from backend.services.strategy.capabilities_v2 import build_capabilities_report
from backend.services.strategy.normalize_v2 import normalize_schema_v2_input, canonicalize_schema_v2_output


def _flatten_pydantic_errors(errs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in errs or []:
        loc = e.get("loc") or ()
        path = ".".join([str(x) for x in loc if x is not None])
        out.append({"path": path, "message": str(e.get("msg") or ""), "type": str(e.get("type") or "validation_error"), "severity": "error"})
    return out


def validate_schema_v2(spec: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    校验 StrategySchema v2：
    - pydantic 类型校验 + 自定义引用校验
    返回：(ok, report)
    """
    input_fixes: List[Dict[str, Any]] = []
    try:
        spec2, input_fixes = normalize_schema_v2_input(spec, source="user")
        m = StrategySchemaV2.parse_obj(spec2)
    except ValidationError as ve:
        return False, {
            "status": "error",
            "validation_errors": _flatten_pydantic_errors(ve.errors()),
            "normalized_spec": None,
            "normalization_fixes": input_fixes,
        }
    except Exception as e:
        return False, {
            "status": "error",
            "validation_errors": [{"path": "", "message": str(e), "type": "exception", "severity": "error"}],
            "normalized_spec": None,
            "normalization_fixes": input_fixes,
        }

    # normalized_spec：将默认值补齐后的 dict 作为规范化输出
    normalized = m.dict()
    normalized, output_fixes = canonicalize_schema_v2_output(normalized)

    capabilities_required, unsupported_features, warnings = build_capabilities_report(normalized)
    status = "ok" if not unsupported_features else "warning"

    return True, {
        "status": status,
        "validation_errors": [],
        "normalized_spec": normalized,
        "capabilities_required": capabilities_required,
        "unsupported_features": unsupported_features,
        "warnings": warnings,
        "normalization_fixes": input_fixes + output_fixes,
        "schema": {"version": "2.0", "jsonschema": schema_json()},
    }
