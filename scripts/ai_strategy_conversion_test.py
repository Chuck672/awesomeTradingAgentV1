#!/usr/bin/env python3
"""
AI 策略转换测试（Strategy prompt -> StrategySchema v2 -> validate）

用法：
  # 1) 真实调用（需要环境变量）
  export AI_BASE_URL="https://api.openai.com"
  export AI_API_KEY="..."
  export AI_MODEL="gpt-4.1-mini"
  python3 scripts/ai_strategy_conversion_test.py

  # 2) 无 key 模式（只验证 fixture）
  python3 scripts/ai_strategy_conversion_test.py --fixture-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="http://127.0.0.1:8000", help="backend base url")
    ap.add_argument("--fixture-only", action="store_true", help="skip llm call, only validate fixture")
    args = ap.parse_args()

    prompt = (
        "在30m上识别收敛三角/上升三角/下降三角（deterministic），输出边界zone；当30m实体收线有效突破边界zone，"
        "并通过4h上下文过滤后给出机会；止损放在边界zone外，目标至少 1.5R。"
    )

    fixture = {
        "spec_version": "2.0",
        "meta": {"strategy_id": "xau_triangle_breakout_30m_v1", "name": "XAU 三角突破", "version": "1.0.0", "description": "fixture"},
        "universe": {"symbols": ["XAUUSDz"], "primary_timeframe": "30m"},
        "data": {"history_lookback_bars": 800, "higher_timeframes": ["4h"]},
        "indicators": [{"id": "atr_30m_14", "name": "ATR", "timeframe": "30m", "params": {"period": 14}, "unit": "pips"}],
        "patterns": [{"type": "triangle_contraction", "timeframe": "30m", "lookback_bars": 120, "pivot_left": 3, "pivot_right": 3, "min_score_to_emit": 70, "emit_boundary_as_zone": True}],
        "action": {"type": "breakout"},
        "outputs": {"emit_evidence_pack": True, "emit_draw_plan": True, "emit_compilation_report": True, "emit_trace": True, "emit_intermediate_artifacts": False},
    }

    # 1) fixture validate
    v = _post(f"{args.backend}/api/strategy/schema/v2/validate", {"strategy_schema": fixture})
    print("fixture validate ok=", v.get("ok"), "status=", v.get("status"))
    if v.get("unsupported_features"):
        print("unsupported_features:", len(v.get("unsupported_features") or []))
    if not v.get("ok"):
        print(json.dumps(v.get("validation_errors"), ensure_ascii=False, indent=2))
        return 2

    if args.fixture_only:
        return 0

    base_url = os.environ.get("AI_BASE_URL", "").strip()
    api_key = os.environ.get("AI_API_KEY", "").strip()
    model = os.environ.get("AI_MODEL", "").strip()
    if not (base_url and api_key and model):
        print("missing env: AI_BASE_URL/AI_API_KEY/AI_MODEL; use --fixture-only", file=sys.stderr)
        return 3

    rep = _post(
        f"{args.backend}/api/strategy/parse_ai",
        {"prompt": prompt, "settings": {"base_url": base_url, "api_key": api_key, "model": model}, "temperature": 0.2},
    )
    print("ai parse ok=", rep.get("ok"), "via=", (rep.get("parse_meta") or {}).get("via"))
    if not rep.get("ok"):
        print(json.dumps(rep.get("parse_meta"), ensure_ascii=False, indent=2))
        return 4
    # print normalized schema summary
    ns = rep.get("normalized_schema") or {}
    print("normalized.meta.strategy_id=", ((ns.get("meta") or {}).get("strategy_id")))
    print("capabilities_required=", rep.get("capabilities_required"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
