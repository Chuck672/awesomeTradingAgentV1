#!/usr/bin/env python3
"""
LLM 策略转换基准测试（推荐用法）

目的：
1) 多条自然语言策略 → /api/strategy/parse_ai
2) 自动做 schema 校验（后端已内置）
3) 输出“准确性检查清单”（基于启发式断言）+ 保存报告

使用方法（在你自己的环境里运行，避免把 key 写进代码/日志）：
  export AI_BASE_URL="https://api.siliconflow.cn/v1"
  export AI_API_KEY="..."
  export AI_MODEL="Qwen/Qwen3.5-9B"
  export BACKEND_URL="http://127.0.0.1:8000"
  python3 scripts/ai_strategy_conversion_benchmark.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def _post(url: str, payload: dict, *, timeout_sec: int = 420) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=int(timeout_sec)) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


@dataclass
class Case:
    id: str
    prompt: str
    expect_action: Optional[str] = None  # breakout/pullback/mean_reversion/...
    expect_tf: Optional[str] = None  # e.g. "30m"
    expect_symbols: Optional[List[str]] = None  # e.g. ["XAUUSDz"]
    expect_indicator_ids: Optional[List[str]] = None  # e.g. ["atr_30m_14"]


def _get(d: Dict[str, Any], path: str, default=None):
    cur: Any = d
    for p in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default


def check_case(case: Case, rep: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    轻量“准确性检查”（启发式，非严格语义证明）
    - 强一致性：schema validate 通过
    - 弱一致性：action.type / timeframe / symbols / 指标声明是否存在
    """
    issues: List[str] = []
    ok = bool(rep.get("ok"))
    if not ok:
        issues.append("schema 校验未通过")
        errs = (rep.get("parse_meta") or {}).get("schema_validation_errors") or []
        if errs:
            issues.append(f"errors: {len(errs)}")
        return False, issues

    ns = rep.get("normalized_schema") or {}
    if case.expect_action:
        act = str(_get(ns, "action.type", "")).strip()
        if act != case.expect_action:
            issues.append(f"action.type 不符合预期：got={act} expect={case.expect_action}")
    if case.expect_tf:
        tf = str(_get(ns, "universe.primary_timeframe", "")).strip()
        if tf != case.expect_tf:
            issues.append(f"primary_timeframe 不符合预期：got={tf} expect={case.expect_tf}")
    if case.expect_symbols:
        syms = _get(ns, "universe.symbols", []) or []
        syms = [str(x) for x in syms]
        for s in case.expect_symbols:
            if s not in syms:
                issues.append(f"symbols 缺少 {s}（got={syms})")
    if case.expect_indicator_ids:
        inds = _get(ns, "indicators", []) or []
        ids = [str((x or {}).get("id")) for x in inds if isinstance(x, dict)]
        for iid in case.expect_indicator_ids:
            if iid not in ids:
                issues.append(f"indicators 缺少 id={iid}（got={ids})")

    return len(issues) == 0, issues


def main() -> int:
    backend = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").strip()
    base_url = os.environ.get("AI_BASE_URL", "").strip()
    api_key = os.environ.get("AI_API_KEY", "").strip()
    model = os.environ.get("AI_MODEL", "").strip()
    if not (base_url and api_key and model):
        raise SystemExit("请设置 AI_BASE_URL/AI_API_KEY/AI_MODEL（避免把 key 写进脚本）")

    cases: List[Case] = [
        Case(
            id="triangle_breakout_retest",
            prompt="XAUUSDz 在30m识别收敛三角形（deterministic），输出边界zone；当30m实体收线有效突破边界zone后，等待回踩确认入场；止损放在边界zone外，目标至少1.5R。",
            expect_action="breakout",
            expect_tf="30m",
            expect_symbols=["XAUUSDz"],
        ),
        Case(
            id="pullback_trend",
            prompt="做多：4h趋势向上（EMA50上斜且价格在EMA上），30m出现推动段后回撤到EMA20附近出现看涨吞没进场；止损在回撤低点下方，RR>=2才做。",
            expect_action="pullback",
            expect_tf="30m",
        ),
        Case(
            id="mean_reversion_range",
            prompt="30m震荡：当价格偏离VWAP超过2倍ATR并出现pinbar反转时做均值回归，目标回到VWAP，止损放在pinbar极值外。",
            expect_action="mean_reversion",
            expect_tf="30m",
        ),
        Case(
            id="breakout_simple_no_ind",
            prompt="XAUUSDz 30m：收盘价突破近48根最高/最低就给机会，不用任何指标。",
            expect_action="breakout",
            expect_tf="30m",
            expect_symbols=["XAUUSDz"],
        ),
        Case(
            id="multi_indicator_filter",
            prompt="XAUUSDz 15m：突破前高做多，但要求ADX(14)>20且ATR(14)大于某阈值；大周期1h方向一致；点差过大不做。",
            expect_action="breakout",
            expect_tf="15m",
            expect_symbols=["XAUUSDz"],
        ),
    ]

    results: List[Dict[str, Any]] = []
    passed = 0
    t0 = time.time()
    for c in cases:
        rep = _post(
            f"{backend}/api/strategy/parse_ai",
            {
                "prompt": c.prompt,
                "settings": {"base_url": base_url, "api_key": api_key, "model": model},
                "temperature": 0.2,
                "timeout_sec": 300,
            },
            timeout_sec=420,
        )
        ok2, issues = check_case(c, rep)
        if ok2:
            passed += 1
        results.append(
            {
                "id": c.id,
                "ok": bool(rep.get("ok")),
                "via": (rep.get("parse_meta") or {}).get("via"),
                "attempt": (rep.get("parse_meta") or {}).get("attempt"),
                "fixes_count": len(((rep.get("parse_meta") or {}).get("fixes") or [])),
                "check_ok": ok2,
                "issues": issues,
                "capabilities_required": rep.get("capabilities_required"),
                "unsupported_features": rep.get("unsupported_features"),
                "normalized_schema": rep.get("normalized_schema"),
            }
        )

    dt = time.time() - t0
    summary = {"total": len(cases), "passed_checks": passed, "elapsed_sec": round(dt, 2)}

    out = {"summary": summary, "results": results}
    fn = os.path.join(os.getcwd(), f"ai_strategy_conversion_report_{int(time.time())}.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("saved:", fn)
    print("summary:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
