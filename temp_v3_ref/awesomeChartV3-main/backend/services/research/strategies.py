from __future__ import annotations

from typing import Any, Dict, List, Optional


def list_strategies() -> List[Dict[str, Any]]:
    """
    MVP：策略注册表（可在前端下拉选择）。
    说明：这里的策略都是“事件驱动”，信号来自 ChartScene 的 volume_profile.events[].id。
    """
    return [
        {
            "id": "sweep_recover_reversal",
            "name": "Sweep Recover Reversal",
            "description": "liquidity sweep 回收后的反转（适合 M1/M5，M15+ 可能信号偏少）",
            "long_event_ids": ["liquidity_sweep_down_recover"],
            "short_event_ids": ["liquidity_sweep_up_recover"],
            # 默认不做 timeout（hold_bars=0），仅由 SL/TP 出场；用户可在前端手动设置 hold_bars 启用超时
            "default_params": {"hold_bars": 0, "atr_stop_mult": 2.0, "atr_tp_mult": 3.0},
            "default_engine_params": {},
        },
        {
            "id": "sweep_detected_reversal",
            "name": "Sweep Detected Reversal",
            "description": "sweep 刺破刚发生就逆向入场（信号更频繁，适合 M15/M30 做最小可用闭环）",
            "long_event_ids": ["sweep_down_detected"],
            "short_event_ids": ["sweep_up_detected"],
            "default_params": {"hold_bars": 0, "atr_stop_mult": 1.8, "atr_tp_mult": 2.2},
            "default_engine_params": {"sweep_recover_window_bars": 18, "sweep_min_reclaim_pct_of_range": 0.25},
        },
        {
            "id": "reclaim_continuation",
            "name": "Reclaim Continuation",
            "description": "结构点 breakout→retest→reclaim 确认后的顺势延续（更适合 M15/M30/H1）",
            "long_event_ids": ["reclaim_struct_high_confirmed"],
            "short_event_ids": ["reclaim_struct_low_confirmed"],
            "default_params": {"hold_bars": 0, "atr_stop_mult": 2.0, "atr_tp_mult": 3.0},
            "default_engine_params": {"retest_window_bars": 16, "reclaim_window_bars": 8},
        },
    ]


def get_strategy_by_id(strategy_id: str) -> Optional[Dict[str, Any]]:
    sid = str(strategy_id or "")
    for s in list_strategies():
        if s.get("id") == sid:
            return s
    return None
