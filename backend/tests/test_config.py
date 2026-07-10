import pytest

from app.core.config import Settings


def test_default_demo_settings() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("sqlite:///")
    assert settings.ai_connect_timeout_seconds == 10
    assert settings.ai_read_timeout_seconds == 90


def test_rejects_non_sqlite_database() -> None:
    with pytest.raises(ValueError, match="SQLite"):
        Settings(_env_file=None, database_url="mysql+pymysql://localhost/dawenzhang")


def test_rejects_non_positive_ai_timeout() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        Settings(_env_file=None, ai_read_timeout_seconds=0)
