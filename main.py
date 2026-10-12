import os
import re
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, SessionLocal
from .models import User, Store, Product, Role
from .auth import (hash_password, verify_password, create_token,
                   current_user, require_roles)
from .notify import send_telegram
from .pwa import MANIFEST, SERVICE_WORKER, icon_png
from .schedule import get_settings
from . import schemas
from .dokon_routes import router as dokon_router
from .zavod_routes import router as zavod_router
from .admin_routes import router as admin_router, account_router

Base.metadata.create_all(engine)

app = FastAPI(title="Distribyutor platformasi")
app.include_router(dokon_router)
app.include_router(zavod_router)
app.include_router(admin_router)
app.include_router(account_router)


@app.get("/", include_in_schema=False)
def index():
    """Admin va distribyutor paneli."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/ilova", include_in_schema=False)
def store_app():
    """Do'kon ilovasi (telefonga o'rnatiladigan PWA)."""
    return FileResponse(Path(__file__).parent / "static" / "store.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return Response(SERVICE_WORKER, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


@app.get("/icon-{size}.png", include_in_schema=False)
def icon(size: int):
    if size not in (180, 192, 512):
        raise HTTPException(404, "Topilmadi")
    return Response(icon_png(size), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.on_event("startup")
def startup():
    """Birinchi ishga tushishda admin va sozlamalar qatori yaratiladi."""
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.role == Role.admin)):
            db.add(User(username="admin", full_name="Administrator",
                        password_hash=hash_password(os.getenv("ADMIN_PASSWORD", "admin123")), role=Role.admin))
            db.commit()
        get_settings(db)


def norm_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    return digits


# ---------- Autentifikatsiya ----------
@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    name = form.username.strip()
    user = db.scalar(select(User).where(User.username == name))
    if not user and norm_phone(name):
        user = db.scalar(select(User).where(User.username == norm_phone(name)))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Login yoki parol noto'g'ri")
    return {"access_token": create_token(user), "token_type": "bearer", "role": user.role}


@app.post("/auth/register")
def register(data: schemas.RegisterIn, db: Session = Depends(get_db)):
    """Do'kon egasi o'zi ro'yxatdan o'tadi. Distribyutor tasdiqlaguncha buyurtma bera olmaydi."""
    digits = norm_phone(data.phone)
    if len(digits) != 12 or not digits.startswith("998"):
        raise HTTPException(400, "Telefon raqamini to'liq kiriting (masalan: 90 123 45 67)")
    if db.scalar(select(User).where(User.username == digits)):
        raise HTTPException(400, "Bu telefon raqami bilan allaqachon ro'yxatdan o'tilgan")
    user = User(username=digits, full_name=data.full_name.strip(), phone=data.phone.strip(),
                password_hash=hash_password(data.password), role=Role.dokon)
    db.add(user)
    db.flush()
    db.add(Store(name=data.store_name.strip(), address=data.address.strip(),
                 phone=data.phone.strip(), user_id=user.id, approved=False))
    db.commit()
    send_telegram(f"Yangi do'kon ro'yxatdan o'tdi\nNomi: {data.store_name}\n"
                  f"Egasi: {data.full_name}\nTelefon: {data.phone}\nTasdiqlash kerak.")
    return {"access_token": create_token(user), "token_type": "bearer", "role": user.role}


@app.get("/auth/me", response_model=schemas.UserOut)
def me(user: User = Depends(current_user)):
    return user


# ---------- Admin: yaratish ----------
admin_only = Depends(require_roles(Role.admin))


@app.post("/admin/users", response_model=schemas.UserOut, dependencies=[admin_only])
def create_user(data: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == data.username)):
        raise HTTPException(400, "Bu login band")
    user = User(username=data.username, full_name=data.full_name,
                password_hash=hash_password(data.password), role=data.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/admin/users", response_model=list[schemas.UserOut], dependencies=[admin_only])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User)).all()


@app.post("/admin/stores", response_model=schemas.StoreOut, dependencies=[admin_only])
def create_store(data: schemas.StoreCreate, db: Session = Depends(get_db)):
    store = Store(**data.model_dump(), approved=True)
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@app.post("/admin/products", response_model=schemas.ProductOut, dependencies=[admin_only])
def create_product(data: schemas.ProductCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Product).where(Product.name == data.name)):
        raise HTTPException(400, "Bu tovar allaqachon mavjud")
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


# ---------- Ro'yxatlar ----------
@app.get("/products", response_model=list[schemas.ProductOut])
def list_products(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.scalars(select(Product).order_by(Product.category, Product.name)).all()


@app.get("/stores", response_model=list[schemas.StoreOut],
         dependencies=[Depends(require_roles(Role.admin, Role.zavod))])
def list_stores(db: Session = Depends(get_db)):
    return db.scalars(select(Store)).all()
