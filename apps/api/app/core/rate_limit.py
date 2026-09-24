"""Limitador de intentos de login en memoria (ventana deslizante).

Suficiente para una sola instancia. Con varias réplicas se reemplaza por Redis
(INCR + EXPIRE por clave) manteniendo la misma interfaz.
"""

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_hits: int, window_seconds: int):
        self.max_hits = max_hits
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def is_blocked(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) >= self.max_hits

    def hit(self, key: str) -> None:
        now = time.monotonic()
        self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


# 5 intentos fallidos por IP+email cada 5 minutos.
login_limiter = SlidingWindowLimiter(max_hits=5, window_seconds=300)
