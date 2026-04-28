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


def _safe_float(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

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

        from pydantic import BaseModel, Field
        from typing import Optional, List
        
        class AnalyzerPlan(BaseModel):
            signal: str = Field(description="Trading signal: buy, sell, or hold")
            confidence: float = Field(description="Confidence score of the signal, 0.0 to 100.0")
            entry_type: Optional[str] = Field(None, description="Type of entry: market, limit, or stop")
            entry_price: Optional[float] = Field(None, description="Suggested entry price level")
            stop_loss: Optional[float] = Field(None, description="Suggested stop loss price level")
            take_profit: Optional[float] = Field(None, description="Suggested take profit price level")
            risk_reward_ratio: Optional[float] = Field(None, description="Risk to reward ratio")
            evidence_refs: Optional[List[str]] = Field(None, description="List of evidence references")
            invalidation_condition: Optional[str] = Field(None, description="Condition that invalidates the trade")
            trade_horizon: Optional[str] = Field(None, description="Expected time horizon for the trade")

        try:
            # 引入 Structured Output 强制约束输出格式，杜绝解析异常
            structured_llm = analyzer_llm.with_structured_output(AnalyzerPlan)
            msg = await asyncio.to_thread(
                structured_llm.invoke,
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
            
            # 由于使用的是 Structured Output，msg 直接是 AnalyzerPlan 对象
            if msg:
                analyzer_plan = msg.model_dump()
                analyzer_text = json.dumps(analyzer_plan, ensure_ascii=False, indent=2)
            else:
                analyzer_plan = {}
                analyzer_text = "{}"
        except Exception as e:
            logger.exception("event_dual analyzer_structured_output_failed session=%s err=%s", session_id, str(e))
            analyzer_ms = int((time.perf_counter() - t1) * 1000)
            analyzer_plan = {}
            analyzer_text = f"{{\"error\": \"{str(e)}\"}}"

        def _fill_take_profit(plan: dict) -> dict:
            if not isinstance(plan, dict):
                return plan
            sig = str(plan.get("signal") or "").lower()
            if sig not in ("buy", "sell"):
                return plan
            tp = plan.get("take_profit")
            if tp is not None:
                return plan
            ep = plan.get("entry_price")
            sl = plan.get("stop_loss")
            if ep is None or sl is None:
                return plan
            rr = plan.get("risk_reward_ratio")
            try:
                rr_f = float(rr) if rr is not None else 2.0
            except Exception:
                rr_f = 2.0
            rr_f = rr_f if rr_f > 0 else 2.0
            try:
                ep_f = float(ep)
                sl_f = float(sl)
            except Exception:
                return plan
            risk = abs(ep_f - sl_f)
            if risk <= 0:
                return plan
            if sig == "buy":
                plan["take_profit"] = ep_f + risk * rr_f
            else:
                plan["take_profit"] = ep_f - risk * rr_f
            plan["risk_reward_ratio"] = rr_f
            return plan

        analyzer_plan = _fill_take_profit(analyzer_plan)
        try:
            analyzer_text = json.dumps(analyzer_plan, ensure_ascii=False, indent=2) if analyzer_plan else analyzer_text
        except Exception:
            pass

        analyzer_raw = ""
        try:
            raw_prompt = (
                "你是资深交易分析师。请基于下面的事件触发与上下文，输出一份详细的中文策略报告。\n"
                "要求：必须引用输入 JSON 中的具体结构/指标/形态证据（例如 zone/break/bos/choch/pattern 的 id 与关键字段），并用因果链条说明结论。\n"
                "输出使用 Markdown 分段：Trigger 解读/结构证据/指标证据/形态证据/推理链条/执行计划/失效条件。\n"
            )
            raw_msg = await asyncio.to_thread(
                analyzer_llm.invoke,
                [
                    HumanMessage(
                        content=(
                            raw_prompt
                            + "\n\nDecision State JSON:\n```json\n"
                            + json.dumps(decision_state, ensure_ascii=False)
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
            analyzer_raw = str(getattr(raw_msg, "content", "") or "").strip()
        except Exception as e:
            logger.exception("event_dual analyzer_raw_failed session=%s err=%s", session_id, str(e))
            analyzer_raw = f"(analyzer_raw_failed) {str(e)}"

        report_lines.append("**AnalyzerPlan (JSON)**:")
        report_lines.append("```json")
        report_lines.append(analyzer_text)
        report_lines.append("```")
        if analyzer_raw:
            report_lines.append("**AnalyzerRaw (Full Reply)**:")
            report_lines.append(analyzer_raw)
        await agent_comm.broadcast_status(session_id, "analyzer", "finished", analyzer_text)

        analyzer_plan_json = ""
        if isinstance(analyzer_plan, dict) and analyzer_plan:
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
