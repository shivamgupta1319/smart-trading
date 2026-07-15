"""Tiny thread-safe in-process TTL cache for yfinance responses.

The dashboard polls live prices every 10s and re-requests charts frequently;
without caching every call re-hits yfinance (slow + rate-limit prone). This
caches by key for a short TTL. Per-process only — fine for the single engine
worker; swap for Redis if the engine ever scales horizontally.
"""
import time
import threading
from typing import Any, Callable, Optional

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


def cache_get(key: str, ttl: float) -> Optional[Any]:
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and now - hit[0] <= ttl:
            return hit[1]
    return None


def cache_set(key: str, value: Any) -> None:
    with _lock:
        _store[key] = (time.monotonic(), value)
        # bound memory
        if len(_store) > 5000:
            cutoff = time.monotonic()
            for k in [k for k, (t, _) in _store.items() if cutoff - t > 300]:
                _store.pop(k, None)


def cached(key: str, ttl: float, producer: Callable[[], Any]) -> Any:
    """Return the cached value for `key`, or call `producer()` and cache it."""
    val = cache_get(key, ttl)
    if val is not None:
        return val
    val = producer()
    if val is not None:
        cache_set(key, val)
    return val
