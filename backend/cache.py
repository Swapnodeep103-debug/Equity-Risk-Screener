"""
cache.py

A minimal disk-based cache with a time-to-live (TTL). Used to avoid
re-fetching the same price history / fundamentals / FX rates on every run,
which is both slow and a good way to get rate-limited by Yahoo Finance.

This is intentionally simple (pickle files on disk) - swap it out for
Redis/SQLite/etc. later if you need multi-process sharing.
"""

import os
import pickle
import time
from typing import Any, Callable, Optional

DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")


class DiskCache:
    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.ttl = ttl_seconds
        os.makedirs(self.cache_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        safe_key = "".join(c if c.isalnum() else "_" for c in key)
        return os.path.join(self.cache_dir, f"{safe_key}.pkl")

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not os.path.exists(path):
            return None
        if time.time() - os.path.getmtime(path) > self.ttl:
            return None
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        try:
            with open(path, "wb") as f:
                pickle.dump(value, f)
        except Exception as e:
            print(f"[warn] failed to write cache for key '{key}': {e}")

    def get_or_fetch(self, key: str, fetch_fn: Callable[[], Any]) -> Any:
        """Return the cached value if present and fresh, otherwise call
        fetch_fn(), cache the result (if not None), and return it."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fetch_fn()
        if value is not None:
            self.set(key, value)
        return value
