import enum
from datetime import datetime, date
from sqlalchemy import (String, Float, ForeignKey, DateTime, Date, Enum, Boolean)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Role(str, enum.Enum):
    admin = "admin"
    zavod = "zavod"      # distribyutor / ulgurchi
    dokon = "dokon"      # CHSK / buyurtmachi


class OrderStatus(str, enum.Enum):
    yangi = "yangi"
    tasdiqlandi = "tasdiqlandi"
    yetkazildi = "yetkazildi"
    bekor = "bekor qilindi"


class PayMethod(str, enum.Enum):
    naqd = "naqd"
    otkazma = "o'tkazma"
    online = "online"


class PayStatus(str, enum.Enum):
    kutilmoqda = "kutilmoqda"
    tasdiqlandi = "tasdiqlandi"
    rad = "rad etildi"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Store(Base):
    """Do'kon (CHSK). Har bir do'konga bitta 'dokon' roli foydalanuvchisi bog'lanadi."""
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)  # o'zi ro'yxatdan o'tganlar uchun False
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[User | None] = relationship()


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    unit: Mapped[str] = mapped_column(String(20), default="dona")  # kg, dona, blok
    price: Mapped[float] = mapped_column(Float, default=0)
    category: Mapped[str] = mapped_column(String(50), default="")
    description: Mapped[str] = mapped_column(String(300), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    """Buyurtma qabul qilish jadvali va shartlari (bitta qator, id=1)."""
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_days: Mapped[str] = mapped_column(String(20), default="1,2,3,4,5,6")  # 1=Dushanba ... 7=Yakshanba
    open_time: Mapped[str] = mapped_column(String(5), default="08:00")
    close_time: Mapped[str] = mapped_column(String(5), default="18:00")
    min_order_sum: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str] = mapped_column(String(300), default="")


class Order(Base):
    """Do'konning distribyutorga arizasi (bir nechta tovar bo'lishi mumkin)."""
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.yangi)
    payment_method: Mapped[PayMethod] = mapped_column(Enum(PayMethod), default=PayMethod.naqd)
    wanted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    store: Mapped[Store] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order",
                                                    cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float, default=0)   # buyurtma paytidagi narx
    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Delivery(Base):
    """Distribyutor do'konga yetkazgan tovar."""
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float, default=0)
    delivered_on: Mapped[date] = mapped_column(Date, default=date.today)
    confirmed_by_store: Mapped[bool] = mapped_column(Boolean, default=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    store: Mapped[Store] = relationship()
    product: Mapped[Product] = relationship()


class Sale(Base):
    """Do'kon aholiga sotgan tovar (kunlik)."""
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[float] = mapped_column(Float)
    sold_on: Mapped[date] = mapped_column(Date, default=date.today)
    store: Mapped[Store] = relationship()
    product: Mapped[Product] = relationship()


class Payment(Base):
    """Do'konning distribyutorga to'lovi (naqd, o'tkazma yoki online)."""
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    paid_on: Mapped[date] = mapped_column(Date, default=date.today)
    method: Mapped[PayMethod] = mapped_column(Enum(PayMethod), default=PayMethod.naqd)
    status: Mapped[PayStatus] = mapped_column(Enum(PayStatus), default=PayStatus.tasdiqlandi)
    note: Mapped[str] = mapped_column(String(200), default="")
