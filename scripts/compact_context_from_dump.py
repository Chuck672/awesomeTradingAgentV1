import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.ai.agent_context_builder import build_agent_context


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True)
    p.add_argument("--out", dest="out_path", default="")
    p.add_argument("--keep-ohlcv", action="store_true")
    p.add_argument("--ohlcv-limit", type=int, default=0)
    args = p.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        src = json.load(f)

    event = src.get("event") or {}
    market = src.get("market") or {}
    ohlcv = market.get("ohlcv") or {}

    compact_indicators = {}
    for tf, bars in ohlcv.items():
        if not isinstance(bars, list) or not bars:
            compact_indicators[tf] = {"error": "no_data"}
            continue
        try:
            ctx_json = build_agent_context(bars)
            compact_indicators[tf] = json.loads(ctx_json)
        except Exception as e:
            compact_indicators[tf] = {"error": "build_agent_context_failed", "message": str(e)}

    out = {
        "schema": "compact_agent_context_v1",
        "generated_at_unix": int(time.time()),
        "source_dump": os.path.abspath(args.in_path),
        "event": event,
        "market": {
            "indicators_compact": compact_indicators,
        },
    }

    if args.keep_ohlcv:
        trimmed = {}
        for tf, bars in ohlcv.items():
            if not isinstance(bars, list):
                continue
            if args.ohlcv_limit and args.ohlcv_limit > 0:
                trimmed[tf] = bars[-int(args.ohlcv_limit) :]
            else:
                trimmed[tf] = bars
        out["market"]["ohlcv"] = trimmed

    out_path = args.out_path.strip()
    if not out_path:
        base = os.path.splitext(os.path.basename(args.in_path))[0]
        out_dir = os.path.join(os.path.dirname(os.path.abspath(args.in_path)), "")
        out_path = os.path.join(out_dir, f"{base}__compact.json")
    else:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote: {out_path}")
    print(f"tfs={list(compact_indicators.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
