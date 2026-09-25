"""Limitador de intentos de login en memoria (ventana deslizante).

Estado por proceso: con `--workers N` o varias réplicas el límite efectivo es N veces el
configurado. Con varias réplicas se reemplaza por Redis (INCR + EXPIRE por clave)
manteniendo la misma interfaz.
"""

import time
from collections import deque

from app.core.errors import TooManyRequestsError


class SlidingWindowLimiter:
    def __init__(self, max_hits: int, window_seconds: int):
        self.max_hits = max_hits
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key, deque())
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if not hits:
            # Sin esto, cada IP+email probado deja una clave viva para siempre (fuga de memoria).
            self._hits.pop(key, None)
        return hits

    def is_blocked(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) >= self.max_hits

    def hit(self, key: str) -> None:
        now = time.monotonic()
        hits = self._prune(key, now)
        hits.append(now)
        self._hits[key] = hits

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def consume(self, key: str) -> None:
        """Cuenta una petición; 429 si la clave ya agotó su ventana."""
        if self.is_blocked(key):
            raise TooManyRequestsError("Vas muy rápido. Espera un momento e inténtalo de nuevo")
        self.hit(key)


# 5 intentos fallidos por IP+email cada 5 minutos (fuerza bruta a una cuenta).
login_limiter = SlidingWindowLimiter(max_hits=5, window_seconds=300)
# 50 fallidos por IP cada 5 minutos (probar muchos emails). Solo cuentan los fallidos y el
# tope es holgado: un colegio entero puede salir a internet por la misma IP.
login_ip_limiter = SlidingWindowLimiter(max_hits=50, window_seconds=300)
# Por usuario autenticado, en toda la API. El autoguardado va con debounce: un estudiante
# real no pasa de unas pocas peticiones por segundo.
api_limiter = SlidingWindowLimiter(max_hits=120, window_seconds=60)
# Endpoints que llaman a proveedores de pago (STT, LLM, TTS): acota el gasto por usuario.
paid_limiter = SlidingWindowLimiter(max_hits=10, window_seconds=60)

ALL_LIMITERS = (login_limiter, login_ip_limiter, api_limiter, paid_limiter)
