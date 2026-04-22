from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SessionVPOptions:
    days_to_calculate: int = 5
    # 前端 defaultSessionVPOptions.bins = 70
    bins: int = 70
    value_area_pct: float = 70.0


def _day_str_utc(ts: int, adjust_next_day_for_21: bool = False) -> str:
    import datetime as dt

    d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    if adjust_next_day_for_21 and d.hour >= 21:
        d = d + dt.timedelta(days=1)
    return f"{d.year}-{d.month}-{d.day}"


def _session_type_utc(ts: int) -> str:
    """
    与前端 SessionVP/Calculator.ts 保持一致（UTC 时段 + 周一 Sydney 特例）：
    - 21:00-00:00：周一为 SYDNEY，否则归 ASIA
    - 00:00-07:00：ASIA
    - 07:00-12:00：EUROPE
    - 12:00-21:00：US
    """
    import datetime as dt

    d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    h = d.hour
    day_of_week = d.weekday()  # Mon=0..Sun=6

    if h >= 21:
        if day_of_week == 0:
            return "SYDNEY"
        return "ASIA"
    if 0 <= h < 7:
        return "ASIA"
    if 7 <= h < 12:
        return "EUROPE"
    if 12 <= h < 21:
        return "US"
    return "ASIA"


def _block_id(ts: int, session_type: str) -> str:
    # 与 TS 一致：h>=21 的 bar 属于“下一交易日”，因此 dayStr 需要 +1
    import datetime as dt

    d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    h = d.hour
    adj = d
    if h >= 21:
        adj = d + dt.timedelta(days=1)
    day_str = f"{adj.year}-{adj.month}-{adj.day}"
    return f"{day_str}-{session_type}"


def calculate_all(data: List[Dict[str, Any]], options: SessionVPOptions) -> List[Dict[str, Any]]:
    """
    纯 Python 复刻前端 SessionVP/Calculator.ts 的计算逻辑与返回结构（SessionBlock[]）。
    data 每条至少包含：time/open/high/low/close/volume
    """
    if not data:
        return []

    # 1) 找最近 N 天（按 UTC dayStr）
    days_to_calc = int(options.days_to_calculate)
    unique_days = set()
    start_index = 0
    for i in range(len(data) - 1, -1, -1):
        day_str = _day_str_utc(int(data[i]["time"]))
        unique_days.add(day_str)
        if len(unique_days) > days_to_calc:
            start_index = i + 1
            break
    active = data[start_index:]
    if not active:
        return []

    blocks: List[Dict[str, Any]] = []
    current_bars: List[Dict[str, Any]] = []
    current_id = ""
    current_type = ""

    for bar in active:
        ts = int(bar["time"])
        s_type = _session_type_utc(ts)
        b_id = _block_id(ts, s_type)

        if current_id != b_id:
            if current_bars:
                blk = calculate_block(current_id, current_type, current_bars, options)
                if blk:
                    blocks.append(blk)
            current_id = b_id
            current_type = s_type
            current_bars = [bar]
        else:
            current_bars.append(bar)

    if current_bars:
        blk = calculate_block(current_id, current_type, current_bars, options)
        if blk:
            blocks.append(blk)

    return blocks


