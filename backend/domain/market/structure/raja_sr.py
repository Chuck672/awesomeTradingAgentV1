from __future__ import annotations

from typing import Any, Dict, List, Optional


def compute_raja_sr_level_zones(
    bars: List[Dict[str, Any]],
    *,
    lookback: int = 1000,
    pivot: int = 2,
    max_zones: int = 6,
) -> List[Dict[str, Any]]:
    try:
        from backend.domain.market.structure.raja_sr_calc import calc_raja_sr
    except Exception:
        return []
    try:
        zones = calc_raja_sr(bars, lookback=lookback, pivot=pivot, max_zones=max_zones)
    except Exception:
        return []
    return zones if isinstance(zones, list) else []


def to_level_zone_struct(z: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        top = float(z.get("top"))
        bottom = float(z.get("bottom"))
    except Exception:
        return None
    center = (top + bottom) / 2.0
    kind = str(z.get("type") or "zone")
    out: Dict[str, Any] = {
        "type": "zone",
        "kind": f"raja_sr_{kind}",
        "top": top,
        "bottom": bottom,
        "center": center,
        "score": z.get("score"),
        "touches": z.get("touches"),
        "last_touch_time": z.get("last_touch_time"),
    }
    return out
