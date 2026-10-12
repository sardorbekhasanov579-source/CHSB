import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Kompyuterda: SQLite fayl. Serverda (Render): DATABASE_URL muhit o'zgaruvchisi orqali PostgreSQL.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./distribyutor.db")

# Render/Neon "postgres://" yoki "postgresql://" beradi; SQLAlchemy uchun drayver nomi kerak
for prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(prefix):]
        break

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
