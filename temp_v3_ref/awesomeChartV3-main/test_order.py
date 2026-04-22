import requests

url = "http://127.0.0.1:8000/api/history?symbol=US30z&timeframe=H1&limit=5000"
response = requests.get(url)
data = response.json()

for i in range(1, len(data)):
    if data[i]['time'] <= data[i-1]['time']:
        print(f"Out of order at index {i}: {data[i-1]['time']} -> {data[i]['time']}")
print("Check complete.")
