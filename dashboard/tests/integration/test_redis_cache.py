"""Integration tests for Redis and InMemory cache adapters.

Tests the CachePort implementations without requiring a real Redis instance.
Uses a simple in-memory dict mock for Redis behavior.
"""

import pytest

from domain.ports import CachePort
from dashboard.adapters.outbound.redis_cache import RedisCacheAdapter, InMemoryCacheAdapter


class TestInMemoryCacheAdapter:
    """Tests for the InMemoryCacheAdapter (dict-based, for testing)."""

    def test_implements_cache_port(self):
        assert isinstance(InMemoryCacheAdapter(), CachePort)

    def test_set_and_get(self):
        cache = InMemoryCacheAdapter()
        cache.set("key1", {"data": 42})
        assert cache.get("key1") == {"data": 42}

    def test_get_missing_key(self):
        cache = InMemoryCacheAdapter()
        assert cache.get("nonexistent") is None

    def test_invalidate_by_prefix(self):
        cache = InMemoryCacheAdapter()
        cache.set("achats:total", 100)
        cache.set("achats:detail", [1, 2])
        cache.set("logistique:total", 50)
        cache.invalidate("achats:")
        assert cache.get("achats:total") is None
        assert cache.get("achats:detail") is None
        assert cache.get("logistique:total") == 50

    def test_overwrite_value(self):
        cache = InMemoryCacheAdapter()
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"


class TestRedisCacheAdapter:
    """Tests for the RedisCacheAdapter (Redis-backed with JSON serialization)."""

    def test_implements_cache_port(self):
        assert isinstance(RedisCacheAdapter(), CachePort)

    def test_no_redis_get_returns_none(self):
        cache = RedisCacheAdapter(redis_client=None)
        assert cache.get("key") is None

    def test_no_redis_set_is_noop(self):
        cache = RedisCacheAdapter(redis_client=None)
        cache.set("key", "value")  # Should not raise

    def test_no_redis_invalidate_is_noop(self):
        cache = RedisCacheAdapter(redis_client=None)
        cache.invalidate("prefix")  # Should not raise

    def test_with_mock_redis(self):
        """Test get/set with a simple mock Redis client."""

        class MockRedis:
            def __init__(self):
                self._data = {}

            def get(self, key):
                return self._data.get(key)

            def setex(self, key, ttl, value):
                self._data[key] = value

            def scan_iter(self, pattern):
                import fnmatch
                return [k for k in self._data if fnmatch.fnmatch(k, pattern)]

            def delete(self, key):
                self._data.pop(key, None)

        redis = MockRedis()
        cache = RedisCacheAdapter(redis_client=redis)

        cache.set("test_key", {"value": 123})
        result = cache.get("test_key")
        assert result == {"value": 123}

    def test_with_mock_redis_invalidate(self):
        """Test prefix-based invalidation with a mock Redis client."""

        class MockRedis:
            def __init__(self):
                self._data = {}

            def get(self, key):
                return self._data.get(key)

            def setex(self, key, ttl, value):
                self._data[key] = value

            def scan_iter(self, pattern):
                import fnmatch
                return [k for k in self._data if fnmatch.fnmatch(k, pattern)]

            def delete(self, key):
                self._data.pop(key, None)

        redis = MockRedis()
        cache = RedisCacheAdapter(redis_client=redis)
        cache.set("achats:x", 1)
        cache.set("achats:y", 2)
        cache.set("log:z", 3)
        cache.invalidate("achats:")
        assert cache.get("achats:x") is None
        assert cache.get("achats:y") is None
        assert cache.get("log:z") == 3
