"""
TTL-based decision cache to prevent re-asking the same state.
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CachedDecision:
    key: str
    response: dict
    timestamp: float
    ttl: float


class DecisionCache:
    """Prevents redundant LLM calls by caching decisions keyed on game state."""

    def __init__(self, default_ttl: float = 300.0):
        self._cache: dict[str, CachedDecision] = {}
        self.default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, state_key: str) -> Optional[dict]:
        entry = self._cache.get(state_key)
        if entry is None:
            self._misses += 1
            return None
        if time.time() - entry.timestamp > entry.ttl:
            del self._cache[state_key]
            self._misses += 1
            return None
        self._hits += 1
        logger.debug(f"Cache hit for {state_key[:32]}...")
        return entry.response

    def put(self, state_key: str, response: dict, ttl: float = None):
        self._cache[state_key] = CachedDecision(
            key=state_key,
            response=response,
            timestamp=time.time(),
            ttl=ttl or self.default_ttl,
        )

    def invalidate(self, state_key: str):
        self._cache.pop(state_key, None)

    def clear(self):
        self._cache.clear()

    @staticmethod
    def make_key(**kwargs) -> str:
        """Create a cache key from state parameters."""
        raw = str(sorted(kwargs.items()))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get_stats(self) -> dict:
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(self._hits + self._misses, 1),
        }
