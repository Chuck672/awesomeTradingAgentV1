import argparse
import datetime
import glob
import os
import re

import duckdb

from backend.database.app_config import app_config


def _utc(ts: int | None):
    if not ts:
        return None
    return datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="", help="e.g. XAUUSDz")
    ap.add_argument("--timeframe", default="", help="e.g. M1, H1")
    ap.add_argument("--limit", type=int, default=200, help="max files to print")
    args = ap.parse_args()

    broker = (app_config.get_active_broker() or {}).get("id")
    if not broker:
        raise SystemExit("No active broker configured in app_config.")

    root = os.path.join(app_config.get_brokers_dir(), broker, "parquet")
    if args.symbol and args.timeframe:
        pattern = os.path.join(root, args.symbol, args.timeframe, "*.parquet")
    else:
        pattern = os.path.join(root, "**", "*.parquet")

    files = sorted(glob.glob(pattern, recursive=True))
    print("parquet_root:", root)
    print("files:", len(files))

    con = duckdb.connect()
    rx = re.compile(r"(\d{4})_(\d{2})\.parquet$")

    bad = 0
    shown = 0
    for f in files:
        if shown >= args.limit:
            break
        m = rx.search(os.path.basename(f))
        if not m:
            continue
        year = int(m.group(1))
        month = int(m.group(2))

        c, mn, mx = con.execute(
            "select count(*) c, min(time) mn, max(time) mx from read_parquet(?)", [f.replace("\\", "/")]
        ).fetchone()
        mndt = _utc(mn)
        mxdt = _utc(mx)
        ok = True
        if mndt and (mndt.year != year or mndt.month != month):
            ok = False
        if mxdt and (mxdt.year != year or mxdt.month != month):
            ok = False
        if not ok:
            bad += 1

        rel = os.path.relpath(f, root)
        print(("OK " if ok else "BAD"), rel, "rows", c, "min", mndt, "max", mxdt)
        shown += 1

    print("mismatched_files:", bad)


if __name__ == "__main__":
    main()

