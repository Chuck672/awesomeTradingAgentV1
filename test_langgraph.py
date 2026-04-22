import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.services.agents.graph import build_multi_agent_graph
from langchain_core.messages import HumanMessage

async def main():
    print("=== Testing LangGraph Multi-Agent Architecture ===")
    graph = build_multi_agent_graph()
    
    # Simulate an event trigger or a user request
    inputs = {
        "messages": [HumanMessage(content="The price just touched the RajaSR resistance level. Please analyze the context and draw a marker if it's a good short setup.")]
    }
    
    print("Starting execution...\n")
    # Stream the graph execution
    async for event in graph.astream(inputs, stream_mode="updates"):
        for node_name, state_update in event.items():
            print(f"--- Node [{node_name}] executed ---")
            if "messages" in state_update:
                for msg in state_update["messages"]:
                    print(f"Message from {msg.name if hasattr(msg, 'name') and msg.name else node_name}:\n{msg.content}\n")
            if "next" in state_update:
                print(f"Supervisor routed to: {state_update['next']}\n")

if __name__ == "__main__":
    asyncio.run(main())
