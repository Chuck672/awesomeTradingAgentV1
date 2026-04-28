import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.services.chart_scene.indicators import (
    calc_volume_profile,
    calc_raja_sr,
    calc_msb_zigzag,
    calc_trend_exhaustion
)
from backend.services.ai.agent_context_builder import build_agent_context
from backend.services.ai.agent_tools import analyzer_tool_schemas, executor_tool_schemas

def test_indicators():
    print("=== Testing Python Indicators ===")
    
    # Generate some dummy trending up data
    bars = []
    base_price = 1.1000
    for i in range(100):
        # Create a basic zigzag up trend
        trend = i * 0.0010
        noise = (i % 5) * 0.0020
        high = base_price + trend + noise + 0.0010
        low = base_price + trend + noise - 0.0010
        open_p = base_price + trend + noise
        close_p = base_price + trend + noise + 0.0005
        bars.append({
            "time": 1600000000 + i * 3600,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close_p,
            "volume": 100 + (i % 10) * 10
        })

    # 1. Volume Profile
    vp = calc_volume_profile(bars)
    print("\n[Volume Profile]")
    print(f"POC: {vp['pocPrice']:.4f}, VAL: {vp['valueAreaLow']:.4f}, VAH: {vp['valueAreaHigh']:.4f}")
    assert vp["pocPrice"] > 0
    
    # 2. Raja SR
    raja = calc_raja_sr(bars)
    print("\n[Raja SR Zones]")
    print(f"Found {len(raja)} zones.")
    for z in raja[:2]:
        print(f"- {z['type']}: {z['bottom']:.4f} - {z['top']:.4f} (touches: {z['touches']})")
        
    # 3. MSB ZigZag
    msb = calc_msb_zigzag(bars)
    print("\n[MSB ZigZag (BoS/ChoCh)]")
    for line in msb["lines"]:
        print(f"- {line['type']} at {line['level']:.4f}")
        
    # 4. Trend Exhaustion
    te = calc_trend_exhaustion(bars)
    print("\n[Trend Exhaustion]")
    print(f"Is OB: {te['is_overbought']}, Is OS: {te['is_oversold']}")

    print("\n=== Testing Context Builder ===")
    context_json = build_agent_context(bars)
    ctx = json.loads(context_json)
    print(f"Current Price: {ctx['current_price']:.4f}")
    print(f"Market Structure: {ctx['advanced_indicators']['Market_Structure']}")
    print(f"Nearest Resistance: {ctx['advanced_indicators']['Nearest_Resistance']}")
    print(f"Nearest Support: {ctx['advanced_indicators']['Nearest_Support']}")
    
    print("\n=== Testing Tool Schemas ===")
    print(f"Analyzer Tools Count: {len(analyzer_tool_schemas())}")
    print(f"Executor Tools Count: {len(executor_tool_schemas())}")

if __name__ == "__main__":
    test_indicators()
