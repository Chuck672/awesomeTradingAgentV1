import json
import os
import sys
import time


def main() -> int:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    symbol = (sys.argv[1] if len(sys.argv) >= 2 else "XAUUSD").strip()
    tf = (sys.argv[2] if len(sys.argv) >= 3 else "M15").strip()
    out_path = sys.argv[3] if len(sys.argv) >= 4 else ""

    if not out_path:
        ts = int(time.time())
        out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "debug_dumps")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"event_context_all_features_{symbol}_{tf}_{ts}.json")

    from backend.services.ai.event_context_builder import build_event_context
    from backend.domain.market.catalog import get_market_feature_catalog

    cat = get_market_feature_catalog()
    enabled = []
    for g in (cat.get("groups") or []):
        if not isinstance(g, dict):
            continue
        if str(g.get("id") or "") != "patterns":
            continue
        for it in (g.get("items") or []):
            if not isinstance(it, dict):
                continue
            fid = it.get("id")
            if isinstance(fid, str) and fid:
                enabled.append(fid)

    enabled = sorted(set(enabled))
    cfg = {"context_features": {"timeframe": tf, "enabled": enabled, "params": {}}}

    payload = build_event_context(
        event_id="debug_dump",
        trigger_type="manual",
        trigger_text="debug_dump_all_features",
        symbol=symbol,
        event_timeframe=tf,
        configs=cfg,
    )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
