"""Thin wrapper over diskcache - key is URL + params, TTL per category.

Default policy:

- acts (single-act metadata): 24h
- lists/search: 1h
- dictionaries (publishers/statistics): 7 days
- recent changes: 5 min (this data must be fresh)

Inherited verbatim from sejm-eli-mcp (only the env var and cache dir differ).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from diskcache import Cache

DEFAULT_TTL_ACT = 24 * 60 * 60
DEFAULT_TTL_LIST = 60 * 60
DEFAULT_TTL_DICT = 7 * 24 * 60 * 60
DEFAULT_TTL_CHANGES = 5 * 60


def _resolve_cache_dir() -> Path:
    env = os.environ.get("DE_ELI_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".matematic" / "cache" / "de-eli"


class HttpCache:
    """Caches HTTP responses (already deserialized to dict / str)."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._dir = (cache_dir or _resolve_cache_dir()).expanduser()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: Cache = Cache(str(self._dir))

    def get(self, key: str) -> Any:
        return self._cache.get(key, default=None)

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._cache.set(key, value, expire=ttl)

    def close(self) -> None:
        self._cache.close()

    @staticmethod
    def ttl_for(category: str) -> int:
        match category:
            case "act":
                return DEFAULT_TTL_ACT
            case "list" | "search":
                return DEFAULT_TTL_LIST
            case "dict":
                return DEFAULT_TTL_DICT
            case "changes":
                return DEFAULT_TTL_CHANGES
            case _:
                return DEFAULT_TTL_LIST
