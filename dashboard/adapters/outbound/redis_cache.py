"""Redis cache adapter implementing CachePort.

Falls back to no-op when Redis is unavailable.
"""

from __future__ import annotations

import json

from domain.ports import CachePort


class RedisCacheAdapter(CachePort):
    """CachePort implementation backed by Redis with JSON serialization.

    When *redis_client* is ``None`` every operation is a silent no-op,
    which makes it safe to use in environments where Redis is not available.
    """

    PREFIX = "rationalize:"

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _key(self, key: str) -> str:
        return f"{self.PREFIX}{key}"

    # ── CachePort interface ──────────────────────────────────────────────

    def get(self, key: str) -> object | None:
        if not self._redis:
            return None
        raw = self._redis.get(self._key(key))
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: str, value: object, ttl: int = 3600) -> None:
        if not self._redis:
            return
        self._redis.setex(self._key(key), ttl, json.dumps(value, default=str))

    def invalidate(self, prefix: str) -> None:
        if not self._redis:
            return
        full_prefix = self._key(prefix)
        for k in self._redis.scan_iter(f"{full_prefix}*"):
            self._redis.delete(k)


class InMemoryCacheAdapter(CachePort):
    """CachePort implementation using a simple in-memory dict.

    Intended for testing and environments where persistence is not needed.
    TTL is accepted but ignored (values never expire).
    """

    def __init__(self):
        self._store: dict[str, object] = {}

    def get(self, key: str) -> object | None:
        return self._store.get(key)

    def set(self, key: str, value: object, ttl: int = 3600) -> None:
        self._store[key] = value

    def invalidate(self, prefix: str) -> None:
        keys_to_remove = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._store[k]
