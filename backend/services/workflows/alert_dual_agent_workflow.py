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
        from typing import Optional, List, Dict, Any, Tuple
        
        class EntryZone(BaseModel):
            bottom: Optional[float] = Field(None, description="Entry zone bottom price")
            top: Optional[float] = Field(None, description="Entry zone top price")
            timeframe: Optional[str] = Field(None, description="Timeframe for this zone (e.g., M15/H1)")
            ref: Optional[str] = Field(None, description="Reference id for this zone (e.g., zone_M15_xxx / rectangle_range)")

        class PlaybookPlan(BaseModel):
            signal: str = Field(description="Trading bias: buy, sell, or hold")
            playbook: Optional[str] = Field(None, description="Selected execution playbook")
            status: Optional[str] = Field(None, description="wait or ready")
            entry_type: Optional[str] = Field(None, description="Type of entry: market, limit, or stop")
            entry_zone: Optional[EntryZone] = Field(None, description="Where to wait for entry")
            entry_price: Optional[float] = Field(None, description="Suggested entry price level")
            stop_loss: Optional[float] = Field(None, description="Suggested stop loss price level")
            take_profit: Optional[float] = Field(None, description="Suggested take profit price level")
            risk_reward_ratio: Optional[float] = Field(None, description="Risk to reward ratio")
            confirm_rules: Optional[List[str]] = Field(None, description="Atomic confirm rules list")
            invalidate_rules: Optional[List[str]] = Field(None, description="Atomic invalidation rules list")
            evidence_refs: Optional[List[str]] = Field(None, description="List of evidence references")

        class AnalyzerPlan(PlaybookPlan):
            confidence_note: str = Field(description="Human-readable confidence assessment and sizing guidance")
            regime: Optional[str] = Field(None, description="Market regime: trend/range/exhaustion")
            invalidation_condition: Optional[str] = Field(None, description="Condition that invalidates the trade")
            trade_horizon: Optional[str] = Field(None, description="Expected time horizon for the trade")
            alternate_plan: Optional[PlaybookPlan] = Field(None, description="Alternate mutually-exclusive plan")

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

        def _normalize_trade_levels(plan: dict) -> dict:
            if not isinstance(plan, dict):
                return plan
            sig = str(plan.get("signal") or "").lower()
            if sig not in ("buy", "sell"):
                return plan

            ep = plan.get("entry_price")
            sl = plan.get("stop_loss")
            tp = plan.get("take_profit")

            try:
                ep_f = float(ep) if ep is not None else None
                sl_f = float(sl) if sl is not None else None
                tp_f = float(tp) if tp is not None else None
            except Exception:
                return plan

            if ep_f is None or not (ep_f == ep_f):
                return plan

            rr = plan.get("risk_reward_ratio")
            try:
                rr_f = float(rr) if rr is not None else None
            except Exception:
                rr_f = None
            if rr_f is not None and (not (rr_f == rr_f) or rr_f <= 0):
                rr_f = None

            def _recompute_rr(_ep: float, _sl: float, _tp: float) -> Optional[float]:
                risk = abs(_ep - _sl)
                reward = abs(_ep - _tp)
                if risk <= 0 or reward <= 0:
                    return None
                return reward / risk

            def _fix_buy() -> Tuple[Optional[float], Optional[float], Optional[float]]:
                _sl = sl_f
                _tp = tp_f
                if _sl is not None and _sl >= ep_f and _tp is not None and _tp > ep_f:
                    if rr_f is None:
                        _sl = ep_f - abs(_tp - ep_f) / 2.0
                    else:
                        _sl = ep_f - abs(_tp - ep_f) / rr_f
                if _tp is not None and _tp <= ep_f and _sl is not None and _sl < ep_f:
                    risk = abs(ep_f - _sl)
                    use_rr = rr_f if rr_f is not None else 2.0
                    _tp = ep_f + risk * use_rr
                if _sl is not None and _sl >= ep_f and _tp is not None and _tp <= ep_f:
                    return None, None, None
                return _sl, _tp, rr_f

            def _fix_sell() -> Tuple[Optional[float], Optional[float], Optional[float]]:
                _sl = sl_f
                _tp = tp_f
                if _sl is not None and _sl > ep_f and _tp is not None and _tp >= ep_f:
                    risk = abs(ep_f - _sl)
                    use_rr = rr_f if rr_f is not None else 2.0
                    _tp = ep_f - risk * use_rr
                if _tp is not None and _tp < ep_f and _sl is not None and _sl <= ep_f:
                    reward = abs(ep_f - _tp)
                    use_rr = rr_f if rr_f is not None else 2.0
                    _sl = ep_f + reward / use_rr
                if _sl is not None and _sl <= ep_f and _tp is not None and _tp >= ep_f:
                    return None, None, None
                return _sl, _tp, rr_f

            if sig == "buy":
                sl2, tp2, _ = _fix_buy()
            else:
                sl2, tp2, _ = _fix_sell()

            if sl2 is None or tp2 is None:
                note = str(plan.get("confidence_note") or "")
                extra = "计划无效：止损/止盈与 signal 方向不一致，已转为 hold。"
                plan["signal"] = "hold"
                plan["confidence_note"] = (note + ("；" if note else "") + extra)[:500]
                plan["entry_type"] = None
                plan["entry_price"] = None
                plan["stop_loss"] = None
                plan["take_profit"] = None
                plan["risk_reward_ratio"] = None
                return plan

            plan["stop_loss"] = float(sl2)
            plan["take_profit"] = float(tp2)
            rr2 = _recompute_rr(ep_f, float(sl2), float(tp2))
            if rr2 is not None:
                plan["risk_reward_ratio"] = float(rr2)
            return plan

        analyzer_plan = _fill_take_profit(analyzer_plan)
        analyzer_plan = _normalize_trade_levels(analyzer_plan)
        try:
            inv = str(analyzer_plan.get("invalidation_condition") or "")
        except Exception:
            inv = ""

        def _parse_playbook_block(block: str) -> dict:
            out: dict[str, Any] = {"confirm_rules": [], "invalidate_rules": []}
            mode = None
            for raw in (block or "").splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.lower().startswith("confirm_rules"):
                    mode = "confirm"
                    continue
                if line.lower().startswith("invalidate_rules"):
                    mode = "invalidate"
                    continue
                if line.startswith("-"):
                    item = line[1:].strip()
                    if not item:
                        continue
                    if mode == "confirm":
                        out["confirm_rules"].append(item)
                    elif mode == "invalidate":
                        out["invalidate_rules"].append(item)
                    continue
                mode = None
                if line.startswith("regime="):
                    out["regime"] = line.split("=", 1)[1].strip()
                elif line.startswith("playbook="):
                    out["playbook"] = line.split("=", 1)[1].strip()
                elif line.startswith("bias="):
                    out["signal"] = line.split("=", 1)[1].strip()
                elif line.startswith("status="):
                    out["status"] = line.split("=", 1)[1].strip()
                elif line.startswith("entry_zone="):
                    try:
                        parts = line.split()
                        ref = parts[0].split("=", 1)[1].strip()
                        bottom = None
                        top = None
                        tf = None
                        for p in parts[1:]:
                            if p.startswith("bottom="):
                                bottom = float(p.split("=", 1)[1])
                            elif p.startswith("top="):
                                top = float(p.split("=", 1)[1])
                            elif p.startswith("tf="):
                                tf = p.split("=", 1)[1].strip()
                        out["entry_zone"] = {"ref": ref or None, "bottom": bottom, "top": top, "timeframe": tf}
                    except Exception:
                        pass
            if not out["confirm_rules"]:
                out["confirm_rules"] = None
            if not out["invalidate_rules"]:
                out["invalidate_rules"] = None
            return out

        def _extract_playbooks_from_text(text: str) -> tuple[dict | None, dict | None, str | None]:
            if not text:
                return None, None, None
            regime = None
            primary = None
            alternate = None
            try:
                if "[REGIME]" in text:
                    seg = text.split("[REGIME]", 1)[1]
                    line0 = seg.strip().splitlines()[0] if seg.strip() else ""
                    if line0.strip().startswith("regime="):
                        regime = line0.split("=", 1)[1].strip()
            except Exception:
                regime = None
            try:
                if "[PRIMARY_PLAYBOOK]" in text:
                    seg = text.split("[PRIMARY_PLAYBOOK]", 1)[1]
                    seg = seg.split("[ALTERNATE_PLAYBOOK]", 1)[0] if "[ALTERNATE_PLAYBOOK]" in seg else seg
                    primary = _parse_playbook_block(seg)
            except Exception:
                primary = None
            try:
                if "[ALTERNATE_PLAYBOOK]" in text:
                    seg = text.split("[ALTERNATE_PLAYBOOK]", 1)[1]
                    seg = seg.split("[EXECUTION]", 1)[0] if "[EXECUTION]" in seg else seg
                    alternate = _parse_playbook_block(seg)
            except Exception:
                alternate = None
            return primary, alternate, regime

        def _ensure_playbook_fields(plan: dict) -> dict:
            if not isinstance(plan, dict):
                return plan
            inv_txt = str(plan.get("invalidation_condition") or "")
            primary, alternate, regime_txt = _extract_playbooks_from_text(inv_txt)
            if plan.get("regime") is None and regime_txt:
                plan["regime"] = regime_txt
            if primary:
                for k in ("playbook", "status", "confirm_rules", "invalidate_rules", "entry_zone"):
                    if plan.get(k) is None and primary.get(k) is not None:
                        plan[k] = primary.get(k)
                if (not plan.get("signal") or str(plan.get("signal")).lower() == "hold") and primary.get("signal"):
                    plan["signal"] = primary.get("signal")
            if plan.get("alternate_plan") is None and alternate:
                plan["alternate_plan"] = alternate
            return plan

        def _enforce_wait(plan: dict) -> dict:
            if not isinstance(plan, dict):
                return plan
            st = str(plan.get("status") or "").strip().lower()
            et = plan.get("entry_type")
            wait = st == "wait" or et is None
            if wait:
                plan["entry_type"] = None
                plan["entry_price"] = None
                plan["stop_loss"] = None
                plan["take_profit"] = None
                plan["risk_reward_ratio"] = None
            alt = plan.get("alternate_plan")
            if isinstance(alt, dict):
                st2 = str(alt.get("status") or "").strip().lower()
                et2 = alt.get("entry_type")
                if st2 == "wait" or et2 is None:
                    alt["entry_type"] = None
                    alt["entry_price"] = None
                    alt["stop_loss"] = None
                    alt["take_profit"] = None
                    alt["risk_reward_ratio"] = None
            return plan

        analyzer_plan = _ensure_playbook_fields(analyzer_plan)
        analyzer_plan = _enforce_wait(analyzer_plan)
        try:
            analyzer_text = json.dumps(analyzer_plan, ensure_ascii=False, indent=2) if analyzer_plan else analyzer_text
        except Exception:
            pass

        analyzer_raw = ""
        try:
            raw_prompt = (
                "你是资深交易分析师。请基于下面的事件触发与上下文，输出一份详细的中文策略报告。\n"
                "你必须严格遵循 AnalyzerPlan(JSON) 的交易参数：signal/entry_type/entry_price/stop_loss/take_profit/risk_reward_ratio/trade_horizon/confidence_note。\n"
                "止损、止盈、入场价、盈亏比不得重新计算，不得给出替代方案（例如 TP1/TP2 或不同的止损止盈），必须与 AnalyzerPlan 数值一致。\n"
                "要求：必须引用输入 JSON 中的具体结构/指标/形态证据（例如 zone/break/bos/choch/pattern 的 id 与关键字段），并用因果链条说明结论。\n"
                "输出使用 Markdown 分段：Trigger 解读/结构证据/指标证据/形态证据/推理链条/执行计划/失效条件。\n"
                "执行计划段必须显式复述 AnalyzerPlan 的入场/止损/止盈/盈亏比，并解释这些数值分别锚定在什么结构/zone/ATR 上。\n"
            )
            raw_msg = await asyncio.to_thread(
                analyzer_llm.invoke,
                [
                    HumanMessage(
                        content=(
                            raw_prompt
                            + "\n\nAnalyzerPlan(JSON):\n```json\n"
                            + json.dumps(analyzer_plan or {}, ensure_ascii=False)
                            + "\n```"
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
                        "confidence_note": analyzer_plan.get("confidence_note"),
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

            def _tf_to_seconds(tf: str) -> int:
                mapping = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
                return int(mapping.get(str(tf or "").upper(), 60))

            def _snapshot_ts() -> int:
                try:
                    q = ((context.get("market_state") or {}).get("current_quote") or {}) if isinstance(context, dict) else {}
                    t = int(q.get("time") or 0)
                    if t > 0:
                        return t
                except Exception:
                    pass
                return int(time.time())

            def _find_zone(zone_id: str) -> tuple[float | None, float | None]:
                if not zone_id:
                    return None, None
                m = (context.get("market") or {}) if isinstance(context, dict) else {}
                inds = (m.get("indicators") or {}) if isinstance(m, dict) else {}
                for tf_, it in inds.items():
                    zlist = (it or {}).get("active_zones") if isinstance(it, dict) else None
                    if not isinstance(zlist, list):
                        continue
                    for z in zlist:
                        if not isinstance(z, dict):
                            continue
                        if str(z.get("evidence_id") or "") == zone_id:
                            try:
                                b = float(z.get("level_zone_bottom_edge_price"))
                                t = float(z.get("level_zone_top_edge_price"))
                                return b, t
                            except Exception:
                                return None, None
                return None, None

            def _find_rectangle(rect_id: str, tf_hint: str | None) -> tuple[float | None, float | None]:
                m = (context.get("market") or {}) if isinstance(context, dict) else {}
                pats = (m.get("patterns") or {}) if isinstance(m, dict) else {}
                tf0 = str(tf_hint or "") or str((context.get("event") or {}).get("exec_tf") or "")
                cand_tfs = [tf0] + [k for k in pats.keys() if k != tf0]
                for tf_ in cand_tfs:
                    p = pats.get(tf_) if isinstance(pats, dict) else None
                    if not isinstance(p, dict):
                        continue
                    rects = p.get("rectangle_ranges")
                    if not isinstance(rects, list) or not rects:
                        continue
                    r0 = rects[0] if isinstance(rects[0], dict) else None
                    if not isinstance(r0, dict):
                        continue
                    try:
                        top = float(r0.get("top"))
                        bottom = float(r0.get("bottom"))
                        return bottom, top
                    except Exception:
                        continue
                return None, None

            def _find_structure_level(tf_: str, kind: str) -> float | None:
                m = (context.get("market") or {}) if isinstance(context, dict) else {}
                inds = (m.get("indicators") or {}) if isinstance(m, dict) else {}
                it = inds.get(tf_) if isinstance(inds, dict) else None
                adv = (it.get("advanced_indicators") or {}) if isinstance(it, dict) else {}
                if not isinstance(adv, dict):
                    return None
                v = adv.get(kind)
                try:
                    return float(v) if v is not None else None
                except Exception:
                    return None

            def _resolve_rule_level(rule: str) -> tuple[str, float] | None:
                r = str(rule or "").strip()
                if not r:
                    return None
                if "zone.top:" in r:
                    zone_id = r.split("zone.top:", 1)[1].strip()
                    b, t = _find_zone(zone_id)
                    if t is not None:
                        return f"zone.top:{zone_id}", float(t)
                    return None
                if "zone.bottom:" in r:
                    zone_id = r.split("zone.bottom:", 1)[1].strip()
                    b, t = _find_zone(zone_id)
                    if b is not None:
                        return f"zone.bottom:{zone_id}", float(b)
                    return None
                if "rectangle.top:" in r:
                    rect_id = r.split("rectangle.top:", 1)[1].strip()
                    b, t = _find_rectangle(rect_id, (context.get("event") or {}).get("exec_tf") if isinstance(context, dict) else None)
                    if t is not None:
                        return f"rectangle.top:{rect_id}", float(t)
                    return None
                if "rectangle.bottom:" in r:
                    rect_id = r.split("rectangle.bottom:", 1)[1].strip()
                    b, t = _find_rectangle(rect_id, (context.get("event") or {}).get("exec_tf") if isinstance(context, dict) else None)
                    if b is not None:
                        return f"rectangle.bottom:{rect_id}", float(b)
                    return None
                if "Structure_High:" in r:
                    tf_ = r.split("Structure_High:", 1)[1].strip()
                    v = _find_structure_level(tf_, "Structure_High")
                    if v is not None:
                        return f"Structure_High:{tf_}", float(v)
                    return None
                if "Structure_Low:" in r:
                    tf_ = r.split("Structure_Low:", 1)[1].strip()
                    v = _find_structure_level(tf_, "Structure_Low")
                    if v is not None:
                        return f"Structure_Low:{tf_}", float(v)
                    return None
                return None

            def _add_playbook_overlay(plan: dict, *, tag: str, base_color: str, fill_opacity: float) -> None:
                if not isinstance(plan, dict):
                    return
                ez = plan.get("entry_zone")
                if isinstance(ez, dict):
                    try:
                        low = float(ez.get("bottom")) if ez.get("bottom") is not None else None
                        high = float(ez.get("top")) if ez.get("top") is not None else None
                    except Exception:
                        low = None
                        high = None
                    if low is not None and high is not None and low > 0 and high > 0:
                        ts = _snapshot_ts()
                        exec_tf = str((context.get("event") or {}).get("exec_tf") or timeframe)
                        tf_sec = _tf_to_seconds(exec_tf)
                        extend_bars = 60
                        from_time = ts - tf_sec * extend_bars
                        to_time = ts
                        objects.append(
                            {
                                "type": "box",
                                "from_time": from_time,
                                "to_time": to_time,
                                "low": min(low, high),
                                "high": max(low, high),
                                "color": base_color,
                                "fillColor": base_color,
                                "fillOpacity": fill_opacity,
                                "lineStyle": "dotted",
                                "lineWidth": 1,
                            }
                        )

                def _rules_list(key: str) -> list[str]:
                    xs = plan.get(key)
                    if isinstance(xs, list):
                        return [str(x) for x in xs if x is not None]
                    return []

                used = set()
                for rr in _rules_list("confirm_rules"):
                    lvl = _resolve_rule_level(rr)
                    if not lvl:
                        continue
                    k, price = lvl
                    if (tag, "c", k) in used:
                        continue
                    used.add((tag, "c", k))
                    objects.append({"type": "hline", "price": float(price), "color": base_color, "lineStyle": "dashed", "lineWidth": 2})

                for rr in _rules_list("invalidate_rules"):
                    lvl = _resolve_rule_level(rr)
                    if not lvl:
                        continue
                    k, price = lvl
                    if (tag, "i", k) in used:
                        continue
                    used.add((tag, "i", k))
                    objects.append({"type": "hline", "price": float(price), "color": "#f59e0b", "lineStyle": "dashed", "lineWidth": 2})

                ts = _snapshot_ts()
                pb = str(plan.get("playbook") or "")
                st = str(plan.get("status") or "")
                sig = str(plan.get("signal") or "")
                pos = "belowBar" if sig.lower() == "buy" else "aboveBar"
                objects.append({"type": "marker", "time": ts, "position": pos, "shape": "circle", "color": base_color, "text": f"{tag}:{sig}:{pb}:{st}"[:60]})

            primary_color = "#3b82f6" if signal == "buy" else ("#ef4444" if signal == "sell" else "#94a3b8")
            _add_playbook_overlay(analyzer_plan, tag="P", base_color=primary_color, fill_opacity=0.10)
            alt = analyzer_plan.get("alternate_plan")
            if isinstance(alt, dict):
                _add_playbook_overlay(alt, tag="A", base_color="#94a3b8", fill_opacity=0.06)
            
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
