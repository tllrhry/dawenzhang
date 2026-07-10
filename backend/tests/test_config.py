import pytest

from app.core.config import Settings


def test_default_isolation_settings() -> None:
    settings = Settings(_env_file=None)
    assert settings.mysql_database == "dawenzhang"
    assert settings.redis_db == 1
    assert settings.redis_key_prefix == "dawenzhang:"


def test_rejects_existing_project_database() -> None:
    with pytest.raises(ValueError, match="dawenzhang"):
        Settings(_env_file=None, mysql_database="ai_tag_fix")


def test_rejects_redis_db0() -> None:
    with pytest.raises(ValueError, match="db0"):
        Settings(_env_file=None, redis_db=0)

