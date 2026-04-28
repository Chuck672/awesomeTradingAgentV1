from __future__ import annotations

from typing import Any, Dict, List, Optional


def calc_volume_profile(bars: List[Dict[str, Any]], bins_count: int = 50, value_area_pct: float = 70.0) -> Optional[Dict[str, Any]]:
    if not bars:
        return None

    min_price = float("inf")
    max_price = float("-inf")
    total_vol = 0.0

    for b in bars:
        low = float(b["low"])
        high = float(b["high"])
        vol = float(b.get("tick_volume", b.get("volume", 0)))
        if low < min_price:
            min_price = low
        if high > max_price:
            max_price = high
        total_vol += vol

    if min_price == float("inf") or max_price == float("-inf") or min_price == max_price or total_vol == 0:
        return None

    epsilon = (max_price - min_price) * 0.000001
    bin_size = (max_price - min_price + epsilon) / bins_count

    bins = [{"yStart": min_price + i * bin_size, "yEnd": min_price + (i + 1) * bin_size, "totalVolume": 0.0} for i in range(bins_count)]

    for b in bars:
        low = float(b["low"])
        high = float(b["high"])
        close = float(b["close"])
        vol = float(b.get("tick_volume", b.get("volume", 0)))
        if vol == 0:
            continue

        rng = high - low
        if rng == 0:
            bin_idx = min(int((close - min_price) / bin_size), bins_count - 1)
            if 0 <= bin_idx < bins_count:
                bins[bin_idx]["totalVolume"] += vol
            continue

        for i in range(bins_count):
            overlap_start = max(low, bins[i]["yStart"])
            overlap_end = min(high, bins[i]["yEnd"])
            overlap = overlap_end - overlap_start
            if overlap > 0:
                ratio = overlap / rng
                bins[i]["totalVolume"] += vol * ratio

    max_vol = 0
    poc_index = 0
    for i in range(bins_count):
        if bins[i]["totalVolume"] > max_vol:
            max_vol = bins[i]["totalVolume"]
            poc_index = i

    target_va = total_vol * (value_area_pct / 100.0)
    current_va = bins[poc_index]["totalVolume"]

    up_idx = poc_index + 1
    down_idx = poc_index - 1

    while current_va < target_va and (up_idx < bins_count or down_idx >= 0):
        vol_up = bins[up_idx]["totalVolume"] if up_idx < bins_count else -1
        vol_down = bins[down_idx]["totalVolume"] if down_idx >= 0 else -1

        if vol_up > vol_down:
            current_va += vol_up
            up_idx += 1
        elif vol_down > vol_up:
            current_va += vol_down
            down_idx -= 1
        else:
            if up_idx < bins_count:
                current_va += vol_up
                up_idx += 1
            if down_idx >= 0 and current_va < target_va:
                current_va += vol_down
                down_idx -= 1

    return {
        "pocPrice": (bins[poc_index]["yStart"] + bins[poc_index]["yEnd"]) / 2,
        "pocVolume": max_vol,
        "valueAreaLow": bins[down_idx + 1]["yStart"] if down_idx >= 0 else bins[0]["yStart"],
        "valueAreaHigh": bins[up_idx - 1]["yEnd"] if up_idx < bins_count else bins[-1]["yEnd"],
    }
