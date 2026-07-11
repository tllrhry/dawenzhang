from fastapi.testclient import TestClient

from app.api.routes import health as health_route
from app.main import app


def test_api_root_is_versioned() -> None:
    response = TestClient(app).get("/api/v1")
    assert response.status_code == 200
    assert response.json()["name"] == "dawenzhang"


def test_health_ok_when_database_reachable(monkeypatch) -> None:
    monkeypatch.setattr(
        health_route,
        "check_database",
        lambda: {"status": "ok", "engine": "postgresql", "pgvector": "enabled"},
    )
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["engine"] == "postgresql"
    assert body["database"]["pgvector"] == "enabled"
    assert "siliconflow" in body["models"]
    assert "deepseek" in body["models"]


def test_health_degraded_when_database_unreachable(monkeypatch) -> None:
    monkeypatch.setattr(
        health_route,
        "check_database",
        lambda: {"status": "error", "engine": "postgresql", "detail": "PostgreSQL connection failed"},
    )
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["status"] == "error"
