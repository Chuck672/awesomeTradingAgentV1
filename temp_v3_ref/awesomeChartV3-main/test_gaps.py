import requests

url = "http://127.0.0.1:8000/api/history?symbol=US30z&timeframe=H1&limit=5000"
response = requests.get(url)
data = response.json()

for i in range(1, len(data)):
    diff = data[i]['time'] - data[i-1]['time']
    if diff > 3600 * 24 * 7: # gap larger than a week
        print(f"Huge gap at index {i}: {diff/3600/24} days")
print("Gap check complete.")
