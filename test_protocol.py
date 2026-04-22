import asyncio
import json
import uuid
import websockets
import httpx

async def test_tool_execution_flow():
    session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    # 模拟前端的 WebSocket 路径格式 (需要带有 symbol 和 timeframe)
    ws_url = "ws://127.0.0.1:8000/api/ws/XAUUSDz/M15"
    api_url = "http://127.0.0.1:8000/api/agent/trigger_decision"

    print(f"Connecting to WebSocket: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as ws:
            print("✅ WebSocket connected.")
            
            # Start a background task to listen to messages
            async def listen():
                tool_execution_count = 0
                final_text_received = False
                
                while True:
                    try:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        msg_type = data.get("type")
                        
                        # 过滤掉来自行情数据引擎的更新事件，只关注 agent_status 和 tool_execution
                        if msg_type == "update":
                            continue
                            
                        if msg_type == "agent_status":
                            agent = data.get('current_agent')
                            status = data.get('status')
                            text = data.get('latest_message', '')
                            
                            print(f"[WS] Status -> {agent}: {status}")
                            
                            # 检查 1: 确保 Executor 的回复文本中没有 JSON 代码块
                            if agent == "executor" and status == "finished":
                                final_text_received = True
                                print(f"\n[TEXT CHECK] Executor's final message: \n{text}\n")
                                if "```json" in text or "{" in text:
                                    print("❌ [WARNING] Executor's text message STILL contains JSON traces! Backend parsing might be incomplete.")
                                else:
                                    print("✅ [TEXT CHECK PASSED] Executor's text is clean.")
                            
                            if status == "finished" and agent == "supervisor":
                                print("✅ Workflow Finished.")
                                return tool_execution_count > 0 and final_text_received
                                
                        elif msg_type == "tool_execution":
                            tool_execution_count += 1
                            print(f"\n🎉 [WS] SUCCESS! Received TOOL_EXECUTION event #{tool_execution_count}:\n{json.dumps(data, indent=2, ensure_ascii=False)}\n")
                            
                            # 检查 2: 验证 payload 是否满足前端 drawObjects 的要求
                            payload = data.get("payload", {})
                            if not ("action" in payload or "type" in payload):
                                print("❌ [WARNING] Tool payload is missing 'action' or 'type' field. Frontend will ignore it!")
                            else:
                                print("✅ [PAYLOAD CHECK PASSED] Payload format is valid for frontend.")
                                
                        else:
                            print(f"[WS] Unknown event: {data}")
                    except Exception as e:
                        print(f"WS Error: {e}")
                        break
            
            listener_task = asyncio.create_task(listen())
            
            # Send HTTP request to trigger the agent
            payload = {
                "session_id": session_id,
                "message": "在价格 4750.0 处画一条支撑线，并且在时间戳 1776826800 处标记一个 Buy 图标。",
                "symbol": "XAUUSDz",
                "timeframe": "M15",
                "configs": {
                    "supervisor": {"base_url": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V3", "api_key": "sk-lndylrnzgtughmniqttzlpjejznzcxgqllzidhdzimwwurji"},
                    "analyzer": {"base_url": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V3", "api_key": "sk-lndylrnzgtughmniqttzlpjejznzcxgqllzidhdzimwwurji"},
                    "executor": {"base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen3.5-35B-A3B", "api_key": "sk-lndylrnzgtughmniqttzlpjejznzcxgqllzidhdzimwwurji"}
                }
            }
            
            print(f"Triggering decision API for session: {session_id}...")
            async with httpx.AsyncClient() as client:
                resp = await client.post(api_url, json=payload, timeout=10)
                print(f"API Response: {resp.status_code} - {resp.json()}")
            
            # Wait for workflow to finish
            success = await listener_task
            
            if success:
                print("\n✅ TEST PASSED: The new protocol architecture is working perfectly.")
            else:
                print("\n❌ TEST FAILED: Did not receive the `tool_execution` event from the backend.")
                
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_tool_execution_flow())
