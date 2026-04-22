from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.services.historical import historical_service

from .indicators import (
    atr,
    confirmed_structure_levels,
    detect_swings,
    macd,
    rsi,
    slope_direction,
    sma,
    structure_state_from_swings,
)
from .patterns import detect_candlestick_patterns
from .scene_params import SceneParams
from .session_vp import (
    SessionVPOptions,
    calculate_all as sessionvp_calculate_all,
    calculate_block as sessionvp_calculate_block,
    _block_id as sessionvp_block_id,
    _session_type_utc as sessionvp_session_type_utc,
)
from .vp_events import build_vp_events


def _utc_now_ts() -> int:
    return int(dt.datetime.now(tz=dt.timezone.utc).timestamp())


def _to_beijing(ts_utc: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts_utc, tz=dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=8)))


def _fmt_beijing(ts_utc: int) -> str:
    return _to_beijing(ts_utc).strftime("%Y-%m-%d %H:%M")


def _active_session_utc(ts_utc: int) -> str:
    d = dt.datetime.fromtimestamp(ts_utc, tz=dt.timezone.utc)
    h = d.hour
    day_of_week = d.weekday()  # Mon=0..Sun=6
    if h >= 21:
        return "SYDNEY" if day_of_week == 0 else "ASIA"
    if 0 <= h < 7:
        return "ASIA"
    if 7 <= h < 12:
        return "EUROPE"
    if 12 <= h < 21:
        return "US"
    return "ASIA"


