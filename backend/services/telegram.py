from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import Optional


def send_telegram_message(*, bot_token: str, chat_id: str, text: str, timeout_sec: int = 15) -> Optional[str]:
    """
    发送 Telegram 消息（MVP：不做重试/队列）。
    返回 message_id（若可解析）。
    """
    token = (bot_token or "").strip()
    cid = (chat_id or "").strip()
    if not token or not cid:
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    ctx = ssl.create_default_context()
    
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            j = json.loads(raw)
            if isinstance(j, dict) and j.get("ok") and isinstance(j.get("result"), dict):
                return str(j["result"].get("message_id") or "")
    except urllib.error.HTTPError as e:
        # If it's a 400 Bad Request, it's almost certainly a Markdown parsing error.
        # Fallback to plain text.
        if e.code == 400:
            print(f"[TELEGRAM] Markdown parsing failed (HTTP 400), falling back to plain text...")
            payload["parse_mode"] = "" # Remove parse_mode
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    j = json.loads(raw)
                    if isinstance(j, dict) and j.get("ok") and isinstance(j.get("result"), dict):
                        return str(j["result"].get("message_id") or "")
            except Exception as e2:
                print(f"[TELEGRAM] Plain text fallback also failed: {e2}")
                raise e2
        else:
            raise e
    return None

