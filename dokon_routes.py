"""Do'kon (buyurtmachi) ilovasi."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .database import get_db
from .models import (User, Store, Product, Delivery, Sale, Order, OrderItem,
                     OrderStatus, Payment, PayMethod, PayStatus, Role)
from .auth import require_roles
from .notify import send_telegram
from .schedule import get_settings, window_info, now_local
from .finance import store_debt

router = APIRouter(prefix="/dokon", tags=["Do'kon ilovasi"])
dokon_user = Depends(require_roles(Role.dokon))


# ---------- Yordamchi funksiyalar ----------
def get_my_store(user: User, db: Session, need_approved: bool = True) -> Store:
    store = db.scalar(select(Store).where(Store.user_id == user.id))
    if not store:
        raise HTTPException(404, "Sizga do'kon biriktirilmagan. Admin bilan bog'laning.")
    if need_approved and not store.approved:
        raise HTTPException(403, "Hisobingiz hali tasdiqlanmagan. Distribyutor tasdiqlashini kuting.")
    return store


def _sum_by_product(db: Session, model, store_id: int, *extra):
    q = (select(model.product_id, func.sum(model.quantity))
         .where(model.store_id == store_id, *extra)
         .group_by(model.product_id))
    return {pid: float(total) for pid, total in db.execute(q).all()}


def calc_stock(db: Session, store_id: int):
    """Qoldiq = tasdiqlangan yetkazilgan - sotilgan."""
    delivered = _sum_by_product(db, Delivery, store_id, Delivery.confirmed_by_store.is_(True))
    sold = _sum_by_product(db, Sale, store_id)
    since = date.today() - timedelta(days=7)
    sold_7d = _sum_by_product(db, Sale, store_id, Sale.sold_on >= since)

    rows = []
    products = db.scalars(select(Product).where(
        Product.id.in_(set(delivered) | set(sold)))).all()
    for p in products:
        d, s, s7 = delivered.get(p.id, 0), sold.get(p.id, 0), sold_7d.get(p.id, 0)
        left = d - s
        rows.append({
            "product_id": p.id, "product": p.name, "unit": p.unit,
            "delivered": d, "sold": s, "remaining": left,
            "sold_last_7_days": s7,
            "suggested_order": round(max(0.0, s7 - left), 2),
        })
    return rows


def order_dict(o: Order) -> dict:
    return {
        "id": o.id, "status": o.status, "note": o.note,
        "payment_method": o.payment_method, "wanted_date": o.wanted_date,
        "created_at": o.created_at,
        "total": sum(i.quantity * i.price for i in o.items),
        "items": [{"id": i.id, "product_id": i.product_id, "product": i.product.name,
                   "unit": i.product.unit, "quantity": i.quantity, "price": i.price}
                  for i in o.items],
    }


# ---------- Sxemalar ----------
class SaleIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)
    sold_on: date | None = None


class OrderItemIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)


class OrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1)
    payment_method: PayMethod = PayMethod.naqd
    wanted_date: date | None = None
    note: str = Field(default="", max_length=200)


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: PayMethod = PayMethod.naqd
    note: str = Field(default="", max_length=200)


# ---------- Profil va jadval ----------
@router.get("/me")
def my_profile(db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db, need_approved=False)
    return {"full_name": user.full_name,
            "store": {"id": store.id, "name": store.name, "address": store.address,
                      "phone": store.phone, "approved": store.approved}}


@router.get("/schedule")
def schedule(db: Session = Depends(get_db), user: User = dokon_user):
    return window_info(get_settings(db))


# ---------- Katalog ----------
@router.get("/catalog")
def catalog(db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    left = {r["product_id"]: r["remaining"] for r in calc_stock(db, store.id)}
    products = db.scalars(select(Product).where(Product.is_active.is_(True))
                          .order_by(Product.category, Product.name)).all()
    return [{"id": p.id, "name": p.name, "unit": p.unit, "price": p.price,
             "category": p.category, "description": p.description,
             "remaining": left.get(p.id, 0)} for p in products]


# ---------- Buyurtmalar ----------
@router.post("/orders")
def create_order(data: OrderIn, db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    setting = get_settings(db)
    info = window_info(setting)
    if not info["open_now"]:
        raise HTTPException(400, f"Hozir buyurtma qabul qilinmaydi. {info['message']}")

    merged: dict[int, float] = {}
    for it in data.items:
        merged[it.product_id] = merged.get(it.product_id, 0) + it.quantity
    products = {p.id: p for p in db.scalars(
        select(Product).where(Product.id.in_(list(merged)))).all()}
    lines = []
    for pid, qty in merged.items():
        p = products.get(pid)
        if not p or not p.is_active:
            raise HTTPException(404, "Tovar topilmadi yoki hozir sotuvda yo'q")
        lines.append((p, qty))

    total = sum(p.price * q for p, q in lines)
    if setting.min_order_sum and total < setting.min_order_sum:
        raise HTTPException(400, f"Minimal buyurtma summasi: {setting.min_order_sum:g} so'm")
    if data.wanted_date and data.wanted_date < now_local().date():
        raise HTTPException(400, "Yetkazish sanasi o'tib ketgan")

    order = Order(store_id=store.id, payment_method=data.payment_method,
                  wanted_date=data.wanted_date, note=data.note)
    order.items = [OrderItem(product_id=p.id, quantity=q, price=p.price) for p, q in lines]
    db.add(order)
    db.commit()

    text = [f"Yangi buyurtma #{order.id}", f"Do'kon: {store.name}"]
    text += [f"- {p.name}: {q:g} {p.unit}" for p, q in lines]
    text.append(f"Jami: {total:,.0f} so'm".replace(",", " "))
    text.append(f"To'lov: {data.payment_method.value}")
    if data.wanted_date:
        text.append(f"Kerakli sana: {data.wanted_date}")
    if data.note:
        text.append(f"Izoh: {data.note}")
    send_telegram("\n".join(text))
    return {"detail": "Buyurtma yuborildi", "id": order.id, "total": total}


@router.get("/orders")
def my_orders(db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    q = select(Order).where(Order.store_id == store.id).order_by(Order.id.desc())
    return [order_dict(o) for o in db.scalars(q).all()]


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    o = db.get(Order, order_id)
    if not o or o.store_id != store.id:
        raise HTTPException(404, "Buyurtma topilmadi")
    if o.status != OrderStatus.yangi:
        raise HTTPException(400, "Faqat yangi buyurtmani bekor qilish mumkin")
    o.status = OrderStatus.bekor
    db.commit()
    return {"detail": "Buyurtma bekor qilindi"}


@router.post("/orders/{order_id}/receive")
def receive_order(order_id: int, db: Session = Depends(get_db), user: User = dokon_user):
    """Buyurtma bo'yicha yetkazilgan hamma tovarni qabul qilish."""
    store = get_my_store(user, db)
    o = db.get(Order, order_id)
    if not o or o.store_id != store.id:
        raise HTTPException(404, "Buyurtma topilmadi")
    pending = db.scalars(select(Delivery).where(
        Delivery.order_id == o.id, Delivery.confirmed_by_store.is_(False))).all()
    if not pending:
        raise HTTPException(400, "Qabul qilinadigan yetkazish yo'q")
    for d in pending:
        d.confirmed_by_store = True
    o.status = OrderStatus.yetkazildi
    db.commit()
    return {"detail": "Qabul qilindi"}


