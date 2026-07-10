from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_database_url,
        pool_pre_ping=settings.mysql_pool_pre_ping,
        pool_recycle=1800,
        future=True,
    )


def get_db() -> Generator:
    with get_engine().connect() as connection:
        yield connection


def check_mysql(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or get_settings()
    if settings.mysql_database != "dawenzhang":
        return {"status": "error", "detail": "database isolation validation failed"}
    try:
        with get_engine().connect() as connection:
            database = connection.execute(text("SELECT DATABASE()")).scalar_one_or_none()
        if database != "dawenzhang":
            return {"status": "error", "detail": "connected database is not dawenzhang"}
        return {"status": "ok", "database": "dawenzhang"}
    except SQLAlchemyError:
        return {"status": "error", "detail": "MySQL connection failed"}

