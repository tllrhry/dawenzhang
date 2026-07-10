from fastapi.testclient import TestClient

from app.main import app


def test_api_root_is_versioned() -> None:
    response = TestClient(app).get("/api/v1")
    assert response.status_code == 200
    assert response.json()["name"] == "dawenzhang"

