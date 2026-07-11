from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def check_database() -> dict[str, object]:
    """Report PostgreSQL reachability and whether the pgvector extension is enabled."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            pgvector_enabled = bool(
                connection.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                ).first()
            )
        return {
            "status": "ok",
            "engine": "postgresql",
            "pgvector": "enabled" if pgvector_enabled else "missing",
        }
    except SQLAlchemyError:
        return {"status": "error", "engine": "postgresql", "detail": "PostgreSQL connection failed"}
