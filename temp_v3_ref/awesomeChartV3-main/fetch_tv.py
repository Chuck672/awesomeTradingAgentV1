import json
import re

with open('tv_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

# TradingView stores state in a json-like object inside window.initData
match = re.search(r'("scriptSource":\s*".*?")', html)
if match:
    json_str = '{' + match.group(1) + '}'
    try:
        obj = json.loads(json_str)
        with open('mstm_source.pine', 'w', encoding='utf-8') as f:
            f.write(obj['scriptSource'])
        print("Successfully extracted scriptSource.")
    except Exception as e:
        print("Failed to parse json:", e)
else:
    print("Could not find scriptSource.")
