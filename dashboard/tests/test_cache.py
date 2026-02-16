import pytest
from unittest.mock import MagicMock
from dashboard.data.cache import CacheManager


def test_cache_get_miss_calls_compute():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # cache miss

    cache = CacheManager(redis_client=mock_redis, ttl=3600)
    result = cache.get_or_compute("test_key", lambda: {"value": 42})

    assert result == {"value": 42}
    mock_redis.setex.assert_called_once()


def test_cache_get_hit_returns_cached():
    import json
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps({"value": 42}).encode()

    cache = CacheManager(redis_client=mock_redis, ttl=3600)
    compute_called = False

    def compute():
        nonlocal compute_called
        compute_called = True
        return {"value": 99}

    result = cache.get_or_compute("test_key", compute)
    assert result == {"value": 42}
    assert not compute_called


def test_cache_invalidate():
    mock_redis = MagicMock()
    cache = CacheManager(redis_client=mock_redis, ttl=3600)
    cache.invalidate("some_key")
    mock_redis.delete.assert_called_once_with("rationalize:some_key")
