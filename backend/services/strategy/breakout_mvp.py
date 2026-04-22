import re
from typing import Any, Dict, List, Tuple


TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


def _tf_to_sec(tf: str) -> int:
    tf = str(tf or "M15").upper()
    return (
        60
        if tf == "M1"
        else 300
        if tf == "M5"
        else 900
        if tf == "M15"
        else 1800
        if tf == "M30"
        else 3600
        if tf == "H1"
        else 14400
        if tf == "H4"
        else 86400
    )


def parse_breakout_prompt_to_protocol(
    *,
    prompt: str,
    symbols: List[str],
    timeframes: List[str],
    lookback_bars: int = 2000,
    n_breakout: int = 48,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    复杂策略解析协议 v1.0 的一个 MVP 落地：仅覆盖 breakout 类。
    - 不依赖 LLM，保证稳定与低延迟。
    - 对未知/复杂意图，返回 needs_clarification/unsupported。
    """
    p = (prompt or "").strip()
    if not p:
        return {
            "protocol_version": "1.0",
            "strategy_spec": None,
            "parse_meta": {
                "status": "needs_clarification",
                "confidence": 0.0,
                "assumptions": [],
                "ambiguities": [],
                "open_questions": [
                    {
                        "id": "Q0",
                        "question": "请描述你要扫描的突破策略（例如：收盘价上破近48根最高点）。",
                        "options": [],
                        "default": None,
                        "required": True,
                    }
                ],
                "unsupported_features": [],
                "normalization": {},
            },
        }

    # 目前仅支持突破类 MVP（避免误解析导致 silently wrong）
    if not re.search(r"(突破|breakout|上破|下破|收盘站上|收盘站下)", p, flags=re.I):
        return {
            "protocol_version": "1.0",
            "strategy_spec": None,
            "parse_meta": {
                "status": "unsupported",
                "confidence": 0.2,
                "assumptions": [],
                "ambiguities": [],
                "open_questions": [],
                "unsupported_features": [
                    {
                        "id": "UN0",
                        "feature": "非突破类策略",
                        "reason": "当前 MVP 仅支持 breakout（近 N 根高/低突破）",
                        "workaround": "请将策略改写为“收盘价上破/下破近48根最高/最低”形式，或等待后续扩展。",
                    }
                ],
                "normalization": {},
            },
        }

    direction = "both"
    if re.search(r"(向上|上破|突破高|做多|long)", p, flags=re.I) and not re.search(r"(向下|下破|跌破低|做空|short)", p, flags=re.I):
        direction = "up"
    if re.search(r"(向下|下破|跌破低|做空|short)", p, flags=re.I) and not re.search(r"(向上|上破|突破高|做多|long)", p, flags=re.I):
        direction = "down"

    # timeframes/symbols 兜底清洗
    tfs = [str(x).upper() for x in (timeframes or []) if str(x).upper() in TIMEFRAMES]
    if not tfs:
        tfs = ["M15"]
    syms = [str(x).strip() for x in (symbols or []) if str(x).strip()]
    if not syms:
        syms = []

    spec: Dict[str, Any] = {
        "spec_version": "1.0",
        "name": "Breakout MVP (48 bars)",
        "description": "MVP：收盘价突破近48根最高/最低",
        "tags": ["breakout", "mvp"],
        "universe": {"symbols": syms},
        "timeframes": tfs,
        "lookback": {"bars": int(max(100, min(20000, lookback_bars)))},
        "risk": {"direction": "both" if direction == "both" else ("long_only" if direction == "up" else "short_only")},
        "signal": {
            "type": "breakout",
            "entry": {
                "all": [
                    {
                        "op": "cross_up" if direction in ("both", "up") else "cross_down",
                        "lhs": {"type": "ohlc", "field": "close"},
                        "rhs": {"type": "hl", "field": "high" if direction in ("both", "up") else "low", "bars": int(n_breakout)},
                    }
                ]
            },
            "filters": {"all": [{"op": "gt", "lhs": {"type": "indicator", "name": "atr", "params": {"n": 14}}, "rhs": {"type": "const", "value": 0}}]},
            "explain": {"key_levels": 6, "draw_style": "minimal"},
        },
        "mvp": {"n_breakout": int(n_breakout), "top_n": int(top_n), "direction": direction},
    }

    assumptions = [
        {"id": "A1", "title": "突破窗口固定为48根", "detail": "MVP 固定 N=48。", "impact": "medium"},
        {"id": "A2", "title": "突破以收盘价为准", "detail": "使用 close cross_up/cross_down。", "impact": "high"},
    ]
    if direction == "both":
        assumptions.append({"id": "A3", "title": "方向默认双向", "detail": "未明确多/空时，扫描 up/down 都可入选。", "impact": "low"})

    return {
        "protocol_version": "1.0",
        "strategy_spec": spec,
        "parse_meta": {
            "status": "ok",
            "confidence": 0.85,
            "assumptions": assumptions,
            "ambiguities": [],
            "open_questions": [],
            "unsupported_features": [],
            "normalization": {"direction": direction, "n_breakout": int(n_breakout), "top_n": int(top_n)},
        },
    }


def compile_breakout_spec_to_dsl(spec: Dict[str, Any]) -> str:
    """
    Spec→DSL/1.0（确定性）。当前仅支持 breakout MVP。
    """
    mvp = spec.get("mvp") if isinstance(spec.get("mvp"), dict) else {}
    n = int(mvp.get("n_breakout") or 48)
    direction = str(mvp.get("direction") or "both")
    # DSL 的 RULE 只表达触发条件；direction 在 scan 侧决定 up/down 两套 score
    return "\n".join(
        [
            "DSL/1.0",
            "RULE breakout_mvp:",
            f"  WHEN ATR(14) > 0",
            f"  SCORE 0",
            f"  EVIDENCE {{ n: {n}, direction: \"{direction}\" }}",
        ]
    )


def compile_breakout_spec_with_report(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    StrategySpec -> DSL + CompilationReport（确定性）。
    目标：让前端能清晰展示“成功/警告/失败”、默认值清单、能力不支持点、规则摘要。
    """
    spec = spec if isinstance(spec, dict) else {}

    warnings: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    defaults_applied: List[Dict[str, Any]] = []
    unsupported: List[Dict[str, Any]] = []

    def _get(path: str, default: Any) -> Any:
        # 仅用于生成 report；不强行改写用户原 spec
        return default

    # -------- Validate basic structure --------
    spec_version = str(spec.get("spec_version") or "1.0")
    if not spec.get("spec_version"):
        defaults_applied.append({"path": "spec_version", "value": "1.0", "source": "system_default"})

    signal = spec.get("signal") if isinstance(spec.get("signal"), dict) else {}
    sig_type = str(signal.get("type") or "")
    if sig_type and sig_type != "breakout":
        unsupported.append(
            {
                "feature": f"signal.type={sig_type}",
                "reason": "当前编译器 MVP 仅支持 breakout",
                "workaround": "请使用 breakout 相关模板，或等待后续扩展更多 signal types。",
            }
        )
        errors.append({"code": "UNSUPPORTED_SIGNAL", "message": "不支持的 signal.type", "path": "signal.type", "severity": "error"})
    if not sig_type:
        # 允许：把缺省看作 breakout（MVP），但给 warning
        warnings.append({"code": "DEFAULT_SIGNAL", "message": "未指定 signal.type，已按 breakout 处理（MVP）", "path": "signal.type", "severity": "warning"})
        defaults_applied.append({"path": "signal.type", "value": "breakout", "source": "system_default"})
        sig_type = "breakout"

    uni = spec.get("universe") if isinstance(spec.get("universe"), dict) else {}
    symbols = uni.get("symbols") if isinstance(uni.get("symbols"), list) else []
    symbols = [str(s).strip() for s in symbols if str(s).strip()]
    if not symbols:
        warnings.append({"code": "EMPTY_UNIVERSE", "message": "universe.symbols 为空：扫描阶段可能无候选", "path": "universe.symbols", "severity": "warning"})

    timeframes = spec.get("timeframes") if isinstance(spec.get("timeframes"), list) else []
    timeframes = [str(tf).upper() for tf in timeframes if str(tf).strip()]
    if not timeframes:
        defaults_applied.append({"path": "timeframes", "value": ["M30"], "source": "system_default"})
        warnings.append({"code": "DEFAULT_TIMEFRAMES", "message": "未指定 timeframes，已默认使用 M30", "path": "timeframes", "severity": "warning"})
        timeframes = ["M30"]

    lookback = spec.get("lookback") if isinstance(spec.get("lookback"), dict) else {}
    lookback_bars = int(lookback.get("bars") or 2000)
    if not lookback.get("bars"):
        defaults_applied.append({"path": "lookback.bars", "value": 2000, "source": "system_default"})
    if lookback_bars < 200:
        warnings.append({"code": "LOOKBACK_TOO_SMALL", "message": "lookback.bars 偏小，可能导致触发点不足", "path": "lookback.bars", "severity": "warning"})

    mvp = spec.get("mvp") if isinstance(spec.get("mvp"), dict) else {}
    n = int(mvp.get("n_breakout") or 48)
    top_n = int(mvp.get("top_n") or 20)
    direction = str(mvp.get("direction") or "both")
    if not mvp.get("n_breakout"):
        defaults_applied.append({"path": "mvp.n_breakout", "value": 48, "source": "system_default"})
    if not mvp.get("top_n"):
        defaults_applied.append({"path": "mvp.top_n", "value": 20, "source": "system_default"})
    if not mvp.get("direction"):
        defaults_applied.append({"path": "mvp.direction", "value": "both", "source": "system_default"})

    n2 = max(20, min(500, n))
    if n2 != n:
        warnings.append({"code": "CLAMP_N", "message": f"mvp.n_breakout 超出范围，已夹到 {n2}", "path": "mvp.n_breakout", "severity": "warning"})
        n = n2
    top_n2 = max(5, min(200, top_n))
    if top_n2 != top_n:
        warnings.append({"code": "CLAMP_TOPN", "message": f"mvp.top_n 超出范围，已夹到 {top_n2}", "path": "mvp.top_n", "severity": "warning"})
        top_n = top_n2
    if direction not in ("both", "up", "down"):
        warnings.append({"code": "BAD_DIRECTION", "message": "mvp.direction 非法，已回退为 both", "path": "mvp.direction", "severity": "warning"})
        direction = "both"

    # -------- Compile (deterministic) --------
    if errors:
        status = "error"
        dsl_text = ""
    else:
        # 使用确定性编译器
        # 注意：compile_breakout_spec_to_dsl 目前只表达最简规则；后续可替换为 AST + 解释器
        dsl_text = compile_breakout_spec_to_dsl({"mvp": {"n_breakout": n, "direction": direction}})
        status = "warning" if warnings else "ok"

    report = {
        "report_version": "1.0",
        "status": status,
        "warnings": warnings,
        "errors": errors,
        "unsupported": unsupported,
        "defaults_applied": defaults_applied,
        "rule_summary": {
            "signal_type": "breakout",
            "entry": f"close crosses above/below HH/LL({n})",
            "filters": "ATR(14) > 0",
            "scoring": "score = breakout_distance / ATR(14)",
            "universe": {"symbols": symbols, "symbols_count": len(symbols)},
            "timeframes": timeframes,
            "lookback_bars": int(lookback_bars),
            "top_n": int(top_n),
            "direction": direction,
        },
        "normalized": {"spec_version": spec_version, "dsl_version": "1.0", "n_breakout": int(n), "top_n": int(top_n), "direction": direction},
    }

    return {"dsl_version": "1.0", "dsl_text": dsl_text, "report": report}


def _atr14(highs: List[float], lows: List[float], closes: List[float]) -> float:
    if len(closes) < 15:
        return 0.0
    trs = []
    for i in range(-14, 0):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sum(trs) / max(1, len(trs))


def scan_breakout_on_bars(
    *,
    symbol: str,
    timeframe: str,
    bars: List[Dict[str, Any]],
    n: int = 48,
    direction: str = "both",
) -> Tuple[float | None, Dict[str, Any] | None]:
    """
    返回 (score, evidence_pack)；未命中返回 (None, None)
    """
    if len(bars) < n + 3:
        return None, None
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    times = [int(b["time"]) for b in bars]

    prior_high = max(highs[-n - 1 : -1])
    prior_low = min(lows[-n - 1 : -1])
    prev_close = closes[-2]
    last_close = closes[-1]
    t = times[-1]

    atr = _atr14(highs, lows, closes)
    if atr <= 0:
        return None, None

    up = prev_close <= prior_high and last_close > prior_high
    down = prev_close >= prior_low and last_close < prior_low

    if direction == "up" and not up:
        return None, None
    if direction == "down" and not down:
        return None, None
    if direction == "both" and not (up or down):
        return None, None

    if up:
        score = (last_close - prior_high) / atr
        level = prior_high
        dir2 = "long"
        reason = "close crossed above 48-bar high"
        marker_pos = "aboveBar"
        marker_color = "#22c55e"
    else:
        score = (prior_low - last_close) / atr
        level = prior_low
        dir2 = "short"
        reason = "close crossed below 48-bar low"
        marker_pos = "belowBar"
        marker_color = "#ef4444"

    evidence = {
        "evidence_version": "1.0",
        "symbol": symbol,
        "timeframe": timeframe,
        "trigger_time": int(t),
        "rule_id": "breakout_mvp",
        "score": float(score),
        "facts": {
            "level": float(level),
            "close": float(last_close),
            "atr14": float(atr),
            "direction": dir2,
            "reason": reason,
        },
        "draw_plan": {
            "objects": [
                {"type": "hline", "price": float(level), "color": "#60a5fa", "text": "Breakout level (48)"},
                {"type": "marker", "time": int(t), "position": marker_pos, "color": marker_color, "text": "Breakout"},
            ],
            "notes": "MVP：用于候选验证；可进一步添加回踩/确认/风控逻辑。",
        },
    }
    return float(score), evidence


def scan_breakout_candidates_on_bars(
    *,
    symbol: str,
    timeframe: str,
    bars: List[Dict[str, Any]],
    n: int = 48,
    direction: str = "both",
    top_n: int = 20,
) -> List[Dict[str, Any]]:
    """
    在整个 bars（通常为 lookback 范围）内扫描所有触发点（而不是只看最后一根）。
    返回按 score 降序的 EvidencePack 列表（最多 top_n）。

    约束：
    - deterministic：同样输入 bars 必须输出同样结果
    - 防止爆量：仅保留 top_n
    """
    if len(bars) < max(n + 3, 60):
        return []
    n = max(20, min(500, int(n)))
    top_n = max(5, min(200, int(top_n)))

    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    times = [int(b["time"]) for b in bars]

    out: List[Dict[str, Any]] = []

    def _atr14_at(i: int) -> float:
        # ATR 需要 i-14..i 的窗口（含 i），因此 i 至少 15
        if i < 15:
            return 0.0
        trs = []
        for k in range(i - 14, i + 1):
            h = highs[k]
            l = lows[k]
            pc = closes[k - 1]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return sum(trs) / max(1, len(trs))

    # 从 i=n+1 开始：需要 prior window（i-n..i-1）以及 prev_close（i-1）
    for i in range(n + 1, len(bars)):
        prior_high = max(highs[i - n : i])
        prior_low = min(lows[i - n : i])
        prev_close = closes[i - 1]
        c = closes[i]
        t = times[i]

        atr = _atr14_at(i)
        if atr <= 0:
            continue

        up = prev_close <= prior_high and c > prior_high
        down = prev_close >= prior_low and c < prior_low
        if direction == "up" and not up:
            continue
        if direction == "down" and not down:
            continue
        if direction == "both" and not (up or down):
            continue

        if up:
            score = (c - prior_high) / atr
            level = prior_high
            dir2 = "long"
            reason = f"close crossed above {n}-bar high"
            marker_pos = "aboveBar"
            marker_color = "#22c55e"
            marker_shape = "arrowUp"
            level_color = "#60a5fa"
        else:
            score = (prior_low - c) / atr
            level = prior_low
            dir2 = "short"
            reason = f"close crossed below {n}-bar low"
            marker_pos = "belowBar"
            marker_color = "#ef4444"
            marker_shape = "arrowDown"
            level_color = "#60a5fa"

        # 让“落图”更可读：
        # - box：突破前 N 根的区间（prior_low~prior_high）
        # - 两条水平线：区间上沿/下沿（不同线型）
        # - marker：触发K线（方向箭头 + 文本）
        from_time = int(times[max(0, i - n)])
        to_time = int(t)
        box_low = float(prior_low)
        box_high = float(prior_high)

        # 用“箭头 Drawing”替代 series markers（更稳定、可控、跨主题一致）
        # 语义：多头绿色上箭头（放在 candle 下方）/ 空头红色下箭头（放在 candle 上方）
        # 注意：ArrowDrawing 自带一条连线，因此这里刻意让线段更短，并整体偏移到 candle 外侧。
        bar_high = float(highs[i])
        bar_low = float(lows[i])
        arrow_len = max(float(atr) * 0.25, abs(float(prior_high) - float(prior_low)) * 0.08, 0.001)
        pad = max(float(atr) * 0.18, abs(float(prior_high) - float(prior_low)) * 0.06, 0.001)
        if dir2 == "long":
            # 箭头整体放在 candle 下方：tip 在 low 下方一点，尾部再往下
            arrow_p2 = bar_low - pad
            arrow_p1 = arrow_p2 - arrow_len
        else:
            # 箭头整体放在 candle 上方：tip 在 high 上方一点，尾部再往上
            arrow_p2 = bar_high + pad
            arrow_p1 = arrow_p2 + arrow_len

        out.append(
            {
                "evidence_version": "1.0",
                "symbol": symbol,
                "timeframe": timeframe,
                "trigger_time": int(t),
                "rule_id": "breakout_mvp",
                "score": float(score),
                "facts": {
                    "level": float(level),
                    "range_high": float(prior_high),
                    "range_low": float(prior_low),
                    "window_from_time": int(from_time),
                    "window_to_time": int(to_time),
                    "close": float(c),
                    "atr14": float(atr),
                    "direction": dir2,
                    "reason": reason,
                    "n": int(n),
                },
                "draw_plan": {
                    "objects": [
                        {
                            "type": "box",
                            "from_time": int(from_time),
                            "to_time": int(to_time),
                            "low": box_low,
                            "high": box_high,
                            "color": "#94a3b8",
                            "lineStyle": "dotted",
                            "fillColor": "#94a3b8",
                            "fillOpacity": 0.08,
                        },
                        {"type": "hline", "price": float(prior_high), "color": level_color, "lineStyle": "solid", "lineWidth": 2, "text": f"Range High ({n})"},
                        {"type": "hline", "price": float(prior_low), "color": "#94a3b8", "lineStyle": "dashed", "lineWidth": 1, "text": f"Range Low ({n})"},
                        {"type": "hline", "price": float(level), "color": level_color, "lineStyle": "solid", "lineWidth": 3, "text": f"Breakout Level ({n})"},
                        {
                            "type": "arrow",
                            "t1": int(t),
                            "p1": float(arrow_p1),
                            "t2": int(t),
                            "p2": float(arrow_p2),
                            "color": marker_color,
                            "lineWidth": 2,
                            "arrowSize": 14,
                            "meta": {"direction": dir2, "shape": marker_shape},
                        },
                    ],
                    "notes": "MVP：用于候选验证；可进一步添加回踩/确认/风控逻辑。",
                },
            }
        )

    out.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return out[:top_n]
