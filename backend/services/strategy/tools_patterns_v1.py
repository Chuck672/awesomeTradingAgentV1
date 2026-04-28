from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.services.chart_scene.patterns import detect_candlestick_patterns
from backend.domain.market.structure.swings import detect_swings, structure_state_from_swings, confirmed_structure_levels


def _bars_for_tf(bars_by_tf: Dict[str, Any], tf: str) -> List[Dict[str, Any]]:
    v = bars_by_tf.get(tf)
    return v if isinstance(v, list) else []


def _atr14_from_bars(bars: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    """
    轻量 ATR（仅用于 detector 容错与阈值转换）；不依赖 indicator 计算结果。
    """
    if len(bars) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(bars)):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    return float(np.mean(trs[-period:]))


def _last_close(bars: List[Dict[str, Any]]) -> Optional[float]:
    if not bars:
        return None
    try:
        return float(bars[-1]["close"])
    except Exception:
        return None


def _levels_and_zones(structures_levels: Any, structures_zones: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    levels = structures_levels if isinstance(structures_levels, list) else []
    zones = structures_zones if isinstance(structures_zones, list) else []
    return levels, zones


def _interval_iou(a0: int, a1: int, b0: int, b1: int) -> float:
    if a1 <= a0 or b1 <= b0:
        return 0.0
    inter = max(0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return float(inter) / float(max(1, union))


def detect_rectangle_ranges(
    bars: List[Dict[str, Any]],
    *,
    lookback_bars: int = 120,
    min_touches_per_side: int = 2,
    tolerance_atr_mult: float = 0.25,
    min_containment: float = 0.80,
    max_height_atr: float = 8.0,
    max_drift_atr: float = 3.0,
    max_efficiency: float = 0.45,
    emit: str = "best",  # best|distinct|all
    max_results: int = 50,
    distinct_no_overlap: bool = True,
    dedup_iou: float = 0.55,
) -> Dict[str, Any]:
    from backend.domain.market.patterns.pattern_detectors_v1 import detect_rectangle_ranges as _impl

    return _impl(
        bars,
        lookback_bars=lookback_bars,
        min_touches_per_side=min_touches_per_side,
        tolerance_atr_mult=tolerance_atr_mult,
        min_containment=min_containment,
        max_height_atr=max_height_atr,
        max_drift_atr=max_drift_atr,
        max_efficiency=max_efficiency,
        emit=emit,
        max_results=max_results,
        distinct_no_overlap=distinct_no_overlap,
        dedup_iou=dedup_iou,
    )


def detect_rectangle_range(
    bars: List[Dict[str, Any]],
    *,
    lookback_bars: int = 120,
    min_touches_per_side: int = 2,
    tolerance_atr_mult: float = 0.25,
    min_containment: float = 0.80,
    max_height_atr: float = 8.0,
    max_drift_atr: float = 3.0,
    max_efficiency: float = 0.45,
) -> Optional[Dict[str, Any]]:
    from backend.domain.market.patterns.pattern_detectors_v1 import detect_rectangle_range as _impl

    return _impl(
        bars,
        lookback_bars=lookback_bars,
        min_touches_per_side=min_touches_per_side,
        tolerance_atr_mult=tolerance_atr_mult,
        min_containment=min_containment,
        max_height_atr=max_height_atr,
        max_drift_atr=max_drift_atr,
        max_efficiency=max_efficiency,
    )


def detect_close_outside_level_zone(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    zones: List[Dict[str, Any]],
    close_buffer: float = 0.0,
    scan_mode: str = "realtime",  # realtime|historical
    lookback_bars: int = 300,
    confirm_mode: str = "one_body",  # one_body|two_close
    confirm_n: int = 2,
    max_events: int = 50,
) -> List[Dict[str, Any]]:
    from backend.domain.market.patterns.pattern_detectors_v1 import detect_close_outside_level_zone as _impl

    return _impl(
        bars,
        levels=levels,
        zones=zones,
        close_buffer=close_buffer,
        scan_mode=scan_mode,
        lookback_bars=lookback_bars,
        confirm_mode=confirm_mode,
        confirm_n=confirm_n,
        max_events=max_events,
    )


def detect_breakout_retest_hold(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    zones: List[Dict[str, Any]],
    scan_mode: str = "realtime",  # realtime|historical
    lookback_bars: int = 300,
    confirm_mode: str = "one_body",  # one_body|two_close
    confirm_n: int = 2,
    retest_window_bars: int = 16,
    continue_window_bars: int = 8,
    buffer: float = 0.0,
    pullback_margin: float = 0.0,
    max_events: int = 50,
) -> List[Dict[str, Any]]:
    from backend.domain.market.patterns.pattern_detectors_v1 import detect_breakout_retest_hold as _impl

    return _impl(
        bars,
        levels=levels,
        zones=zones,
        scan_mode=scan_mode,
        lookback_bars=lookback_bars,
        confirm_mode=confirm_mode,
        confirm_n=confirm_n,
        retest_window_bars=retest_window_bars,
        continue_window_bars=continue_window_bars,
        buffer=buffer,
        pullback_margin=pullback_margin,
        max_events=max_events,
    )


def detect_false_breakout(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    zones: List[Dict[str, Any]],
    lookback_bars: int = 120,
    buffer: float = 0.0,
) -> List[Dict[str, Any]]:
    from backend.domain.market.patterns.breakouts import detect_false_breakout as _impl

    return _impl(bars, levels=levels, zones=zones, lookback_bars=lookback_bars, buffer=buffer)


def detect_liquidity_sweep(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    lookback_bars: int = 160,
    buffer: float = 0.0,
    recover_within_bars: int = 3,
) -> List[Dict[str, Any]]:
    from backend.domain.market.patterns.breakouts import detect_liquidity_sweep as _impl

    return _impl(bars, levels=levels, lookback_bars=lookback_bars, buffer=buffer, recover_within_bars=recover_within_bars)


def detect_bos_choch(
    bars: List[Dict[str, Any]],
    *,
    lookback_bars: int = 220,
    pivot_left: int = 3,
    pivot_right: int = 3,
    buffer: float = 0.0,
) -> List[Dict[str, Any]]:
    from backend.domain.market.patterns.pattern_detectors_v1 import detect_bos_choch as _impl

    return _impl(bars, lookback_bars=lookback_bars, pivot_left=pivot_left, pivot_right=pivot_right, buffer=buffer)

def tool_pattern_detect_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload:
      - bars_by_tf: {tf:[bars]}
      - detectors: [PatternDetector dicts]
      - structures?: {levels:[], zones:[]}
      - indicator_series?: {id:{...}} (可选，后续用于 ATR ref 等)

    returns:
      - pattern_pack: {items:[...], summary:{...}}
    """
    bars_by_tf = payload.get("bars_by_tf") if isinstance(payload.get("bars_by_tf"), dict) else {}
    detectors = payload.get("detectors") if isinstance(payload.get("detectors"), list) else []
    structures = payload.get("structures") if isinstance(payload.get("structures"), dict) else None
    if not structures:
        # 兼容 IR executor：compile_v2_to_ir 可能会以 levels/zones 顶层输入传入
        lv_in = payload.get("levels") if isinstance(payload.get("levels"), list) else []
        zn_in = payload.get("zones") if isinstance(payload.get("zones"), list) else []
        structures = {"levels": lv_in, "zones": zn_in}
    levels, zones = _levels_and_zones(structures.get("levels"), structures.get("zones"))

    items: List[Dict[str, Any]] = []

    for d in detectors:
        if not isinstance(d, dict):
            continue
        t = str(d.get("type") or "")
        tf = str(d.get("timeframe") or "30m")
        bars = _bars_for_tf(bars_by_tf, tf)
        if not bars:
            continue

        if t == "rectangle_range":
            emit = str(d.get("emit") or "best")
            rep = detect_rectangle_ranges(
                bars,
                lookback_bars=int(d.get("lookback_bars") or 120),
                min_touches_per_side=int(d.get("min_touches_per_side") or 2),
                tolerance_atr_mult=float(d.get("tolerance_atr_mult") or 0.25),
                min_containment=float(d.get("min_containment") or 0.80),
                max_height_atr=float(d.get("max_height_atr") or 8.0),
                max_drift_atr=float(d.get("max_drift_atr") or 3.0),
                max_efficiency=float(d.get("max_efficiency") or 0.45),
                emit=emit,
                max_results=int(d.get("max_results") or 50),
                distinct_no_overlap=bool(d.get("distinct_no_overlap") if d.get("distinct_no_overlap") is not None else True),
                dedup_iou=float(d.get("dedup_iou") or 0.55),
            )
            for it in (rep.get("items") or []) if isinstance(rep, dict) else []:
                if not isinstance(it, dict):
                    continue
                it["timeframe"] = tf
                # 透传“候选总数”，帮助前端显示“找到多少 / 输出多少”
                if isinstance(it.get("evidence"), dict) and isinstance(rep.get("candidates"), int):
                    it["evidence"]["candidates_total"] = int(rep["candidates"])
                    it["evidence"]["emit_mode"] = emit
                items.append(it)

        elif t == "close_outside_level_zone":
            close_buf = float(d.get("close_buffer") or 0.0)
            for it in detect_close_outside_level_zone(
                bars,
                levels=levels,
                zones=zones,
                close_buffer=close_buf,
                scan_mode=str(d.get("scan_mode") or "realtime"),
                lookback_bars=int(d.get("lookback_bars") or 300),
                confirm_mode=str(d.get("confirm_mode") or "one_body"),
                confirm_n=int(d.get("confirm_n") or 2),
                max_events=int(d.get("max_events") or 50),
            ):
                it["timeframe"] = tf
                items.append(it)

        elif t == "breakout_retest_hold":
            for it in detect_breakout_retest_hold(
                bars,
                levels=levels,
                zones=zones,
                scan_mode=str(d.get("scan_mode") or "realtime"),
                lookback_bars=int(d.get("lookback_bars") or 300),
                confirm_mode=str(d.get("confirm_mode") or "one_body"),
                confirm_n=int(d.get("confirm_n") or 2),
                retest_window_bars=int(d.get("retest_window_bars") or 16),
                continue_window_bars=int(d.get("continue_window_bars") or 8),
                buffer=float(d.get("buffer") or 0.0),
                pullback_margin=float(d.get("pullback_margin") or 0.0),
                max_events=int(d.get("max_events") or 50),
            ):
                it["timeframe"] = tf
                items.append(it)

        elif t == "candlestick":
            atr14 = _atr14_from_bars(bars) or 0.0
            pats = detect_candlestick_patterns(bars, atr14=atr14)
            # filter by requested patterns if provided
            allow = d.get("patterns") if isinstance(d.get("patterns"), list) else []
            if allow:
                pats = [p for p in pats if p.get("id") in set(map(str, allow))]
            for p in pats:
                p2 = dict(p)
                p2["type"] = "candlestick"
                p2["timeframe"] = tf
                items.append(p2)

        elif t == "false_breakout":
            buf = float(d.get("buffer") or 0.0)
            for it in detect_false_breakout(bars, levels=levels, zones=zones, lookback_bars=int(d.get("lookback_bars") or 120), buffer=buf):
                it["timeframe"] = tf
                items.append(it)

        elif t == "liquidity_sweep":
            buf = float(d.get("buffer") or 0.0)
            for it in detect_liquidity_sweep(
                bars,
                levels=levels,
                lookback_bars=int(d.get("lookback_bars") or 160),
                buffer=buf,
                recover_within_bars=int(d.get("recover_within_bars") or 3),
            ):
                it["timeframe"] = tf
                items.append(it)

        elif t in ("bos", "choch"):
            # 统一由 detect_bos_choch 产出两者
            buf = float(d.get("buffer") or 0.0)
            got = detect_bos_choch(
                bars,
                lookback_bars=int(d.get("lookback_bars") or 220),
                pivot_left=int(d.get("pivot_left") or 3),
                pivot_right=int(d.get("pivot_right") or 3),
                buffer=buf,
            )
            for it in got:
                if it.get("type") != t:
                    continue
                it["timeframe"] = tf
                items.append(it)

        # 其他 type：后续 phase2 再接

    summary = {"items": len(items), "types": sorted(list({str(i.get("type")) for i in items if i.get("type")}))}
    return {"pattern_pack": {"items": items, "summary": summary}}
