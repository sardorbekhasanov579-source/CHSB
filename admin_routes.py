"""Admin paneli: foydalanuvchilar, do'konlar, tovarlar, umumiy ko'rsatkichlar, hisobot."""
import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .database import get_db
from .models import (User, Store, Product, Delivery, Sale, Order, Payment, PayStatus, Role)
from .auth import (require_roles, current_user, hash_password, verify_password)
from .finance import store_debt

router = APIRouter(prefix="/admin", tags=["Admin kabinasi"],
                   dependencies=[Depends(require_roles(Role.admin))])
account_router = APIRouter(prefix="/auth", tags=["Hisob"])


# ---------- Sxemalar ----------
class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    role: Role | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=6)


class StoreUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    user_id: int | None = None      # null yuborilsa, foydalanuvchi ajratiladi
    approved: bool | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    price: float | None = Field(default=None, ge=0)
    category: str | None = None
    description: str | None = None
    is_active: bool | None = None


class ChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


# ---------- Hisob (hamma rollar uchun) ----------
@account_router.post("/change-password")
def change_password(data: ChangePassword, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(400, "Joriy parol noto'g'ri")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"detail": "Parol o'zgartirildi"}


# ---------- Foydalanuvchilar ----------
@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db),
                me: User = Depends(current_user)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    changes = data.model_dump(exclude_unset=True)
    if u.id == me.id and (changes.get("is_active") is False or
                          ("role" in changes and changes["role"] != Role.admin)):
        raise HTTPException(400, "O'zingizni bloklab yoki rolingizni o'zgartirib bo'lmaydi")
    if "role" in changes and changes["role"] != Role.dokon:
        if db.scalar(select(Store.id).where(Store.user_id == u.id)):
            raise HTTPException(400, "Bu foydalanuvchi do'konga biriktirilgan. Avval do'kondan ajrating")
    for k, v in changes.items():
        if v is not None:
            setattr(u, k, v)
    db.commit()
    return {"detail": "Saqlandi"}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, data: PasswordReset, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    u.password_hash = hash_password(data.new_password)
    db.commit()
    return {"detail": "Parol yangilandi"}


# ---------- Do'konlar ----------
@router.patch("/stores/{store_id}")
def update_store(store_id: int, data: StoreUpdate, db: Session = Depends(get_db)):
    s = db.get(Store, store_id)
    if not s:
        raise HTTPException(404, "Do'kon topilmadi")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("user_id") is not None:
        u = db.get(User, changes["user_id"])
        if not u or u.role != Role.dokon:
            raise HTTPException(400, "Faqat 'Do'kon' rolidagi foydalanuvchini biriktirish mumkin")
        other = db.scalar(select(Store).where(Store.user_id == u.id, Store.id != s.id))
        if other:
            raise HTTPException(400, f"Bu foydalanuvchi allaqachon '{other.name}' do'koniga biriktirilgan")
    for k, v in changes.items():
        if k == "user_id" or v is not None:
            setattr(s, k, v)
    db.commit()
    return {"detail": "Saqlandi"}


# ---------- Tovarlar ----------
@router.patch("/products/{product_id}")
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Tovar topilmadi")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        dup = db.scalar(select(Product).where(Product.name == changes["name"], Product.id != p.id))
        if dup:
            raise HTTPException(400, "Bu nomdagi tovar allaqachon mavjud")
    for k, v in changes.items():
        if v is not None:
            setattr(p, k, v)
    db.commit()
    return {"detail": "Saqlandi"}


