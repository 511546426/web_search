"""SQLite 数据库配置、会话与轻量迁移."""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "couple.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
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
    """创建所有表，并对旧库执行轻量补列迁移."""
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()


def _sqlite_columns(table_name: str) -> set:
    """读取 SQLite 表字段列表。"""
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _add_column_if_missing(table_name: str, column_name: str, ddl: str) -> None:
    """字段不存在时执行 ALTER TABLE ADD COLUMN。"""
    cols = _sqlite_columns(table_name)
    if column_name in cols:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def _run_lightweight_migrations() -> None:
    """兼容历史 SQLite 库：补齐新增字段，避免接口 500。"""
    # comic_scripts: 新增过 review_score / error_message
    _add_column_if_missing("comic_scripts", "review_score", "review_score FLOAT")
    _add_column_if_missing("comic_scripts", "error_message", "error_message TEXT")

    # product_ads: 旧库可能缺少评审与错误信息字段
    _add_column_if_missing("product_ads", "review_score", "review_score FLOAT")
    _add_column_if_missing("product_ads", "error_message", "error_message TEXT")

    # product_ads: 步骤确认字段
    _add_column_if_missing("product_ads", "composite_confirmed", "composite_confirmed BOOLEAN DEFAULT 0")
    _add_column_if_missing("product_ads", "composite_photo_ids", "composite_photo_ids TEXT")
    _add_column_if_missing("product_ads", "composite_retry_count", "composite_retry_count INTEGER DEFAULT 0")
    _add_column_if_missing("product_ads", "script_confirmed", "script_confirmed BOOLEAN DEFAULT 0")
    _add_column_if_missing("product_ads", "script_user_feedback", "script_user_feedback TEXT")
    _add_column_if_missing("product_ads", "review_detail", "review_detail TEXT")
    _add_column_if_missing("product_ads", "script_variants", "script_variants TEXT")

    # novels: 兼容旧表
    _add_column_if_missing("novels", "error_message", "error_message TEXT")
    _add_column_if_missing("novels", "user_feedback", "user_feedback TEXT")
