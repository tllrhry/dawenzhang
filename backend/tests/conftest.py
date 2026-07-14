import os
import subprocess
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

from app.core.config import get_settings


_ROOT = Path(__file__).resolve().parents[2]
_OWNED_DATABASE_NAME: str | None = None
_ADMIN_URL: URL | None = None


def _drop_owned_database() -> None:
    if _OWNED_DATABASE_NAME is None or _ADMIN_URL is None:
        return
    engine = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{_OWNED_DATABASE_NAME}" WITH (FORCE)'
            )
    finally:
        engine.dispose()


def _activate_isolated_database() -> None:
    global _ADMIN_URL, _OWNED_DATABASE_NAME

    source_url = make_url(get_settings().database_url)
    current_database = source_url.database or ""
    if current_database.startswith("dawenzhang_test_"):
        return

    database_name = f"dawenzhang_test_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    admin_url = source_url.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    finally:
        engine.dispose()

    _OWNED_DATABASE_NAME = database_name
    _ADMIN_URL = admin_url
    test_url = source_url.set(database=database_name)
    os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
    get_settings.cache_clear()
    try:
        subprocess.run(
            ["bash", str(_ROOT / "backend/scripts/migrate.sh")],
            cwd=_ROOT,
            env=os.environ.copy(),
            check=True,
        )
    except BaseException:
        _drop_owned_database()
        raise


_activate_isolated_database()


def pytest_sessionfinish() -> None:
    _drop_owned_database()
