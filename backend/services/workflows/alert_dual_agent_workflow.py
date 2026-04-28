import asyncio
import json
import logging
import time

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from backend.services.agents.communication import agent_comm
from backend.services.ai.llm_factory import get_llm
from backend.services.tools.drawing_tools import draw_clear_ai, draw_objects, draw_remove_object

logger = logging.getLogger(__name__)


class AlertDualAgentWorkflow:
    @staticmethod
    async def run(
        *,
        session_id: str,
        initial_message: str,
        configs: dict,
        symbol: str,
        timeframe: str,
        alert_id: int,
        telegram_config: dict | None,
        trigger_type: str,
        trigger_text: str,
    ) -> str:
        report_lines: list[str] = [f"🚨 **Trigger Event**: {initial_message}"]

        await agent_comm.broadcast_status(session_id, "analyzer", "thinking", "Building event context...")
        t0 = time.perf_counter()
        from backend.services.ai.event_context_builder import build_event_context

        context = await asyncio.to_thread(
            build_event_context,
            event_id=session_id,
            trigger_type=trigger_type,
            trigger_text=trigger_text,
            symbol=symbol,
            event_timeframe=timeframe,
            configs=configs,
        )
        t_context_ms = int((time.perf_counter() - t0) * 1000)

        context_json = json.dumps(context, ensure_ascii=False)
        logger.info(
            "event_dual context_built session=%s alert_id=%s symbol=%s tf=%s ms=%s bytes=%s missing=%s",
            session_id,
            alert_id,
            symbol,
            timeframe,
            t_context_ms,
            len(context_json.encode("utf-8")),
            len(context.get("missing_indicators") or []),
        )

        def _extract_json_object(text: str) -> dict | None:
            if not text:
                return None
            try:
                return json.loads(text)
            except Exception:
                pass
            start = text.find("{")
            if start < 0:
                return None
            end = text.rfind("}")
            if end <= start:
                return None
            chunk = text[start : end + 1]
            try:
                return json.loads(chunk)
            except Exception:
                return None

        def _build_default_decision_state(ctx: dict) -> dict:
            ev = (ctx or {}).get("event") or {}
            m = (ctx or {}).get("market") or {}
            ind = (m.get("indicators") or {}) if isinstance(m, dict) else {}
            h1_adv = (ind.get("H1") or {}).get("advanced_indicators") or {}
            m15_adv = (ind.get("M15") or {}).get("advanced_indicators") or {}
            rules: list[str] = []
            h1_low = h1_adv.get("Structure_Low")
            h1_high = h1_adv.get("Structure_High")
            m15_low = m15_adv.get("Structure_Low")
            m15_high = m15_adv.get("Structure_High")
            if h1_low is not None:
                rules.append(f"若价格有效跌破 H1 Structure_Low={h1_low}，多头假设失效，禁止继续做多。")
            if h1_high is not None:
                rules.append(f"若价格有效突破 H1 Structure_High={h1_high}，空头假设失效，禁止继续做空。")
            if m15_low is not None:
                rules.append(f"若价格有效跌破 M15 Structure_Low={m15_low}，短线多头入场条件失效。")
            if m15_high is not None:
                rules.append(f"若价格有效突破 M15 Structure_High={m15_high}，短线空头入场条件失效。")
            return {
                "schema": "event_dual_decision_state_v1",
                "symbol": ev.get("symbol"),
                "exec_tf": ev.get("exec_tf"),
                "trend_tf": ev.get("trend_tf"),
                "position_state": "flat",
                "thesis": "",
                "last_decision": None,
                "invalidation_rules": rules,
            }

        def _normalize_position_state(plan: dict) -> str:
            ps = str(plan.get("position_state") or "").lower()
            if ps in ("flat", "long", "short"):
                return ps
            sig = str(plan.get("signal") or "").lower()
            if sig == "buy":
                return "long"
            if sig == "sell":
                return "short"
            return "flat"

        from backend.services.ai.prompt_library import load_alert_analyzer_prompt

        analyzer_prompt = load_alert_analyzer_prompt()
        if not analyzer_prompt:
            analyzer_prompt = (
                "你是资深技术量化分析师。\n"
                "你将收到一个事件上下文 JSON 与 decision_state。\n"
                "只输出一个合法 JSON，并严格遵循输入 JSON 的 constraints。\n"
            )

        state_exec_tf = (context.get("event") or {}).get("exec_tf") or timeframe
        try:
            from backend.services.alerts_store import get_ai_decision_state

            decision_state = await asyncio.to_thread(get_ai_decision_state, alert_id, symbol, state_exec_tf)
        except Exception:
            decision_state = None
        if not isinstance(decision_state, dict):
            decision_state = _build_default_decision_state(context)

        analyzer_llm = get_llm("analyzer", configs)
        await agent_comm.broadcast_status(session_id, "analyzer", "thinking", "Analyzing event...")
        t1 = time.perf_counter()
        msg = await asyncio.to_thread(
            analyzer_llm.invoke,
            [
                HumanMessage(
                    content=(
                        analyzer_prompt
                        + "\n\nDecision State JSON:\n```json\n"
                        + json.dumps(
                            decision_state,
                            ensure_ascii=False,
                        )
                        + "\n```"
                        + "\n\n事件触发描述:\n"
                        + str(trigger_text)
                        + "\n\n上下文 JSON:\n```json\n"
                        + context_json
                        + "\n```"
                    )
                )
            ],
        )
        analyzer_ms = int((time.perf_counter() - t1) * 1000)
        analyzer_text = getattr(msg, "content", "") or ""
        report_lines.append(f"**Analyzer**: {analyzer_text}")
        await agent_comm.broadcast_status(session_id, "analyzer", "finished", analyzer_text)

        analyzer_plan = _extract_json_object(analyzer_text)
        analyzer_plan_json = ""
        if isinstance(analyzer_plan, dict):
            try:
                analyzer_plan_json = json.dumps(analyzer_plan, ensure_ascii=False)
            except Exception:
                analyzer_plan_json = ""
            try:
                prev = decision_state
                new_state = {
                    **prev,
                    "position_state": _normalize_position_state(analyzer_plan),
                    "last_decision": {
                        "signal": analyzer_plan.get("signal"),
                        "confidence": analyzer_plan.get("confidence"),
                        "evidence_refs": analyzer_plan.get("evidence_refs"),
                        "entry_type": analyzer_plan.get("entry_type"),
                        "entry_price": analyzer_plan.get("entry_price"),
                        "stop_loss": analyzer_plan.get("stop_loss"),
                        "take_profit": analyzer_plan.get("take_profit"),
                        "risk_reward_ratio": analyzer_plan.get("risk_reward_ratio"),
                        "invalidation_condition": analyzer_plan.get("invalidation_condition"),
                        "trade_horizon": analyzer_plan.get("trade_horizon"),
                    },
                }
                from backend.services.alerts_store import save_ai_decision_state

                await asyncio.to_thread(save_ai_decision_state, alert_id, symbol, state_exec_tf, new_state)
            except Exception:
                logger.exception("event_dual decision_state_update_failed session=%s alert_id=%s", session_id, alert_id)

        final_report = "\n\n".join(report_lines)

        try:
            from backend.services.alerts_store import save_ai_report

            save_ai_report(alert_id, session_id, final_report)
        except Exception as e:
            logger.exception(
                "event_dual save_ai_report_failed session=%s alert_id=%s err=%s", session_id, alert_id, str(e)
            )

        telegram_ms = 0
        if telegram_config:
            token = telegram_config.get("token")
            chat_id = telegram_config.get("chat_id")
            if token and chat_id:
                from backend.services.telegram import send_telegram_message

                t_tg = time.perf_counter()
                try:
                    # Fire-and-forget: do not block the UI rendering
                    asyncio.create_task(
                        asyncio.to_thread(
                            send_telegram_message, bot_token=token, chat_id=chat_id, text=final_report
                        )
                    )
                except Exception as e:
                    logger.exception(
                        "event_dual telegram_send_failed session=%s alert_id=%s err=%s",
                        session_id,
                        alert_id,
                        str(e),
                    )
                telegram_ms = int((time.perf_counter() - t_tg) * 1000)

        logger.info(
            "event_dual analyzer_done session=%s alert_id=%s symbol=%s tf=%s context_ms=%s analyzer_ms=%s telegram_ms=%s",
            session_id,
            alert_id,
            symbol,
            timeframe,
            t_context_ms,
            analyzer_ms,
            telegram_ms,
        )

        # 废除 Executor LLM，改用纯代码映射
        await agent_comm.broadcast_status(session_id, "executor", "thinking", "Drawing on chart...")
        t2 = time.perf_counter()
        
        ui_actions: list[dict] = [{"action": "draw_clear_ai"}]
        if isinstance(analyzer_plan, dict):
            objects = []
            ep = _safe_float(analyzer_plan.get("entry_price"))
            sl = _safe_float(analyzer_plan.get("stop_loss"))
            tp = _safe_float(analyzer_plan.get("take_profit"))
            
            # 根据 signal (buy, sell, hold) 决定线型样式
            signal = str(analyzer_plan.get("signal") or "").strip().lower()
            line_style = 2 if signal == "hold" else 0  # Lightweight Charts: 0=Solid(实线), 1=Dotted, 2=Dashed(虚线)

            if ep > 0:
                objects.append({"type": "hline", "price": ep, "color": "#3b82f6", "text": "Entry", "lineStyle": line_style})
            if sl > 0:
                objects.append({"type": "hline", "price": sl, "color": "#ef4444", "text": "SL", "lineStyle": line_style})
            if tp > 0:
                objects.append({"type": "hline", "price": tp, "color": "#22c55e", "text": "TP", "lineStyle": line_style})
            
            if objects:
                ui_actions.append({"action": "draw_objects", "objects": objects})

        executor_ms = int((time.perf_counter() - t2) * 1000)

        for action in ui_actions:
            await agent_comm.broadcast_tool_execution(
                session_id, "executor", action.get("action", "execute_ui_action"), action
            )

        await agent_comm.broadcast_status(session_id, "executor", "finished", "FINISHED")
        logger.info(
            "event_dual executor_done session=%s alert_id=%s symbol=%s tf=%s executor_ms=%s ui_actions=%s",
            session_id,
            alert_id,
            symbol,
            timeframe,
            executor_ms,
            len(ui_actions),
        )

        return final_report
