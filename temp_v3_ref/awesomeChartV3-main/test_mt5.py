import MetaTrader5 as mt5
from datetime import datetime, timezone
import time

if not mt5.initialize():
    print("initialize() failed")
    quit()

symbol = "EURUSD"
mt5_tf = mt5.TIMEFRAME_H1
current_time = int(time.time())
safe_last_sync = current_time - (24 * 3600)

print("Using int timestamps:")
rates_int = mt5.copy_rates_range(symbol, mt5_tf, safe_last_sync, current_time)
if rates_int is None:
    print("Int result error:", mt5.last_error())
else:
    print("Int result length:", len(rates_int))

print("\nUsing naive datetimes:")
dt_from = datetime.fromtimestamp(safe_last_sync)
dt_to = datetime.fromtimestamp(current_time)
rates_naive = mt5.copy_rates_range(symbol, mt5_tf, dt_from, dt_to)
if rates_naive is None:
    print("Naive result error:", mt5.last_error())
else:
    print("Naive result length:", len(rates_naive))

print("\nUsing UTC datetimes:")
dt_from_utc = datetime.fromtimestamp(safe_last_sync, tz=timezone.utc)
dt_to_utc = datetime.fromtimestamp(current_time, tz=timezone.utc)
rates_utc = mt5.copy_rates_range(symbol, mt5_tf, dt_from_utc, dt_to_utc)
if rates_utc is None:
    print("UTC result error:", mt5.last_error())
else:
    print("UTC result length:", len(rates_utc))

mt5.shutdown()