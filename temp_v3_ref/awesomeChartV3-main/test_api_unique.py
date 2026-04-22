import requests

url = "http://127.0.0.1:8000/api/history?symbol=US30z&timeframe=H1&limit=5000"
response = requests.get(url)
data = response.json()
print(f"Total records: {len(data)}")
unique_times = set([d['time'] for d in data])
print(f"Unique times: {len(unique_times)}")
if len(data) > 0:
    print(f"Sample data: {data[-2:]}")
