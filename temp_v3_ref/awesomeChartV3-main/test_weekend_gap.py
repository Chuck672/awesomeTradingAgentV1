import MetaTrader5 as mt5
from datetime import datetime, timezone
import sys

if not mt5.initialize():
    print("initialize() failed")
    mt5.shutdown()
    sys.exit()

symbol = "XAUUSDz"
tf = mt5.TIMEFRAME_M1

# start on Sunday 14:00
start_ts = int(datetime(2026, 4, 5, 14, 0, tzinfo=timezone.utc).timestamp())
# end on Monday 14:30
end_ts = int(datetime(2026, 4, 6, 14, 30, tzinfo=timezone.utc).timestamp())

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

mt5.shutdown()
