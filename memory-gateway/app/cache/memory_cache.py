"""In-process LRU/TTL cache backend (no external deps)."""
from __future__ import annotations

import hashlib
import json
import time
from threading import Lock
from typing import Any

from app.cache.interface import CacheBackend


class InMemoryCache(CacheBackend):
    """Thread-safe dict cache with optional TTL. Default max 512 entries."""

    def __init__(self, max_size: int = 512) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}  # key -> (value, expires_at|None)
        self._max_size = max_size
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        with self._lock:
            if len(self._store) >= self._max_size and key not in self._store:
                # Evict oldest entry (first inserted due to dict ordering)
                evict = next(iter(self._store))
                del self._store[evict]
            expires_at = time.monotonic() + ttl_seconds if ttl_seconds is not None else None
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear_prefix(self, prefix: str) -> None:
        with self._lock:
            to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in to_delete:
                del self._store[k]

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


def make_cache_key(
    namespace: str,
    conversation_id: str,
    context_version: int,
    *extra_parts: Any,
) -> str:
    """Build a stable, version-aware cache key.

    Key format: ``<namespace>:<conv>:<ctx_ver>:<hash(extras)>``

    The ``context_version`` ensures stale entries are automatically
    unreachable after a context update (no explicit invalidation needed
    for most read paths).
    """
    extras_blob = json.dumps(extra_parts, sort_keys=True, default=str)
    extras_hash = hashlib.sha256(extras_blob.encode()).hexdigest()[:16]
    return f"{namespace}:{conversation_id}:{context_version}:{extras_hash}"


def make_request_key(
    conversation_id: str,
    context_version: int,
    request_body: dict,
) -> str:
    """Convenience key for full request/compilation caches."""
    return make_cache_key("request", conversation_id, context_version, request_body)
