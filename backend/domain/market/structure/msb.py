from __future__ import annotations

from typing import Any, Dict, List


def calc_msb_zigzag(bars: List[Dict[str, Any]], pivot_period: int = 5) -> Dict[str, Any]:
    if len(bars) < pivot_period * 2 + 1:
        return {"lines": []}

    points = []
    lines = []

    def get_pivot(idx, is_high):
        if idx < pivot_period or idx >= len(bars) - pivot_period:
            return None
        val = float(bars[idx]["high"] if is_high else bars[idx]["low"])
        for i in range(1, pivot_period + 1):
            comp_val_prev = float(bars[idx - i]["high"] if is_high else bars[idx - i]["low"])
            comp_val_next = float(bars[idx + i]["high"] if is_high else bars[idx + i]["low"])
            if is_high and (comp_val_prev > val or comp_val_next > val):
                return None
            if (not is_high) and (comp_val_prev < val or comp_val_next < val):
                return None
        return val

    for i in range(pivot_period, len(bars) - pivot_period):
        h_piv = get_pivot(i, True)
        l_piv = get_pivot(i, False)

        if h_piv is not None:
            points.append({"time": bars[i]["time"], "value": h_piv, "type": "H", "index": i})
        if l_piv is not None:
            points.append({"time": bars[i]["time"], "value": l_piv, "type": "L", "index": i})

    ext_trend = "No Trend"
    maj_h = maj_l = None

    for i in range(len(points)):
        pt = points[i]
        if pt["type"] == "H":
            maj_h = pt["value"]
        elif pt["type"] == "L":
            maj_l = pt["value"]

        next_idx = points[i + 1]["index"] if i < len(points) - 1 else len(bars) - 1
        for j in range(pt["index"], next_idx + 1):
            c = float(bars[j]["close"])
            if maj_h is not None and c > maj_h:
                if ext_trend in ["No Trend", "Up Trend"]:
                    lines.append({"type": "BoS Bull", "level": maj_h, "time": bars[j]["time"]})
                else:
                    lines.append({"type": "ChoCh Bull", "level": maj_h, "time": bars[j]["time"]})
                ext_trend = "Up Trend"
                maj_h = None
            elif maj_l is not None and c < maj_l:
                if ext_trend in ["No Trend", "Down Trend"]:
                    lines.append({"type": "BoS Bear", "level": maj_l, "time": bars[j]["time"]})
                else:
                    lines.append({"type": "ChoCh Bear", "level": maj_l, "time": bars[j]["time"]})
                ext_trend = "Down Trend"
                maj_l = None

    return {"lines": lines[-10:]}

