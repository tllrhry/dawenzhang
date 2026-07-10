from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    database_path = settings.database_path
    if database_path is not None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )


def get_db() -> Generator:
    with get_engine().connect() as connection:
        yield connection


def check_database() -> dict[str, object]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "engine": "sqlite"}
    except SQLAlchemyError:
        return {"status": "error", "detail": "SQLite connection failed"}
