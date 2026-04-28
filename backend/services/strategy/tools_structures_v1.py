from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import datetime as dt

from backend.domain.market.structure.swings import detect_swings


def _prev_day_hl(bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    取“上一交易日”的高低点（UTC day）。
    用纯 Python datetime 计算，避免 pandas 时区/类型细节导致的空集问题。
    """
    if not bars:
        return []
    # 最后一根 bar 的日期
    try:
        last_ts = int(bars[-1].get("time"))
    except Exception:
        return []
    last_day = dt.datetime.utcfromtimestamp(last_ts).date()
    prev_day = last_day - dt.timedelta(days=1)

    hi = None
    lo = None
    for b in bars:
        try:
            day = dt.datetime.utcfromtimestamp(int(b.get("time"))).date()
        except Exception:
            continue
        if day != prev_day:
            continue
        try:
            h = float(b.get("high"))
            l = float(b.get("low"))
        except Exception:
            continue
        hi = h if hi is None else max(hi, h)
        lo = l if lo is None else min(lo, l)
    if hi is None or lo is None:
        return []
    return [
        {"type": "level", "kind": "prev_day_high", "price": hi},
        {"type": "level", "kind": "prev_day_low", "price": lo},
    ]


def _swing_levels(bars: List[Dict[str, Any]], *, left: int = 3, right: int = 3, max_levels: int = 8) -> List[Dict[str, Any]]:
    # 对于结构/回测扫描，需要更多 swing 点覆盖历史区间；max_points 随 max_levels 扩大
    swings = detect_swings(bars, left=left, right=right, max_points=max(20, int(max_levels) * 6))
    out: List[Dict[str, Any]] = []
    for s in swings:
        out.append({"type": "level", "kind": "swing_high" if s.kind == "H" else "swing_low", "price": float(s.price), "time": int(s.time)})
    # 最新优先
    out = sorted(out, key=lambda x: x.get("time", 0), reverse=True)[: max_levels * 2]
    # 去重：同价位近似去重（简单）
    dedup: List[Dict[str, Any]] = []
    for it in out:
        p = float(it["price"])
        if any(abs(p - float(j["price"])) < 1e-6 for j in dedup):
            continue
        dedup.append(it)
        if len(dedup) >= max_levels:
            break
    return dedup


def _infer_price_digits(bars: List[Dict[str, Any]]) -> int:
    """
    从历史价格推断小数位数（用于把 pips 转为价格单位）。
    规则：寻找一个 scale，使得 close*scale 的小数部分对大多数样本接近 0。
    """
    if not bars:
        return 0
    samples: List[float] = []
    for b in bars[-300:]:
        try:
            samples.append(float(b.get("close")))
        except Exception:
            continue
    if not samples:
        return 0
    for digits, scale in [(0, 1), (1, 10), (2, 100), (3, 1000), (4, 10000), (5, 100000)]:
        ok = 0
        for v in samples:
            if abs(round(v * scale) - v * scale) < 1e-6:
                ok += 1
        if ok / max(1, len(samples)) >= 0.8:
            return digits
    return 2


def _pip_size_from_digits(digits: int) -> float:
    """
    将小数位数映射为 pip 大小：
    - digits>=2：pip = 10^(-(digits-1))  (例如 3位 => 0.01；5位 => 0.0001)
    - digits<2：pip = 1
    """
    try:
        d = int(digits)
    except Exception:
        d = 2
    if d >= 2:
        return float(10 ** (-(d - 1)))
    return 1.0


def tool_structure_level_generator(payload: Dict[str, Any]) -> Dict[str, Any]:
    from backend.domain.market.structure.structures_tool_v1 import tool_structure_level_generator as _impl

    return _impl(payload)
