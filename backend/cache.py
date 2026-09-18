"""Thread-safe TTL cache for upstream API responses.

Why this exists: a single briefing calls `stationinfo` once per airport, then
fans out into seven more calls, and the diversion panel repeats the METAR
bounding-box query the briefing just made. Two people analysing KJFK→KLAX a
minute apart pay for all of it twice. Airport coordinates in particular never
change, and we were fetching them over the network on every request.

`functools.lru_cache` would handle the memoisation but has no notion of
expiry, which is exactly the part that matters for weather.
"""

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

from backend.config import CACHE_MAX_ENTRIES

log = logging.getLogger(__name__)


class TTLCache:
    """LRU-bounded cache where every entry has its own expiry."""

    def __init__(self, ttl_seconds: int, max_entries: int = CACHE_MAX_ENTRIES, name: str = 'cache'):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.name = name
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None

            expires_at, value = entry
            if expires_at < now:
                del self._store[key]
                self.misses += 1
                return None

            self._store.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self.ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    def get_or_call(self, key: str, producer: Callable[[], Any], *, cache_empty: bool = True) -> Any:
        """Return the cached value, else call `producer` and cache what it gives.

        `cache_empty=False` is for calls where an empty list means "upstream
        threw us a 204 or timed out" rather than "there is genuinely no
        weather here". Caching that would keep a blank panel blank for the
        whole TTL, long after upstream recovered.
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        value = producer()
        if value or cache_empty:
            self.set(key, value)
        return value

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                'name': self.name,
                'entries': len(self._store),
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': round(self.hits / total, 3) if total else 0.0,
            }

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
