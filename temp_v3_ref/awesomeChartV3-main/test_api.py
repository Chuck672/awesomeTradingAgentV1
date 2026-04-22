import requests
import sys

symbol = "US30z"
timeframe = "H1"
url = f"http://127.0.0.1:8000/api/history?symbol={symbol}&timeframe={timeframe}&limit=10000"

try:
    response = requests.get(url)
    data = response.json()
    if data:
        print(f"Fetched {len(data)} records for {symbol} {timeframe}")
        print(f"Earliest: {data[0]['time']}")
        print(f"Latest: {data[-1]['time']}")
    else:
        print("No data returned.")
except Exception as e:
    print(f"Error fetching data: {e}")
