import duckdb
from datetime import datetime
con = duckdb.connect(':memory:')
df = con.execute("SELECT MIN(time), MAX(time), COUNT(*) FROM read_parquet('C:\\\\Users\\\\chuck\\\\AppData\\\\Roaming\\\\AwesomeChart\\\\data\\\\brokers\\\\Exness_MT5Real5_default\\\\parquet\\\\XAUUSDz\\\\M1\\\\2026_03.parquet')").fetchall()
print(datetime.fromtimestamp(df[0][0]), 'to', datetime.fromtimestamp(df[0][1]), 'count:', df[0][2])
