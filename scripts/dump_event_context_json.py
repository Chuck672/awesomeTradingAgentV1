import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.ai.event_context_builder import build_event_context


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="XAUUSDz")
    p.add_argument("--timeframe", default="M15")
    p.add_argument("--trigger-type", default="manual_dump")
    p.add_argument("--trigger-text", default="")
    p.add_argument("--event-id", default="")
    p.add_argument("--out", default="")
    p.add_argument("--limits", default="")
    args = p.parse_args()

    ts = int(time.time())
    event_id = args.event_id.strip() or f"dump_{args.symbol}_{args.timeframe}_{ts}"
    trigger_text = args.trigger_text.strip() or f"Manual dump for {args.symbol} {args.timeframe} at {ts}"

    limits = None
    if args.limits.strip():
        limits = json.loads(args.limits)
        if not isinstance(limits, dict):
            raise ValueError("--limits must be a JSON object, e.g. '{\"H1\":400,\"M15\":600}'")

    payload = build_event_context(
        event_id=event_id,
        trigger_type=args.trigger_type.strip() or "manual_dump",
        trigger_text=trigger_text,
        symbol=args.symbol.strip(),
        event_timeframe=args.timeframe.strip(),
        history_limits=limits,
    )

    out_path = args.out.strip()
    if not out_path:
        out_dir = os.path.join(os.getcwd(), "tmp")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{event_id}.json")
    else:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    market = payload.get("market") or {}
    ohlcv = market.get("ohlcv") or {}
    indicators = market.get("indicators") or {}
    print(f"Wrote: {out_path}")
    print(f"event_id={payload.get('event', {}).get('event_id')}")
    print(f"snapshot_time={payload.get('event', {}).get('snapshot_time')}")
    print(f"tfs_ohlcv={list(ohlcv.keys())} tfs_indicators={list(indicators.keys())}")
    print(f"missing={len(payload.get('missing_indicators') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
