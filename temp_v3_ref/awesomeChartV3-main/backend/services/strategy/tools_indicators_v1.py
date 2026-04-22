from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


def _df_from_bars(bars: List[Dict[str, Any]]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume", "delta_volume"])
    df = pd.DataFrame(bars)
    # ensure numeric
    for c in ["open", "high", "low", "close", "tick_volume", "delta_volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "time" in df.columns:
        df["time"] = pd.to_numeric(df["time"], errors="coerce").astype("Int64")
    return df


def _ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=int(period), adjust=False).mean()


def _sma(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(int(period)).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h = df["high"]
    l = df["low"]
    c = df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(int(period)).mean()


def _rsi(s: pd.Series, period: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(int(period)).mean()
    loss = (-delta.clip(upper=0)).rolling(int(period)).mean()
    rs = gain / (loss.replace(0, np.nan))
    return 100 - (100 / (1 + rs))


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h = df["high"]
    l = df["low"]
    c = df["close"]
    up = h.diff()
    down = -l.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([(h - l).abs(), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(int(period)).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(int(period)).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(int(period)).mean() / atr.replace(0, np.nan))
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(np.nan)
    adx = dx.rolling(int(period)).mean()
    return adx


def _vwap(df: pd.DataFrame) -> pd.Series:
    # 简化：用 tick_volume；若无则用 delta_volume；再无则 1
    vol = df["tick_volume"] if "tick_volume" in df.columns else None
    if vol is None or vol.isna().all():
        vol = df["delta_volume"] if "delta_volume" in df.columns else None
    if vol is None:
        vol = pd.Series(1.0, index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_vol = vol.fillna(0).cumsum().replace(0, np.nan)
    return (tp * vol.fillna(0)).cumsum() / cum_vol


def _bb(df: pd.DataFrame, period: int = 20, mult: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid = _sma(df["close"], period)
    std = df["close"].rolling(int(period)).std()
    upper = mid + float(mult) * std
    lower = mid - float(mult) * std
    return lower, mid, upper


def _kc(df: pd.DataFrame, period: int = 20, mult: float = 1.5, atr_period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid = _ema(df["close"], period)
    a = _atr(df, atr_period)
    upper = mid + float(mult) * a
    lower = mid - float(mult) * a
    return lower, mid, upper


def tool_indicator_compute_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload:
      bars_by_tf: {tf: [bars]}
      decls: [IndicatorDecl-like dicts]
    returns:
      series: {id: {name,timeframe,values:[...], last:float|null, meta:{...}}}
    """
    bars_by_tf = payload.get("bars_by_tf") or {}
    decls = payload.get("decls") or []
    out: Dict[str, Any] = {}

    for d in decls:
        if not isinstance(d, dict):
            continue
        ind_id = str(d.get("id") or "")
        name = str(d.get("name") or "").strip().lower()
        tf = str(d.get("timeframe") or "30m")
        params = d.get("params") if isinstance(d.get("params"), dict) else {}
        if not ind_id or not name:
            continue

        bars = bars_by_tf.get(tf) if isinstance(bars_by_tf, dict) else None
        if not isinstance(bars, list) or not bars:
            out[ind_id] = {"id": ind_id, "name": name, "timeframe": tf, "values": [], "last": None, "meta": {"error": f"no bars for timeframe {tf}"}}
            continue

        df = _df_from_bars(bars)
        if df.empty:
            out[ind_id] = {"id": ind_id, "name": name, "timeframe": tf, "values": [], "last": None, "meta": {"error": "empty bars"}}
            continue

        values: List[float] = []
        meta: Dict[str, Any] = {"params": params}

        try:
            if name == "sma":
                period = int(params.get("period") or 20)
                s = _sma(df["close"], period)
                values = [None if pd.isna(x) else float(x) for x in s.tolist()]  # type: ignore
            elif name == "ema":
                period = int(params.get("period") or 20)
                s = _ema(df["close"], period)
                values = [None if pd.isna(x) else float(x) for x in s.tolist()]  # type: ignore
            elif name == "atr":
                period = int(params.get("period") or 14)
                s = _atr(df, period)
                values = [None if pd.isna(x) else float(x) for x in s.tolist()]  # type: ignore
            elif name == "rsi":
                period = int(params.get("period") or 14)
                s = _rsi(df["close"], period)
                values = [None if pd.isna(x) else float(x) for x in s.tolist()]  # type: ignore
            elif name == "adx":
                period = int(params.get("period") or 14)
                s = _adx(df, period)
                values = [None if pd.isna(x) else float(x) for x in s.tolist()]  # type: ignore
            elif name == "vwap":
                s = _vwap(df)
                values = [None if pd.isna(x) else float(x) for x in s.tolist()]  # type: ignore
            elif name in ("bb", "bollinger", "bollinger_bands"):
                period = int(params.get("period") or 20)
                mult = float(params.get("mult") or 2.0)
                lower, mid, upper = _bb(df, period, mult)
                meta["bands"] = {
                    "lower": [None if pd.isna(x) else float(x) for x in lower.tolist()],
                    "mid": [None if pd.isna(x) else float(x) for x in mid.tolist()],
                    "upper": [None if pd.isna(x) else float(x) for x in upper.tolist()],
                }
                values = meta["bands"]["mid"]
            elif name in ("kc", "keltner", "keltner_channels"):
                period = int(params.get("period") or 20)
                mult = float(params.get("mult") or 1.5)
                atr_period = int(params.get("atr_period") or 14)
                lower, mid, upper = _kc(df, period, mult, atr_period)
                meta["bands"] = {
                    "lower": [None if pd.isna(x) else float(x) for x in lower.tolist()],
                    "mid": [None if pd.isna(x) else float(x) for x in mid.tolist()],
                    "upper": [None if pd.isna(x) else float(x) for x in upper.tolist()],
                }
                values = meta["bands"]["mid"]
            else:
                out[ind_id] = {"id": ind_id, "name": name, "timeframe": tf, "values": [], "last": None, "meta": {"error": f"unknown indicator: {name}"}}
                continue
        except Exception as e:
            out[ind_id] = {"id": ind_id, "name": name, "timeframe": tf, "values": [], "last": None, "meta": {"error": str(e), "params": params}}
            continue

        last = None
        for x in reversed(values):
            if x is not None:
                last = x
                break

        out[ind_id] = {"id": ind_id, "name": name, "timeframe": tf, "values": values, "last": last, "meta": meta}

    return {"series": out}

