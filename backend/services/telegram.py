from __future__ import annotations

import json
import logging
import ssl
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

def _split_telegram_text(text: str, max_len: int) -> list[str]:
    t = str(text or "")
    if not t:
        return [""]
    parts: list[str] = []
    while t:
        if len(t) <= max_len:
            parts.append(t)
            break
        cut = t.rfind("\n", 0, max_len)
        if cut < int(max_len * 0.6):
            cut = max_len
        parts.append(t[:cut])
        t = t[cut:].lstrip("\n")
    return parts


def send_telegram_message(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    timeout_sec: int = 15,
    max_len: int = 3800,
) -> Optional[str]:
    """
    发送 Telegram 消息（MVP：不做重试/队列）。
    返回 message_id（若可解析）。
    """
    token = (bot_token or "").strip()
    cid = (chat_id or "").strip()
    if not token or not cid:
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ctx = ssl.create_default_context()

    last_msg_id: Optional[str] = None
    chunks = _split_telegram_text(text, int(max_len))
    for idx, chunk in enumerate(chunks, start=1):
        prefix = f"[{idx}/{len(chunks)}]\n" if len(chunks) > 1 else ""
        payload = {"chat_id": cid, "text": prefix + chunk, "parse_mode": "Markdown"}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                j = json.loads(raw)
                if isinstance(j, dict) and j.get("ok") and isinstance(j.get("result"), dict):
                    last_msg_id = str(j["result"].get("message_id") or "") or last_msg_id
        except urllib.error.HTTPError as e:
            if e.code == 400:
                logger.warning("telegram_markdown_failed http=400 fallback=plain_text")
                payload["parse_mode"] = ""
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data, method="POST")
                req.add_header("Content-Type", "application/json")
                try:
                    with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
                        raw = resp.read().decode("utf-8", errors="replace")
                        j = json.loads(raw)
                        if isinstance(j, dict) and j.get("ok") and isinstance(j.get("result"), dict):
                            last_msg_id = str(j["result"].get("message_id") or "") or last_msg_id
                except Exception as e2:
                    logger.exception("telegram_plain_text_fallback_failed err=%s", str(e2))
                    raise e2
            else:
                raise e
    return last_msg_id
