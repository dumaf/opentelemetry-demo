"""Incident grouping and deduplication."""
from __future__ import annotations

import time
from collections import defaultdict

class IncidentGrouper:
    def __init__(self, cooldown_seconds: int = 300):
        self.cooldown = cooldown_seconds
        self._last: dict[str, float] = {}

    def should_create(self, key: str) -> bool:
        now = time.time()
        last = self._last.get(key)
        if last is not None and (now - last) < self.cooldown:
            return False
        self._last[key] = now
        return True

    def key_for(self, services: list[str], signals: list[str]) -> str:
        return "|".join(sorted(services)) + "::" + "|".join(sorted(signals))
