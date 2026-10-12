"""Zavod (distribyutor) paneli."""
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .database import get_db
from .models import (Store, Product, Delivery, Order, OrderStatus,
                     Payment, PayMethod, PayStatus, Role)
from .auth import require_roles
from .dokon_routes import calc_stock, order_dict
from .finance import store_debt
from .schedule import get_settings, window_info, TIME_RE

router = APIRouter(prefix="/zavod", tags=["Zavod paneli"],
                   dependencies=[Depends(require_roles(Role.admin, Role.zavod))])


# ---------- Sxemalar ----------
class DeliveryIn(BaseModel):
    store_id: int
    product_id: int
    quantity: float = Field(gt=0)
    price: float | None = None
    delivered_on: date | None = None


class DeliverOrderIn(BaseModel):
    # {buyurtma_qatori_id: yetkazilgan_miqdor}. Berilmasa, hammasi to'liq yetkaziladi.
    quantities: dict[int, float] | None = None
    delivered_on: date | None = None


class PaymentIn(BaseModel):
    store_id: int
    amount: float = Field(gt=0)
    method: PayMethod = PayMethod.naqd
    paid_on: date | None = None
    note: str = Field(default="", max_length=200)


class SettingsIn(BaseModel):
    order_days: list[int]
    open_time: str
    close_time: str
    min_order_sum: float = Field(default=0, ge=0)
    note: str = Field(default="", max_length=300)


def _get_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")
    return order


# ---------- Sozlamalar (buyurtma kunlari va soatlari) ----------
@router.get("/settings")
def read_settings(db: Session = Depends(get_db)):
    return window_info(get_settings(db))


@router.put("/settings")
def save_settings(data: SettingsIn, db: Session = Depends(get_db)):
    days = sorted(set(data.order_days))
    if any(d < 1 or d > 7 for d in days):
        raise HTTPException(400, "Kunlar 1 (Dushanba) dan 7 (Yakshanba) gacha bo'lishi kerak")
    if not (TIME_RE.match(data.open_time) and TIME_RE.match(data.close_time)):
        raise HTTPException(400, "Vaqtni SS:DD ko'rinishida kiriting (masalan 08:00)")
    if data.open_time >= data.close_time:
        raise HTTPException(400, "Ochilish vaqti yopilish vaqtidan oldin bo'lishi kerak")
    s = get_settings(db)
    s.order_days = ",".join(str(d) for d in days)
    s.open_time, s.close_time = data.open_time, data.close_time
    s.min_order_sum, s.note = data.min_order_sum, data.note
    db.commit()
    return {"detail": "Saqlandi", **window_info(s)}


# ---------- Buyurtmalar ----------
@router.get("/orders")
def list_orders(status: OrderStatus | None = None, store_id: int | None = None,
                db: Session = Depends(get_db)):
    q = select(Order).order_by(Order.id.desc())
    if status:
        q = q.where(Order.status == status)
    if store_id:
        q = q.where(Order.store_id == store_id)
    out = []
    for o in db.scalars(q).all():
        d = order_dict(o)
        d.update(store_id=o.store_id, store=o.store.name, store_phone=o.store.phone)
        out.append(d)
    return out


@router.post("/orders/{order_id}/approve")
def approve_order(order_id: int, db: Session = Depends(get_db)):
    order = _get_order(db, order_id)
    if order.status != OrderStatus.yangi:
        raise HTTPException(400, "Faqat yangi buyurtmani tasdiqlash mumkin")
    order.status = OrderStatus.tasdiqlandi
    db.commit()
    return {"detail": "Buyurtma tasdiqlandi", "id": order.id}


@router.post("/orders/{order_id}/reject")
def reject_order(order_id: int, db: Session = Depends(get_db)):
    order = _get_order(db, order_id)
    if order.status != OrderStatus.yangi:
        raise HTTPException(400, "Faqat yangi buyurtmani rad etish mumkin")
    order.status = OrderStatus.bekor
    db.commit()
    return {"detail": "Buyurtma rad etildi", "id": order.id}


@router.post("/orders/{order_id}/deliver")
def deliver_order(order_id: int, data: DeliverOrderIn | None = None,
                  db: Session = Depends(get_db)):
    """Buyurtmani yetkazish. Do'kon qabul qilgach, buyurtma 'yetkazildi' bo'ladi."""
    data = data or DeliverOrderIn()
    order = _get_order(db, order_id)
    if order.status not in (OrderStatus.yangi, OrderStatus.tasdiqlandi):
        raise HTTPException(400, f"Bu buyurtmani yetkazib bo'lmaydi (holati: {order.status.value})")
    if db.scalar(select(Delivery.id).where(Delivery.order_id == order.id)):
        raise HTTPException(400, "Bu buyurtma uchun yetkazish allaqachon kiritilgan")
    created = 0
    for item in order.items:
        qty = item.quantity
        if data.quantities is not None and item.id in data.quantities:
            qty = data.quantities[item.id]
        if qty <= 0:
            continue
        db.add(Delivery(store_id=order.store_id, product_id=item.product_id, quantity=qty,
                        price=item.price, delivered_on=data.delivered_on or date.today(),
                        order_id=order.id))
        created += 1
    if not created:
        raise HTTPException(400, "Kamida bitta tovar uchun miqdor kiriting")
    order.status = OrderStatus.tasdiqlandi
    db.commit()
    return {"detail": "Yetkazish kiritildi (do'kon qabul qilishi kutilmoqda)"}


