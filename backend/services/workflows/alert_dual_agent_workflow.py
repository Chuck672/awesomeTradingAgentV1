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
        trigger_payload: dict | None = None,
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
            trigger_payload=trigger_payload,
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

        class EntryZone(BaseModel):
            ref: str = Field(description="Anchor id (zone_id/rect_id/te_id)")
            bottom: float = Field(description="Zone bottom price")
            top: float = Field(description="Zone top price")
            timeframe: str = Field(description="Zone timeframe, e.g. M15/H1")

        class PlaybookPlan(BaseModel):
            signal: str = Field(description="Trading bias: buy, sell, or hold")
            playbook: str = Field(description="Selected execution playbook")
            status: str = Field(description="wait or ready")
            entry_type: Optional[str] = Field(None, description="market/limit/stop (ready only)")
            entry_zone: Optional[EntryZone] = Field(None, description="Where to wait for entry")
            entry_price: Optional[float] = Field(None, description="Suggested entry price (ready only)")
            stop_loss: Optional[float] = Field(None, description="Suggested stop loss (ready only)")
            take_profit: Optional[float] = Field(None, description="Suggested take profit (ready only)")
            risk_reward_ratio: Optional[float] = Field(None, description="RR (ready only)")
            confirm_rules: Optional[List[str]] = Field(None, description="Atomic confirm rules list")
            invalidate_rules: Optional[List[str]] = Field(None, description="Atomic invalidation rules list")
            evidence_refs: Optional[List[str]] = Field(None, description="Evidence ids referenced")
            targets: Optional[List[float]] = Field(None, description="Target levels for visualization")

        class AnalyzerPlan(PlaybookPlan):
            confidence_note: str = Field(description="Human-readable confidence assessment and guidance")
            regime: Optional[str] = Field(None, description="Optional market regime label")
            invalidation_condition: Optional[str] = Field(None, description="Global invalidation condition")
            trade_horizon: Optional[str] = Field(None, description="Expected time horizon")
            alternate_plan: Optional[PlaybookPlan] = Field(None, description="Alternate mutually-exclusive plan")

        def _tf_to_seconds(tf: str) -> int:
            t = str(tf or "").upper()
            if t.startswith("M"):
                try:
                    return int(t[1:]) * 60
                except Exception:
                    return 60
            if t.startswith("H"):
                try:
                    return int(t[1:]) * 3600
                except Exception:
                    return 3600
            if t in ("D1", "D"):
                return 86400
            return 60

        def _trigger_family(tt: str) -> str:
            t = str(tt or "").lower()
            if t == "raja_sr_touch":
                return "raja_sr"
            if t == "msb_zigzag_break":
                return "msb_break"
            if t == "consolidation_rectangle_breakout":
                return "consolidation_rectangle"
            if t == "trend_exhaustion":
                return "trend_exhaustion"
            return "generic"

        def _allowed_playbooks(family: str) -> list[str]:
            if family == "raja_sr":
                return ["trend_pullback_limit", "trend_break_retest", "exhaustion_confirmed_reversal", "no_trade"]
            if family == "consolidation_rectangle":
                return ["range_breakout_confirmed", "no_trade"]
            if family == "trend_exhaustion":
                return ["exhaustion_confirmed_reversal", "no_trade"]
            if family == "msb_break":
                return ["trend_pullback_limit", "trend_break_retest", "exhaustion_confirmed_reversal", "no_trade"]
            return ["no_trade"]

        def _anchor_from_context(family: str) -> dict | None:
            ev = context.get("event") if isinstance(context, dict) else None
            if not isinstance(ev, dict):
                return None
            if family == "raja_sr":
                z = ev.get("trigger_zone")
                return z if isinstance(z, dict) else None
            if family == "consolidation_rectangle":
                r = ev.get("trigger_rectangle")
                return r if isinstance(r, dict) else None
            if family == "trend_exhaustion":
                te = ev.get("trigger_te")
                return te if isinstance(te, dict) else None
            return None

        def _make_no_trade(reason: str, *, family: str) -> dict:
            anchor = _anchor_from_context(family)
            ref = ""
            bottom = None
            top = None
            tf = str((context.get("event") or {}).get("exec_tf") or timeframe)
            if isinstance(anchor, dict):
                if family == "raja_sr":
                    ref = str(anchor.get("zone_id") or "")
                    bottom = anchor.get("bottom")
                    top = anchor.get("top")
                    tf = str(anchor.get("timeframe") or tf)
                if family == "consolidation_rectangle":
                    ref = str(anchor.get("rect_id") or "")
                    bottom = anchor.get("bottom")
                    top = anchor.get("top")
                    tf = str(anchor.get("timeframe") or tf)
                if family == "trend_exhaustion":
                    ref = str(anchor.get("te_id") or "")
                    bottom = anchor.get("box_low")
                    top = anchor.get("box_high")
                    tf = str(anchor.get("timeframe") or tf)
            tg: list[float] = []
            try:
                if bottom is not None and float(bottom) > 0:
                    tg.append(float(bottom))
            except Exception:
                pass
            try:
                if top is not None and float(top) > 0 and float(top) not in tg:
                    tg.append(float(top))
            except Exception:
                pass
            plan = {
                "signal": "hold",
                "playbook": "no_trade",
                "status": "wait",
                "entry_type": None,
                "entry_zone": {"ref": ref or "no_trade", "bottom": float(bottom or 0.0), "top": float(top or 0.0), "timeframe": tf} if bottom and top else None,
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward_ratio": None,
                "confirm_rules": [],
                "invalidate_rules": [],
                "evidence_refs": [ref] if ref else [],
                "targets": tg if tg else None,
                "confidence_note": f"no_trade: {reason}",
                "regime": None,
                "invalidation_condition": reason,
                "trade_horizon": str((context.get("event") or {}).get("exec_tf") or timeframe),
                "alternate_plan": None,
            }
            return plan

        family = _trigger_family(trigger_type)
        allowed = _allowed_playbooks(family)
        anchor = _anchor_from_context(family)
        policy = {
            "trigger_family": family,
            "allowed_playbooks": allowed,
            "anchor": anchor,
            "rules": {
                "no_retest_ok": True,
                "no_event_exists": True,
                "require_anchor_ref": True,
                "no_trade_on_violation": True,
            },
        }

        analyzer_prompt_final = (
            analyzer_prompt
            + "\n\nEvent Policy JSON:\n```json\n"
            + json.dumps(policy, ensure_ascii=False)
            + "\n```"
            + "\n\nRules:\n"
            + "- RajaSR trigger: PRIMARY/ALTERNATE 必须围绕 trigger_zone(ref=zone_id) 输出，不允许 range_mean_reversion/range_breakout_confirmed。\n"
            + "- consolidation_rectangle_breakout: 必须围绕 trigger_rectangle(ref=rect_id) 输出。\n"
            + "- trend_exhaustion: 必须围绕 trigger_te(ref=te_id, box_high/box_low) 输出。\n"
            + "- 若违反 allowed_playbooks 或 anchor 约束：输出 playbook=no_trade，并给 targets（至少包含 anchor top/bottom 或 TE box_high/low）。\n"
            + "- confirm_rules/invalidate_rules 禁止 retest_ok/event_exists，只能使用 zone/rectangle/Structure/te.box 这类可落图原子规则。\n"
        )
        
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
            structured_llm = analyzer_llm.with_structured_output(AnalyzerPlan)
            msg = await asyncio.to_thread(
                structured_llm.invoke,
                [
                    HumanMessage(
                        content=(
                            analyzer_prompt_final
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
            analyzer_ms = int((time.perf_counter() - t1) * 1000)
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

        def _has_bad_rule(xs: list[str] | None) -> bool:
            if not isinstance(xs, list):
                return False
            for r in xs:
                s = str(r or "").lower()
                if "retest_ok" in s or "event_exists" in s:
                    return True
            return False

        def _validate_plan(plan: dict) -> dict:
            if not isinstance(plan, dict):
                return _make_no_trade("invalid_plan_type", family=family)
            pb = str(plan.get("playbook") or "")
            if pb not in allowed:
                return _make_no_trade(f"playbook_not_allowed:{pb}", family=family)
            if family == "raja_sr" and pb in ("range_mean_reversion", "range_breakout_confirmed"):
                return _make_no_trade(f"playbook_forbidden:{pb}", family=family)
            ez = plan.get("entry_zone") if isinstance(plan.get("entry_zone"), dict) else None
            if family == "raja_sr":
                z = (context.get("event") or {}).get("trigger_zone") if isinstance((context.get("event") or {}).get("trigger_zone"), dict) else None
                zid = str((z or {}).get("zone_id") or "")
                if not zid or not ez or str(ez.get("ref") or "") != zid:
                    return _make_no_trade("missing_or_mismatched_trigger_zone", family=family)
                alt = plan.get("alternate_plan") if isinstance(plan.get("alternate_plan"), dict) else None
                if not alt:
                    return _make_no_trade("missing_alternate_plan", family=family)
                sig = str(plan.get("signal") or "").lower()
                sig2 = str((alt or {}).get("signal") or "").lower()
                if sig not in ("buy", "sell") or sig2 not in ("buy", "sell") or sig == sig2:
                    return _make_no_trade("alternate_plan_not_opposite", family=family)
                ez2 = alt.get("entry_zone") if isinstance(alt.get("entry_zone"), dict) else None
                if not ez2 or str(ez2.get("ref") or "") != zid:
                    return _make_no_trade("alternate_anchor_mismatch", family=family)
            if family == "consolidation_rectangle":
                r = (context.get("event") or {}).get("trigger_rectangle") if isinstance((context.get("event") or {}).get("trigger_rectangle"), dict) else None
                rid = str((r or {}).get("rect_id") or "")
                if not rid or not ez or str(ez.get("ref") or "") != rid:
                    return _make_no_trade("missing_or_mismatched_trigger_rectangle", family=family)
            if family == "trend_exhaustion":
                te = (context.get("event") or {}).get("trigger_te") if isinstance((context.get("event") or {}).get("trigger_te"), dict) else None
                tid = str((te or {}).get("te_id") or "")
                if not tid or not ez or str(ez.get("ref") or "") != tid:
                    return _make_no_trade("missing_or_mismatched_trigger_te", family=family)
            if _has_bad_rule(plan.get("confirm_rules")) or _has_bad_rule(plan.get("invalidate_rules")):
                return _make_no_trade("contains_unchartable_rules", family=family)
            tg = plan.get("targets")
            if isinstance(tg, list):
                out = []
                for x in tg:
                    try:
                        v = float(x)
                    except Exception:
                        continue
                    if v > 0:
                        out.append(v)
                plan["targets"] = out if out else None
            if pb == "no_trade" and plan.get("targets") is None:
                nt = _make_no_trade("no_trade_missing_targets", family=family)
                nt["playbook"] = "no_trade"
                return nt
            return plan

        analyzer_plan = _validate_plan(analyzer_plan)
        try:
            analyzer_text = json.dumps(analyzer_plan, ensure_ascii=False, indent=2) if analyzer_plan else analyzer_text
        except Exception:
            pass

        def _wait_summary_lines(plan: dict) -> list[str]:
            st = str(plan.get("status") or "").strip().lower()
            if st != "wait":
                return []
            ez = plan.get("entry_zone")
            if not isinstance(ez, dict):
                return []
            try:
                b = float(ez.get("bottom"))
                t = float(ez.get("top"))
            except Exception:
                return []
            if b <= 0 or t <= 0:
                return []
            sig = str(plan.get("signal") or "").strip().lower()
            alt = plan.get("alternate_plan") if isinstance(plan.get("alternate_plan"), dict) else None
            sig2 = str((alt or {}).get("signal") or "").strip().lower() if alt else ""
            upper = "buy" if "buy" in (sig, sig2) else ("sell" if "sell" in (sig, sig2) else "hold")
            lower = "sell" if "sell" in (sig, sig2) else ("buy" if "buy" in (sig, sig2) else "hold")
            out = [f"level-zone:({b:.3f} ~ {t:.3f})"]
            if upper != "hold":
                out.append(f"价格在 level-zone 以上尝试 {upper}")
            if lower != "hold":
                out.append(f"价格在 level-zone 以下尝试 {lower}")
            return out

        report_lines.extend(_wait_summary_lines(analyzer_plan))
        report_lines.append("**AnalyzerPlan (JSON)**:")
        report_lines.append("```json")
        report_lines.append(analyzer_text)
        report_lines.append("```")

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
        telegram_report = "\n\n".join(report_lines[:])
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
                            send_telegram_message, bot_token=token, chat_id=chat_id, text=telegram_report
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
            def _find_zone(zone_id: str) -> dict | None:
                m = context.get("market") if isinstance(context, dict) else None
                inds = (m or {}).get("indicators") if isinstance(m, dict) else None
                if not isinstance(inds, dict):
                    return None
                for tfk, it in inds.items():
                    if not isinstance(it, dict):
                        continue
                    zs = it.get("active_zones")
                    if not isinstance(zs, list):
                        continue
                    for z in zs:
                        if isinstance(z, dict) and str(z.get("evidence_id") or "") == zone_id:
                            return z
                return None

            def _find_rect(rect_id: str) -> dict | None:
                m = context.get("market") if isinstance(context, dict) else None
                pats = (m or {}).get("patterns") if isinstance(m, dict) else None
                if not isinstance(pats, dict):
                    return None
                for tfk, it in pats.items():
                    rr = (it or {}).get("rectangle_ranges") if isinstance(it, dict) else None
                    if not isinstance(rr, list):
                        continue
                    for r in rr:
                        if isinstance(r, dict) and str(r.get("rect_id") or "") == rect_id:
                            return r
                return None

            def _structure_level(tfk: str, key: str) -> float | None:
                m = context.get("market") if isinstance(context, dict) else None
                inds = (m or {}).get("indicators") if isinstance(m, dict) else None
                it = (inds or {}).get(tfk) if isinstance(inds, dict) else None
                adv = (it or {}).get("advanced_indicators") if isinstance(it, dict) else None
                try:
                    v = (adv or {}).get(key) if isinstance(adv, dict) else None
                    return float(v) if v is not None else None
                except Exception:
                    return None

            def _resolve_rule_level(rule: str) -> float | None:
                s = str(rule or "")
                if ":" not in s:
                    return None
                tail = s.split(":", 1)[1]
                if "zone.bottom" in s:
                    z = _find_zone(tail)
                    try:
                        return float(z.get("level_zone_bottom_edge_price")) if isinstance(z, dict) else None
                    except Exception:
                        return None
                if "zone.top" in s:
                    z = _find_zone(tail)
                    try:
                        return float(z.get("level_zone_top_edge_price")) if isinstance(z, dict) else None
                    except Exception:
                        return None
                if "rectangle.bottom" in s:
                    r = _find_rect(tail)
                    try:
                        return float(r.get("bottom")) if isinstance(r, dict) else None
                    except Exception:
                        return None
                if "rectangle.top" in s:
                    r = _find_rect(tail)
                    try:
                        return float(r.get("top")) if isinstance(r, dict) else None
                    except Exception:
                        return None
                if "te.box_high" in s:
                    te = (context.get("event") or {}).get("trigger_te") if isinstance((context.get("event") or {}), dict) else None
                    try:
                        if isinstance(te, dict) and str(te.get("te_id") or "") == tail:
                            return float(te.get("box_high"))
                    except Exception:
                        return None
                if "te.box_low" in s:
                    te = (context.get("event") or {}).get("trigger_te") if isinstance((context.get("event") or {}), dict) else None
                    try:
                        if isinstance(te, dict) and str(te.get("te_id") or "") == tail:
                            return float(te.get("box_low"))
                    except Exception:
                        return None
                if "Structure_High" in s:
                    return _structure_level(tail, "Structure_High")
                if "Structure_Low" in s:
                    return _structure_level(tail, "Structure_Low")
                return None

            def _snapshot_ts() -> int:
                ev = context.get("event") if isinstance(context, dict) else {}
                iso = (ev or {}).get("snapshot_time_iso") if isinstance(ev, dict) else None
                if isinstance(iso, str) and iso:
                    try:
                        from datetime import datetime, timezone

                        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp())
                    except Exception:
                        pass
                return int(time.time())

            def _draw_plan(plan: dict, tag: str, base_color: str) -> None:
                ez = plan.get("entry_zone") if isinstance(plan.get("entry_zone"), dict) else None
                sig = str(plan.get("signal") or "").strip().lower()
                st = str(plan.get("status") or "").strip().lower()
                ts = _snapshot_ts()
                exec_tf = str((context.get("event") or {}).get("exec_tf") or timeframe)
                tf_sec = _tf_to_seconds(exec_tf)
                future_bars = 30

                if isinstance(ez, dict):
                    try:
                        low = float(ez.get("bottom"))
                        high = float(ez.get("top"))
                    except Exception:
                        low = None
                        high = None
                    if low and high and low > 0 and high > 0:
                        objects.append(
                            {
                                "type": "box",
                                "from_time": ts,
                                "to_time": ts + tf_sec * future_bars,
                                "from_price": float(low),
                                "to_price": float(high),
                                "color": base_color,
                                "lineColor": base_color,
                                "lineWidth": 2,
                                "lineStyle": "dashed" if st == "wait" else "solid",
                            }
                        )

                for rr in plan.get("confirm_rules") if isinstance(plan.get("confirm_rules"), list) else []:
                    lvl = _resolve_rule_level(str(rr))
                    if lvl and float(lvl) > 0:
                        objects.append({"type": "hline", "price": float(lvl), "color": "#22c55e", "lineStyle": "dashed", "lineWidth": 2})

                for rr in plan.get("invalidate_rules") if isinstance(plan.get("invalidate_rules"), list) else []:
                    lvl = _resolve_rule_level(str(rr))
                    if lvl and float(lvl) > 0:
                        objects.append({"type": "hline", "price": float(lvl), "color": "#f59e0b", "lineStyle": "dashed", "lineWidth": 2})

                tg = plan.get("targets")
                if isinstance(tg, list):
                    for x in tg:
                        try:
                            v = float(x)
                        except Exception:
                            continue
                        if v > 0:
                            objects.append({"type": "hline", "price": float(v), "color": base_color, "lineStyle": "dotted", "lineWidth": 1})

                pos = "belowBar" if sig == "buy" else "aboveBar"
                objects.append({"type": "marker", "time": ts, "position": pos, "text": f"{tag}:{sig}:{plan.get('playbook')}:{st}", "color": base_color})

                if st == "ready":
                    ep = plan.get("entry_price")
                    sl = plan.get("stop_loss")
                    tp = plan.get("take_profit")
                    try:
                        if ep is not None and float(ep) > 0:
                            objects.append({"type": "hline", "price": float(ep), "color": base_color, "lineStyle": "solid", "lineWidth": 2})
                    except Exception:
                        pass
                    try:
                        if sl is not None and float(sl) > 0:
                            objects.append({"type": "hline", "price": float(sl), "color": "#ef4444", "lineStyle": "solid", "lineWidth": 2})
                    except Exception:
                        pass
                    try:
                        if tp is not None and float(tp) > 0:
                            objects.append({"type": "hline", "price": float(tp), "color": "#22c55e", "lineStyle": "solid", "lineWidth": 2})
                    except Exception:
                        pass

            base = "#3b82f6" if str(analyzer_plan.get("signal") or "").lower() == "buy" else "#ef4444"
            _draw_plan(analyzer_plan, "P", base)
            alt = analyzer_plan.get("alternate_plan") if isinstance(analyzer_plan.get("alternate_plan"), dict) else None
            if alt:
                _draw_plan(alt, "A", "#9ca3af")

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
