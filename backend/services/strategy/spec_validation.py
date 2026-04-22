from __future__ import annotations

from typing import Any, Dict, List, Optional


def validate_strategy_spec(spec: Dict[str, Any], *, prev_spec: Optional[Dict[str, Any]] = None, default_source: str = "system_default") -> Dict[str, Any]:
    """
    Stage1 用：对 StrategySpec 做 schema 校验 + 默认值来源标注（MVP 版）。

    说明：
    - 当前系统的编译器/扫描器 MVP 仅支持 breakout 类策略，因此这里先做 breakout 相关字段校验。
    - 返回 normalized_spec 以便前端可选择“应用规范化”。
    """
    spec = spec if isinstance(spec, dict) else {}

    errors: List[Dict[str, Any]] = []
    defaults_applied: List[Dict[str, Any]] = []
    prev_spec = prev_spec if isinstance(prev_spec, dict) else None

    def _err(path: str, message: str, severity: str = "error"):
        errors.append({"path": path, "message": message, "severity": severity})

    def _default(path: str, value: Any, source: str = "system_default"):
        defaults_applied.append({"path": path, "value": value, "source": source})

    def _prev(path: str) -> Any:
        if not prev_spec:
            return None
        cur: Any = prev_spec
        for seg in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(seg)
        return cur

    # ---- normalize with defaults (do not mutate original) ----
    out: Dict[str, Any] = {**spec}

    # spec_version
    if not out.get("spec_version"):
        out["spec_version"] = "1.0"
        _default("spec_version", "1.0")
    if not isinstance(out.get("spec_version"), str):
        _err("spec_version", "必须为 string")

    # universe.symbols
    uni = out.get("universe")
    if not isinstance(uni, dict):
        uni = {}
        out["universe"] = uni
        _default("universe", {}, "system_default")
    symbols = uni.get("symbols")
    if symbols is None:
        uni["symbols"] = []
        _default("universe.symbols", [])
        symbols = []
    if not isinstance(symbols, list):
        _err("universe.symbols", "必须为 string[]")
        uni["symbols"] = []
        symbols = []
    else:
        uni["symbols"] = [str(s).strip() for s in symbols if str(s).strip()]

    # timeframes
    tfs = out.get("timeframes")
    if tfs is None:
        v = _prev("timeframes")
        if isinstance(v, list) and v:
            out["timeframes"] = v
            _default("timeframes", v, "last_used")
        else:
            out["timeframes"] = ["M30"]
            _default("timeframes", ["M30"], default_source)
        tfs = ["M30"]
    if not isinstance(tfs, list):
        _err("timeframes", "必须为 string[]")
        out["timeframes"] = ["M30"]
    else:
        out["timeframes"] = [str(tf).upper() for tf in tfs if str(tf).strip()] or ["M30"]

    # lookback.bars
    lookback = out.get("lookback")
    if not isinstance(lookback, dict):
        lookback = {}
        out["lookback"] = lookback
    if lookback.get("bars") is None:
        v = _prev("lookback.bars")
        if v is not None:
            lookback["bars"] = v
            _default("lookback.bars", v, "last_used")
        else:
            lookback["bars"] = 2000
            _default("lookback.bars", 2000, default_source)
    try:
        bars = int(lookback.get("bars") or 0)
        if bars < 200:
            _err("lookback.bars", "bars 太小，建议 >= 200", "warning")
        if bars > 20000:
            _err("lookback.bars", "bars 太大，建议 <= 20000", "warning")
        lookback["bars"] = max(200, min(20000, bars))
    except Exception:
        _err("lookback.bars", "必须为整数")
        lookback["bars"] = 2000

    # signal.type (MVP breakout)
    signal = out.get("signal")
    if not isinstance(signal, dict):
        signal = {}
        out["signal"] = signal
    if signal.get("type") is None:
        v = _prev("signal.type")
        if isinstance(v, str) and v:
            signal["type"] = v
            _default("signal.type", v, "last_used")
        else:
            signal["type"] = "breakout"
            _default("signal.type", "breakout", default_source)
    if signal.get("type") != "breakout":
        _err("signal.type", "当前 MVP 仅支持 breakout", "error")

    # mvp
    mvp = out.get("mvp")
    if not isinstance(mvp, dict):
        mvp = {}
        out["mvp"] = mvp
    if mvp.get("n_breakout") is None:
        v = _prev("mvp.n_breakout")
        if v is not None:
            mvp["n_breakout"] = v
            _default("mvp.n_breakout", v, "last_used")
        else:
            mvp["n_breakout"] = 48
            _default("mvp.n_breakout", 48, default_source)
    if mvp.get("top_n") is None:
        v = _prev("mvp.top_n")
        if v is not None:
            mvp["top_n"] = v
            _default("mvp.top_n", v, "last_used")
        else:
            mvp["top_n"] = 20
            _default("mvp.top_n", 20, default_source)
    if mvp.get("direction") is None:
        v = _prev("mvp.direction")
        if isinstance(v, str) and v:
            mvp["direction"] = v
            _default("mvp.direction", v, "last_used")
        else:
            mvp["direction"] = "both"
            _default("mvp.direction", "both", default_source)

    try:
        n = int(mvp.get("n_breakout") or 48)
        if n < 20 or n > 500:
            _err("mvp.n_breakout", "范围建议 20~500（已自动夹取）", "warning")
        mvp["n_breakout"] = max(20, min(500, n))
    except Exception:
        _err("mvp.n_breakout", "必须为整数")
        mvp["n_breakout"] = 48

    try:
        top_n = int(mvp.get("top_n") or 20)
        if top_n < 5 or top_n > 200:
            _err("mvp.top_n", "范围建议 5~200（已自动夹取）", "warning")
        mvp["top_n"] = max(5, min(200, top_n))
    except Exception:
        _err("mvp.top_n", "必须为整数")
        mvp["top_n"] = 20

    direction = str(mvp.get("direction") or "both")
    if direction not in ("both", "up", "down"):
        _err("mvp.direction", "必须为 both/up/down（已回退 both）", "warning")
        direction = "both"
    mvp["direction"] = direction

    status = "ok"
    if any(e.get("severity") == "error" for e in errors):
        status = "error"
    elif errors:
        status = "warning"

    return {
        "status": status,
        "validation_errors": errors,
        "defaults_applied": defaults_applied,
        "normalized_spec": out,
    }
