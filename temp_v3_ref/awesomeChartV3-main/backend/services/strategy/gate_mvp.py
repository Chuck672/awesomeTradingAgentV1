from __future__ import annotations

from typing import Any, Dict


def suggest_trade_plan_from_evidence(evidence_pack: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stage5 MVP: 基于 EvidencePack 生成一个“可执行结构”的 TradePlan（通用字段）。
    注意：这是确定性模板，用于跑通 Gate→Exec 的结构链路，不追求交易表现。
    """
    facts = evidence_pack.get("facts") if isinstance(evidence_pack.get("facts"), dict) else {}
    direction = str(facts.get("direction") or "")
    symbol = str(evidence_pack.get("symbol") or "")
    timeframe = str(evidence_pack.get("timeframe") or "")
    trigger_time = int(evidence_pack.get("trigger_time") or 0)

    level = float(facts.get("level") or 0.0)
    range_high = float(facts.get("range_high") or 0.0)
    range_low = float(facts.get("range_low") or 0.0)
    close = float(facts.get("close") or 0.0)
    atr = float(facts.get("atr14") or 0.0)

    # 简单止损：放到区间外侧 + 0.2*ATR 作为缓冲；若缺失则 fallback 到 close±ATR
    pad = max(0.2 * atr, 0.0)
    if direction == "long":
        stop = (range_low - pad) if range_low > 0 else (close - max(atr, 0.0))
        entry = close if close > 0 else level
        risk = max(entry - stop, 0.0)
        tp1 = entry + 1.5 * risk if risk > 0 else entry
    else:
        stop = (range_high + pad) if range_high > 0 else (close + max(atr, 0.0))
        entry = close if close > 0 else level
        risk = max(stop - entry, 0.0)
        tp1 = entry - 1.5 * risk if risk > 0 else entry

    plan = {
        "plan_version": "1.0",
        "symbol": symbol,
        "timeframe": timeframe,
        "trigger_time": trigger_time,
        "direction": direction,
        "entry": {
            "type": "market",
            "price_hint": entry,
            "time_in_force": "IOC",
        },
        "risk": {
            "stop_loss": {"price": stop, "type": "hard"},
            "take_profit": [{"price": tp1, "size_pct": 100}],
            "risk_budget_mode": "unset",  # Stage6 接入前可先不自动算仓位
        },
        "constraints": {
            "max_slippage": None,
            "cancel_after_sec": 120,
        },
        "links": {
            "snapshot_id": str(facts.get("snapshot_id") or evidence_pack.get("snapshot_id") or ""),
            "data_version": facts.get("data_version") or evidence_pack.get("data_version") or {},
            "evidence_id": str(evidence_pack.get("rule_id") or ""),
        },
    }
    return plan


def suggest_gate_decision_mvp(evidence_pack: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stage5 MVP: 默认返回 'review'，由用户/后续 agent 决策 pass/reject。
    """
    facts = evidence_pack.get("facts") if isinstance(evidence_pack.get("facts"), dict) else {}
    return {
        "decision_version": "1.0",
        "status": "review",  # review|pass|reject|downgrade
        "reason": str(facts.get("reason") or ""),
        "notes": "",
        "tags": [],
    }

