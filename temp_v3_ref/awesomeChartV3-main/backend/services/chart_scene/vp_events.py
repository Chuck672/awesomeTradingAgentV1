from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def _bin_center(b: Dict[str, Any]) -> float:
    return (float(b["yStart"]) + float(b["yEnd"])) / 2.0


def developing_poc_from_bins(bins: List[Dict[str, Any]]) -> Optional[float]:
    """
    用 SessionVP 的 vol3（最后 1/3 时段）近似 developing POC：
    - 取 vol3 最大的 bin center
    """
    if not bins:
        return None
    best_i = None
    best_v = -1.0
    for i, b in enumerate(bins):
        v = float(b.get("vol3", 0.0) or 0.0)
        if v > best_v:
            best_v = v
            best_i = i
    if best_i is None or best_v <= 0:
        return None
    return _bin_center(bins[int(best_i)])


def hvn_clusters_from_bins(
    bins: List[Dict[str, Any]],
    *,
    max_volume: float,
    threshold_ratio: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    从 SessionVP bins 派生 HVN cluster（不修改原 VP 算法，只做结构化结论）。
    cluster = 连续 bins.totalVolume >= max_volume * threshold_ratio
    """
    if not bins or max_volume <= 0:
        return []
    thr = float(max_volume) * float(threshold_ratio)
    total = sum(float(b.get("totalVolume", 0.0) or 0.0) for b in bins) or 1e-9

    out: List[Dict[str, Any]] = []
    in_c = False
    start = 0
    for i, b in enumerate(bins):
        v = float(b.get("totalVolume", 0.0) or 0.0)
        if v >= thr and not in_c:
            in_c = True
            start = i
        if in_c and (v < thr or i == len(bins) - 1):
            end = i if (v >= thr and i == len(bins) - 1) else i - 1
            seg = bins[start : end + 1]
            seg_total = sum(float(x.get("totalVolume", 0.0) or 0.0) for x in seg)
            # cluster poc：seg 内最大 totalVolume bin center
            poc_bin = max(seg, key=lambda x: float(x.get("totalVolume", 0.0) or 0.0))
            out.append(
                {
                    "low": float(seg[0]["yStart"]),
                    "high": float(seg[-1]["yEnd"]),
                    "poc": _bin_center(poc_bin),
                    "volume_share": float(seg_total / total),
                }
            )
            in_c = False
    return out


def lvn_gaps_from_bins(
    bins: List[Dict[str, Any]],
    *,
    max_volume: float,
    threshold_ratio: float = 0.2,
) -> List[Dict[str, Any]]:
    """
    从 bins 派生 LVN gaps：
    gap = 连续 bins.totalVolume <= max_volume * threshold_ratio
    """
    if not bins or max_volume <= 0:
        return []
    thr = float(max_volume) * float(threshold_ratio)
    out: List[Dict[str, Any]] = []
    in_g = False
    start = 0
    for i, b in enumerate(bins):
        v = float(b.get("totalVolume", 0.0) or 0.0)
        if v <= thr and not in_g:
            in_g = True
            start = i
        if in_g and (v > thr or i == len(bins) - 1):
            end = i if (v <= thr and i == len(bins) - 1) else i - 1
            seg = bins[start : end + 1]
            out.append({"low": float(seg[0]["yStart"]), "high": float(seg[-1]["yEnd"])})
            in_g = False
    return out


def _find_cluster_containing(clusters: List[Dict[str, Any]], price: float) -> Optional[Dict[str, Any]]:
    for c in clusters:
        if float(c["low"]) <= float(price) <= float(c["high"]):
            return c
    return None


def _count_in_range(values: List[float], lo: float, hi: float) -> int:
    return sum(1 for v in values if lo <= float(v) <= hi)


def build_vp_events(
    *,
    close: float,
    atr14: float,
    poc: float,
    vah: float,
    val: float,
    poc_zone_w: float,
    last_closes: List[float],
    active_block: Optional[Dict[str, Any]],
    evidence_map: Dict[str, bool],
    bos: str,
    choch: str,
    structure_high: Optional[float] = None,
    structure_low: Optional[float] = None,
    break_buffer: float = 0.0,
    last_high: Optional[float] = None,
    last_low: Optional[float] = None,
    recent_highs: Optional[List[float]] = None,
    recent_lows: Optional[List[float]] = None,
    recent_closes: Optional[List[float]] = None,
    va_break_confirm_bars: int = 1,
    va_fakeout_window_bars: int = 3,
    hvn_threshold_ratio: float = 0.7,
    lvn_threshold_ratio: float = 0.2,
    hvn_leave_window_bars: int = 12,
    hvn_leave_max_inside: int = 2,
    new_hvn_window_bars: int = 12,
    new_hvn_min_inside: int = 10,
) -> Dict[str, Any]:
    """
    基于 SessionVP active_block + 当前价格状态 派生 VP 事件。
    返回：
    - derived: developing_poc/hvn/lvn 等结构
    - events: 事件列表（给 AI/前端）
    """
    events: List[Dict[str, Any]] = []
    derived: Dict[str, Any] = {}

    buf = max(float(break_buffer), 0.05 * float(atr14), 1e-9) if atr14 and atr14 > 0 else max(float(break_buffer), 1e-9)
    z_low, z_high = float(poc) - float(poc_zone_w), float(poc) + float(poc_zone_w)

    # --- break/fakeout of POC ---
    cross_up = bool(evidence_map.get("close_cross_poc_up"))
    cross_down = bool(evidence_map.get("close_cross_poc_down"))
    rej_up = bool(evidence_map.get("rejection_window_up"))
    rej_down = bool(evidence_map.get("rejection_window_down"))
    acc_up = bool(evidence_map.get("value_area_acceptance_up"))
    acc_down = bool(evidence_map.get("value_area_acceptance_down"))

    if cross_up:
        events.append({"id": "break_of_poc", "direction": "Bullish", "strength": "Medium", "evidence": {"close": close, "poc": poc}})
    if cross_down:
        events.append({"id": "break_of_poc", "direction": "Bearish", "strength": "Medium", "evidence": {"close": close, "poc": poc}})
    if rej_up and not acc_up:
        events.append({"id": "fake_out_of_poc", "direction": "Bearish", "strength": "Strong", "evidence": {"reason": "rejection_window_up"}})
    if rej_down and not acc_down:
        events.append({"id": "fake_out_of_poc", "direction": "Bullish", "strength": "Strong", "evidence": {"reason": "rejection_window_down"}})

    # --- break/fakeout of VAH/VAL ---
    confirm_n = max(1, int(va_break_confirm_bars))
    cseq = (recent_closes or [])[-confirm_n:] if recent_closes else []
    vah_break_confirmed = bool(cseq) and all(float(c) > float(vah) + buf for c in cseq)
    val_break_confirmed = bool(cseq) and all(float(c) < float(val) - buf for c in cseq)

    if vah_break_confirmed:
        events.append({"id": "break_of_vah", "direction": "Bullish", "strength": "Medium", "evidence": {"vah": vah}})
        events.append({"id": "break_of_value_area", "direction": "Bullish", "strength": "Weak", "evidence": {"vah": vah}})
    if val_break_confirmed:
        events.append({"id": "break_of_val", "direction": "Bearish", "strength": "Medium", "evidence": {"val": val}})
        events.append({"id": "break_of_value_area", "direction": "Bearish", "strength": "Weak", "evidence": {"val": val}})

    # fakeout：刺破但收回价值区
    w = max(1, int(va_fakeout_window_bars))
    highs_w = (recent_highs or [])[-w:] if recent_highs else []
    lows_w = (recent_lows or [])[-w:] if recent_lows else []
    swept_vah_recent = (last_high is not None and float(last_high) > float(vah) + buf) or any(float(h) > float(vah) + buf for h in highs_w)
    swept_val_recent = (last_low is not None and float(last_low) < float(val) - buf) or any(float(l) < float(val) - buf for l in lows_w)

    if swept_vah_recent and close < float(vah) - buf:
        events.append({"id": "fake_out_of_vah", "direction": "Bearish", "strength": "Strong", "evidence": {"vah": vah, "high": last_high}})
    if swept_val_recent and close > float(val) + buf:
        events.append({"id": "fake_out_of_val", "direction": "Bullish", "strength": "Strong", "evidence": {"val": val, "low": last_low}})

    # --- acceptance / rejection events ---
    if acc_up:
        events.append({"id": "acceptance", "direction": "Bullish", "strength": "Medium", "evidence": {"window": 12, "maxReversions": 2}})
    if acc_down:
        events.append({"id": "acceptance", "direction": "Bearish", "strength": "Medium", "evidence": {"window": 12, "maxReversions": 2}})
    if rej_up:
        events.append({"id": "rejection", "direction": "Bearish", "strength": "Medium", "evidence": {"window": 6}})
    if rej_down:
        events.append({"id": "rejection", "direction": "Bullish", "strength": "Medium", "evidence": {"window": 6}})

    # --- HVN/LVN derived from bins ---
    if active_block and active_block.get("bins"):
        bins = active_block["bins"]
        max_vol = float(active_block.get("maxVolume") or 0.0)
        hvn = hvn_clusters_from_bins(bins, max_volume=max_vol, threshold_ratio=float(hvn_threshold_ratio))
        lvn = lvn_gaps_from_bins(bins, max_volume=max_vol, threshold_ratio=float(lvn_threshold_ratio))
        dev_poc = developing_poc_from_bins(bins) or float(active_block.get("pocPrice") or poc)

        primary_hvn = _find_cluster_containing(hvn, float(active_block.get("pocPrice") or poc))
        dev_hvn = _find_cluster_containing(hvn, dev_poc)

        derived = {
            "poc": float(active_block.get("pocPrice") or poc),
            "vah": float(active_block.get("valueAreaHigh") or vah),
            "val": float(active_block.get("valueAreaLow") or val),
            "developing_poc": float(dev_poc),
            "hvn_clusters": hvn[:6],
            "lvn_gaps": lvn[:6],
            "primary_hvn": primary_hvn,
        }

        # leave_hvn：最近 N 根 close 大多数在 primary_hvn 外
        if primary_hvn and last_closes:
            recent = last_closes[-int(hvn_leave_window_bars) :] if hvn_leave_window_bars > 0 else last_closes
            inside = _count_in_range(recent, float(primary_hvn["low"]), float(primary_hvn["high"]))
            if inside <= int(hvn_leave_max_inside) and (
                close < float(primary_hvn["low"]) - buf or close > float(primary_hvn["high"]) + buf
            ):
                events.append(
                    {
                        "id": "leave_hvn",
                        "direction": "Bullish" if close > float(primary_hvn["high"]) else "Bearish",
                        "strength": "Medium",
                        "evidence": {
                            "inside_count_window": inside,
                            "window_bars": int(hvn_leave_window_bars),
                            "hvn": {"low": primary_hvn["low"], "high": primary_hvn["high"]},
                        },
                    }
                )

        # new_hvn_formed：developing_poc 落入不同 cluster，且最近 N 根大多数在该 cluster 内
        if primary_hvn and dev_hvn and (dev_hvn is not primary_hvn) and last_closes:
            recent = last_closes[-int(new_hvn_window_bars) :] if new_hvn_window_bars > 0 else last_closes
            inside_dev = _count_in_range(recent, float(dev_hvn["low"]), float(dev_hvn["high"]))
            if inside_dev >= int(new_hvn_min_inside):
                events.append(
                    {
                        "id": "new_hvn_formed",
                        "direction": "Bullish" if dev_poc > float(primary_hvn["poc"]) else "Bearish",
                        "strength": "Medium",
                        "evidence": {
                            "developing_poc": float(dev_poc),
                            "cluster": {"low": dev_hvn["low"], "high": dev_hvn["high"], "poc": dev_hvn["poc"]},
                            "inside_count_window": inside_dev,
                            "window_bars": int(new_hvn_window_bars),
                        },
                    }
                )

    return {"derived": derived, "events": events}

