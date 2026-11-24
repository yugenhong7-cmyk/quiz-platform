"""SQLAlchemy 数据库连接与会话管理。"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  确保模型已注册
    Base.metadata.create_all(bind=engine)
    _migrate(engine)


def _migrate(engine):
    """轻量级列迁移：为已有库补新增列（SQLite 不支持 ADD COLUMN IF NOT EXISTS）。"""
    from sqlalchemy import text
    with engine.connect() as conn:
        def _has_col(table: str, col: str) -> bool:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return col in {row[1] for row in rows}
        if _has_col("users", "id") and not _has_col("users", "last_login_at"):
            conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
        if _has_col("wrong_questions", "id") and not _has_col("wrong_questions", "streak"):
            conn.execute(text("ALTER TABLE wrong_questions ADD COLUMN streak INTEGER DEFAULT 0"))
        conn.commit()
