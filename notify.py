"""Telegram orqali ogohlantirish (ixtiyoriy).
Ishlashi uchun TELEGRAM_BOT_TOKEN va TELEGRAM_CHAT_ID muhit o'zgaruvchilari kerak (run.bat ichida)."""
import os
import json
import threading
import urllib.request


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return  # sozlanmagan bo'lsa, jim o'tib ketadi

    def _send():
        try:
            data = json.dumps({"chat_id": chat_id, "text": text}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:  # ogohlantirish xatosi asosiy ishni to'xtatmasin
            print("Telegram xatosi:", e)

    threading.Thread(target=_send, daemon=True).start()
