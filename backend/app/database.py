"""SQLite 数据库配置与会话."""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "couple.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表."""
    import app.models  # noqa: F401 - 注册表
    Base.metadata.create_all(bind=engine)
    _ensure_legacy_columns()


def _has_column(conn, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _ensure_legacy_columns():
    """
    兼容旧库：无迁移框架时，为已有业务表补 owner_id 列。
    """
    with engine.begin() as conn:
        for table in ("memories", "anniversaries", "photos", "notes"):
            if _has_column(conn, table, "owner_id"):
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER"))
