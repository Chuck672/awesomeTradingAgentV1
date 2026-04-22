from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from backend.services.historical import historical_service


def _timeframe_to_limit_bars(timeframe: str, lookback_bars: int) -> int:
    # 简单映射：为了避免一次拉太多，这里直接用 lookback_bars
    return int(max(100, min(20000, lookback_bars)))


def tool_data_load_bars(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload:
      symbols: [str]
      primary_timeframe: str
      higher_timeframes: [str]
      history_lookback_bars: int
      bars_override?: { timeframe: [bars] } 或 { "primary": [bars] }
    returns:
      bars_by_tf: {tf: [bars]}
    """
    symbols = payload.get("symbols") or []
    primary_tf = payload.get("primary_timeframe") or "30m"
    higher_tfs = payload.get("higher_timeframes") or []
    lookback = int(payload.get("history_lookback_bars") or 500)

    bars_override = payload.get("bars_override")
    if isinstance(bars_override, dict) and bars_override:
        # normalize key: allow "primary"
        out: Dict[str, Any] = {}
        for k, v in bars_override.items():
            tf = primary_tf if k == "primary" else str(k)
            if isinstance(v, list):
                out[tf] = v
        if primary_tf not in out and isinstance(bars_override.get("primary"), list):
            out[primary_tf] = bars_override["primary"]
        return {"bars_by_tf": out}

    # 仅支持单 symbol（当前 IR 也是按单 symbol 规划；多 symbol 扩展后再做）
    sym = symbols[0] if symbols else "XAUUSDz"
    out: Dict[str, List[Dict[str, Any]]] = {}

    # primary
    out[str(primary_tf)] = historical_service.get_history(sym, str(primary_tf), before_time=0, limit=_timeframe_to_limit_bars(str(primary_tf), lookback))
    # higher tfs
    for tf in higher_tfs:
        tfs = str(tf)
        out[tfs] = historical_service.get_history(sym, tfs, before_time=0, limit=_timeframe_to_limit_bars(tfs, lookback))

    return {"bars_by_tf": out}

