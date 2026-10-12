import os
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Role

# Ishlab chiqarishda SECRET_KEY ni muhit o'zgaruvchisida saqlang!
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if os.getenv("DATABASE_URL"):   # server (haqiqiy) muhiti: kalitsiz ishga tushmasin
        raise RuntimeError("SECRET_KEY muhit o'zgaruvchisi o'rnatilmagan")
    SECRET_KEY = "faqat-kompyuterda-sinash-uchun"
ALGORITHM = "HS256"
TOKEN_HOURS = 12

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hex_hash = stored.split("$")
    except ValueError:
        return False
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return hmac.compare_digest(h.hex(), hex_hash)


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    err = HTTPException(status.HTTP_401_UNAUTHORIZED, "Token yaroqsiz yoki muddati tugagan")
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.get(User, int(data["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise err
    if not user or not user.is_active:
        raise err
    return user


def require_roles(*roles: Role):
    """Faqat ko'rsatilgan rollarga ruxsat beruvchi dependency."""
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sizda bu amal uchun ruxsat yo'q")
        return user
    return checker
