from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from backend.domain.market.types import bar_time, f


def _atr_from_bars(bars: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(bars)):
        h = f(bars[i].get("high"))
        l = f(bars[i].get("low"))
        pc = f(bars[i - 1].get("close"))
        if h is None or l is None or pc is None:
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    tail = trs[-period:]
    return sum(tail) / max(1, len(tail))


def _norm_zone_edges(z: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    top = f(z.get("top"))
    bot = f(z.get("bottom"))
    if top is not None and bot is not None:
        return float(top), float(bot)
    center = f(z.get("center"))
    if center is None:
        return None
    half = f(z.get("half_width"))
    if half is None:
        hw_pips = f(z.get("half_width_pips"))
        pip_size = f(z.get("pip_size"))
        if hw_pips is not None and pip_size is not None and pip_size > 0:
            half = float(hw_pips) * float(pip_size)
        elif hw_pips is not None:
            half = float(hw_pips)
    if half is None:
        return None
    return float(center) + float(half), float(center) - float(half)


def _build_candidates_from_structures(
    *,
    levels: List[Dict[str, Any]],
    zones: List[Dict[str, Any]],
    max_candidates: int,
) -> List[Tuple[str, float, float, Dict[str, Any]]]:
    out: List[Tuple[str, float, float, Dict[str, Any]]] = []
    for z in zones:
        if not isinstance(z, dict):
            continue
        edges = _norm_zone_edges(z)
        if edges is None:
            continue
        top, bot = edges
        key = str(z.get("key") or z.get("id") or f"zone@{round((top + bot) / 2.0, 6)}")
        out.append((key, float(top), float(bot), {"source": "zone", "zone": z}))
        if len(out) >= int(max_candidates):
            return out
    for lv in levels:
        if not isinstance(lv, dict):
            continue
        p = f(lv.get("price"))
        if p is None:
            continue
        kind = str(lv.get("kind") or "level")
        key = str(lv.get("key") or lv.get("id") or f"{kind}@{p}")
        out.append((key, float(p), float(p), {"source": "level", "level": lv}))
        if len(out) >= int(max_candidates):
            return out
    return out


def _maybe_add_raja_sr_zones(
    *,
    bars: List[Dict[str, Any]],
    candidates: List[Tuple[str, float, float, Dict[str, Any]]],
    max_candidates: int,
    max_raja_zones: int,
) -> None:
    if len(candidates) >= int(max_candidates) or int(max_raja_zones) <= 0:
        return
    try:
        from backend.domain.market.structure.raja_sr_calc import calc_raja_sr
    except Exception:
        return
    try:
        z_all = calc_raja_sr(bars) or []
    except Exception:
        return
    if not isinstance(z_all, list) or not z_all:
        return
    z_all_sorted = []
    for z in z_all:
        if not isinstance(z, dict):
            continue
        score = f(z.get("score")) or 0.0
        top = f(z.get("top"))
        bot = f(z.get("bottom"))
        if top is None or bot is None:
            continue
        z_all_sorted.append((float(score), float(top), float(bot), z))
    z_all_sorted.sort(key=lambda x: x[0], reverse=True)
    for score, top, bot, z in z_all_sorted[: int(max_raja_zones)]:
        key = f"raja_sr@{round(bot, 6)}-{round(top, 6)}"
        candidates.append((key, float(top), float(bot), {"source": "raja_sr", "zone": z, "score": score}))
        if len(candidates) >= int(max_candidates):
            return


def detect_false_breakout(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    zones: List[Dict[str, Any]],
    lookback_bars: int = 120,
    buffer: float = 0.0,
    buffer_atr_mult: float = 0.05,
    max_candidates: int = 30,
    include_raja_sr: bool = True,
    max_raja_zones: int = 6,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lb = int(lookback_bars)
    if lb <= 3 or len(bars) < lb:
        return out
    win = bars[-lb:]

    atr = _atr_from_bars(win) or 0.0
    buf = max(float(buffer), float(atr) * max(0.0, float(buffer_atr_mult)))

    candidates = _build_candidates_from_structures(levels=levels, zones=zones, max_candidates=int(max_candidates))
    if bool(include_raja_sr):
        _maybe_add_raja_sr_zones(bars=win, candidates=candidates, max_candidates=int(max_candidates), max_raja_zones=int(max_raja_zones))
    if not candidates:
        return out

    hits: List[Tuple[int, float, Dict[str, Any]]] = []
    for key, top, bot, meta in candidates[: int(max_candidates)]:
        best: Optional[Dict[str, Any]] = None
        best_t = -1
        best_exc = 0.0
        for i in range(len(win) - 1, 0, -1):
            b = win[i]
            p = win[i - 1]
            h = f(b.get("high"))
            l = f(b.get("low"))
            c = f(b.get("close"))
            pc = f(p.get("close"))
            t = bar_time(b)
            if h is None or l is None or c is None or pc is None or t is None:
                continue
            if h > top + buf and c < top - buf and pc <= top + buf:
                exc = float(h - top)
                if t > best_t or (t == best_t and exc > best_exc):
                    best_t = int(t)
                    best_exc = exc
                    best = {
                        "id": "false_breakout_up",
                        "type": "false_breakout",
                        "direction": "Bearish",
                        "strength": "Medium",
                        "score": 76.0,
                        "evidence": {"key": key, "top": float(top), "bottom": float(bot), "bar_time": int(t), "bar_idx": i, "buffer": float(buf), "high": float(h), "close": float(c), "prev_close": float(pc), "source": meta.get("source")},
                    }
            if l < bot - buf and c > bot + buf and pc >= bot - buf:
                exc = float(bot - l)
                if t > best_t or (t == best_t and exc > best_exc):
                    best_t = int(t)
                    best_exc = exc
                    best = {
                        "id": "false_breakout_down",
                        "type": "false_breakout",
                        "direction": "Bullish",
                        "strength": "Medium",
                        "score": 76.0,
                        "evidence": {"key": key, "top": float(top), "bottom": float(bot), "bar_time": int(t), "bar_idx": i, "buffer": float(buf), "low": float(l), "close": float(c), "prev_close": float(pc), "source": meta.get("source")},
                    }
        if best is not None:
            hits.append((best_t, best_exc, best))

    if not hits:
        return out
    hits.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out.append(hits[0][2])
    return out[:8]


def detect_liquidity_sweep(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    lookback_bars: int = 160,
    buffer: float = 0.0,
    buffer_atr_mult: float = 0.05,
    recover_within_bars: int = 3,
    max_candidates: int = 40,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lb = int(lookback_bars)
    if lb <= 5 or len(bars) < lb:
        return out
    win = bars[-lb:]

    atr = _atr_from_bars(win) or 0.0
    buf = max(float(buffer), float(atr) * max(0.0, float(buffer_atr_mult)))

    cand: List[Tuple[str, float]] = []
    for lv in levels:
        if not isinstance(lv, dict):
            continue
        p = f(lv.get("price"))
        if p is None:
            continue
        kind = str(lv.get("kind") or "level")
        cand.append((str(lv.get("key") or f"{kind}@{p}"), float(p)))
    if not cand:
        return out

    best: Optional[Tuple[int, int, Dict[str, Any]]] = None
    for key, level in cand[: int(max_candidates)]:
        for i in range(len(win) - 1, 0, -1):
            b = win[i]
            h = f(b.get("high"))
            l = f(b.get("low"))
            t = bar_time(b)
            if h is None or l is None or t is None:
                continue
            if h > level + buf:
                for j in range(i, min(len(win), i + 1 + max(1, int(recover_within_bars)))):
                    c = f(win[j].get("close"))
                    tj = bar_time(win[j])
                    if c is None or tj is None:
                        continue
                    if c < level - buf:
                        ev = {
                            "id": "liquidity_sweep_up_recover",
                            "type": "liquidity_sweep",
                            "direction": "Bearish",
                            "strength": "Strong" if j > i else "Medium",
                            "score": 82.0,
                            "evidence": {"key": key, "level": float(level), "sweep_time": int(t), "sweep_idx": i, "recover_time": int(tj), "recover_idx": j, "buffer": float(buf)},
                        }
                        cand_best = (int(tj), int(t), ev)
                        if best is None or cand_best[0] > best[0] or (cand_best[0] == best[0] and cand_best[1] > best[1]):
                            best = cand_best
                        break
            if l < level - buf:
                for j in range(i, min(len(win), i + 1 + max(1, int(recover_within_bars)))):
                    c = f(win[j].get("close"))
                    tj = bar_time(win[j])
                    if c is None or tj is None:
                        continue
                    if c > level + buf:
                        ev = {
                            "id": "liquidity_sweep_down_recover",
                            "type": "liquidity_sweep",
                            "direction": "Bullish",
                            "strength": "Strong" if j > i else "Medium",
                            "score": 82.0,
                            "evidence": {"key": key, "level": float(level), "sweep_time": int(t), "sweep_idx": i, "recover_time": int(tj), "recover_idx": j, "buffer": float(buf)},
                        }
                        cand_best = (int(tj), int(t), ev)
                        if best is None or cand_best[0] > best[0] or (cand_best[0] == best[0] and cand_best[1] > best[1]):
                            best = cand_best
                        break

    if best is None:
        return out
    out.append(best[2])
    return out[:8]
