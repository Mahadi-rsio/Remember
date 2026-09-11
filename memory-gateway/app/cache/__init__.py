"""Cache package — version-aware in-process + optional Redis."""
from app.cache.interface import CacheBackend
from app.cache.memory_cache import InMemoryCache, make_cache_key, make_request_key
from app.cache.redis_adapter import RedisCache, create_cache_backend

__all__ = [
    "CacheBackend",
    "InMemoryCache",
    "make_cache_key",
    "make_request_key",
    "RedisCache",
    "create_cache_backend",
]
