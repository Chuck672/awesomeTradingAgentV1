import requests

url = "http://127.0.0.1:8000/api/history?symbol=XAUUSDz&timeframe=H1&limit=5000"
response = requests.get(url)
data = response.json()

if not data:
    print("No data for XAUUSDz")
else:
    print(f"Total records: {len(data)}")
    # Check order
    out_of_order = 0
    for i in range(1, len(data)):
        if data[i]['time'] <= data[i-1]['time']:
            out_of_order += 1
            if out_of_order < 5:
                print(f"Out of order at index {i}: {data[i-1]['time']} -> {data[i]['time']}")
    print(f"Total out of order: {out_of_order}")
    
    gaps = 0
    for i in range(1, len(data)):
        diff = data[i]['time'] - data[i-1]['time']
        if diff > 3600 * 24 * 7: # gap larger than a week
            gaps += 1
            if gaps < 5:
                print(f"Huge gap at index {i}: {diff/3600/24} days")
    print(f"Total huge gaps: {gaps}")
