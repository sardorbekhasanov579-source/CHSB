"""Sinov uchun tayyor foydalanuvchilar, do'kon, tovarlar va buyurtma jadvalini yaratadi.
Ishga tushirish (loyiha papkasida):  python seed_demo.py
Qayta ishga tushirsangiz ham xato bermaydi (mavjudini o'tkazib yuboradi).
Haqiqiy foydalanishdan oldin bu parollarni albatta o'zgartiring!"""
from sqlalchemy import select

from app.database import Base, engine, SessionLocal
from app.models import User, Store, Product, Role
from app.auth import hash_password
from app.schedule import get_settings

Base.metadata.create_all(engine)

USERS = [
    ("admin", "Administrator", "admin123", Role.admin),
    ("zavod1", "Distribyutor", "zavod123", Role.zavod),
    ("dokon1", "Namuna do'kon", "dokon123", Role.dokon),
]
PRODUCTS = [
    ("Cola 1.5L", "blok", 50000, "Ichimliklar", "6 dona, 1.5 litr"),
    ("Fanta 1.5L", "blok", 48000, "Ichimliklar", "6 dona, 1.5 litr"),
    ("Mineral suv 1L", "blok", 30000, "Ichimliklar", "12 dona"),
    ("Un (1-nav)", "kg", 6500, "Oziq-ovqat", "50 kg qopdan"),
    ("Yog' 1L", "dona", 17000, "Oziq-ovqat", "Kungaboqar yog'i"),
    ("Shakar", "kg", 11000, "Oziq-ovqat", ""),
]

with SessionLocal() as db:
    for username, full_name, password, role in USERS:
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(username=username, full_name=full_name,
                        password_hash=hash_password(password), role=role))
    db.commit()

    dokon_user = db.scalar(select(User).where(User.username == "dokon1"))
    if not db.scalar(select(Store).where(Store.user_id == dokon_user.id)):
        db.add(Store(name="Namuna do'kon", address="Toshkent", phone="+998 90 000 00 00",
                     user_id=dokon_user.id, approved=True))
    for name, unit, price, cat, desc in PRODUCTS:
        if not db.scalar(select(Product).where(Product.name == name)):
            db.add(Product(name=name, unit=unit, price=price, category=cat, description=desc))
    db.commit()

    # Sinov paytida buyurtma hamma vaqt ochiq bo'lsin (Zavod/Admin "Sozlamalar" da o'zgartiriladi)
    s = get_settings(db)
    if (s.order_days, s.open_time, s.close_time) == ("1,2,3,4,5,6", "08:00", "18:00"):
        s.order_days, s.open_time, s.close_time = "1,2,3,4,5,6,7", "00:00", "23:59"
        db.commit()

print("Tayyor. Kirish ma'lumotlari:")
for username, _, password, role in USERS:
    print(f"  {role.value:6}  login: {username:8} parol: {password}")
print("Sinov uchun buyurtma qabul qilish 24 soat ochiq qilindi (Sozlamalar bo'limida o'zgartirasiz).")
