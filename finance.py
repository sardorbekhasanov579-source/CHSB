"""Hisob-kitob: do'kon qarzi."""
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .models import Delivery, Payment, PayStatus


def store_debt(db: Session, store_id: int | None = None) -> dict:
    """Qarz = do'kon qabul qilgan tovar summasi - tasdiqlangan to'lovlar.
    store_id berilmasa, hamma do'konlar bo'yicha umumiy hisob."""
    dq = select(func.coalesce(func.sum(Delivery.quantity * Delivery.price), 0)).where(
        Delivery.confirmed_by_store.is_(True))
    pq = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == PayStatus.tasdiqlandi)
    wq = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == PayStatus.kutilmoqda)
    if store_id is not None:
        dq = dq.where(Delivery.store_id == store_id)
        pq = pq.where(Payment.store_id == store_id)
        wq = wq.where(Payment.store_id == store_id)
    total = float(db.scalar(dq) or 0)
    paid = float(db.scalar(pq) or 0)
    pending = float(db.scalar(wq) or 0)
    return {"total_delivered_sum": total, "paid": paid,
            "pending_payments": pending, "debt": total - paid}