# ---------- Yetkazishlar ----------
@router.post("/deliveries")
def add_delivery(data: DeliveryIn, db: Session = Depends(get_db)):
    """Buyurtmasiz, qo'lda yetkazish kiritish."""
    if not db.get(Store, data.store_id):
        raise HTTPException(404, "Do'kon topilmadi")
    product = db.get(Product, data.product_id)
    if not product:
        raise HTTPException(404, "Tovar topilmadi")
    d = Delivery(store_id=data.store_id, product_id=data.product_id, quantity=data.quantity,
                 price=data.price if data.price is not None else product.price,
                 delivered_on=data.delivered_on or date.today())
    db.add(d)
    db.commit()
    return {"detail": "Yetkazish kiritildi (do'kon qabul qilishi kutilmoqda)", "id": d.id}


@router.get("/deliveries")
def list_deliveries(store_id: int | None = None, only_pending: bool = False,
                    db: Session = Depends(get_db)):
    q = select(Delivery).order_by(Delivery.id.desc())
    if store_id:
        q = q.where(Delivery.store_id == store_id)
    if only_pending:
        q = q.where(Delivery.confirmed_by_store.is_(False))
    return [{"id": d.id, "store": d.store.name, "product": d.product.name,
             "unit": d.product.unit, "quantity": d.quantity, "price": d.price,
             "delivered_on": d.delivered_on, "confirmed": d.confirmed_by_store,
             "order_id": d.order_id} for d in db.scalars(q).all()]


# ---------- Do'konlar qoldig'i ----------
@router.get("/stock")
def all_stores_stock(db: Session = Depends(get_db)):
    return [{"store_id": s.id, "store": s.name, "items": calc_stock(db, s.id)}
            for s in db.scalars(select(Store).where(Store.approved.is_(True))).all()]


# ---------- To'lovlar va qarzdorlik ----------
@router.post("/payments")
def add_payment(data: PaymentIn, db: Session = Depends(get_db)):
    """Distribyutor qabul qilgan to'lovni (naqd yoki o'tkazma) kiritadi."""
    if not db.get(Store, data.store_id):
        raise HTTPException(404, "Do'kon topilmadi")
    p = Payment(store_id=data.store_id, amount=data.amount, method=data.method,
                status=PayStatus.tasdiqlandi, paid_on=data.paid_on or date.today(), note=data.note)
    db.add(p)
    db.commit()
    return {"detail": "To'lov saqlandi", "id": p.id, **store_debt(db, data.store_id)}


@router.get("/payments")
def list_payments(store_id: int | None = None, status: PayStatus | None = None,
                  db: Session = Depends(get_db)):
    q = select(Payment).order_by(Payment.id.desc()).limit(200)
    if store_id:
        q = q.where(Payment.store_id == store_id)
    if status:
        q = q.where(Payment.status == status)
    stores = {s.id: s.name for s in db.scalars(select(Store)).all()}
    return [{"id": p.id, "store_id": p.store_id, "store": stores.get(p.store_id),
             "amount": p.amount, "method": p.method, "status": p.status,
             "paid_on": p.paid_on, "note": p.note} for p in db.scalars(q).all()]


def _decide_payment(db: Session, payment_id: int, new_status: PayStatus):
    p = db.get(Payment, payment_id)
    if not p:
        raise HTTPException(404, "To'lov topilmadi")
    if p.status != PayStatus.kutilmoqda:
        raise HTTPException(400, "Bu to'lov allaqachon ko'rib chiqilgan")
    p.status = new_status
    db.commit()
    return {"detail": "Saqlandi", **store_debt(db, p.store_id)}


@router.post("/payments/{payment_id}/confirm")
def confirm_payment(payment_id: int, db: Session = Depends(get_db)):
    return _decide_payment(db, payment_id, PayStatus.tasdiqlandi)


@router.post("/payments/{payment_id}/reject")
def reject_payment(payment_id: int, db: Session = Depends(get_db)):
    return _decide_payment(db, payment_id, PayStatus.rad)


@router.get("/debts")
def all_debts(db: Session = Depends(get_db)):
    rows = [{"store_id": s.id, "store": s.name, **store_debt(db, s.id)}
            for s in db.scalars(select(Store)).all()]
    return {"total_debt": sum(r["debt"] for r in rows), "stores": rows}


# ---------- Bosh sahifa ----------
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    new_orders = db.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.yangi)) or 0
    waiting = db.scalar(select(func.count(Delivery.id)).where(Delivery.confirmed_by_store.is_(False))) or 0
    pending_payments = db.scalar(select(func.count(Payment.id)).where(Payment.status == PayStatus.kutilmoqda)) or 0
    pending_stores = db.scalar(select(func.count(Store.id)).where(Store.approved.is_(False))) or 0
    stores = db.scalars(select(Store).where(Store.approved.is_(True))).all()
    need_restock = []
    for s in stores:
        for r in calc_stock(db, s.id):
            if r["suggested_order"] > 0:
                need_restock.append({"store": s.name, "product": r["product"], "unit": r["unit"],
                                     "remaining": r["remaining"], "suggested_order": r["suggested_order"]})
    return {"new_orders": new_orders, "deliveries_waiting_store_confirmation": waiting,
            "pending_payments": pending_payments, "pending_stores": pending_stores,
            "stores_count": len(stores), "total_debt": store_debt(db)["debt"],
            "need_restock": need_restock}
