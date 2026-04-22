from __future__ import annotations

import csv
import json
import os
import random
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from backend.database.app_config import app_config
from backend.services.research.strategy_backtest import run_strategy_backtest


def _report_dir() -> str:
    p = os.path.join(app_config.get_base_dir(), "reports")
    os.makedirs(p, exist_ok=True)
    return p


def _objective(summary: Dict[str, Any]) -> float:
    """
    MVP 目标函数（越大越好）：
    - 主要：total_return
    - 惩罚：max_drawdown
    - 惩罚：trades 太少
    """
    tr = float(summary.get("total_return") or 0.0)
    dd = float(summary.get("max_drawdown") or 0.0)
    trades = int(summary.get("trades") or 0)
    score = tr - 0.7 * dd
    if trades < 5:
        score -= 0.2
    return float(score)


def run_optimize(
    *,
    symbol: str,
    timeframe: str,
    limit: int,
    trials: int,
    seed: int = 7,
    fast: bool = True,
    long_event_ids: Optional[List[str]] = None,
    short_event_ids: Optional[List[str]] = None,
    update_cb=None,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    MVP 循环优化：
    - 随机搜索 SceneParams（sweep 相关）+ 策略参数（hold/SL/TP）
    - 对每组参数跑一次 strategy-backtest
    """
    t0 = time.time()
    rng = random.Random(int(seed))

    # 搜索空间（先用可解释参数，后续再扩展到更多阈值/路径系数）
    space = {
        "sweep_recover_window_bars": [6, 10, 14, 18],
        "sweep_min_reclaim_pct_of_range": [0.25, 0.35, 0.45],
        "break_buffer_atr_mult": [0.05, 0.1, 0.15],
        "hold_bars": [20, 30, 40, 60] if timeframe != "M1" else [40, 60, 90, 120],
        "atr_stop_mult": [1.5, 2.0, 2.5],
        "atr_tp_mult": [2.5, 3.0, 3.5],
    }

    history: List[Dict[str, Any]] = []
    best = None

    for k in range(int(trials)):
        if update_cb:
            try:
                update_cb(k / max(1, trials), {"trial": int(k), "trials": int(trials), "best_score": (best.get("score") if best else None)})
            except TypeError:
                update_cb(k / max(1, trials))

        engine_params = {
            "sweep_recover_window_bars": rng.choice(space["sweep_recover_window_bars"]),
            "sweep_min_reclaim_pct_of_range": rng.choice(space["sweep_min_reclaim_pct_of_range"]),
            "break_buffer_atr_mult": rng.choice(space["break_buffer_atr_mult"]),
        }
        hold_bars = int(rng.choice(space["hold_bars"]))
        atr_stop_mult = float(rng.choice(space["atr_stop_mult"]))
        atr_tp_mult = float(rng.choice(space["atr_tp_mult"]))

        summary, _files = run_strategy_backtest(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            long_event_ids=long_event_ids,
            short_event_ids=short_event_ids,
            hold_bars=hold_bars,
            atr_stop_mult=atr_stop_mult,
            atr_tp_mult=atr_tp_mult,
            engine_params=engine_params,
            fast=bool(fast),
            update_cb=None,
        )
        score = _objective(summary)
        rec = {
            "trial": k,
            "score": score,
            "total_return": summary.get("total_return"),
            "max_drawdown": summary.get("max_drawdown"),
            "profit_factor": summary.get("profit_factor"),
            "trades": summary.get("trades"),
            "hold_bars": hold_bars,
            "atr_stop_mult": atr_stop_mult,
            "atr_tp_mult": atr_tp_mult,
            **engine_params,
        }
        history.append(rec)
        if best is None or score > float(best["score"]):
            best = dict(rec)

    out = {
        "symbol": symbol,
        "timeframe": timeframe,
        "limit": int(limit),
        "trials": int(trials),
        "seed": int(seed),
        "fast": bool(fast),
        "strategy": {"long_event_ids": long_event_ids or [], "short_event_ids": short_event_ids or []},
        "best": best,
        "elapsed_sec": round(time.time() - t0, 3),
    }

    rid = f"optimize_{symbol}_{timeframe}_{int(time.time())}"
    base = _report_dir()
    json_path = os.path.join(base, f"{rid}.json")
    csv_path = os.path.join(base, f"{rid}.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": out, "history": history}, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        cols = list(history[0].keys()) if history else ["trial", "score"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in history:
            w.writerow(r)

    zip_path = os.path.join(base, f"{rid}.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(json_path, arcname=os.path.basename(json_path))
        z.write(csv_path, arcname=os.path.basename(csv_path))

    return out, {"json": json_path, "csv": csv_path, "zip": zip_path}
