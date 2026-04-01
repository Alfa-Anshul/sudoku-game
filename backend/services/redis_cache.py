import json

from ..config import get_settings

settings = get_settings()


class RedisCache:
    def __init__(self) -> None:
        self.client = None
        self.memory_store: dict[str, str] = {}

        if settings.redis_url:
            try:
                from redis import Redis

                self.client = Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                self.client = None

    def get_json(self, key: str) -> dict | list | None:
        raw = self.client.get(key) if self.client else self.memory_store.get(key)
        if not raw:
            return None
        return json.loads(raw)

    def set_json(self, key: str, value: dict | list, ttl_seconds: int = 3600) -> None:
        payload = json.dumps(value)
        if self.client:
            self.client.setex(key, ttl_seconds, payload)
            return
        self.memory_store[key] = payload


redis_cache = RedisCache()
