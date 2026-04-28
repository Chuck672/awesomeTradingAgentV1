from __future__ import annotations

from typing import Any, Dict, List


def calc_trend_exhaustion(
    bars: List[Dict[str, Any]],
    short_len: int = 21,
    short_smooth: int = 7,
    long_len: int = 112,
    long_smooth: int = 3,
    threshold: int = 20,
) -> Dict[str, bool]:
    if len(bars) < max(short_len, long_len) + max(short_smooth, long_smooth):
        return {"is_overbought": False, "is_oversold": False, "ob_reversal": False, "os_reversal": False}

    def get_highest(idx, length):
        start = max(0, idx - length + 1)
        slice_bars = bars[start : idx + 1]
        return max(float(b["high"]) for b in slice_bars)

    def get_lowest(idx, length):
        start = max(0, idx - length + 1)
        slice_bars = bars[start : idx + 1]
        return min(float(b["low"]) for b in slice_bars)

    s_raw = []
    l_raw = []
    for i in range(len(bars)):
        c = float(bars[i]["close"])
        s_max = get_highest(i, short_len)
        s_min = get_lowest(i, short_len)
        s_val = -50.0 if s_max == s_min else 100 * (c - s_max) / (s_max - s_min)
        s_raw.append(s_val)

        l_max = get_highest(i, long_len)
        l_min = get_lowest(i, long_len)
        l_val = -50.0 if l_max == l_min else 100 * (c - l_max) / (l_max - l_min)
        l_raw.append(l_val)

    def calc_ema(src: List[float], length: int) -> List[float]:
        if length <= 1:
            return src
        alpha = 2 / (length + 1)
        res = []
        ema = None
        for val in src:
            if ema is None:
                ema = val
            else:
                ema = alpha * val + (1 - alpha) * ema
            res.append(ema)
        return res

    s_pr = calc_ema(s_raw, short_smooth)
    l_pr = calc_ema(l_raw, long_smooth)

    idx_curr = len(bars) - 1
    idx_prev = len(bars) - 2

    def is_ob(idx):
        return s_pr[idx] >= -threshold and l_pr[idx] >= -threshold

    def is_os(idx):
        return s_pr[idx] <= -100 + threshold and l_pr[idx] <= -100 + threshold

    curr_ob = is_ob(idx_curr)
    curr_os = is_os(idx_curr)

    prev_ob = is_ob(idx_prev)
    prev_os = is_os(idx_prev)

    ob_reversal = (not curr_ob) and prev_ob
    os_reversal = (not curr_os) and prev_os

    return {"is_overbought": curr_ob, "is_oversold": curr_os, "ob_reversal": ob_reversal, "os_reversal": os_reversal}

