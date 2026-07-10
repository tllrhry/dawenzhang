from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.db.session import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response) -> dict[str, object]:
    settings = get_settings()
    database = check_database()
    dependencies_ok = database["status"] == "ok"
    if not dependencies_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if dependencies_ok else "error",
        "application": {"status": "ok", "name": settings.app_name, "version": settings.app_version},
        "database": database,
    }