# ---------- Umumiy ko'rsatkichlar ----------
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    users = {k.value: v for k, v in db.execute(
        select(User.role, func.count(User.id)).group_by(User.role)).all()}
    orders = {k.value: v for k, v in db.execute(
        select(Order.status, func.count(Order.id)).group_by(Order.status)).all()}
    debt = store_debt(db)
    since = date.today() - timedelta(days=7)
    sales = db.execute(
        select(Product.name, Product.unit, func.sum(Sale.quantity))
        .join(Product, Product.id == Sale.product_id)
        .where(Sale.sold_on >= since).group_by(Product.id)
        .order_by(func.sum(Sale.quantity).desc())).all()
    return {
        "users": users,
        "stores_count": db.scalar(select(func.count(Store.id)).where(Store.approved.is_(True))) or 0,
        "pending_stores": db.scalar(select(func.count(Store.id)).where(Store.approved.is_(False))) or 0,
        "products_count": db.scalar(select(func.count(Product.id))) or 0,
        "orders": orders,
        "total_delivered_sum": debt["total_delivered_sum"],
        "total_paid": debt["paid"],
        "pending_payments": debt["pending_payments"],
        "total_debt": debt["debt"],
        "sales_last_7_days": [{"product": n, "unit": u, "quantity": float(q)} for n, u, q in sales],
    }


# ---------- Hisobot ----------
def _period(date_from: date | None, date_to: date | None):
    d_to = date_to or date.today()
    d_from = date_from or (d_to - timedelta(days=30))
    if d_from > d_to:
        raise HTTPException(400, "Boshlanish sanasi tugash sanasidan keyin bo'lmasligi kerak")
    return d_from, d_to


def _sales_rows(db: Session, d_from: date, d_to: date):
    q = (select(Sale.sold_on, Store.name, Product.name, Product.unit, Sale.quantity)
         .join(Store, Store.id == Sale.store_id)
         .join(Product, Product.id == Sale.product_id)
         .where(Sale.sold_on >= d_from, Sale.sold_on <= d_to)
         .order_by(Sale.sold_on, Store.name))
    return db.execute(q).all()


@router.get("/report")
def report(date_from: date | None = None, date_to: date | None = None,
           db: Session = Depends(get_db)):
    d_from, d_to = _period(date_from, date_to)
    by_product, by_store = {}, {}
    for _, store, product, unit, qty in _sales_rows(db, d_from, d_to):
        key = (product, unit)
        by_product[key] = by_product.get(key, 0) + qty
        by_store.setdefault(store, {})
        by_store[store][key] = by_store[store].get(key, 0) + qty
    delivered = {(n, u): float(q) for n, u, q in db.execute(
        select(Product.name, Product.unit, func.sum(Delivery.quantity))
        .join(Product, Product.id == Delivery.product_id)
        .where(Delivery.delivered_on >= d_from, Delivery.delivered_on <= d_to)
        .group_by(Product.id)).all()}
    pay_by_method = {m.value: float(t) for m, t in db.execute(
        select(Payment.method, func.sum(Payment.amount))
        .where(Payment.status == PayStatus.tasdiqlandi,
               Payment.paid_on >= d_from, Payment.paid_on <= d_to)
        .group_by(Payment.method)).all()}
    paid = sum(pay_by_method.values())
    keys = set(by_product) | set(delivered)
    return {
        "date_from": d_from, "date_to": d_to, "payments_total": paid,
        "payments_by_method": pay_by_method,
        "by_product": sorted(
            [{"product": k[0], "unit": k[1], "sold": by_product.get(k, 0),
              "delivered": delivered.get(k, 0)} for k in keys],
            key=lambda r: -r["sold"]),
        "by_store": [{"store": s, "lines": [{"product": k[0], "unit": k[1], "sold": v}
                                            for k, v in sorted(items.items())]}
                     for s, items in sorted(by_store.items())],
    }


@router.get("/report.csv")
def report_csv(date_from: date | None = None, date_to: date | None = None,
               db: Session = Depends(get_db)):
    d_from, d_to = _period(date_from, date_to)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Sana", "Do'kon", "Tovar", "Birlik", "Miqdor"])
    for sold_on, store, product, unit, qty in _sales_rows(db, d_from, d_to):
        w.writerow([sold_on.isoformat(), store, product, unit, qty])
    # utf-8-sig: Excel o'zbekcha harflarni to'g'ri ochishi uchun
    return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="hisobot_{d_from}_{d_to}.csv"'})
