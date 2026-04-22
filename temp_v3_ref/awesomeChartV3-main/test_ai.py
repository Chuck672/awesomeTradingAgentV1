import os
import requests
import json
url = "http://127.0.0.1:8000/api/ai/chat"
payload = {
    "input": "关闭所有指标",
    "settings": {
        "base_url": "https://api.openai.com",
        "model": "gpt-4o-mini",
        "api_key": os.environ.get("OPENAI_API_KEY", "sk-")
    },
    "chart_state": {
        "symbol": "XAUUSDz",
        "timeframe": "M5",
        "enabled": {
            "svp": True, "vrvp": True, "bubble": True,
            "RajaSR": True, "RSI": True, "MACD": True,
            "EMA": True, "BB": True, "VWAP": True, "ATR": True
        }
    }
}
try:
    resp = requests.post(url, json=payload)
    print("STATUS:", resp.status_code)
    print("RESPONSE:", json.dumps(resp.json(), ensure_ascii=False, indent=2))
except Exception as e:
    print("ERROR:", str(e))
