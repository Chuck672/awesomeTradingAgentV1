from __future__ import annotations

import csv
import json
import os
import zipfile
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.database.app_config import app_config
from backend.services.chart_scene.scene_engine import ChartSceneEngine
from backend.services.chart_scene.scene_params import SceneParams
from backend.services.historical import historical_service


def _report_dir() -> str:
    p = os.path.join(app_config.get_base_dir(), "reports")
    os.makedirs(p, exist_ok=True)
    return p


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _max_drawdown(equity: List[float]) -> float:
    peak = 1.0
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        mdd = max(mdd, dd)
    return float(mdd)


def run_strategy_backtest(
    *,
    symbol: str,
    timeframe: str,
    limit: int,
    long_event_ids: Optional[List[str]] = None,
    short_event_ids: Optional[List[str]] = None,
    hold_bars: int,
    atr_stop_mult: float,
    atr_tp_mult: float,
    engine_params: Optional[Dict[str, Any]] = None,
    fast: bool = True,
    update_cb=None,  # fn(progress: float, stats: dict)
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    MVP 策略回测（事件驱动）：
    - 信号：由 long_event_ids / short_event_ids 决定
    - 入场：信号 bar 收盘价
    - 出场：先触发 SL/TP；若 hold_bars > 0 则启用超时出场（收盘）
    """

    t0 = time.time()
    bars = historical_service.get_history(symbol, timeframe, limit=int(limit))
    if not bars or len(bars) < 400:
        raise RuntimeError(f"bars not enough for {symbol} {timeframe}, got={len(bars) if bars else 0}")

    engine = ChartSceneEngine()
    if engine_params:
        p = SceneParams.from_env()
        for k, v in engine_params.items():
            if hasattr(p, k):
                setattr(p, k, v)
        engine.params = p
    warmup = 260
    max_len = 3000

    trades: List[Dict[str, Any]] = []
    equity: List[float] = [1.0]

    pos = None  # {dir, entry_time, entry_price, stop, tp, entry_i}
    long_ids = set(str(x) for x in (long_event_ids or ["liquidity_sweep_down_recover"]))
    short_ids = set(str(x) for x in (short_event_ids or ["liquidity_sweep_up_recover"]))

    total = len(bars)
    last_trade_note: Optional[str] = None

    for i in range(warmup, len(bars) - 2):
        if update_cb and (i % 150 == 0):
            p = i / max(1, total)
            stats = {
                "bars_processed": i,
                "bars_total": total,
                "trades": len(trades),
                "has_position": bool(pos),
                "last_time": int(bars[i]["time"]),
                "last_trade": last_trade_note,
            }
            try:
                update_cb(p, stats)
            except TypeError:
                update_cb(p)

        window = bars[max(0, i - max_len + 1) : i + 1]
        scene = engine.build_from_bars(symbol, timeframe, window, fast=bool(fast))
        events = (scene.get("volume_profile") or {}).get("events") or []
        ids = set(str(e.get("id")) for e in events if isinstance(e, dict) and e.get("id"))

        bar = bars[i]
        t_bar = int(bar["time"])
        o = _safe_float(bar.get("open"))
        h = _safe_float(bar.get("high"))
        l = _safe_float(bar.get("low"))
        c = _safe_float(bar.get("close"))
        atr = _safe_float(((scene.get("volatility") or {}).get("atr_14") or 0.0), 0.0)
        if atr <= 0:
            atr = max(1e-6, abs(h - l))

        # 管理持仓：检查止损/止盈/（可选）超时
        if pos is not None:
            dirn = pos["dir"]
            stop = float(pos["stop"])
            tp = float(pos["tp"])
            entry_price = float(pos["entry_price"])
            entry_i = int(pos["entry_i"])

            exit_reason = None
            exit_price = None

            # 同一根 bar 内同时触发时，保守处理：先止损
            if dirn == "LONG":
                if l <= stop:
                    exit_reason = "stop"
                    exit_price = stop
                elif h >= tp:
                    exit_reason = "tp"
                    exit_price = tp
            else:
                if h >= stop:
                    exit_reason = "stop"
                    exit_price = stop
                elif l <= tp:
                    exit_reason = "tp"
                    exit_price = tp

            if exit_reason is None and int(hold_bars) > 0 and (i - entry_i) >= int(hold_bars):
                exit_reason = "timeout"
                exit_price = c

            if exit_reason is not None and exit_price is not None:
                pnl = (exit_price - entry_price) if dirn == "LONG" else (entry_price - exit_price)
                pnl_pct = pnl / entry_price if entry_price != 0 else 0.0
                last_trade_note = f"exit {dirn} {exit_reason} pnl_pct={pnl_pct:.4f}"
                trades.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "dir": dirn,
                        "entry_time": int(pos["entry_time"]),
                        "exit_time": t_bar,
                        "entry": entry_price,
                        "exit": float(exit_price),
                        "stop": float(stop),
                        "tp": float(tp),
                        "pnl": float(pnl),
                        "pnl_pct": float(pnl_pct),
                        "reason": exit_reason,
                        "hold_bars": int(i - entry_i),
                    }
                )
                equity.append(equity[-1] * (1.0 + pnl_pct))
                pos = None

        # 开仓：仅在无持仓时
        if pos is None:
            if ids & long_ids:
                entry = c
                pos = {
                    "dir": "LONG",
                    "entry_time": t_bar,
                    "entry_price": entry,
                    "stop": entry - float(atr_stop_mult) * atr,
                    "tp": entry + float(atr_tp_mult) * atr,
                    "entry_i": i,
                }
                last_trade_note = f"enter LONG ({next(iter(ids & long_ids))})"
            elif ids & short_ids:
                entry = c
                pos = {
                    "dir": "SHORT",
                    "entry_time": t_bar,
                    "entry_price": entry,
                    "stop": entry + float(atr_stop_mult) * atr,
                    "tp": entry - float(atr_tp_mult) * atr,
                    "entry_i": i,
                }
                last_trade_note = f"enter SHORT ({next(iter(ids & short_ids))})"

    # 汇总指标
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    gross_win = sum(float(t["pnl"]) for t in wins)
    gross_loss = -sum(float(t["pnl"]) for t in losses)  # positive
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None
    winrate = (len(wins) / len(trades)) if trades else 0.0
    total_ret = equity[-1] - 1.0
    mdd = _max_drawdown(equity)

    summary = {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars_used": len(bars),
        "limit": int(limit),
        "trades": len(trades),
        "winrate": float(winrate),
        "profit_factor": float(profit_factor) if profit_factor is not None else None,
        "total_return": float(total_ret),
        "max_drawdown": float(mdd),
        "params": {
            "hold_bars": int(hold_bars),
            "atr_stop_mult": float(atr_stop_mult),
            "atr_tp_mult": float(atr_tp_mult),
            "engine_params": engine_params or {},
            "fast": bool(fast),
        },
        "elapsed_sec": round(time.time() - t0, 3),
    }

    rid = f"strategy_bt_{symbol}_{timeframe}_{int(time.time())}"
    base = _report_dir()
    json_path = os.path.join(base, f"{rid}.json")
    trades_csv = os.path.join(base, f"{rid}_trades.csv")
    equity_csv = os.path.join(base, f"{rid}_equity.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "trades": trades, "equity": equity}, f, ensure_ascii=False, indent=2)

    with open(trades_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "timeframe",
                "dir",
                "entry_time",
                "exit_time",
                "entry",
                "exit",
                "stop",
                "tp",
                "pnl",
                "pnl_pct",
                "reason",
                "hold_bars",
            ],
        )
        w.writeheader()
        for t in trades:
            w.writerow(t)

    with open(equity_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["step", "equity"])
        for i, v in enumerate(equity):
            w.writerow([i, v])

    zip_path = os.path.join(base, f"{rid}.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(json_path, arcname=os.path.basename(json_path))
        z.write(trades_csv, arcname=os.path.basename(trades_csv))
        z.write(equity_csv, arcname=os.path.basename(equity_csv))

    return summary, {"json": json_path, "trades_csv": trades_csv, "equity_csv": equity_csv, "zip": zip_path}
