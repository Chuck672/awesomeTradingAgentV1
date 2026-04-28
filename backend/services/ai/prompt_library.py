from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

DEFAULT_ALERT_ANALYZER_PROMPT = """
你是严格的量化交易审计员（Quant Auditor）。你将收到一个事件上下文 JSON 与 decision_state。

输出要求：
- 只输出一个合法 JSON（不要输出任何额外文本）。
- 字段以运行时 schema/constraints 为准；如果 constraints 缺失，则至少包含：
  signal/confidence_note/entry_type/entry_price/stop_loss/take_profit/risk_reward_ratio/evidence_refs/invalidation_condition/trade_horizon。
- 禁止捏造：所有关键价格与证据必须来自输入 JSON；无法确认时输出 hold 并写明原因。

证据链要求：
- evidence_refs 不允许只给空泛 id：每条必须能定位到输入 JSON 中的对象（zone/break/bos/choch/pattern 等）。
- invalidation_condition 必须写成可复盘的分段报告：
  1) Trigger 解读
  2) 结构证据（>=2）
  3) 指标证据（>=2）
  4) 形态/行为证据（>=1）
  5) 推理链条（因为…所以…）
  6) 执行计划（含确认条件）
  7) 失效条件（绑定具体结构位/zone 边界）
""".strip() + "\n"


@lru_cache(maxsize=8)
def _read_text_cached(path_str: str, mtime_ns: int) -> str:
    p = Path(path_str)
    return p.read_text(encoding="utf-8")


def load_alert_analyzer_prompt() -> str:
    try:
        from backend.services.alerts_store import get_analyzer_system_prompt

        db_text = (get_analyzer_system_prompt() or "").strip()
        if db_text:
            return db_text + "\n"
    except Exception:
        pass

    override = os.environ.get("AWESOMECHART_ALERT_ANALYZER_PROMPT_PATH", "").strip()
    p = Path(override) if override else (_repo_root() / "docs" / "Analyzer_prompts.md")
    try:
        mtime_ns = int(p.stat().st_mtime_ns)
    except Exception:
        mtime_ns = 0
    try:
        text = _read_text_cached(str(p), mtime_ns)
    except Exception:
        return DEFAULT_ALERT_ANALYZER_PROMPT
    text = (text or "").strip()
    return (text + "\n") if text else DEFAULT_ALERT_ANALYZER_PROMPT
