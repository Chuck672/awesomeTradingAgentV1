import asyncio
import logging

from langchain_core.messages import HumanMessage

from backend.services.agents.communication import agent_comm
from backend.services.agents.graph import build_multi_agent_graph

logger = logging.getLogger(__name__)


class TriAgentWorkflow:
    @staticmethod
    async def run(
        *,
        session_id: str,
        initial_message: str,
        configs: dict,
        symbol: str,
        timeframe: str,
        image_data: str | None = None,
    ) -> str:
        logger.info("tri_workflow_start session=%s symbol=%s tf=%s", session_id, symbol, timeframe)

        graph = build_multi_agent_graph(configs)
        context_msg = f"[System Context: User is viewing {symbol} on {timeframe} timeframe]\n\n{initial_message}"

        if image_data:
            image_url = image_data if image_data.startswith("data:image") else f"data:image/png;base64,{image_data}"
            content = [{"type": "text", "text": context_msg}, {"type": "image_url", "image_url": {"url": image_url}}]
            inputs = {"messages": [HumanMessage(content=content)]}
        else:
            inputs = {"messages": [HumanMessage(content=context_msg)]}

        report_lines: list[str] = [f"🚨 **Trigger Event**: {initial_message}"]

        try:
            await agent_comm.broadcast_status(
                session_id, "supervisor", "thinking", "Analyzing task and planning route..."
            )
            async for event in graph.astream(inputs, stream_mode="updates"):
                for node_name, state_update in event.items():
                    if node_name == "supervisor":
                        next_route = state_update.get("next", "FINISH")
                        if next_route == "FINISH":
                            await agent_comm.broadcast_status(
                                session_id, "supervisor", "finished", "Workflow completed."
                            )
                        else:
                            await agent_comm.broadcast_status(
                                session_id, "supervisor", "idle", f"Routing task to {next_route}..."
                            )
                            await agent_comm.broadcast_status(
                                session_id, next_route, "thinking", "Starting work..."
                            )
                    elif node_name in ["analyzer", "executor"]:
                        if "messages" in state_update and len(state_update["messages"]) > 0:
                            last_msg = state_update["messages"][-1]
                            msg_content = last_msg.content

                            if msg_content:
                                report_lines.append(f"**{node_name.capitalize()}**: {msg_content}")

                            ui_actions = last_msg.additional_kwargs.get("ui_actions", [])
                            if not ui_actions:
                                for m in state_update["messages"]:
                                    if getattr(m, "tool_calls", None):
                                        for tc in m.tool_calls:
                                            if tc["name"].startswith(
                                                ("chart_", "draw_", "indicator_", "execute_ui_action")
                                            ):
                                                args = tc.get("args", {})
                                                if "type" in args and "action" not in args:
                                                    args["action"] = args["type"]
                                                if tc["name"] != "execute_ui_action":
                                                    args["action"] = tc["name"]
                                                ui_actions.append(args)

                            for action in ui_actions:
                                report_lines.append(f"🛠️ **Action**: `{action.get('action')}`")
                                await agent_comm.broadcast_tool_execution(
                                    session_id, node_name, action.get("action", "execute_ui_action"), action
                                )

                            await agent_comm.broadcast_status(session_id, node_name, "finished", msg_content)
                            await agent_comm.broadcast_status(session_id, "supervisor", "thinking", "Reviewing results...")

        except asyncio.CancelledError:
            logger.info("tri_workflow_cancelled session=%s", session_id)
            await agent_comm.broadcast_status(
                session_id, "supervisor", "idle", "Workflow was manually stopped by user."
            )
            await agent_comm.broadcast_status(session_id, "analyzer", "idle", "")
            await agent_comm.broadcast_status(session_id, "executor", "idle", "")
            raise
        except Exception as e:
            logger.exception("tri_workflow_failed session=%s err=%s", session_id, str(e))
            await agent_comm.broadcast_status(
                session_id, "supervisor", "error", f"Error occurred: {str(e)}"
            )

        return "\n\n".join(report_lines)

