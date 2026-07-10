from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.db.session import check_mysql
from app.infra.redis import check_redis

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response) -> dict[str, object]:
    settings = get_settings()
    mysql = check_mysql(settings)
    redis = check_redis(settings)
    dependencies_ok = mysql["status"] == "ok" and redis["status"] == "ok"
    if not dependencies_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if dependencies_ok else "error",
        "application": {"status": "ok", "name": settings.app_name, "version": settings.app_version},
        "mysql": mysql,
        "redis": redis,
    }

