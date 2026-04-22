from __future__ import annotations

import csv
import json
import os
import zipfile
import statistics
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from backend.database.app_config import app_config
from backend.services.chart_scene.scene_engine import ChartSceneEngine
from backend.services.chart_scene.scene_params import SceneParams
from backend.services.historical import historical_service


def _report_dir() -> str:
    # 存在用户配置目录：~/.config/AwesomeChart/data/reports
    p = os.path.join(app_config.get_base_dir(), "reports")
    os.makedirs(p, exist_ok=True)
    return p


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return (b - a) / a


def _window_slice(bars: List[Dict[str, Any]], i: int, max_len: int) -> List[Dict[str, Any]]:
    lo = max(0, i - max_len + 1)
    return bars[lo : i + 1]


def _quantiles(xs: List[float]) -> Dict[str, Optional[float]]:
    if not xs:
        return {"p25": None, "p50": None, "p75": None, "mean": None}
    xs2 = sorted(xs)
    return {
        "p25": float(xs2[int(0.25 * (len(xs2) - 1))]),
        "p50": float(xs2[int(0.50 * (len(xs2) - 1))]),
        "p75": float(xs2[int(0.75 * (len(xs2) - 1))]),
        "mean": float(sum(xs2) / len(xs2)),
    }


def run_event_study(
    *,
    symbol: str,
    timeframe: str,
    limit: int,
    horizons: List[int],
    event_ids: List[str],
    engine_params: Optional[Dict[str, Any]] = None,
    mode: str = "any",  # any | all
    fast: bool = True,
    update_cb=None,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    事件研究（MVP）：
    - 使用 ChartSceneEngine 在滚动窗口上生成 scene
    - 当 scene 中出现指定事件（volume_profile.events[].id）则记录样本
    - 计算未来 N bars 的收益、MFE、MAE
    """

    t0 = time.time()
    bars = historical_service.get_history(symbol, timeframe, limit=int(limit))
    if not bars or len(bars) < max(200, max(horizons) + 10):
        raise RuntimeError(f"bars not enough for {symbol} {timeframe}, got={len(bars) if bars else 0}")

    # 独立引擎（不污染实时 runtime）
    engine = ChartSceneEngine()
    if engine_params:
        # 覆盖部分参数
        p = SceneParams.from_env()
        for k, v in engine_params.items():
            if hasattr(p, k):
                setattr(p, k, v)
        engine.params = p

    horizons = sorted(set(int(x) for x in horizons if int(x) > 0))
    event_ids_set = set(str(x) for x in event_ids)
    need_all = str(mode).lower() == "all"

    samples: List[Dict[str, Any]] = []
    max_len = 3000
    warmup = 260  # SMA/VP 等需要一定长度

    for i in range(warmup, len(bars) - max(horizons) - 1):
        if update_cb and (i % 200 == 0):
            update_cb(i / max(1, len(bars)))

        window = _window_slice(bars, i, max_len)
        # 回测/批处理：fast 模式可跳过部分重计算以提升速度
        scene = engine.build_from_bars(symbol, timeframe, window, fast=bool(fast))
        events = (scene.get("volume_profile") or {}).get("events") or []
        ids = [str(e.get("id")) for e in events if isinstance(e, dict) and e.get("id")]
        idset = set(ids)
        triggered = (event_ids_set & idset)
        ok = False
        if need_all:
            ok = event_ids_set.issubset(idset) if event_ids_set else False
        else:
            ok = bool(triggered)
        if not ok:
            continue

        bar0 = bars[i]
        t_bar = int(bar0["time"])
        c0 = _safe_float(bar0["close"])

        # 未来窗口数据
        for h in horizons:
            j = i + h
            if j >= len(bars):
                continue
            seg = bars[i + 1 : j + 1]
            if not seg:
                continue
            ch = _safe_float(bars[j]["close"])
            highs = [_safe_float(b.get("high")) for b in seg]
            lows = [_safe_float(b.get("low")) for b in seg]
            mfe = (max(highs) - c0) if highs else 0.0
            mae = (min(lows) - c0) if lows else 0.0

            samples.append(
                {
                    "time": t_bar,
                    "horizon": int(h),
                    "close0": c0,
                    "close_h": ch,
                    "ret": _pct_change(c0, ch),
                    "mfe": mfe,
                    "mae": mae,
                    "triggered": sorted(triggered) if triggered else ids[:5],
                }
            )

    # 汇总
    rets = [float(s["ret"]) for s in samples]
    mfes = [float(s["mfe"]) for s in samples]
    maes = [float(s["mae"]) for s in samples]
    winrate = (sum(1 for r in rets if r > 0) / len(rets)) if rets else 0.0

    summary = {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars_used": len(bars),
        "events": event_ids,
        "mode": mode,
        "horizons": horizons,
        "samples": len(samples),
        "winrate": float(winrate),
        "ret": _quantiles(rets),
        "mfe": _quantiles(mfes),
        "mae": _quantiles(maes),
        "engine_params": engine.params.to_dict() if hasattr(engine, "params") else None,
        "fast": bool(fast),
        "elapsed_sec": round(time.time() - t0, 3),
    }

    # 输出文件
    rid = f"event_study_{symbol}_{timeframe}_{int(time.time())}"
    base = _report_dir()
    json_path = os.path.join(base, f"{rid}.json")
    csv_path = os.path.join(base, f"{rid}.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "samples": samples}, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(samples[0].keys()) if samples else ["time", "horizon", "ret", "mfe", "mae", "triggered"])
        w.writeheader()
        for s in samples:
            row = dict(s)
            row["triggered"] = "|".join(row.get("triggered") or [])
            w.writerow(row)

    zip_path = os.path.join(base, f"{rid}.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(json_path, arcname=os.path.basename(json_path))
        z.write(csv_path, arcname=os.path.basename(csv_path))

    return summary, {"json": json_path, "csv": csv_path, "zip": zip_path}
