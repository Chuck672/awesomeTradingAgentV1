import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.alerts_store import get_ai_decision_state, save_ai_decision_state


def main() -> int:
    alert_id = 999999
    symbol = "XAUUSDz"
    exec_tf = "M15"
    state = {
        "schema": "event_dual_decision_state_v1",
        "symbol": symbol,
        "exec_tf": exec_tf,
        "updated_at_test": int(time.time()),
        "position_state": "flat",
        "last_decision": {"signal": "hold"},
    }
    save_ai_decision_state(alert_id, symbol, exec_tf, state)
    got = get_ai_decision_state(alert_id, symbol, exec_tf)
    ok = isinstance(got, dict) and got.get("updated_at_test") == state["updated_at_test"]
    print("ok" if ok else "failed", got)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