# ---------- Yetkazishlar ----------
@router.get("/deliveries")
def my_deliveries(only_pending: bool = False, db: Session = Depends(get_db),
                  user: User = dokon_user):
    store = get_my_store(user, db)
    q = select(Delivery).where(Delivery.store_id == store.id).order_by(Delivery.id.desc())
    if only_pending:
        q = q.where(Delivery.confirmed_by_store.is_(False))
    return [{"id": d.id, "order_id": d.order_id, "product": d.product.name,
             "unit": d.product.unit, "quantity": d.quantity, "price": d.price,
             "delivered_on": d.delivered_on, "confirmed": d.confirmed_by_store}
            for d in db.scalars(q).all()]


@router.post("/deliveries/{delivery_id}/confirm")
def confirm_delivery(delivery_id: int, db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    d = db.get(Delivery, delivery_id)
    if not d or d.store_id != store.id:
        raise HTTPException(404, "Yetkazish topilmadi")
    if d.confirmed_by_store:
        raise HTTPException(400, "Bu yetkazish allaqachon tasdiqlangan")
    d.confirmed_by_store = True
    db.flush()
    if d.order_id:
        left = db.scalar(select(func.count(Delivery.id)).where(
            Delivery.order_id == d.order_id, Delivery.confirmed_by_store.is_(False)))
        order = db.get(Order, d.order_id)
        if order and not left:
            order.status = OrderStatus.yetkazildi
    db.commit()
    return {"detail": "Qabul qilindi", "id": d.id}


# ---------- Qoldiq va sotuv ----------
@router.get("/stock")
def my_stock(db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    return {"store": store.name, "items": calc_stock(db, store.id)}


@router.post("/sales")
def add_sale(data: SaleIn, db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    if not db.get(Product, data.product_id):
        raise HTTPException(404, "Tovar topilmadi")
    sold_on = data.sold_on or date.today()
    if sold_on > date.today():
        raise HTTPException(400, "Kelajak sanasi bilan sotuv kiritib bo'lmaydi")
    left = next((r["remaining"] for r in calc_stock(db, store.id)
                 if r["product_id"] == data.product_id), 0)
    if data.quantity > left:
        raise HTTPException(400, f"Qoldiq yetarli emas. Hozir qoldiq: {left:g}")
    sale = Sale(store_id=store.id, product_id=data.product_id,
                quantity=data.quantity, sold_on=sold_on)
    db.add(sale)
    db.commit()
    return {"detail": "Sotuv saqlandi", "id": sale.id, "remaining": left - data.quantity}


@router.get("/sales")
def my_sales(date_from: date | None = None, date_to: date | None = None,
             db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    q = select(Sale).where(Sale.store_id == store.id).order_by(Sale.sold_on.desc(), Sale.id.desc())
    if date_from:
        q = q.where(Sale.sold_on >= date_from)
    if date_to:
        q = q.where(Sale.sold_on <= date_to)
    return [{"id": s.id, "product": s.product.name, "unit": s.product.unit,
             "quantity": s.quantity, "sold_on": s.sold_on}
            for s in db.scalars(q).all()]


# ---------- To'lov va qarz ----------
@router.get("/debt")
def my_debt(db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    return store_debt(db, store.id)


@router.post("/payments")
def report_payment(data: PaymentIn, db: Session = Depends(get_db), user: User = dokon_user):
    """Do'kon to'lov qilganini xabar qiladi. Distribyutor tasdiqlagach qarzdan ayriladi."""
    store = get_my_store(user, db)
    p = Payment(store_id=store.id, amount=data.amount, method=data.method,
                status=PayStatus.kutilmoqda, note=data.note)
    db.add(p)
    db.commit()
    send_telegram(f"To'lov xabari\nDo'kon: {store.name}\nSumma: {data.amount:,.0f} so'm".replace(",", " ")
                  + f"\nUsul: {data.method.value}" + (f"\nIzoh: {data.note}" if data.note else "")
                  + "\nTasdiqlash kerak.")
    return {"detail": "To'lov haqida xabar yuborildi", "id": p.id}


@router.get("/payments")
def my_payments(db: Session = Depends(get_db), user: User = dokon_user):
    store = get_my_store(user, db)
    q = select(Payment).where(Payment.store_id == store.id).order_by(Payment.id.desc())
    return [{"id": p.id, "amount": p.amount, "method": p.method, "status": p.status,
             "paid_on": p.paid_on, "note": p.note} for p in db.scalars(q).all()]
