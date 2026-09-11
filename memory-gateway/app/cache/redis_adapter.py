"""Optional Redis cache backend.

Not required for MVP. Activated only when ``REDIS_URL`` is set.
Falls back gracefully to InMemoryCache if redis package unavailable.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.cache.interface import CacheBackend

logger = logging.getLogger(__name__)


class RedisCache(CacheBackend):
    """Redis-backed cache. Requires ``redis`` package."""

    def __init__(self, url: str) -> None:
        try:
            import redis as _redis  # type: ignore[import]

            self._client = _redis.from_url(url, decode_responses=True)
        except ImportError as exc:
            raise RuntimeError(
                "redis package not installed. Run: pip install redis"
            ) from exc

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.exception("Redis get failed for key=%s", key)
            return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        try:
            raw = json.dumps(value, default=str)
            if ttl_seconds is not None:
                self._client.setex(key, ttl_seconds, raw)
            else:
                self._client.set(key, raw)
        except Exception:
            logger.exception("Redis set failed for key=%s", key)

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception:
            logger.exception("Redis delete failed for key=%s", key)

    def clear_prefix(self, prefix: str) -> None:
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=f"{prefix}*", count=100)
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            logger.exception("Redis clear_prefix failed for prefix=%s", prefix)


def create_cache_backend(redis_url: str | None = None) -> CacheBackend:
    """Factory: returns RedisCache if REDIS_URL set, else InMemoryCache."""
    from app.cache.memory_cache import InMemoryCache

    if redis_url:
        try:
            return RedisCache(redis_url)
        except Exception:
            logger.warning("Redis unavailable; falling back to in-memory cache")
    return InMemoryCache()
