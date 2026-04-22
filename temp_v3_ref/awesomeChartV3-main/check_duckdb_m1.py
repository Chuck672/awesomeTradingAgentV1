import duckdb
con = duckdb.connect(r'C:\Users\chuck\AppData\Roaming\AwesomeChart\data\brokers\Exness_MT5Real5_default\hot_data.duckdb', read_only=True)
print('DuckDB M1 rows:', con.execute("SELECT COUNT(*) FROM ohlcv_hot WHERE symbol='XAUUSDz' AND timeframe='M1'").fetchall()[0][0])
