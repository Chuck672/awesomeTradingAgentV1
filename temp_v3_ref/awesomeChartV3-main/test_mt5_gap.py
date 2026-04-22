import MetaTrader5 as mt5
from datetime import datetime, timezone
import sys

# Connect to MT5
if not mt5.initialize():
    print("initialize() failed")
    mt5.shutdown()
    sys.exit()

symbol = "XAUUSDz"
tf = mt5.TIMEFRAME_M1

# The gap is from 2026-04-06 14:06:00 to 2026-04-06 14:25:00
# Let's request from 14:00 to 14:30
start_ts = int(datetime(2026, 4, 6, 14, 0, tzinfo=timezone.utc).timestamp())
end_ts = int(datetime(2026, 4, 6, 14, 30, tzinfo=timezone.utc).timestamp())

print(f"Requesting {symbol} M1 from {start_ts} to {end_ts}")

def ts_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)

rates = mt5.copy_rates_range(symbol, tf, ts_to_dt(start_ts), ts_to_dt(end_ts))

if rates is None:
    print(f"Failed, error: {mt5.last_error()}")
else:
    print(f"Got {len(rates)} bars")
    if len(rates) > 0:
        print(f"First: {datetime.fromtimestamp(rates[0]['time'], tz=timezone.utc)}")
        print(f"Last:  {datetime.fromtimestamp(rates[-1]['time'], tz=timezone.utc)}")
        
        # Check if 14:10 is in there
        times = [r['time'] for r in rates]
        missing = []
        for t in range(start_ts, end_ts, 60):
            if t not in times:
                missing.append(datetime.fromtimestamp(t, tz=timezone.utc).strftime('%H:%M'))
        print(f"Missing minutes: {missing}")

mt5.shutdown()
