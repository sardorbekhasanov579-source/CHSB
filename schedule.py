"""Buyurtma qabul qilish kunlari va soatlari (O'zbekiston vaqti, UTC+5)."""
import re
from datetime import datetime, timedelta, timezone, time

from sqlalchemy.orm import Session

from .models import Setting

TZ = timezone(timedelta(hours=5))
DAY = {1: "Dushanba", 2: "Seshanba", 3: "Chorshanba", 4: "Payshanba",
       5: "Juma", 6: "Shanba", 7: "Yakshanba"}
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def now_local() -> datetime:
    return datetime.now(TZ)


def get_settings(db: Session) -> Setting:
    s = db.get(Setting, 1)
    if not s:
        s = Setting(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def parse_days(raw: str) -> list[int]:
    return sorted({int(x) for x in raw.split(",") if x.strip().isdigit() and 1 <= int(x) <= 7})


def days_text(days: list[int]) -> str:
    if not days:
        return "belgilanmagan"
    runs, start, prev = [], days[0], days[0]
    for d in days[1:]:
        if d == prev + 1:
            prev = d
            continue
        runs.append((start, prev))
        start = prev = d
    runs.append((start, prev))
    parts = []
    for a, b in runs:
        if a == b:
            parts.append(DAY[a])
        elif b == a + 1:
            parts.append(f"{DAY[a]}, {DAY[b]}")
        else:
            parts.append(f"{DAY[a]}–{DAY[b]}")
    return ", ".join(parts)


def window_info(s: Setting) -> dict:
    now = now_local()
    days = parse_days(s.order_days)
    opens, closes = time.fromisoformat(s.open_time), time.fromisoformat(s.close_time)
    open_now = now.isoweekday() in days and opens <= now.time() <= closes
    message = f"Buyurtma qabul qilish: {days_text(days)}, {s.open_time}–{s.close_time}."
    return {"days": days, "days_text": days_text(days),
            "open_time": s.open_time, "close_time": s.close_time,
            "open_now": open_now, "message": message,
            "min_order_sum": s.min_order_sum, "note": s.note,
            "now": now.strftime("%Y-%m-%d %H:%M")}