def calculate_block(id: str, type: str, bars: List[Dict[str, Any]], options: SessionVPOptions) -> Optional[Dict[str, Any]]:
    if not bars:
        return None

    first_ts = int(bars[0]["time"])
    last_ts = int(bars[-1]["time"])
    duration = max(1, last_ts - first_ts)
    t1 = first_ts + duration / 3.0
    t2 = first_ts + (2.0 * duration) / 3.0

    min_price = float("inf")
    max_price = float("-inf")
    total_vol = 0.0
    for b in bars:
        lo = float(b["low"])
        hi = float(b["high"])
        if lo < min_price:
            min_price = lo
        if hi > max_price:
            max_price = hi
        total_vol += float(b.get("volume", 0) or 0)

    if min_price == float("inf") or max_price == float("-inf") or min_price == max_price or total_vol == 0:
        return None

    eps = (max_price - min_price) * 0.000001
    bin_size = (max_price - min_price + eps) / float(options.bins)

    bins: List[Dict[str, Any]] = [
        {
            "yStart": min_price + i * bin_size,
            "yEnd": min_price + (i + 1) * bin_size,
            "vol1": 0.0,
            "vol2": 0.0,
            "vol3": 0.0,
            "totalVolume": 0.0,
            "inValueArea": False,
        }
        for i in range(int(options.bins))
    ]

    # volume allocation
    for b in bars:
        vol = float(b.get("volume", 0) or 0)
        if vol == 0:
            continue
        ts = float(b["time"])
        part = 1 if ts < t1 else (2 if ts < t2 else 3)
        lo = float(b["low"])
        hi = float(b["high"])
        cl = float(b["close"])
        rng = hi - lo

        if rng == 0:
            idx = int((cl - min_price) / bin_size)
            if idx < 0:
                idx = 0
            if idx >= int(options.bins):
                idx = int(options.bins) - 1
            if part == 1:
                bins[idx]["vol1"] += vol
            elif part == 2:
                bins[idx]["vol2"] += vol
            else:
                bins[idx]["vol3"] += vol
            bins[idx]["totalVolume"] += vol
            continue

        for i in range(int(options.bins)):
            bin_ = bins[i]
            overlap_start = max(lo, float(bin_["yStart"]))
            overlap_end = min(hi, float(bin_["yEnd"]))
            overlap = overlap_end - overlap_start
            if overlap > 0:
                ratio = overlap / rng
                alloc = vol * ratio
                if part == 1:
                    bin_["vol1"] += alloc
                elif part == 2:
                    bin_["vol2"] += alloc
                else:
                    bin_["vol3"] += alloc
                bin_["totalVolume"] += alloc

    max_vol = 0.0
    poc_index = 0
    for i in range(int(options.bins)):
        if float(bins[i]["totalVolume"]) > max_vol:
            max_vol = float(bins[i]["totalVolume"])
            poc_index = i

    # value area
    target_va = total_vol * (float(options.value_area_pct) / 100.0)
    current_va = float(bins[poc_index]["totalVolume"])
    bins[poc_index]["inValueArea"] = True
    up_idx = poc_index + 1
    down_idx = poc_index - 1

    while current_va < target_va and (up_idx < int(options.bins) or down_idx >= 0):
        vol_up = float(bins[up_idx]["totalVolume"]) if up_idx < int(options.bins) else -1.0
        vol_down = float(bins[down_idx]["totalVolume"]) if down_idx >= 0 else -1.0

        if vol_up > vol_down:
            current_va += vol_up
            bins[up_idx]["inValueArea"] = True
            up_idx += 1
        elif vol_down > vol_up:
            current_va += vol_down
            bins[down_idx]["inValueArea"] = True
            down_idx -= 1
        else:
            if up_idx < int(options.bins):
                current_va += vol_up
                bins[up_idx]["inValueArea"] = True
                up_idx += 1
            if down_idx >= 0 and current_va < target_va:
                current_va += vol_down
                bins[down_idx]["inValueArea"] = True
                down_idx -= 1

    poc_price = (float(bins[poc_index]["yStart"]) + float(bins[poc_index]["yEnd"])) / 2.0
    value_area_low = float(bins[down_idx + 1]["yStart"]) if down_idx >= 0 else float(bins[0]["yStart"])
    value_area_high = (
        float(bins[up_idx - 1]["yEnd"]) if up_idx < int(options.bins) else float(bins[int(options.bins) - 1]["yEnd"])
    )

    return {
        "id": id,
        "type": type,
        "firstBarTime": first_ts,
        "lastBarTime": last_ts,
        "minPrice": float(min_price),
        "maxPrice": float(max_price),
        "bins": bins,
        "pocPrice": float(poc_price),
        "pocVolume": float(max_vol),
        "maxVolume": float(max_vol),
        "valueAreaLow": float(value_area_low),
        "valueAreaHigh": float(value_area_high),
    }
