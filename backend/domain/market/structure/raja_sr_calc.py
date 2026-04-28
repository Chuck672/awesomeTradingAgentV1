from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


def calc_raja_sr(bars: List[Dict[str, Any]], lookback: int = 1000, pivot: int = 2, max_zones: int = 6) -> List[Dict[str, Any]]:
    bars = bars[-lookback:]
    if len(bars) < 50:
        return []

    def get_median(xs):
        import math

        xs = [x for x in xs if not math.isnan(x)]
        if not xs:
            return 0.0
        return float(np.median(xs))

    recent_bars = bars[-200:]
    trs = []
    for b in recent_bars:
        h, l = float(b.get("high", 0)), float(b.get("low", 0))
        if h > 0 and l > 0 and h > l:
            trs.append(h - l)

    tr_med = max(get_median(trs), 1e-6)

    tol_tr_mult = 0.20
    margin_tr_mult = 0.06
    min_touches = 2

    tol = max(tr_med * tol_tr_mult, 1e-6)
    margin = max(tr_med * margin_tr_mult, 1e-6)
    wick_min = tr_med * 0.25

    highs, lows = [], []
    for b in bars:
        h, l = float(b.get("high", 0)), float(b.get("low", 0))
        if h <= 0 or l <= 0:
            continue
        o, c = float(b.get("open", 0)), float(b.get("close", 0))
        body_high = max(o, c)
        body_low = min(o, c)

        if h - body_high >= wick_min:
            highs.append({"time": b.get("time"), "level": body_high, "wick": h})
        if body_low - l >= wick_min:
            lows.append({"time": b.get("time"), "level": body_low, "wick": l})

    if len(highs) + len(lows) < 6:
        highs, lows = [], []
        n = len(bars)
        if n >= pivot * 2 + 3:
            for i in range(pivot, n - pivot):
                b = bars[i]
                h, l = float(b.get("high", 0)), float(b.get("low", 0))
                if h <= 0 or l <= 0:
                    continue

                left_high = max([float(x.get("high", 0)) for x in bars[i - pivot : i]])
                left_low = min([float(x.get("low", 0)) for x in bars[i - pivot : i]])
                right_high = max([float(x.get("high", 0)) for x in bars[i + 1 : i + 1 + pivot]])
                right_low = min([float(x.get("low", 0)) for x in bars[i + 1 : i + 1 + pivot]])

                o, c = float(b.get("open", 0)), float(b.get("close", 0))

                if h > left_high and h > right_high:
                    highs.append({"time": b.get("time"), "level": max(o, c), "wick": h})
                if l < left_low and l < right_low:
                    lows.append({"time": b.get("time"), "level": min(o, c), "wick": l})

    def cluster_points(pts, t):
        if not pts:
            return []
        pts = sorted(pts, key=lambda x: x["level"])
        clusters = []
        cur = [pts[0]]
        cur_center = pts[0]["level"]
        for p in pts[1:]:
            if abs(p["level"] - cur_center) <= t:
                cur.append(p)
                cur_center = sum(x["level"] for x in cur) / len(cur)
            else:
                clusters.append(cur)
                cur = [p]
                cur_center = p["level"]
        clusters.append(cur)
        return clusters

    res_clusters = cluster_points(highs, tol)
    sup_clusters = cluster_points(lows, tol)

    last_bar = bars[-1]
    last_t = last_bar.get("time")
    last_close = float(last_bar.get("close", 0))

    diffs = []
    recent_80 = bars[-80:]
    for i in range(len(recent_80) - 1):
        try:
            d = int(recent_80[i + 1]["time"]) - int(recent_80[i]["time"])
            if d > 0:
                diffs.append(d)
        except:
            pass
    bar_sec = max(int(get_median(diffs)) if diffs else 60, 1)
    lookback_n = len(bars)

    def zone_quality_metrics(bottom, top):
        wick_touch = 0
        body_overlap = 0
        close_inside = 0
        for b in bars:
            h, l = float(b.get("high", 0)), float(b.get("low", 0))
            o, c = float(b.get("open", 0)), float(b.get("close", 0))
            if h >= bottom and l <= top:
                wick_touch += 1
            body_low = min(o, c)
            body_high = max(o, c)
            if body_high >= bottom and body_low <= top:
                body_overlap += 1
            if bottom <= c <= top:
                close_inside += 1
        return wick_touch, body_overlap, close_inside

    def zone_from_cluster(cluster, side):
        if len(cluster) < min_touches:
            return None
        levels = [p["level"] for p in cluster]
        wicks = [p["wick"] for p in cluster]
        times = [p["time"] for p in cluster]

        base = get_median(levels)
        last_touch_time = max(times)

        if side == "resistance":
            bottom = base
            top = base + margin
            wick_excess = [max(0.0, w - base) for w in wicks]
        else:
            top = base
            bottom = base - margin
            wick_excess = [max(0.0, base - w) for w in wicks]

        avg_excess = sum(wick_excess) / len(wick_excess) if wick_excess else 0.0
        score = len(cluster) * (avg_excess / margin if margin > 0 else 1.0)

        dist = abs(base - last_close)
        score = score / (1.0 + dist / (tr_med * 10.0))

        return {"bottom": bottom, "top": top, "from_time": min(times), "to_time": last_t, "last_touch_time": last_touch_time, "touches": len(cluster), "score": score, "level": base, "avg_wick_excess": avg_excess, "type": side}

    resistance = [z for z in (zone_from_cluster(cl, "resistance") for cl in res_clusters) if z is not None]
    support = [z for z in (zone_from_cluster(cl, "support") for cl in sup_clusters) if z is not None]

    def merge_zones(zs):
        if not zs:
            return []
        sorted_by_score = sorted(zs, key=lambda x: x["score"], reverse=True)
        dedup = []
        min_distance = tol * 1.8
        for cur in sorted_by_score:
            too_close = False
            for ex in dedup:
                overlapping = (cur["top"] >= ex["bottom"]) and (cur["bottom"] <= ex["top"])
                level_close = abs(cur["level"] - ex["level"]) < min_distance
                if overlapping or level_close:
                    too_close = True
                    break
            if not too_close:
                dedup.append(cur)
        return sorted(dedup, key=lambda x: x["bottom"])

    all_cands = merge_zones(resistance + support)
    resistance = [z for z in all_cands if z["type"] == "resistance"]
    support = [z for z in all_cands if z["type"] == "support"]

    import math

    max_close_inside_ratio = 0.22
    max_body_overlap_ratio = 0.35
    dist_mult = 20.0
    half_life_bars = max(20.0, lookback_n * 0.75)
    min_sep = max(tol * 1.2, margin * 1.8)

    def trade_score(z, side):
        dist = abs(z["level"] - last_close)
        if dist > tr_med * dist_mult:
            return -1e9

        wick_t, body_o, close_i = zone_quality_metrics(z["bottom"], z["top"])
        close_ratio = close_i / max(1.0, lookback_n)
        body_ratio = body_o / max(1.0, lookback_n)

        if close_ratio > max_close_inside_ratio:
            return -1e9
        if body_ratio > max_body_overlap_ratio:
            return -1e9

        side_mult = 1.0
        if side == "resistance" and z["bottom"] < last_close - tol:
            side_mult = 0.65
        if side == "support" and z["top"] > last_close + tol:
            side_mult = 0.65

        clean = 1.0 / (1.0 + close_ratio * 3.0 + body_ratio * 1.5)
        age_bars = max(0.0, (int(last_t) - int(z["last_touch_time"])) / bar_sec)
        recency = math.exp(-age_bars / half_life_bars)
        distance = 1.0 / (1.0 + dist / (tr_med * 4.0))

        return z["score"] * clean * recency * distance * side_mult

    def pick_trade(zs, side):
        scored = []
        for z in zs:
            s = trade_score(z, side)
            if s > -1e8:
                z_copy = dict(z)
                z_copy["trade_score"] = s
                scored.append(z_copy)

        picked = []
        if scored:
            if side == "resistance":
                preferred = [z for z in scored if z["level"] >= last_close]
                fallback = [z for z in scored if z["level"] < last_close]
            else:
                preferred = [z for z in scored if z["level"] <= last_close]
                fallback = [z for z in scored if z["level"] > last_close]

            anchor_pool = preferred if preferred else fallback
            anchor_pool = sorted(anchor_pool, key=lambda x: abs(x["level"] - last_close))
            if anchor_pool:
                picked.append(anchor_pool[0])

        scored = sorted(scored, key=lambda x: x["trade_score"], reverse=True)
        for z in scored:
            if len(picked) >= max_zones:
                break
            if any(abs(z["level"] - p["level"]) < min_sep for p in picked):
                continue
            if z not in picked:
                picked.append(z)

        return sorted(picked, key=lambda x: x["level"])

    resistance = pick_trade(resistance, "resistance")
    support = pick_trade(support, "support")

    return resistance + support

