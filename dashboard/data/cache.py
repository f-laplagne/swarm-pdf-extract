import json
import os
from typing import Any, Callable


class CacheManager:
    """Simple Redis cache wrapper with JSON serialization.
    Falls back to no-cache if Redis is unavailable."""

    PREFIX = "rationalize:"

    def __init__(self, redis_client=None, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl

    def _key(self, key: str) -> str:
        return f"{self.PREFIX}{key}"

    def get_or_compute(self, key: str, compute_fn: Callable[[], Any]) -> Any:
        if self.redis:
            cached = self.redis.get(self._key(key))
            if cached is not None:
                return json.loads(cached)

        result = compute_fn()

        if self.redis and result is not None:
            self.redis.setex(self._key(key), self.ttl, json.dumps(result, default=str))

        return result

    def invalidate(self, key: str):
        if self.redis:
            self.redis.delete(self._key(key))

    def invalidate_all(self):
        if self.redis:
            for key in self.redis.scan_iter(f"{self.PREFIX}*"):
                self.redis.delete(key)


def get_cache_manager() -> CacheManager:
    """Factory that creates a CacheManager, connecting to Redis if available."""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            client = redis.from_url(redis_url)
            client.ping()
            return CacheManager(redis_client=client)
        except Exception:
            pass
    return CacheManager(redis_client=None)
