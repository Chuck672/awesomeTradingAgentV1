import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.ai.event_context_builder import build_event_context


def main() -> int:
    args = {
        "event_id": "evt_test",
        "trigger_type": "manual",
        "trigger_text": "test",
        "symbol": "XAUUSDz",
        "event_timeframe": "M15",
    }

    for i in range(2):
        t0 = time.perf_counter()
        ctx = build_event_context(**args)
        ms = int((time.perf_counter() - t0) * 1000)
        missing = len((ctx.get("missing_indicators") or []))
        snap = (ctx.get("event") or {}).get("snapshot_time_iso")
        print(f"run={i+1} ms={ms} missing={missing} snapshot={snap}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
