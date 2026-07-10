from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.db.session import check_database, get_engine


def test_api_root_is_versioned() -> None:
    response = TestClient(app).get("/api/v1")
    assert response.status_code == 200
    assert response.json()["name"] == "dawenzhang"


def test_sqlite_health_check_uses_configured_database(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "demo.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    get_settings.cache_clear()
    get_engine.cache_clear()

    assert check_database() == {"status": "ok", "engine": "sqlite"}
    assert database_path.exists()

    get_engine.cache_clear()
    get_settings.cache_clear()