def _hash_state(scene: Dict[str, Any]) -> str:
    key = {
        "schema_version": scene.get("schema_version"),
        "symbol": scene.get("metadata", {}).get("symbol"),
        "timeframe": scene.get("metadata", {}).get("timeframe"),
        "session": scene.get("context", {}).get("active_session"),
        "close": scene.get("price", {}).get("last", {}).get("c"),
        "vp": scene.get("volume_profile", {}).get("active_block", {}),
        "structure_m30": scene.get("mtf", {}).get("m30", {}).get("structure"),
        "poc_state": scene.get("poc_migration", {}).get("state"),
        "impulse_atr": scene.get("poc_migration", {}).get("impulse_atr"),
    }
    raw = json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _dict_diff(old: Any, new: Any, path: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if type(old) != type(new):
        out.append({"path": path or "$", "value": new})
        return out
    if isinstance(old, dict):
        keys = set(old.keys()) | set(new.keys())
        for k in sorted(keys):
            p = f"{path}.{k}" if path else k
            if k not in old:
                out.append({"path": p, "value": new[k]})
            elif k not in new:
                out.append({"path": p, "value": None})
            else:
                out.extend(_dict_diff(old[k], new[k], p))
        return out
    if isinstance(old, list):
        if old != new:
            out.append({"path": path or "$", "value": new})
        return out
    if old != new:
        out.append({"path": path or "$", "value": new})
    return out


def _bars_since(ts_now: int, ts_start: Optional[int]) -> Optional[int]:
    if not ts_start:
        return None
    return max(0, int((int(ts_now) - int(ts_start)) / 60))


@dataclass
class SweepMemory:
    pending: bool = False
    direction: Optional[str] = None  # "UP" | "DOWN"
    level: Optional[float] = None
    start_time: Optional[int] = None
    max_exceed: float = 0.0
    last_status: Optional[str] = None  # "detected" | "recovered" | "timeout"


@dataclass
class BreakRetestMemory:
    active: bool = False
    key: Optional[str] = None  # "VAH" | "VAL" | "STRUCT_HIGH" | "STRUCT_LOW"
    direction: Optional[str] = None  # "UP" | "DOWN"
    level: Optional[float] = None
    start_time: Optional[int] = None
    touched: bool = False
    touch_time: Optional[int] = None
    last_status: Optional[str] = None  # "break" | "retest" | "reclaim" | "failed" | "timeout"


@dataclass
class SceneCache:
    last_scene: Optional[Dict[str, Any]] = None
    last_scene_id: Optional[str] = None
    prev_scene: Optional[Dict[str, Any]] = None
    prev_scene_id: Optional[str] = None
    # workflows
    sweep_mem: SweepMemory = field(default_factory=SweepMemory)
    retest_mem: BreakRetestMemory = field(default_factory=BreakRetestMemory)
    # diff ring buffer
    snapshots_by_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    snapshots_order: List[str] = field(default_factory=list)
    max_snapshots: int = 200
    last_bar_time: Optional[int] = None


class ChartSceneEngine:
    schema_version = "1.0.0"

    def __init__(self) -> None:
        self._cache: Dict[str, SceneCache] = {}
        self.params: SceneParams = SceneParams.from_env()

    def _key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol}::{timeframe}"

    def _cache_for(self, symbol: str, timeframe: str) -> SceneCache:
        key = self._key(symbol, timeframe)
        if key not in self._cache:
            self._cache[key] = SceneCache()
        return self._cache[key]

    # --- persistence hooks (for runtime_states) ---
    def export_runtime_state(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        cache = self._cache_for(symbol, timeframe)
        return {"sweep_mem": asdict(cache.sweep_mem), "retest_mem": asdict(cache.retest_mem)}

    def restore_runtime_state(self, symbol: str, timeframe: str, state: Dict[str, Any]) -> None:
        cache = self._cache_for(symbol, timeframe)
        sm = state.get("sweep_mem") if isinstance(state, dict) else None
        if isinstance(sm, dict):
            cache.sweep_mem.pending = bool(sm.get("pending", cache.sweep_mem.pending))
            cache.sweep_mem.direction = sm.get("direction", cache.sweep_mem.direction)
            cache.sweep_mem.level = sm.get("level", cache.sweep_mem.level)
            cache.sweep_mem.start_time = sm.get("start_time", cache.sweep_mem.start_time)
            try:
                cache.sweep_mem.max_exceed = float(sm.get("max_exceed", cache.sweep_mem.max_exceed) or 0.0)
            except Exception:
                pass
            cache.sweep_mem.last_status = sm.get("last_status", cache.sweep_mem.last_status)

        rm = state.get("retest_mem") if isinstance(state, dict) else None
        if isinstance(rm, dict):
            cache.retest_mem.active = bool(rm.get("active", cache.retest_mem.active))
            cache.retest_mem.key = rm.get("key", cache.retest_mem.key)
            cache.retest_mem.direction = rm.get("direction", cache.retest_mem.direction)
            cache.retest_mem.level = rm.get("level", cache.retest_mem.level)
            cache.retest_mem.start_time = rm.get("start_time", cache.retest_mem.start_time)
            cache.retest_mem.touched = bool(rm.get("touched", cache.retest_mem.touched))
            cache.retest_mem.touch_time = rm.get("touch_time", cache.retest_mem.touch_time)
            cache.retest_mem.last_status = rm.get("last_status", cache.retest_mem.last_status)

    # --- workflows ---
    def _update_sweep_events(
        self,
        *,
        mem: SweepMemory,
        now_ts: int,
        close: float,
        high: float,
        low: float,
        structure_high: Optional[float],
        structure_low: Optional[float],
        buf: float,
        recover_window_bars: int,
        bos: str,
        choch: str,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        def bars_since(start: int) -> int:
            return max(0, int((now_ts - int(start)) / 60))

        # pending phase: wait recover
        if mem.pending and mem.start_time is not None and mem.level is not None and mem.direction is not None:
            n = bars_since(mem.start_time)
            level = float(mem.level)
            if mem.direction == "UP":
                mem.max_exceed = max(mem.max_exceed, max(0.0, float(high) - level))
                recovered = float(close) < level - buf
            else:
                mem.max_exceed = max(mem.max_exceed, max(0.0, level - float(low)))
                recovered = float(close) > level + buf

            if recovered and n <= recover_window_bars:
                mem.pending = False
                mem.last_status = "recovered"
                out.append(
                    {
                        "id": "liquidity_sweep_up_recover" if mem.direction == "UP" else "liquidity_sweep_down_recover",
                        "direction": "Bearish" if mem.direction == "UP" else "Bullish",
                        "strength": "Strong" if (choch in ("Bearish", "Bullish") or bos in ("Bearish", "Bullish")) else "Medium",
                        "evidence": {"level": level, "bars_to_recover": n, "max_exceed": float(mem.max_exceed), "recover_window_bars": recover_window_bars},
                    }
                )
            elif n > recover_window_bars:
                mem.pending = False
                mem.last_status = "timeout"
                out.append(
                    {
                        "id": "sweep_up_timeout" if mem.direction == "UP" else "sweep_down_timeout",
                        "direction": "Bearish" if mem.direction == "UP" else "Bullish",
                        "strength": "Weak",
                        "evidence": {"level": level, "bars_elapsed": n, "max_exceed": float(mem.max_exceed), "recover_window_bars": recover_window_bars},
                    }
                )
            else:
                out.append(
                    {
                        "id": "sweep_up_detected" if mem.direction == "UP" else "sweep_down_detected",
                        "direction": "Bearish" if mem.direction == "UP" else "Bullish",
                        "strength": "Weak",
                        "evidence": {"level": level, "bars_elapsed": n, "max_exceed": float(mem.max_exceed), "recover_window_bars": recover_window_bars},
                    }
                )

        # detect new sweep (only if not pending)
        if not mem.pending:
            if structure_high is not None and float(high) > float(structure_high) + buf:
                mem.pending = True
                mem.direction = "UP"
                mem.level = float(structure_high)
                mem.start_time = int(now_ts)
                mem.max_exceed = max(0.0, float(high) - float(structure_high))
                mem.last_status = "detected"
                out.append({"id": "sweep_up_detected", "direction": "Bearish", "strength": "Weak", "evidence": {"level": float(structure_high), "bars_elapsed": 0}})
            elif structure_low is not None and float(low) < float(structure_low) - buf:
                mem.pending = True
                mem.direction = "DOWN"
                mem.level = float(structure_low)
                mem.start_time = int(now_ts)
                mem.max_exceed = max(0.0, float(structure_low) - float(low))
                mem.last_status = "detected"
                out.append({"id": "sweep_down_detected", "direction": "Bullish", "strength": "Weak", "evidence": {"level": float(structure_low), "bars_elapsed": 0}})

        return out

    def _update_retest_events(
        self,
        *,
        mem: BreakRetestMemory,
        now_ts: int,
        close: float,
        high: float,
        low: float,
        buf: float,
        break_vah: bool,
        break_val: bool,
        bos_bull: bool,
        bos_bear: bool,
        choch: str,
        acceptance_up: bool,
        acceptance_down: bool,
        vah: float,
        val: float,
        structure_high: Optional[float],
        structure_low: Optional[float],
        retest_window_bars: int,
        reclaim_window_bars: int,
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        def bars_since(start: int) -> int:
            return max(0, int((now_ts - int(start)) / 60))

        def start_flow(key: str, direction: str, level: float) -> None:
            mem.active = True
            mem.key = key
            mem.direction = direction
            mem.level = float(level)
            mem.start_time = int(now_ts)
            mem.touched = False
            mem.touch_time = None
            mem.last_status = "break"

        def strength_for(direction: str) -> str:
            dir_lbl = "Bullish" if direction == "UP" else "Bearish"
            if (choch == "Bullish" and dir_lbl == "Bullish") or (choch == "Bearish" and dir_lbl == "Bearish"):
                return "Strong"
            if (direction == "UP" and acceptance_up) or (direction == "DOWN" and acceptance_down):
                return "Strong"
            return "Medium"

        if mem.active and mem.level is not None and mem.start_time is not None and mem.direction and mem.key:
            n = bars_since(mem.start_time)
            level = float(mem.level)

            if (not mem.touched) and n > int(retest_window_bars):
                events.append({"id": f"retest_{mem.key.lower()}_timeout", "direction": "Bullish" if mem.direction == "UP" else "Bearish", "strength": "Weak", "evidence": {"level": level, "bars_elapsed": n}})
                mem.active = False
                mem.last_status = "timeout"
                return events

            touched_now = (float(low) <= level + buf) and (float(high) >= level - buf)
            if touched_now and not mem.touched:
                mem.touched = True
                mem.touch_time = int(now_ts)
                mem.last_status = "retest"
                events.append({"id": f"retest_{mem.key.lower()}_touched", "direction": "Bullish" if mem.direction == "UP" else "Bearish", "strength": "Medium", "evidence": {"level": level, "bars_elapsed": n}})

            if mem.touched and mem.touch_time is not None:
                m = bars_since(mem.touch_time)
                if m > int(reclaim_window_bars):
                    events.append({"id": f"retest_{mem.key.lower()}_failed", "direction": "Bearish" if mem.direction == "UP" else "Bullish", "strength": "Medium", "evidence": {"level": level, "bars_since_touch": m}})
                    mem.active = False
                    mem.last_status = "failed"
                    return events

                reclaimed = (float(close) > level + buf) if mem.direction == "UP" else (float(close) < level - buf)
                if reclaimed:
                    events.append({"id": f"reclaim_{mem.key.lower()}_confirmed", "direction": "Bullish" if mem.direction == "UP" else "Bearish", "strength": strength_for(mem.direction), "evidence": {"level": level, "bars_since_touch": m}})
                    mem.active = False
                    mem.last_status = "reclaim"
                    return events

            events.append({"id": f"retest_{mem.key.lower()}_pending", "direction": "Bullish" if mem.direction == "UP" else "Bearish", "strength": "Weak", "evidence": {"level": level, "touched": bool(mem.touched), "bars_elapsed": n}})
            return events

        if break_vah:
            start_flow("VAH", "UP", float(vah))
            events.append({"id": "retest_vah_pending", "direction": "Bullish", "strength": "Weak", "evidence": {"level": float(vah)}})
        elif break_val:
            start_flow("VAL", "DOWN", float(val))
            events.append({"id": "retest_val_pending", "direction": "Bearish", "strength": "Weak", "evidence": {"level": float(val)}})
        elif bos_bull and structure_high is not None:
            start_flow("STRUCT_HIGH", "UP", float(structure_high))
            events.append({"id": "retest_struct_high_pending", "direction": "Bullish", "strength": "Weak", "evidence": {"level": float(structure_high)}})
        elif bos_bear and structure_low is not None:
            start_flow("STRUCT_LOW", "DOWN", float(structure_low))
            events.append({"id": "retest_struct_low_pending", "direction": "Bearish", "strength": "Weak", "evidence": {"level": float(structure_low)}})

        return events

    # --- explain / decision helpers (ported from our ai_trader_app version) ---
    def _apply_paths_adjustments(
        self,
        *,
        continuation: float,
        reversal: float,
        range_prob: float,
        entry_quality: float,
        hard_no_chase: bool,
        bos: str,
        choch: str,
        rejection_type: Optional[str],
        vp_event_ids: Set[str],
        evidence_map: Dict[str, bool],
    ) -> Dict[str, Any]:
        base_paths = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
        base_entry_quality = float(entry_quality)
        path_adjustments: List[Dict[str, Any]] = []

        def record_adj(trigger: str, note: str = "") -> Dict[str, Any]:
            obj: Dict[str, Any] = {
                "trigger": trigger,
                "note": note,
                "paths_before": {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)},
                "entry_quality_before": float(entry_quality),
            }
            path_adjustments.append(obj)
            return obj

        # sweep recover：强反转证据
        if "liquidity_sweep_up_recover" in vp_event_ids and (choch == "Bearish" or bos == "Bearish"):
            reversal = max(reversal, 0.60)
            adj = record_adj("liquidity_sweep_up_recover + (choch/bos bearish)", "sweep 回收 + 反向结构确认 → 提高反转路径")
            continuation *= 0.55
            range_prob *= 0.9
            entry_quality = min(entry_quality, 0.30) if not hard_no_chase else entry_quality
            rejection_type = rejection_type or "reversal_seed"
            adj["paths_after"] = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
            adj["entry_quality_after"] = float(entry_quality)

        if "liquidity_sweep_down_recover" in vp_event_ids and (choch == "Bullish" or bos == "Bullish"):
            reversal = max(reversal, 0.60)
            adj = record_adj("liquidity_sweep_down_recover + (choch/bos bullish)", "sweep 回收 + 反向结构确认 → 提高反转路径")
            continuation *= 0.55
            range_prob *= 0.9
            entry_quality = min(entry_quality, 0.30) if not hard_no_chase else entry_quality
            rejection_type = rejection_type or "reversal_seed"
            adj["paths_after"] = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
            adj["entry_quality_after"] = float(entry_quality)

        # VAH/VAL fakeout
        if "fake_out_of_vah" in vp_event_ids:
            range_prob = min(1.0, range_prob + 0.12)
            adj = record_adj("fake_out_of_vah", "刺破 VAH 后收回 → 提高震荡/回归权重")
            continuation *= 0.75
            adj["paths_after"] = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
            adj["entry_quality_after"] = float(entry_quality)

        if "fake_out_of_val" in vp_event_ids:
            range_prob = min(1.0, range_prob + 0.12)
            adj = record_adj("fake_out_of_val", "刺破 VAL 后收回 → 提高震荡/回归权重")
            continuation *= 0.75
            adj["paths_after"] = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
            adj["entry_quality_after"] = float(entry_quality)

        # break VAH/VAL + acceptance
        if ("break_of_vah" in vp_event_ids and evidence_map.get("value_area_acceptance_up")) or (
            "break_of_val" in vp_event_ids and evidence_map.get("value_area_acceptance_down")
        ):
            continuation = min(1.0, continuation + 0.10)
            adj = record_adj("break_of_vah/val + acceptance", "突破价值区边界并被接受 → 提高迁移继续权重")
            range_prob *= 0.9
            adj["paths_after"] = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
            adj["entry_quality_after"] = float(entry_quality)

        # leave_hvn
        if "leave_hvn" in vp_event_ids:
            continuation = min(1.0, continuation + 0.06)
            adj = record_adj("leave_hvn", "离开主 HVN → 降低继续震荡权重")
            range_prob *= 0.85
            adj["paths_after"] = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
            adj["entry_quality_after"] = float(entry_quality)

        # 结构点 reclaim/failed
        if "reclaim_struct_high_confirmed" in vp_event_ids or "reclaim_struct_low_confirmed" in vp_event_ids:
            continuation = min(1.0, continuation + 0.08)
            adj = record_adj("reclaim_struct_confirmed", "结构点回踩后 reclaim/hold 确认 → 提高结构延续倾向")
            range_prob *= 0.88
            adj["paths_after"] = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
            adj["entry_quality_after"] = float(entry_quality)

        if "retest_struct_high_failed" in vp_event_ids or "retest_struct_low_failed" in vp_event_ids:
            range_prob = min(1.0, range_prob + 0.08)
            adj = record_adj("retest_struct_failed", "结构点回踩后未能 reclaim → 提高震荡/反向倾向")
            continuation *= 0.85
            adj["paths_after"] = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
            adj["entry_quality_after"] = float(entry_quality)

        ssum2 = max(continuation + reversal + range_prob, 1e-9)
        continuation /= ssum2
        reversal /= ssum2
        range_prob /= ssum2
        final_paths = {"continuation": float(continuation), "reversal": float(reversal), "range": float(range_prob)}
        return {
            "base_paths": base_paths,
            "base_entry_quality": base_entry_quality,
            "final_paths": final_paths,
            "final_entry_quality": float(entry_quality),
            "adjustments": path_adjustments,
            "rejection_type": rejection_type,
        }

    def _build_next_actions(
        self,
        *,
        hard_no_chase: bool,
        evidence_map: Dict[str, bool],
        paths: Dict[str, float],
        state: str,
        direction_bias: str,
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []

        def add(action: str, trigger: str) -> None:
            actions.append({"action": action, "trigger": trigger})

        if hard_no_chase:
            add("WAIT_NEW_POC", "impulse_atr >= hard_no_chase_atr")
            add("WAIT_RETEST_POC", "price revisits poc_zone")
            return actions

        # sweep recover 优先：反转工作流
        if evidence_map.get("liquidity_sweep_up_recover") or evidence_map.get("liquidity_sweep_down_recover"):
            add("WAIT_CHOCH_BOS_CONFIRM", "sweep recover; wait structure confirmation")
            return actions

        # range / fakeout
        if (paths.get("range", 0.0) >= 0.55) or evidence_map.get("fake_out_of_vah") or evidence_map.get("fake_out_of_val"):
            add("WAIT_RANGE_EDGE", "range path dominant or VA fakeout; avoid chasing")
            add("WAIT_CONFIRM", "watch acceptance/rejection + structure signals")
            return actions

        # reclaim confirmed (VAH/VAL/struct) 分流
        if (
            evidence_map.get("reclaim_vah_confirmed")
            or evidence_map.get("reclaim_val_confirmed")
            or evidence_map.get("reclaim_struct_high_confirmed")
            or evidence_map.get("reclaim_struct_low_confirmed")
        ):
            if paths.get("continuation", 0.0) >= 0.55 and (
                evidence_map.get("value_area_acceptance_up") or evidence_map.get("value_area_acceptance_down")
            ):
                add("WAIT_CONTINUATION_CONFIRM", "reclaim + acceptance; wait continuation structure then act")
            elif paths.get("reversal", 0.0) >= 0.55:
                add("WAIT_REVERSAL_CONFIRM", "reclaim seen but reversal path dominant; wait CHoCH/BOS confirmation")
            else:
                add("WAIT_STRUCTURE_CONTINUE", "reclaim confirmed; wait structure continuation instead of chasing")
            return actions

        # 结构点回踩触达
        if evidence_map.get("retest_struct_high_touched") or evidence_map.get("retest_struct_low_touched"):
            add("WAIT_RECLAIM_CONFIRM", "structure level retest touched; wait reclaim/hold confirmation within window")
            return actions

        add("WAIT_OBSERVE", "no dominant path; keep monitoring")
        return actions

    # --- public APIs ---
    def build_from_bars(self, symbol: str, timeframe: str, bars: List[Dict[str, Any]], *, fast: bool = False) -> Dict[str, Any]:
        """
        从传入 bars 构建 scene（用于回测/批处理）。
        注意：bars 应为按 time 升序的 OHLCV（包含至少 time/open/high/low/close）。
        """
        now_ts = int(bars[-1]["time"]) if bars else _utc_now_ts()

        active_session = _active_session_utc(now_ts)

        closes = [float(b["close"]) for b in bars]
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]
        atr14 = atr(highs, lows, closes, period=14) or 0.0

        sma20 = sma(closes, 20) or 0.0
        sma50 = sma(closes, 50) or 0.0
        sma200 = sma(closes, 200) or 0.0
        if sma20 > sma50 > sma200:
            alignment = "Bullish"
        elif sma20 < sma50 < sma200:
            alignment = "Bearish"
        else:
            alignment = "Mixed"
        primary = "Bullish" if alignment == "Bullish" else ("Bearish" if alignment == "Bearish" else "Neutral")

        swings = detect_swings(bars[-600:]) if bars else []
        struct_state = structure_state_from_swings(swings)
        levels = confirmed_structure_levels(swings)
        structure_high = levels.get("structure_high")
        structure_low = levels.get("structure_low")
        break_buf = max(float(self.params.break_buffer_atr) * float(atr14), 1e-9)

        last = bars[-1] if bars else {"open": 0, "high": 0, "low": 0, "close": 0, "tick_volume": 0, "time": now_ts}
        close = float(last["close"])
        high = float(last["high"])
        low = float(last["low"])
        now_bar_time = int(last["time"])

        # BOS/CHoCH
        bos = "None"
        if structure_high is not None and close > float(structure_high) + break_buf:
            bos = "Bullish"
        if structure_low is not None and close < float(structure_low) - break_buf:
            bos = "Bearish"

        choch = "None"
        if struct_state == "HH_HL" and structure_low is not None and close < float(structure_low) - break_buf:
            choch = "Bearish"
        if struct_state == "LH_LL" and structure_high is not None and close > float(structure_high) + break_buf:
            choch = "Bullish"

        # SessionVP（对齐前端 SessionVP/Calculator.ts）
        # - 为了与前端的 session 划分、POC/VAH/VAL 计算完全一致，后端也使用同样的算法
        # - fast=True 时：只计算“当前 session 的 active_block”（避免全量 daysToCalculate 计算，性能更稳）
        active_block = None
        sessionvp_opts = SessionVPOptions(
            days_to_calculate=int(self.params.vp_days_to_calculate),
            bins=int(self.params.vp_bins),
            value_area_pct=float(self.params.vp_value_area_pct),
        )
        if bars:
            if fast:
                # 仅取当前 session 的 bars（从尾部回溯，直到 blockId 变化）
                now_type = sessionvp_session_type_utc(now_bar_time)
                now_bid = sessionvp_block_id(now_bar_time, now_type)
                session_bars_raw = []
                for b in reversed(bars):
                    ts = int(b["time"])
                    bid = sessionvp_block_id(ts, sessionvp_session_type_utc(ts))
                    if bid != now_bid:
                        break
                    session_bars_raw.append(b)
                    # 安全上限：避免极端情况下窗口过大（不会影响常见 M1~H1）
                    if len(session_bars_raw) >= 5000:
                        break
                session_bars_raw.reverse()
                sessionvp_data = [
                    {
                        "time": int(b["time"]),
                        "open": float(b["open"]),
                        "high": float(b["high"]),
                        "low": float(b["low"]),
                        "close": float(b["close"]),
                        "volume": float(b.get("tick_volume", 0) or 0),
                    }
                    for b in session_bars_raw
                ]
                active_block = sessionvp_calculate_block(now_bid, now_type, sessionvp_data, sessionvp_opts)
            else:
                sessionvp_data = [
                    {
                        "time": int(b["time"]),
                        "open": float(b["open"]),
                        "high": float(b["high"]),
                        "low": float(b["low"]),
                        "close": float(b["close"]),
                        "volume": float(b.get("tick_volume", 0) or 0),
                    }
                    for b in bars
                ]
                blocks = sessionvp_calculate_all(sessionvp_data, sessionvp_opts)
                active_block = blocks[-1] if blocks else None

        if active_block:
            active_session = str(active_block.get("type") or active_session)
            poc = float(active_block.get("pocPrice") or close)
            vah = float(active_block.get("valueAreaHigh") or poc)
            val = float(active_block.get("valueAreaLow") or poc)
        else:
            # 兜底：极端数据异常时回退到 close
            poc = close
            vah = close
            val = close

        # --- evidence for vp_events ---
        poc_zone_w = float(self.params.poc_zone_width_atr) * float(atr14) if atr14 > 0 else 0.0
        prev_close = float(bars[-2]["close"]) if len(bars) >= 2 else close
        z_low, z_high = float(poc) - float(poc_zone_w), float(poc) + float(poc_zone_w)

        close_cross_poc_up = prev_close <= float(poc) and close > float(poc)
        close_cross_poc_down = prev_close >= float(poc) and close < float(poc)

        # acceptance: 最近 N 根收盘绝大多数在 VA 内
        win = int(self.params.acceptance_window_bars)
        max_rev = int(self.params.acceptance_max_reversions)
        recent = closes[-win:] if len(closes) >= win else closes
        inside = [float(val) <= float(c) <= float(vah) for c in recent]
        inside_cnt = sum(1 for x in inside if x)
        accepted = inside_cnt >= max(1, win - max_rev)
        value_area_acceptance_up = bool(accepted and close >= float(poc))
        value_area_acceptance_down = bool(accepted and close <= float(poc))

        # rejection window: close 离开 poc zone（简化版）
        rejection_window_up = close < z_low
        rejection_window_down = close > z_high

        ev_map: Dict[str, bool] = {
            "close_cross_poc_up": bool(close_cross_poc_up),
            "close_cross_poc_down": bool(close_cross_poc_down),
            "value_area_acceptance_up": bool(value_area_acceptance_up),
            "value_area_acceptance_down": bool(value_area_acceptance_down),
            "rejection_window_up": bool(rejection_window_up),
            "rejection_window_down": bool(rejection_window_down),
        }

        # --- vp events ---
        vp_pack = build_vp_events(
            close=close,
            atr14=float(atr14),
            poc=float(poc),
            vah=float(vah),
            val=float(val),
            poc_zone_w=float(poc_zone_w),
            last_closes=[float(b["close"]) for b in bars[-60:]] if bars else [],
            active_block=active_block,
            evidence_map=ev_map,
            bos=bos,
            choch=choch,
            structure_high=structure_high,
            structure_low=structure_low,
            break_buffer=float(break_buf),
            last_high=float(high),
            last_low=float(low),
            recent_highs=[float(b["high"]) for b in bars[-max(5, int(self.params.va_fakeout_window_bars)) :]] if bars else [],
            recent_lows=[float(b["low"]) for b in bars[-max(5, int(self.params.va_fakeout_window_bars)) :]] if bars else [],
            recent_closes=[float(b["close"]) for b in bars[-max(5, int(self.params.va_break_confirm_bars)) :]] if bars else [],
            va_break_confirm_bars=int(self.params.va_break_confirm_bars),
            va_fakeout_window_bars=int(self.params.va_fakeout_window_bars),
            hvn_threshold_ratio=float(self.params.hvn_threshold_ratio),
            lvn_threshold_ratio=float(self.params.lvn_threshold_ratio),
            hvn_leave_window_bars=int(self.params.hvn_leave_window_bars),
            hvn_leave_max_inside=int(self.params.hvn_leave_max_inside),
            new_hvn_window_bars=int(self.params.new_hvn_window_bars),
            new_hvn_min_inside=int(self.params.new_hvn_min_inside),
        )

        cache = self._cache_for(symbol, timeframe)

        # sweep
        sweep_events = self._update_sweep_events(
            mem=cache.sweep_mem,
            now_ts=now_bar_time,
            close=close,
            high=high,
            low=low,
            structure_high=structure_high,
            structure_low=structure_low,
            buf=float(break_buf),
            recover_window_bars=int(self.params.sweep_recover_window_bars),
            bos=bos,
            choch=choch,
        )
        if sweep_events:
            vp_pack["events"] = (vp_pack.get("events") or []) + sweep_events
            # also map into evidence_map for next_actions
            for e in sweep_events:
                ev_map[str(e.get("id"))] = True

        vp_event_ids: Set[str] = set(str(e.get("id")) for e in (vp_pack.get("events") or []) if isinstance(e, dict))

        # retest/reclaim workflow
        retest_events = self._update_retest_events(
            mem=cache.retest_mem,
            now_ts=now_bar_time,
            close=close,
            high=high,
            low=low,
            buf=float(break_buf),
            break_vah=("break_of_vah" in vp_event_ids),
            break_val=("break_of_val" in vp_event_ids),
            bos_bull=(bos == "Bullish"),
            bos_bear=(bos == "Bearish"),
            choch=choch,
            acceptance_up=bool(ev_map.get("value_area_acceptance_up")),
            acceptance_down=bool(ev_map.get("value_area_acceptance_down")),
            vah=float(vah),
            val=float(val),
            structure_high=structure_high,
            structure_low=structure_low,
            retest_window_bars=int(self.params.retest_window_bars),
            reclaim_window_bars=int(self.params.reclaim_window_bars),
        )
        if retest_events:
            vp_pack["events"] = (vp_pack.get("events") or []) + retest_events
            for e in retest_events:
                ev_map[str(e.get("id"))] = True
            vp_event_ids = set(str(e.get("id")) for e in (vp_pack.get("events") or []) if isinstance(e, dict))

        # patterns + map weak evidence (optional)
        patterns = detect_candlestick_patterns(bars[-3:], atr14=float(atr14), min_body_atr=float(self.params.candle_min_body_atr))
        p_ids = set(p.get("id") for p in patterns)
        ev_map["bullish_engulfing"] = "bullish_engulfing" in p_ids
        ev_map["bearish_engulfing"] = "bearish_engulfing" in p_ids
        ev_map["bullish_pinbar"] = "bullish_pinbar" in p_ids
        ev_map["bearish_pinbar"] = "bearish_pinbar" in p_ids
        ev_map["inside_bar"] = "inside_bar" in p_ids
        ev_map["doji"] = "doji" in p_ids

        # initial paths + entry_quality
        impulse_atr = float(abs(close - poc) / max(atr14, 1e-9) if atr14 > 0 else 0.0)
        hard_no_chase = impulse_atr >= float(self.params.hard_no_chase_atr)
        entry_quality = 0.15 if hard_no_chase else (0.35 if impulse_atr >= float(self.params.soft_warn_atr) else 0.7)

        continuation = 0.45
        range_prob = 0.35
        reversal = max(0.0, 1.0 - continuation - range_prob)
        ssum = max(continuation + reversal + range_prob, 1e-9)
        continuation /= ssum
        reversal /= ssum
        range_prob /= ssum

        adj_pack = self._apply_paths_adjustments(
            continuation=continuation,
            reversal=reversal,
            range_prob=range_prob,
            entry_quality=float(entry_quality),
            hard_no_chase=bool(hard_no_chase),
            bos=str(bos),
            choch=str(choch),
            rejection_type=None,
            vp_event_ids=vp_event_ids,
            evidence_map=ev_map,
        )
        base_paths = adj_pack["base_paths"]
        base_entry_quality = float(adj_pack["base_entry_quality"])
        final_paths = adj_pack["final_paths"]
        entry_quality = float(adj_pack["final_entry_quality"])

        next_actions = self._build_next_actions(
            hard_no_chase=bool(hard_no_chase),
            evidence_map=ev_map,
            paths=final_paths,
            state="IDLE",
            direction_bias="Neutral",
        )

        # pattern_workflows
        pattern_workflows: Dict[str, Any] = {}
        if cache.sweep_mem.pending and cache.sweep_mem.level is not None:
            b = _bars_since(now_bar_time, cache.sweep_mem.start_time) or 0
            pattern_workflows["sweep"] = {
                "active": True,
                "direction": cache.sweep_mem.direction,
                "level": float(cache.sweep_mem.level),
                "bars_elapsed": int(b),
                "max_exceed": float(cache.sweep_mem.max_exceed),
                "recover_window_bars": int(self.params.sweep_recover_window_bars),
                "bars_left": max(0, int(self.params.sweep_recover_window_bars) - int(b)),
                "status": cache.sweep_mem.last_status,
            }
        else:
            pattern_workflows["sweep"] = {"active": False}

        rm = cache.retest_mem
        if rm.active and rm.level is not None:
            bs = _bars_since(now_bar_time, rm.start_time) or 0
            bt = _bars_since(now_bar_time, rm.touch_time) if rm.touched else None
            pattern_workflows["retest"] = {
                "active": True,
                "key": rm.key,
                "direction": rm.direction,
                "level": float(rm.level),
                "touched": bool(rm.touched),
                "bars_since_break": int(bs),
                "bars_since_touch": (int(bt) if bt is not None else None),
                "retest_window_bars": int(self.params.retest_window_bars),
                "reclaim_window_bars": int(self.params.reclaim_window_bars),
                "retest_bars_left": max(0, int(self.params.retest_window_bars) - int(bs)),
                "reclaim_bars_left": (max(0, int(self.params.reclaim_window_bars) - int(bt)) if bt is not None else None),
                "status": rm.last_status,
            }
        else:
            pattern_workflows["retest"] = {"active": False}

        # evidence list (for AI stability / debug)
        evidence_list = [{"id": k, "weight": 0.5, "present": bool(v)} for k, v in sorted(ev_map.items())]

        # MTF（fast 模式用于回测/批处理：跳过额外历史查询，避免性能开销与跨进程 DuckDB 锁）
        if fast:
            mtf = {}
        else:
            mtf = {
                "m15": {
                    "timeframe": "M15",
                    "structure": structure_state_from_swings(detect_swings(historical_service.get_history(symbol, "M15", limit=800) or [])),
                },
                "m30": {
                    "timeframe": "M30",
                    "structure": structure_state_from_swings(detect_swings(historical_service.get_history(symbol, "M30", limit=800) or [])),
                },
            }

        phase = "Ranging" if struct_state == "Consolidation" else ("Trending" if primary != "Neutral" else "Ranging")

        snap_id = f"snap_{now_ts}_{hashlib.md5((symbol+str(now_ts)).encode()).hexdigest()[:6]}"

        scene: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "snapshot_id": snap_id,
            "ts_utc": int(now_ts),
            "ts_beijing": _fmt_beijing(int(now_ts)),
            "metadata": {"symbol": symbol, "timeframe": timeframe, "data_quality": {"tick_volume": "approx", "missing_bars": 0, "staleness_sec": max(0.0, float(_utc_now_ts() - int(now_ts)))}},
            "context": {"active_session": active_session, "market_phase": phase, "volatility": {"atr_14": float(atr14), "regime": "Normal", "atr_percentile_200": 50.0}},
            "price": {"last": {"o": float(last["open"]), "h": float(last["high"]), "l": float(last["low"]), "c": float(last["close"]), "v": float(last.get("tick_volume", 0) or 0), "time": int(last["time"])}, "microstructure": {"spread_points": 0.0}},
            "trend": {
                "primary": primary,
                "moving_averages": {"sma20": float(sma20), "sma50": float(sma50), "sma200": float(sma200), "alignment": alignment, "slope": {"sma20": slope_direction(closes[-40:], 10), "sma50": slope_direction(closes[-80:], 10)}},
                "structure": {"state": struct_state, "last_swings": [{"type": s.kind, "price": float(s.price), "time": int(s.time)} for s in swings], "bos": bos, "choch": choch, "structure_high": structure_high, "structure_low": structure_low, "break_buffer": float(break_buf)},
            },
            "momentum": {"rsi_14": {"value": float(rsi(closes, 14) or 50.0), "zone": "Neutral", "divergence": "None"}, "macd": {"state": "Neutral", "cross": "None", "histogram": "Shrinking"}},
            "mtf": mtf,
            "volume_profile": {"active_session": active_session, "sessionvp_options": {"daysToCalculate": int(self.params.vp_days_to_calculate), "bins": int(self.params.vp_bins), "valueAreaPct": float(self.params.vp_value_area_pct)}, "active_block": active_block, "derived": vp_pack.get("derived"), "events": vp_pack.get("events", [])},
            "patterns": patterns,
            "pattern_workflows": pattern_workflows,
            "poc_migration": {
                "state": "IDLE",
                "direction_bias": "Neutral",
                "poc_zone": {"low": float(poc - poc_zone_w), "high": float(poc + poc_zone_w)},
                "distance_to_poc_atr": float(abs(close - poc) / max(atr14, 1e-9) if atr14 > 0 else 0.0),
                "impulse_atr": float(impulse_atr),
                "rejection": {"present": False, "type": None, "notes": ""},
                "evidence": evidence_list,
                "scores": {"migration": 0.0, "reversion": 0.0, "entry_quality": float(entry_quality), "no_chase": bool(hard_no_chase)},
                "paths": final_paths,
                "paths_explain": {"base_paths": base_paths, "final_paths": final_paths, "adjustments": adj_pack.get("adjustments", []), "base_entry_quality": float(base_entry_quality), "final_entry_quality": float(entry_quality)},
                "next_actions": next_actions,
            },
            "ai_controls": {"update_type": "FULL", "diff_from": None, "state_hash": ""},
        }
        scene["ai_controls"]["state_hash"] = _hash_state(scene)

        cache.prev_scene = cache.last_scene
        cache.prev_scene_id = cache.last_scene_id
        cache.last_scene = copy.deepcopy(scene)
        cache.last_scene_id = scene["snapshot_id"]
        cache.last_bar_time = int(last["time"])

        sid = str(scene["snapshot_id"])
        cache.snapshots_by_id[sid] = copy.deepcopy(scene)
        cache.snapshots_order.append(sid)
        if len(cache.snapshots_order) > int(cache.max_snapshots):
            old = cache.snapshots_order.pop(0)
            cache.snapshots_by_id.pop(old, None)

        return scene

    def build_latest(self, symbol: str, timeframe: str = "M1") -> Dict[str, Any]:
        bars = historical_service.get_history(symbol, timeframe, limit=3000)
        return self.build_from_bars(symbol, timeframe, bars, fast=False)

    def diff_since(self, symbol: str, timeframe: str, since_snapshot_id: str) -> Dict[str, Any]:
        cache = self._cache_for(symbol, timeframe)
        if cache.last_scene is None:
            return {"ok": False, "message": "no scene yet"}
        base = cache.snapshots_by_id.get(str(since_snapshot_id))
        if base is None:
            out = copy.deepcopy(cache.last_scene)
            out["ai_controls"]["update_type"] = "FULL"
            out["ai_controls"]["diff_from"] = None
            return {"ok": True, "update_type": "FULL", "scene": out, "diff": []}
        diff = _dict_diff(base, cache.last_scene or {})
        return {"ok": True, "update_type": "DIFF", "diff_from": str(since_snapshot_id), "snapshot_id": cache.last_scene_id, "state_hash": cache.last_scene.get("ai_controls", {}).get("state_hash"), "diff": diff}


scene_engine = ChartSceneEngine()
