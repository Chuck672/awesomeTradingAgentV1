import json
import sys
from pathlib import Path

# 允许直接运行该脚本（不依赖安装包）
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.strategy.tools_patterns_v1 import tool_pattern_detect_batch  # noqa: E402


def main() -> int:
    fixture_path = Path(__file__).parent / "fixtures" / "pattern_phase1_fixtures.json"
    fx = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = fx.get("cases") or []

    total = 0
    passed = 0
    failures = []

    for c in cases:
        total += 1
        cid = c.get("id")
        payload = {
            "bars_by_tf": c.get("bars_by_tf") or {},
            "detectors": c.get("detectors") or [],
            "structures": c.get("structures") or {},
        }
        rep = tool_pattern_detect_batch(payload)
        items = (rep.get("pattern_pack") or {}).get("items") or []
        got_ids = set(str(i.get("id")) for i in items)
        expect_any = set(str(x) for x in (c.get("expect_any_ids") or []))
        ok = bool(got_ids & expect_any) if expect_any else True
        if ok:
            passed += 1
        else:
            failures.append({"id": cid, "expect_any": sorted(expect_any), "got": sorted(got_ids)})

    print({"total": total, "passed": passed, "failed": len(failures)})
    if failures:
        print("failures:")
        for f in failures:
            print("-", f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
