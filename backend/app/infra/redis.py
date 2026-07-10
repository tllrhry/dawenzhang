from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings


@lru_cache
def get_redis_client() -> Redis:
    settings = get_settings()
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


class ProjectCache:
    """Redis adapter that enforces the project's db1 and key namespace."""

    def __init__(self, client: Redis | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        if self.settings.redis_db != 1:
            raise ValueError("Dawenzhang Redis must use logical database 1")
        self.client = client or get_redis_client()

    def key(self, key: str) -> str:
        clean_key = key.removeprefix(self.settings.redis_key_prefix)
        return f"{self.settings.redis_key_prefix}{clean_key}"

    def set(self, key: str, value: Any, **kwargs: Any) -> bool:
        return bool(self.client.set(self.key(key), value, **kwargs))

    def get(self, key: str) -> Any:
        return self.client.get(self.key(key))

    def delete(self, key: str) -> int:
        return int(self.client.delete(self.key(key)))

    def clear_project(self, batch_size: int = 500) -> int:
        """Delete only this project's keys; never call FLUSHDB/FLUSHALL."""
        keys: list[str] = []
        deleted = 0
        for key in self.client.scan_iter(match=f"{self.settings.redis_key_prefix}*"):
            keys.append(key)
            if len(keys) >= batch_size:
                deleted += int(self.client.delete(*keys))
                keys.clear()
        if keys:
            deleted += int(self.client.delete(*keys))
        return deleted


def check_redis(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or get_settings()
    if settings.redis_db != 1 or not settings.redis_key_prefix.startswith("dawenzhang:"):
        return {"status": "error", "detail": "Redis isolation validation failed"}
    client = get_redis_client()
    probe_key = f"{settings.redis_key_prefix}health:probe"
    try:
        if int(client.connection_pool.connection_kwargs.get("db", -1)) != 1:
            return {"status": "error", "detail": "Redis logical database is not db1"}
        client.ping()
        client.set(probe_key, "ok", ex=10)
        isolated_read = client.get(probe_key) == "ok"
        client.delete(probe_key)
        if not isolated_read:
            return {"status": "error", "detail": "Redis project probe read/write failed"}
        return {"status": "ok", "database": 1, "key_prefix": settings.redis_key_prefix}
    except RedisError:
        return {"status": "error", "detail": "Redis connection failed"}
    finally:
        try:
            client.delete(probe_key)
        except RedisError:
            pass

