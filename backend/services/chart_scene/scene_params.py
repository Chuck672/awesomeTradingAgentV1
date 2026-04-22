from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except Exception:
        return float(default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except Exception:
        return int(default)


@dataclass
class SceneParams:
    """
    ChartScene 的核心参数集中管理（便于调参/回放/一致性）。
    规则：优先从环境变量读取，便于本地调试与多实例。
    """

    # SessionVP（与前端一致）
    vp_days_to_calculate: int = 5
    # 前端 defaultSessionVPOptions.bins = 70
    vp_bins: int = 70
    vp_value_area_pct: float = 70.0

    # POC zone 与迁移状态机
    poc_zone_width_atr: float = 0.25
    acceptance_window_bars: int = 12
    acceptance_max_reversions: int = 2
    rejection_window_bars: int = 6

    # sweep（两阶段 + 回收窗口）
    sweep_recover_window_bars: int = 5

    # HVN/LVN 派生阈值（基于 maxVolume 比例）
    hvn_threshold_ratio: float = 0.7
    lvn_threshold_ratio: float = 0.2

    # HVN 事件窗口
    hvn_leave_window_bars: int = 12
    hvn_leave_max_inside: int = 2
    new_hvn_window_bars: int = 12
    new_hvn_min_inside: int = 10

    # 追单风控
    hard_no_chase_atr: float = 2.0
    soft_warn_atr: float = 1.5

    # 结构点破位缓冲（ATR 比例，最终 buffer=max(break_buf_atr*ATR, 1e-9)）
    break_buffer_atr: float = 0.05

    # 蜡烛形态过滤：实体最小占 ATR（避免 M1 噪音）
    candle_min_body_atr: float = 0.1

    # VAH/VAL 更严格规则
    va_break_confirm_bars: int = 1
    va_fakeout_window_bars: int = 3

    # breakout -> retest -> reclaim/hold（通用窗口）
    retest_window_bars: int = 12
    reclaim_window_bars: int = 6

    @staticmethod
    def from_env() -> "SceneParams":
        p = SceneParams()
        p.vp_days_to_calculate = _env_int("AITRADER_VP_DAYS", p.vp_days_to_calculate)
        p.vp_bins = _env_int("AITRADER_VP_BINS", p.vp_bins)
        p.vp_value_area_pct = _env_float("AITRADER_VP_VA_PCT", p.vp_value_area_pct)

        p.poc_zone_width_atr = _env_float("AITRADER_POC_ZONE_ATR", p.poc_zone_width_atr)
        p.acceptance_window_bars = _env_int("AITRADER_ACCEPT_WIN", p.acceptance_window_bars)
        p.acceptance_max_reversions = _env_int("AITRADER_ACCEPT_MAX_REV", p.acceptance_max_reversions)
        p.rejection_window_bars = _env_int("AITRADER_REJECT_WIN", p.rejection_window_bars)

        p.sweep_recover_window_bars = _env_int("AITRADER_SWEEP_RECOVER_WIN", p.sweep_recover_window_bars)

        p.hvn_threshold_ratio = _env_float("AITRADER_HVN_THR", p.hvn_threshold_ratio)
        p.lvn_threshold_ratio = _env_float("AITRADER_LVN_THR", p.lvn_threshold_ratio)
        p.hvn_leave_window_bars = _env_int("AITRADER_HVN_LEAVE_WIN", p.hvn_leave_window_bars)
        p.hvn_leave_max_inside = _env_int("AITRADER_HVN_LEAVE_MAX_IN", p.hvn_leave_max_inside)
        p.new_hvn_window_bars = _env_int("AITRADER_NEW_HVN_WIN", p.new_hvn_window_bars)
        p.new_hvn_min_inside = _env_int("AITRADER_NEW_HVN_MIN_IN", p.new_hvn_min_inside)

        p.hard_no_chase_atr = _env_float("AITRADER_NOCHASE_ATR", p.hard_no_chase_atr)
        p.soft_warn_atr = _env_float("AITRADER_WARN_ATR", p.soft_warn_atr)

        p.break_buffer_atr = _env_float("AITRADER_BREAKBUF_ATR", p.break_buffer_atr)
        p.candle_min_body_atr = _env_float("AITRADER_CANDLE_MIN_BODY_ATR", p.candle_min_body_atr)
        p.va_break_confirm_bars = _env_int("AITRADER_VA_BREAK_CONFIRM", p.va_break_confirm_bars)
        p.va_fakeout_window_bars = _env_int("AITRADER_VA_FAKEOUT_WIN", p.va_fakeout_window_bars)
        p.retest_window_bars = _env_int("AITRADER_RETEST_WIN", p.retest_window_bars)
        p.reclaim_window_bars = _env_int("AITRADER_RECLAIM_WIN", p.reclaim_window_bars)
        return p

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
